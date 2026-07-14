"""
Input validation node for autocode workflow.
Prevents garbage-in, garbage-out by validating task, mode, and files before processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState  # [v3.0] files is core flat field

def node_validate_input(state: AutocodeState) -> dict:
    """
    Validate task, files, and mode before processing.
    Args:
        state: The autocode state dictionary

    Returns:
        dict: Partial state update, or error if validation fails
    """
    tid = state.get("trace_id", "")
    tracer.step(tid, "validate_input", "Starting input validation")

    # 1. Task validation
    task = state.get("task", "")
    if not task or not isinstance(task, str) or not task.strip():
        error = "Task cannot be empty or non-string"
        tracer.step(tid, "validate_input", f"FAILED: {error}")
        return {"status": "error", "error": error}

    # [v3.1 #42] Goal sanitization — max length + strip control chars.
    # Prevents LLM confusion from garbage input and limits token waste.
    MAX_TASK_LENGTH = 2000
    if len(task) > MAX_TASK_LENGTH:
        error = f"Task too long ({len(task)} chars, max {MAX_TASK_LENGTH}). Truncate or split into smaller tasks."
        tracer.step(tid, "validate_input", f"FAILED: {error}")
        return {"status": "error", "error": error}

    # Strip control chars (keep \n, \t, \r — they're legitimate formatting)
    import re as _re
    cleaned_task = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', task)
    if cleaned_task != task:
        tracer.step(tid, "validate_input", "Stripped control characters from task")
    # Update state with cleaned task (prevents downstream LLM confusion)
    if cleaned_task != task:
        # Return the cleaned task so LangGraph merges it into state
        # (only if we changed something — avoids unnecessary state update)
        task_update = {"task": cleaned_task}
    else:
        task_update = {}

    # 2. Mode validation
    valid_modes = {"feature", "fix", "fix_error", "refactor", "improve", "edit", "create_skill", "audit"}
    mode = state.get("mode", "")
    if mode and mode not in valid_modes:
        error = f"Invalid mode '{mode}'. Must be one of: {valid_modes}"
        tracer.step(tid, "validate_input", f"FAILED: {error}")
        return {"status": "error", "error": error}

    # 3. Files validation
    files = state.get("files", {})  # [v3.0] files is a core flat field (user input), not a sub-state field
    if files:
        if not isinstance(files, dict):
            error = "files must be a dictionary"
            tracer.step(tid, "validate_input", f"FAILED: {error}")
            return {"status": "error", "error": error}

        # Check for path traversal
        for file_path in files.keys():
            if not isinstance(file_path, str):
                error = f"File path must be string, got {type(file_path)}"
                tracer.step(tid, "validate_input", f"FAILED: {error}")
                return {"status": "error", "error": error}

            # [P1 #11] Prevent path traversal — catch Unix, Windows, and Unicode.
            # Old code only checked ".." and leading "/" or "\". Missed:
            #   - Windows absolute paths (C:\...)
            #   - Unicode separators (%2f, %5c)
            #   - Encoded traversal (..%2f..%2f)
            import re as _re
            normalized = file_path.replace("\\", "/").lower()
            if (
                ".." in normalized
                or normalized.startswith("/")
                or _re.match(r"[a-z]:[\\/]", normalized)  # Windows absolute (C:\, D:/)
                or "%2f" in normalized  # URL-encoded /
                or "%5c" in normalized  # URL-encoded \
            ):
                error = f"Invalid file path (traversal detected): {file_path}"
                tracer.step(tid, "validate_input", f"FAILED: {error}")
                return {"status": "error", "error": error}

    tracer.step(tid, "validate_input", "PASSED: All input valid")
    return task_update  # [v3.1 #42] includes cleaned task if control chars were stripped