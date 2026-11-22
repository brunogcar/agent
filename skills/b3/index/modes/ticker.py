"""Mode: ticker -- Find which indices a ticker belongs to."""
from __future__ import annotations

from skills.b3.index._registry import register_mode
from skills.b3.index.helpers import format_pct

from data_sources.b3.index.query_engine import ticker_search


@register_mode(
    "ticker",
    description="Find which indices a ticker belongs to",
    params={"ticker": "str. B3 ticker (PETR4, VALE3, etc). Required."},
    include_in_all=True,
    examples=['skill(domain="b3", sub_domain="index", mode="ticker", params=\'{"ticker":"PETR4"}\')'],
)
def ticker(ticker: str = "", **kwargs) -> dict:
    """Find which indices a ticker belongs to."""
    if not ticker:
        return {"status": "error", "error": "ticker is required"}

    result = ticker_search(ticker)

    if result.get("status") == "ok":
        # Build a table section
        indices = result.get("indices", [])
        result["sections"] = [{
            "type": "table",
            "title": f"{ticker} em Indices B3",
            "columns": ["Indice", "Nome", "Part. %", "Rank", "Data Ref."],
            "rows": [[i["index"], i["name"],
                      format_pct(i.get("participation")),
                      i.get("rank", "-"), i.get("ref_date", "")]
                     for i in indices],
        }]

    return result
