"""
Procedural memory node.
"""

from __future__ import annotations
import json
from typing import Any

from workflows.autocode_helpers.state import AutocodeState
from core.tracer import tracer

def node_distill_memory(state: AutocodeState) -> AutocodeState:
    """
    Store successful debug fixes as procedural knowledge.
    """
    tid = state.get("trace_id", "")
    task = state.get("task", "")
    task_type = state.get("task_type", state.get("classification", {}).get("task_type", "feature"))
    commit_sha = state.get("commit_sha", "")
    hypothesis = state.get("hypothesis", "")
    defense_note = state.get("defense_note", "")

    tracer.step(tid, "node_distill_memory", "Storing procedural memory...")

    # Only store memory for debug fixes
    if task_type not in ["fix", "fix_error"]:
        return state

    memory_entry = {
        "task": task,
        "task_type": task_type,
        "commit_sha": commit_sha,
        "timestamp": __import__("time").time(),
    }

    # Add debug information if available
    if hypothesis:
        memory_entry["root_cause"] = hypothesis
    if defense_note:
        memory_entry["defense_note"] = defense_note

    # Store memory
    try:
        from core.memory import memory as _mem
        _mem.store(
            text=json.dumps(memory_entry),
            collection="procedural",
            metadata={"source": "autocode", "type": "debug_fix"},
        )
        tracer.step(tid, "node_distill_memory", "Stored procedural memory")
    except Exception as e:
        tracer.error(tid, "node_distill_memory", f"Failed to store memory: {e}")

    return state