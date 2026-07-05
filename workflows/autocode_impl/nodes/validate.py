"""
Input validation node for autocode workflow.
Prevents garbage-in, garbage-out by validating task, mode, and files before processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState

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

    # 2. Mode validation
    valid_modes = {"feature", "fix", "fix_error", "refactor", "improve", "edit", "create_skill", "audit"}
    mode = state.get("mode", "")
    if mode and mode not in valid_modes:
        error = f"Invalid mode '{mode}'. Must be one of: {valid_modes}"
        tracer.step(tid, "validate_input", f"FAILED: {error}")
        return {"status": "error", "error": error}

    # 3. Files validation
    files = state.get("files", {})
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
    return {}