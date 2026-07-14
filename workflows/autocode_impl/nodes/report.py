"""
workflows/autocode_impl/nodes/report.py
Autocode report node -- generates code_audit report after verification.
"""
from __future__ import annotations
import json

from workflows.autocode_impl.state import AutocodeState, _get_verify, _get_vcs  # [v2.6+v2.1] accessors


def node_report(state: AutocodeState) -> dict:  # [P1 #2] Was AutocodeState — actually returns dict
    """Generate a code audit report with modified files, tests, and verification."""
    from tools.report import report as report_tool

    tid = state.get("trace_id", "")
    task = state.get("task", "")
    task_type = state.get("task_type", "feature")
    modified_files = list(state.get("files_map", {}).keys())
    test_results = state.get("test_results", {})
    verification_notes = _get_verify(state, "notes", "")  # [v2.6] accessor
    commit_sha = _get_vcs(state, "commit_sha", "")  # [v2.1] accessor

    sections = [
        {"title": "Task", "content": f"**Type:** {task_type}\n\n**Description:** {task}"},
        {"title": "Files Changed", "content": "\n".join(f"- `{f}`" for f in modified_files) or "No files modified."},
    ]

    test_status = "PASSED" if test_results.get("success") else "FAILED"
    test_details = json.dumps(test_results, indent=2, default=str)[:1500]
    sections.append({
        "title": "Test Results",
        "content": f"**Status:** {test_status}\n\n```json\n{test_details}\n```"
    })

    sections.append({
        "title": "Verification",
        "content": verification_notes or "No verification notes."
    })

    if commit_sha:
        sections.append({"title": "Commit", "content": f"`{commit_sha}`"})

    try:
        report_tool(
            action="report",
            trace_id=tid,
            title=f"Code Audit: {task[:50]}",
            data=None,
            config={"sections": sections},
            preset="code_audit",
        )
    except Exception:
        pass  # Best-effort: never fail the workflow for report generation

    return {}
