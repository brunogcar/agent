"""Audit report node — LLM summarizes audit findings.

[v3.7 F7] Calls the planner LLM with AUDIT_REPORT_SYSTEM prompt + the
scan results from node_audit_scan. Produces a structured report with:
- Summary (N files, N lines, N dependencies)
- Dead code candidates
- Complexity hotspots
- Missing type hints
- Recommendations

The report is stored in state["result"] and the workflow ends (no TDD,
no commit — audit is read-only).
"""
from __future__ import annotations

import json
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autocode_impl.helpers import _should_skip_node, _call
from workflows.autocode_impl.state import AutocodeState, _get_impact


def node_audit_report(state: AutocodeState) -> dict:
    """[v3.7 F7] Generate an LLM audit report from scan results.
    
    Reads state["impact"]["audit_scan"], calls LLM with AUDIT_REPORT_SYSTEM,
    stores the report in state["result"].
    """
    if _should_skip_node(state):
        return {}
    
    tid = state.get("trace_id", "")
    tracer.step(tid, "audit_report", "Generating audit report")
    
    scan = _get_impact(state, "audit_scan", {})
    if not scan:
        return {"status": "failed", "error": "No audit scan results found"}
    
    from workflows.autocode_impl.constants import AUDIT_REPORT_SYSTEM
    
    # Build the user prompt from scan results
    user = f"""Project audit scan results:

Total files: {scan.get("total_files", 0)}
Total lines: {scan.get("total_lines", 0)}

Complexity hotspots (top 10 by line count):
{json.dumps(scan.get("complexity_hotspots", []), indent=2)}

Dead code candidates (files with no importers):
{json.dumps(scan.get("dead_code_candidates", []), indent=2)}

Missing type hints (functions without -> annotation):
{json.dumps(scan.get("missing_type_hints", [])[:10], indent=2)}

Dependency map (callers per file):
{json.dumps(scan.get("dependency_map", {}), indent=2)}

Generate a structured audit report with findings and recommendations."""
    
    try:
        report = _call(
            role="planner",
            system=AUDIT_REPORT_SYSTEM,
            user=user,
            timeout=cfg.planner_timeout,
            trace_id=tid,
        )
    except Exception as e:
        tracer.error(tid, "audit_report", f"LLM call failed: {e}")
        return {"status": "failed", "error": f"Audit report generation failed: {e}"}
    
    tracer.step(tid, "audit_report", "Audit report generated")
    
    return {
        "result": report,
        "status": "success",
    }
