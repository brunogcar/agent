"""
workflows/autocode_helpers/nodes/analyze_impact.py
Analyzes the impact of modified files and determines targeted tests.
Uses the project-scoped core/kgraph/test_mapper for persistent, smart mapping.
"""
from __future__ import annotations
from pathlib import Path
from workflows.autocode_helpers.state import AutocodeState
from core.kgraph.test_mapper import get_targeted_tests
from core.config import cfg
from core.tracer import tracer

async def node_analyze_impact(state: AutocodeState) -> dict:
    """
    Analyzes the impact of modified files and determines targeted tests.
    Runs after files are written/patched, and before run_tests.
    Uses FileSnapshot from state to ensure 100% checkpoint idempotency.
    """
    tid = state.get("trace_id", "unknown")
    files_map = state.get("files_map", {})
    project_root = state.get("project_root", "")
    
    # If no files were modified, skip impact analysis
    if not files_map:
        return {"impact_warnings": [], "targeted_test_cmd": None, "impact_analysis_failed": False}

    tracer.step(tid, "analyze_impact", f"Analyzing impact for {len(files_map)} files")
    
    # Extract modified file paths from the FileSnapshot keys (Checkpoint Idempotency)
    modified_files = list(files_map.keys())
    
    try:
        # Resolve project path (fallback to agent_root if not working on an external project)
        project_path = Path(project_root) if project_root else cfg.agent_root
        
        # Call the new project-scoped test mapper
        result = await get_targeted_tests(
            project_path=project_path,
            modified_files=modified_files,
            project_id=project_path.name
        )
        
        test_files = result.get("tests", [])
        fallback = result.get("fallback", False)
        raw_warnings = result.get("warnings", [])
        
        # Convert raw string warnings into typed ImpactWarning dicts
        impact_warnings = []
        agent_fault = False
        
        for w in raw_warnings:
            is_agent_fault = False
            warning_type = "MAPPING_MISS"
            
            # Classify the warning to determine fault
            if "Critical path" in w:
                warning_type = "CRITICAL_PATH"
            elif "Zombie test" in w:
                warning_type = "ZOMBIE_TEST"
            elif "No specific tests" in w or "No valid targeted" in w:
                warning_type = "NO_TEST_MAPPING"
                is_agent_fault = True  # Agent modified a file with no tests mapped
                agent_fault = True
            
            impact_warnings.append({
                "type": warning_type,
                "message": w,
                "agent_fault": is_agent_fault
            })
        
        # Build the targeted test command
        targeted_test_cmd = None
        if not fallback and test_files:
            targeted_test_cmd = "pytest " + " ".join(test_files)
        else:
            targeted_test_cmd = "pytest"  # Fallback to full suite
            
        # Pass has_agent_fault to tracer so the feedback loop can read it easily
        tracer.step(
            tid, "analyze_impact", "Impact analysis complete", 
            targeted_cmd=targeted_test_cmd, 
            fallback=fallback,
            has_agent_fault=agent_fault,
            warnings_count=len(impact_warnings)
        )
        
        return {
            "impact_warnings": impact_warnings,
            "targeted_test_cmd": targeted_test_cmd,
            "impact_analysis_failed": False
        }
        
    except Exception as e:
        tracer.error(tid, "analyze_impact", f"AST analysis failed: {e}")
        return {
            "impact_warnings": [{
                "type": "AST_ERROR",
                "message": f"AST analysis crashed: {e}. Running full test suite.",
                "agent_fault": False  # Infrastructure failure, not agent's fault
            }],
            "targeted_test_cmd": "pytest",
            "impact_analysis_failed": True
        }
