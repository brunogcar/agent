"""Node: report — Generate codebase overview report.

[v1.4.1 P2-4] Summary now includes vectors_created. Was: "Files parsed: N,
Edges created: M". Now: "Files parsed: N, Edges created: M, Vectors created: K"
when vectors_created > 0 (or when embeddings were attempted). Skips the
Vectors line when skip_embeddings=True to avoid confusing the operator
with a "0 vectors" line that means "we didn't even try".
"""
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
    vectors_created = state.get("vectors_created", 0)
    files_skipped = state.get("files_skipped", 0)  # [v1.9.2] oversized/unreadable
    stale_pruned = state.get("stale_pruned", 0)  # [v1.9.2] orphaned entries cleaned
    skip_embeddings = state.get("skip_embeddings", False)
    errors = state.get("errors", [])

    # [v1.4.1 P2-4] Build summary — include vectors_created when relevant.
    # Skip the Vectors line when skip_embeddings=True so the operator doesn't
    # see a misleading "0 vectors" line that actually means "skipped".
    vectors_line = f"\n**Vectors created:** {vectors_created}" if not skip_embeddings else ""
    skipped_line = f"\n**Files skipped:** {files_skipped} (oversized/unreadable)" if files_skipped else ""
    pruned_line = f"\n**Stale entries pruned:** {stale_pruned}" if stale_pruned else ""
    note = state.get("note", "")
    if files_parsed == 0 and not errors:
        summary = (
            f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}"
            f"{vectors_line}{skipped_line}{pruned_line}\n\n✅ Codebase is up to date — no changes since last index."
        )
    elif files_parsed == 0 and errors:
        summary = (
            f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}"
            f"{vectors_line}{skipped_line}{pruned_line}\n\n⚠️ No files were parsed (errors occurred)."
        )
    else:
        summary = (
            f"**Files parsed:** {files_parsed}\n**Edges created:** {edges_created}"
            f"{vectors_line}{skipped_line}{pruned_line}"
        )

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
