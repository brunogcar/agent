"""
Skill creation node.
"""

from __future__ import annotations

from typing import Any

from workflows.autocode_helpers.state import AutocodeState, EXECUTOR_TIMEOUT
from workflows.autocode_helpers.constants import CREATE_SKILL_SYSTEM
from workflows.autocode_helpers.helpers import _call, _parse_json
from core.config import cfg
from core.tracer import tracer

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

    skill_name = data.get("skill_name", "unknown")
    skill_file_content = data.get("skill_file", "")
    explanation = data.get("explanation", "")

    updates = {}

    # Write skill file
    if not state.get("dry_run", False):
        try:
            skill_path = cfg.agent_root / "skills" / f"{skill_name}.py"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(skill_file_content, encoding="utf-8")

            updates["skill_path"] = str(skill_path)
            updates["status"] = "done"
            updates["result"] = f"Skill created: {skill_path}\n{explanation}"

            tracer.step(tid, "node_create_skill", f"Created skill: {skill_path}")
        except Exception as e:
            updates["error"] = f"Failed to create skill: {e}"
            updates["status"] = "failed"
            tracer.error(tid, "node_create_skill", updates["error"])
    else:
        updates["skill_path"] = f"[DRY RUN] Would create: skills/{skill_name}.py"
        updates["status"] = "done"
        updates["result"] = f"Dry run: {explanation}"

    return updates