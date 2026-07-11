"""
Skill creation node.

[P1 #3] Now resolves skill path via project_root/workspace_root, not always agent_root.
[P2 #15] Skill name sanitized — no path separators allowed (prevents path traversal).
[P2 #16] Skill code validated with ast.parse() before writing.
[P2 #17] skill_created flag is now set on success.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from workflows.autocode_impl.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_impl.constants import CREATE_SKILL_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json
from core.config import cfg
from core.tracer import tracer


def _sanitize_skill_name(name: str) -> str:
    """[P2 #15] Sanitize skill name — only alphanumeric + underscore allowed."""
    # Replace any non-alphanumeric chars with underscore
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # Strip leading/trailing underscores
    sanitized = sanitized.strip("_")
    # Fallback if empty
    return sanitized or "unnamed_skill"


def _validate_python_syntax(code: str) -> tuple[bool, str]:
    """[P2 #16] Validate that skill code is valid Python."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"


def node_create_skill(state: AutocodeState) -> dict:
    """Create a new skill file based on the task description."""
    tid = state.get("trace_id", "")
    task = state.get("task", "")
    tracer.step(tid, "node_create_skill", f"Creating skill: {task[:100]}...")

    # Generate skill using CREATE_SKILL_SYSTEM
    raw = _call(
        role="executor",
        system=CREATE_SKILL_SYSTEM,
        user=f"Task:\n{task}",
        timeout=EXECUTOR_TIMEOUT,
    )
    data = _parse_json(raw)

    # [P2 #15] Sanitize skill name — prevent path traversal via / or \
    skill_name = _sanitize_skill_name(data.get("skill_name", "unknown"))
    skill_file_content = data.get("skill_file", "")
    explanation = data.get("explanation", "")

    updates = {}

    # [P2 #16] Validate syntax before writing
    if skill_file_content:
        ok, syntax_error = _validate_python_syntax(skill_file_content)
        if not ok:
            updates["error"] = f"Skill code has invalid Python syntax: {syntax_error}"
            updates["status"] = "failed"
            tracer.error(tid, "node_create_skill", updates["error"])
            return updates

    # Write skill file
    if not state.get("dry_run", False):
        try:
            # [P1 #3] Resolve skill directory based on project_root, not always agent_root.
            # If working on a workspace project, write to that project's skills/ dir.
            project_root = state.get("project_root", "")
            if project_root:
                base = Path(project_root) / "skills"
            else:
                base = cfg.agent_root / "skills"

            skill_path = base / f"{skill_name}.py"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            # [Pre-2.0 Fix] Atomic write — was: direct write_text (crash mid-write
            # corrupts the skill file). Now: tempfile + os.replace.
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=skill_path.parent,
                delete=False, suffix='.tmp'
            ) as tmp:
                tmp.write(skill_file_content)
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, skill_path)

            updates["skill_path"] = str(skill_path)
            updates["skill_created"] = True  # [P2 #17] Set flag so autocode.py can detect it
            updates["status"] = "done"
            updates["result"] = f"Skill created: {skill_path}\n{explanation}"

            tracer.step(tid, "node_create_skill", f"Created skill: {skill_path}")
        except Exception as e:
            updates["error"] = f"Failed to create skill: {e}"
            updates["status"] = "failed"
            tracer.error(tid, "node_create_skill", updates["error"])
    else:
        updates["skill_path"] = f"[DRY RUN] Would create: skills/{skill_name}.py"
        updates["skill_created"] = True  # [P2 #17]
        updates["status"] = "done"
        updates["result"] = f"Dry run: {explanation}"

    return updates
