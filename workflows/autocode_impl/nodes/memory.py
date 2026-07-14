"""
Procedural memory node.
Extracts reusable rules from successful autocode workflows using the Planner LLM.

[v2.7] Sub-state migration: now writes a summary to the `memory` sub-state via
read-modify-write (RMW) alongside the legacy `memory_notes` flat field. Before
this, the node returned {} — the `memory` sub-state and `memory_notes` flat
field were both dead code (populated by _default_state() but never written to
by any node). See Track M1 in CHANGELOG.
"""
from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState, _get_debug  # [v2.5] accessor
from core.tracer import tracer
from core.memory_backend.procedural.distill import distill_workflow

def node_distill_memory(state: AutocodeState) -> dict:
    """
    Distill procedural knowledge from the completed autocode workflow.
    """
    tid = state.get("trace_id", "")
    task = state.get("task", "")
    # [P2 #28] Removed dead classification lookup — field never set in AutocodeState.
    # task_type is set by node_classify_task directly.
    task_type = state.get("task_type", "feature")
    # [Bug #11] Changed hypothesis -> root_cause and defense_note -> defense_notes
    # to match what debug.py actually sets. Previously always empty.
    # [v2.5] Use _get_debug accessors (read sub-state first, fall back to flat)
    root_cause = _get_debug(state, "root_cause", "")
    defense_notes = _get_debug(state, "defense_notes", "")
    error_log = state.get("error_log", "")
    modified_files = state.get("modified_files", [])

    tracer.step(tid, "node_distill_memory", "Starting procedural distillation...")

    # We only distill insights from tasks that actually involved problem-solving or code changes
    if task_type in ["unclear", "create_skill"]:
        tracer.step(tid, "node_distill_memory", f"Skipping distillation for task_type: {task_type}")
        return {}

    # Build a rich trace text for the Planner LLM to analyze
    trace_parts = [
        f"TASK TYPE: {task_type}",
        f"TASK DESCRIPTION: {task}",
    ]

    if root_cause:
        trace_parts.append(f"ROOT CAUSE HYPOTHESIS: {root_cause}")
    if defense_notes:
        trace_parts.append(f"DEFENSE NOTE (How to prevent this in future): {defense_notes}")
    if error_log:
        trace_parts.append(f"ERRORS ENCOUNTERED:\n{error_log[:1000]}")
    if modified_files:
        trace_parts.append(f"FILES MODIFIED: {', '.join(modified_files)}")

    trace_text = "\n\n".join(trace_parts)

    distill_status = "skipped"
    distill_summary = ""

    try:
        # Call the new distillation pipeline (has a 15s timeout internally)
        result = distill_workflow(trace_text=trace_text, trace_id=tid)
        distill_status = result.get("status", "unknown")
        stored = result.get("stored", 0)
        skipped = result.get("skipped", 0)
        distill_summary = f"distill_status={distill_status}, stored={stored}, skipped={skipped}"
        tracer.step(tid, "node_distill_memory", f"Distillation result: {distill_status}")
    except Exception as e:
        # [v1.1] Non-fatal: the code is already committed at this point.
        # Memory distillation failure must NOT flip a successful workflow to
        # failed. Use tracer.warning (not tracer.error) to signal non-fatal.
        # Found by cross-LLM review (Mimo, Kimi, Qwen).
        distill_status = "error"
        distill_summary = f"distill_failed: {e}"
        tracer.warning(tid, "node_distill_memory", f"Distillation failed (non-fatal): {e}")

    # [v2.7] RMW: write to memory sub-state + flat mirror.
    # Before this, the node returned {} — the memory sub-state was dead code.
    # Now it records a summary of the distillation outcome for downstream
    # consumers (e.g. report.py could surface it, or future cross-run learning).
    current_memory = dict(state.get("memory", {}))
    current_memory["notes"] = distill_summary
    return {
        "memory_notes": distill_summary,
        "memory": current_memory,
    }