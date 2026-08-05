"""Mode: compare -- Compare index compositions side by side."""
from __future__ import annotations

from skills.b3.index._registry import register_mode
from skills.b3.index.helpers import build_constituent_table

from data_sources.b3.index.catalog import ACTIVE_INDICES
from data_sources.b3.index.query_engine import index as query_index


@register_mode(
    "compare",
    description="Compare index compositions side by side",
    params={"indices": "str. Comma-separated index codes (default: all active)"},
    include_in_all=True,
    examples=['skill(domain="b3", sub_domain="index", mode="compare", params=\'{"indices":"IBOV,SMLL"}\')'],
)
def compare(indices: str = "", **kwargs) -> dict:
    """Compare index compositions."""
    if indices:
        codes = [c.strip().upper() for c in indices.split(",")]
    else:
        codes = ACTIVE_INDICES

    sections = []
    summary = []

    for code in codes:
        idx = query_index(code)
        if idx.get("status") == "ok":
            constituents = idx.get("constituents", [])
            summary.append({
                "index": code,
                "name": idx.get("name", code),
                "constituent_count": len(constituents),
                "top_constituent": constituents[0]["ticker"] if constituents else "-",
                "top_weight": constituents[0].get("participation") if constituents else None,
                "ref_date": idx.get("ref_date", ""),
            })
            sections.append(build_constituent_table(constituents, limit=10))
        else:
            summary.append({"index": code, "error": idx.get("error", "")})

    return {
        "status": "ok",
        "title": "Comparacao de Indices - B3",
        "indices": codes,
        "summary": summary,
        "sections": sections,
    }
