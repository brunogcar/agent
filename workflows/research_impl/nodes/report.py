"""Node: report — Generate research dossier report with citations."""
from __future__ import annotations

from workflows.base import WorkflowState, node_step


def node_report(state: WorkflowState) -> dict:
    """Generate research dossier report with citations."""
    from tools.report import report as report_tool
    from core.citations import citations

    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    result = state.get("result", "")

    if not result:
        return {}

    sources = citations.get_sources(tid) if tid else []
    source_list = [{"title": s.get("title", "Untitled"), "url": s.get("url", "")} for s in sources]

    sections = [
        {"title": "Research Goal", "content": goal},
        {"title": "Findings", "content": result[:20000] if result else "No findings generated."},
    ]

    try:
        report_tool(
            action="report",
            trace_id=tid,
            title=f"Research: {goal[:60]}",
            data=None,
            config={"sections": sections, "sources": source_list},
            preset="research",
        )
        node_step(state, "report", "generated research dossier")
    except Exception as e:
        node_step(state, "report", f"report generation failed: {e}")

    return {}
