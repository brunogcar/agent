"""Mode: yoy_quarterly -- same-quarter year-over-year comparison (Trimestre).

Groups standalone quarters by quarter number (Q1, Q2, Q3, Q4) and compares
the same quarter across multiple years. Shows: Q1 2026 vs Q1 2025 vs Q1 2024,
etc. Helps spot seasonal patterns + YoQ growth.

This is the "Trimestre" tab from the user's private spreadsheet — not a
condensed version of "Res Trimestral", but a same-quarter-across-years
comparison.

Registered as "yoy_quarterly" in skills.cvm.financials._registry.MODES via
the @register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.modes.quarterly import quarterly


def _yoy_growth(curr: float | None, prev: float | None) -> float | None:
    """Compute YoY growth = (curr - prev) / |prev|. None if either missing or prev=0."""
    if curr is None or prev is None or prev == 0:
        return None
    return (curr - prev) / abs(prev)


@register_mode(
    "yoy_quarterly",
    description=(
        "Same-quarter year-over-year comparison (Trimestre). Groups "
        "standalone quarters by Q1/Q2/Q3/Q4 and compares each quarter "
        "across years. Shows YoY growth per quarter. Default: 5 years."
    ),
    params={
        "company":     "str. B3 ticker (PETR4), name, or CNPJ. Required.",
        "years":       "int. Number of years to compare. Default: 5.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="yoy_quarterly", params=\'{"company":"PETR4"}\')',
    ],
)
def yoy_quarterly(company: str = "", years: int = 5, consolidado: int = 1) -> dict:
    """Same-quarter year-over-year comparison.

    Fetches `years * 4` standalone quarters, groups them by quarter number
    (Q1, Q2, Q3, Q4), and for each group produces a time series with YoY
    growth for key metrics (revenue, EBITDA, net income, margins).

    Args:
        company: Ticker, name, or CNPJ.
        years: Number of years to compare. Default: 5 (20 quarters).
        consolidado: 1=consolidated (default), 0=individual.

    Returns:
        Dict shaped as ``{"status": "ok", "company": ..., "groups": [...]}``
        where each group is ``{"quarter": "Q1", "periods": [...]}`` and
        each period has ``{"period", "year", "quarter", "metrics", "ratios",
        "yoy_growth": {"receita_liquida": ..., "ebitda": ..., ...}}``.
        Periods within each group are sorted oldest-first.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    print(f"[financials] YoY: Fetching quarterly data for {company} ({years} years)...", flush=True)

    quarters_needed = years * 4
    qrt = quarterly(company=company, periods=quarters_needed, consolidado=consolidado)
    if qrt.get("status") != "ok":
        return qrt

    all_quarters = qrt.get("periods") or []
    if not all_quarters:
        return {"status": "not_found", "error": "No quarterly data found"}

    print(f"[financials] YoY: Grouping {len(all_quarters)} quarters by Q1/Q2/Q3/Q4...", flush=True)

    # Group by quarter number (1, 2, 3, 4)
    groups: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}
    for p in all_quarters:
        qnum = p.get("quarter")
        if qnum in groups:
            groups[qnum].append(p)

    # Build output groups with YoY growth
    _YOY_METRICS = ["receita_liquida", "ebitda", "lucro_liquido", "ebit"]
    out_groups: list[dict] = []

    for qnum in sorted(groups.keys()):
        group_periods = sorted(groups[qnum], key=lambda p: p.get("year", 0))
        if not group_periods:
            continue

        out_periods: list[dict] = []
        prev_metrics: dict | None = None

        for p in group_periods:
            metrics = p.get("metrics") or {}

            # Compute YoY growth for key metrics
            yoy: dict[str, float | None] = {}
            if prev_metrics is not None:
                for key in _YOY_METRICS:
                    yoy[key] = _yoy_growth(
                        metrics.get(key),
                        prev_metrics.get(key),
                    )

            out_periods.append({
                "period": p.get("period", ""),
                "year": p.get("year"),
                "quarter": qnum,
                "metrics": metrics,
                "ratios": p.get("ratios") or {},
                "yoy_growth": yoy if yoy else {},
            })
            prev_metrics = metrics

        out_groups.append({
            "quarter": f"Q{qnum}",
            "periods": out_periods,
        })

    print(f"[financials] YoY: Done! {len(out_groups)} quarter groups.", flush=True)

    return {
        "status": "ok",
        "company": company,
        "groups": out_groups,
    }
