"""
Procedural memory node.
Extracts reusable rules from successful autocode workflows using the Planner LLM.
"""
from __future__ import annotations

from workflows.autocode_helpers.state import AutocodeState
from core.tracer import tracer
from core.memory_backend.procedural.distill import distill_workflow

def node_distill_memory(state: AutocodeState) -> dict:
    """
    Distill procedural knowledge from the completed autocode workflow.
    """
    tid = state.get("trace_id", "")
    task = state.get("task", "")
    task_type = state.get("task_type", state.get("classification", {}).get("task_type", "feature"))
    hypothesis = state.get("hypothesis", "")
    defense_note = state.get("defense_note", "")
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
    
    if hypothesis:
        trace_parts.append(f"ROOT CAUSE HYPOTHESIS: {hypothesis}")
    if defense_note:
        trace_parts.append(f"DEFENSE NOTE (How to prevent this in future): {defense_note}")
    if error_log:
        trace_parts.append(f"ERRORS ENCOUNTERED:\n{error_log[:1000]}")
    if modified_files:
        trace_parts.append(f"FILES MODIFIED: {', '.join(modified_files)}")
        
    trace_text = "\n\n".join(trace_parts)

    try:
        # Call the new distillation pipeline (has a 15s timeout internally)
        result = distill_workflow(trace_text=trace_text, trace_id=tid)
        tracer.step(tid, "node_distill_memory", f"Distillation result: {result.get('status')}")
    except Exception as e:
        tracer.error(tid, "node_distill_memory", f"Distillation pipeline failed: {e}")

    # LangGraph nodes must return a dict to update state (or empty dict)
    return {}