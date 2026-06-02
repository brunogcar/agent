"""
workflows/autocode_helpers/nodes/analyze_impact.py
Analyzes the impact of modified files and determines targeted tests.
"""
from __future__ import annotations
from workflows.autocode_helpers.state import AutocodeState
from workflows.autocode_helpers.test_mapper import get_targeted_tests
from core.tracer import tracer

async def node_analyze_impact(state: AutocodeState) -> dict:
    """
    Analyzes the impact of modified files and determines targeted tests.
    Runs after files are written/patched, and before run_tests.
    """
    tid = state.get("trace_id", "unknown")
    modified_files = state.get("modified_files", [])
    
    if not modified_files:
        return {"impact_warnings": [], "targeted_test_cmd": None}

    tracer.step(tid, "analyze_impact", f"Analyzing impact for {len(modified_files)} files")
    
    try:
        result = await get_targeted_tests(modified_files)
        test_cmd = result.get("cmd", "pytest")
        warnings = result.get("warnings", [])
        
        is_fallback = (test_cmd == "pytest")
        if is_fallback and not any("full suite" in w for w in warnings):
            warnings.append("Impact analysis fell back to full test suite.")
        
        tracer.step(
            tid, "analyze_impact", "Impact analysis complete", 
            targeted_cmd=test_cmd, 
            warnings=warnings,
            is_fallback=is_fallback
        )
        
        return {
            "impact_warnings": warnings,
            "targeted_test_cmd": test_cmd
        }
    except Exception as e:
        tracer.error(tid, "analyze_impact", f"AST analysis failed: {e}")
        return {
            "impact_warnings": [f"AST analysis crashed: {e}. Running full test suite."],
            "targeted_test_cmd": "pytest",
            "impact_analysis_failed": True  # P0 Fix: Prevents false-positive penalty in feedback loop
        }
