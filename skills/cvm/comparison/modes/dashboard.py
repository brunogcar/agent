"""Mode: dashboard -- multi-tab comparison dashboard (thin composition mode).

Returns a structured payload with tabs optimized for the report tool's
dashboard action:
  - Overview:   KPI cards (cheapest P/L, best ROE, best Div Yield, cheapest
                EV/EBITDA) + Compared Tickers table (ticker + sector) +
                per-ticker errors (if any)
  - Valuation:  side-by-side valuation ratios table (all tickers × metrics)
  - Financials: side-by-side financial metrics table (latest annual)
  - Dividends:  side-by-side dividend metrics table
  - Growth:     QoQ + YoY + TTM ratios growth table

This mode does NOT fetch new data -- it calls ``side_by_side()`` and
``growth()`` and reshapes their outputs into a multi-tab payload. If
``side_by_side()`` itself fails (e.g. < 2 tickers), the dashboard
propagates the error dict instead of rendering empty tabs.

The section-building helpers live in skills.cvm.comparison.report (so they
can be reused by other modes / tests). This module is the orchestrator:
gather data -> call report.* builders -> assemble tabs.

Registered as "dashboard" in skills.cvm.comparison._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations
from datetime import datetime as _dt

from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm._shared_report.price_chart import build_price_chart
from skills.cvm.comparison._registry import register_mode
from skills.cvm.comparison.modes.side_by_side import side_by_side
from skills.cvm.comparison.modes.growth import growth
from skills.cvm.comparison.report import (
    build_overview_kpis,
    build_tickers_section,
    build_errors_section,
    build_valuation_section,
    build_financials_section,
    build_dividends_section,
    build_growth_section,
    build_growth_chart,
    build_peer_comparison_chart,
    build_peer_ratio_grid,
)


# Heuristic: a B3 ticker is 4-6 alphanumeric chars (typically uppercase,
# ending in 3 or 4). Used to decide whether to add a company header in the
# Overview tab — comparison may be invoked with a sector name as the
# (single) company fallback, in which case we skip the header.
import re as _re
_TICKER_RE = _re.compile(r"^[A-Z0-9]{4,6}$")


def _looks_like_ticker(s: str) -> bool:
    """Return True if s looks like a B3 ticker (e.g. PETR4, VALE3, SUZB3)."""
    return bool(s) and bool(_TICKER_RE.match((s or "").strip().upper()))


@register_mode(
    "dashboard",
    description=(
        "Multi-tab comparison dashboard (thin composition of side_by_side() "
        "+ growth()). Tabs: Overview (4 KPI cards + tickers/sectors table), "
        "Valuation (side-by-side ratios), Financials (side-by-side metrics), "
        "Dividends (side-by-side dividend metrics), Growth (QoQ + YoY + TTM). "
        "Optimized for the report tool's dashboard action."
    ),
    params={
        "tickers":     "list[str]. B3 tickers, e.g. [\"PETR4\",\"VALE3\"]. Required (min 2).",
        "company":     "str. Single ticker (fallback if tickers not provided). Note: comparison needs 2+ tickers.",
        "consolidado": "int. 1=consolidated (default), 0=individual.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="comparison", mode="dashboard", params=\'{"tickers":["PETR4","VALE3","ITUB4"]}\')',
    ],
)
def dashboard(tickers: list = None, consolidado: int = 1, company: str = "") -> dict:
    """Multi-tab comparison dashboard (thin composition of side_by_side() + growth()).

    Returns a structured payload with tabs optimized for the report tool's
    dashboard action:
      - Overview:   KPI cards (cheapest P/L, best ROE, best Div Yield,
                    cheapest EV/EBITDA) + Compared Tickers table (with
                    sectors) + per-ticker errors (if any)
      - Valuation:  side-by-side valuation ratios table (all tickers × metrics)
      - Financials: side-by-side financial metrics table (latest annual)
      - Dividends:  side-by-side dividend metrics table
      - Growth:     QoQ + YoY + TTM ratios growth table

    This mode does NOT fetch new data -- it calls ``side_by_side()`` and
    ``growth()`` and reshapes their outputs into a multi-tab payload. If
    ``side_by_side()`` itself fails (e.g. < 2 tickers), the dashboard
    propagates the error dict instead of rendering empty tabs.

    Args:
        tickers: List of B3 tickers, e.g. ["PETR4","VALE3"]. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.

    Returns:
        Dict shaped as ``{"status": "ok", "tickers": ..., "tabs": [...],
        "kpis": [...]}`` where each tab is ``{"name": str, "sections": [...]}``.
        On validation error (no tickers / < 2 tickers), returns the
        ``side_by_side()`` error dict verbatim.
    """
    # [v1.3] If tickers not provided but company is, use company as a single-ticker list.
    # Note: comparison requires min 2 tickers — a single company will return an error
    # from side_by_side(). The user should provide tickers=["PETR4","VALE3"].
    if not tickers and company:
        tickers = [company]

    # [v3] Build company header + price chart for the first ticker (target).
    # Only add if the first ticker looks like a B3 ticker (not a sector name).
    target_ticker = (tickers[0] if tickers else "") or company
    print(f"[comparison] Building company header + price chart for target='{target_ticker}'...", flush=True)
    company_header: dict = {}
    price_chart: dict | None = None
    if _looks_like_ticker(target_ticker):
        company_header = build_company_header(target_ticker)
        price_chart = build_price_chart(target_ticker)

    # Freshness footer (DFP + ITR + COTAHIST sync dates) — computed once.
    freshness_footer = ""
    try:
        from skills.cvm._freshness import get_freshness, get_last_synced_period
        fresh = get_freshness()
        last = get_last_synced_period()
        dfp_sync = fresh.get("dfp", "")
        itr_sync = fresh.get("itr", "")
        cot_sync = fresh.get("cotahist", "")
        dfp_period = last.get("dfp", "")
        itr_period = last.get("itr", "")
        freshness_footer = (
            f"DFP: {dfp_sync[:10] if dfp_sync else '—'} (até {dfp_period or '—'}) • "
            f"ITR: {itr_sync[:10] if itr_sync else '—'} (até {itr_period or '—'}) • "
            f"COTAHIST: {cot_sync[:10] if cot_sync else '—'}"
        )
    except Exception:
        pass

    # ── Gather underlying data (side_by_side + growth, wrapped defensively) ──
    _t0 = _dt.now()
    print(f"[comparison] Starting comparison dashboard for {tickers}...", flush=True)
    print(f"[comparison] Fetching side_by_side()...", flush=True)
    try:
        sbs = side_by_side(tickers=tickers, consolidado=consolidado)
    except Exception as e:
        return {"status": "error",
                "sub_domain": "comparison", "mode": "dashboard",
                "error": str(e)}

    # Propagate validation errors (no tickers / < 2 tickers) as-is rather
    # than rendering empty tabs.
    if sbs.get("status") != "ok":
        return sbs

    # Growth mode is best-effort — if it fails for all tickers, the dashboard
    # still renders the other 4 tabs.
    print(f"[comparison] Fetching growth()...", flush=True)
    try:
        growth_result = growth(tickers=tickers, consolidado=consolidado)
    except Exception:
        growth_result = {"status": "error", "sections": []}

    # ── Top-level KPI cards (leader per metric across all compared tickers) ──
    kpis = build_overview_kpis(sbs)

    # [v5] One-line section timers (ratios pattern): 6 sections.
    _SEC_TOTAL = 6
    _sec_count = 0
    _sec_t0 = _dt.now()

    # ── Section 1/6: Overview ─────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    overview_sections: list[dict] = []
    if company_header.get("name"):
        overview_sections.append({"type": "company_info",
                                   "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    overview_sections.append(build_tickers_section(sbs))
    errors_section = build_errors_section(sbs)
    if errors_section is not None:
        overview_sections.append(errors_section)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/6: Valuation ────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    valuation_sections = [build_valuation_section(sbs)]
    # Use the first ticker as the “target” for the peer comparison chart.
    target = (tickers[0] if tickers else "")
    peer_chart = build_peer_comparison_chart(target, sbs, metric_name="p_l")
    if peer_chart:
        valuation_sections.append(peer_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Valuation ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/6: Financials ───────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    financials_sections = [build_financials_section(sbs)]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Financials ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 4/6: Dividends ────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    dividends_sections = [build_dividends_section(sbs)]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Dividends ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 5/6: Growth ───────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    growth_sections = [build_growth_section(growth_result)]
    # [v3] Add a YoY growth bar chart per ticker (Receita/EBITDA/Lucro).
    growth_chart = build_growth_chart(growth_result)
    if growth_chart:
        growth_sections.append(growth_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Growth ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 6/6: Ratio Grid ───────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    grid_section = build_peer_ratio_grid(sbs)
    grid_sections = [grid_section] if grid_section else []
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Ratio Grid ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Assemble the dashboard payload ─────────────────────────────────────
    # KPIs go at the TOP LEVEL (not inside a tab) — the dashboard template
    # renders them above all tabs via the kpi-grid div.
    # [v3] Sidebar groups: Resumo / Comparação.
    tabs = [
        {"name": "Overview",    "group": "Resumo",     "sections": overview_sections},
        {"name": "Valuation",   "group": "Comparação", "sections": valuation_sections},
        {"name": "Financials",  "group": "Comparação", "sections": financials_sections},
        {"name": "Dividends",   "group": "Comparação", "sections": dividends_sections},
        {"name": "Growth",      "group": "Comparação", "sections": growth_sections},
    ]
    if grid_sections:
        tabs.append({"name": "Ratio Grid", "group": "Comparação",
                     "sections": grid_sections})

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[comparison] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
    return {
        "status": "ok",
        "tickers": sbs.get("tickers") or [],
        "company_header": company_header,
        "tabs": tabs,
        "kpis": kpis,
        "freshness_footer": freshness_footer,
    }
