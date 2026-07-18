"""Node: report — Generate codebase overview report."""
from __future__ import annotations

from pathlib import Path

from workflows.understand_impl.state import UnderstandState
from core.tracer import tracer


def node_report(state: UnderstandState) -> dict:
    """Generate codebase overview report."""
    from tools.report import report as report_tool

    tid = state.get("trace_id", "understand")
    project_path = state.get("project_path", "")
    files_parsed = state.get("files_parsed", 0)
    edges_created = state.get("edges_created", 0)
    errors = state.get("errors", [])

    note = state.get("note", "")
    if files_parsed == 0 and not errors:
        summary = f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}\n\n✅ Codebase is up to date — no changes since last index."
    elif files_parsed == 0 and errors:
        summary = f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}\n\n⚠️ No files were parsed (errors occurred)."
    else:
        summary = f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}"

    sections = [
        {"title": "Project", "content": f"`{project_path}`"},
        {"title": "Indexing Summary", "content": summary},
    ]

    if errors:
        sections.append({
            "title": "Errors",
            "content": "\n".join(f"- {e}" for e in errors[:20])
        })

    try:
        report_tool(
            action="report",
            trace_id=tid,
            title=f"Codebase Overview: {Path(project_path).name}",
            data=None,
            config={"sections": sections},
            preset="code_audit",
        )
    except Exception as e:
        tracer.error(tid, "understand_report", f"Report generation failed: {e}")

    result = {}
    if note:
        result["note"] = note
    return result
