"""Mode: growth -- QoQ + YoY % change + TTM ratios for N tickers.

Calls financials.quarterly(periods=8) per ticker to get standalone quarters,
then computes QoQ (latest vs prior) and YoY (latest vs same quarter prior
year) growth for Receita, EBITDA, Lucro Líquido. Also includes TTM
Marg. EBITDA and ROE from the financials skill's TTM summary.

Growth math lives in skills.cvm.comparison.helpers (_compute_growth +
_pct_change). This module just orchestrates the fetch + section assembly.

Registered as "growth" in skills.cvm.comparison._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.

Concurrency:
    Per-ticker quarterly fetches run concurrently in a ThreadPoolExecutor
    (max_workers=5) via _fetch_one_growth(). We do NOT wrap the executor in
    engine_cache_scope(): that cache is backed by a ContextVar (thread-local),
    so wrapping it at the top level would NOT share the cache across worker
    threads. Each worker gets its own (None = passthrough) cache, which is
    fine — the speedup comes from parallel HTTP, not from cache sharing.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from skills.cvm.comparison._registry import register_mode
from skills.cvm.comparison.helpers import _GROWTH_COLS, _compute_growth
from skills.cvm.comparison.fetchers import _fetch_sectors, _build_section


@register_mode(
    "growth",
    description=(
        "Growth metrics: QoQ + YoY % change for Receita, EBITDA, Lucro "
        "Líquido + TTM Marg. EBITDA + ROE. Calls financials.quarterly("
        "periods=8) per ticker."
    ),
    params={
        "tickers":     "list[str]. Required (min 2).",
        "consolidado": "int. Default: 1.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="comparison", mode="growth", params=\'{"tickers":["SUZB3","KLBN11"]}\')',
    ],
)
def growth(tickers: list = None, consolidado: int = 1) -> dict:
    """Compare N tickers on growth metrics: QoQ + YoY % change + TTM ratios.

    Calls financials.quarterly(periods=8) per ticker to get standalone quarters,
    then computes QoQ (latest vs prior) and YoY (latest vs same quarter prior
    year) growth for Receita, EBITDA, Lucro Líquido. Also includes TTM
    Marg. EBITDA and ROE from the financials skill's TTM summary.

    Args:
        tickers: List of B3 tickers. Required (min 2).
        consolidado: 1=consolidated (default), 0=individual.
    """
    if not tickers or not isinstance(tickers, list):
        return {"status": "error", "error": "tickers (list) is required"}
    if len(tickers) < 2:
        return {"status": "error", "error": "need at least 2 tickers to compare"}
    tickers = [t.strip().upper() for t in tickers]

    # Fetch all tickers concurrently — preserve input order in the result.
    growth_by_ticker: dict[str, dict] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {
            executor.submit(_fetch_one_growth, t, consolidado): t
            for t in tickers
        }
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                growth_dict, err = future.result()
                growth_by_ticker[ticker] = growth_dict
                if err:
                    errors.append(err)
            except Exception as e:
                growth_by_ticker[ticker] = {}
                errors.append(f"{ticker}: financials: {e}")

    # Rebuild growth_data aligned with input tickers order (for _build_section).
    growth_data = [growth_by_ticker.get(t, {}) for t in tickers]

    section = _build_section("Growth Metrics (QoQ + YoY + TTM)", _GROWTH_COLS,
                             growth_data, tickers)

    # [v1.2] Sector tagging
    sectors = _fetch_sectors(tickers)

    return {
        "status": "ok",
        "tickers": tickers,
        "sectors": sectors,
        "sections": [section],
        "errors": errors,
    }


# ── Internal: per-ticker quarterly fetch (runs inside a worker thread) ───────

def _fetch_one_growth(ticker: str, consolidado: int) -> tuple[dict, str]:
    """Fetch quarterly financials for one ticker + compute growth metrics.

    Runs inside a ThreadPoolExecutor worker thread. Best-effort: never raises
    (errors are returned as the second tuple element).

    Args:
        ticker: B3 ticker.
        consolidado: 1=consolidated, 0=individual.

    Returns:
        (growth_dict, error_string_or_None). growth_dict is {} on error.
    """
    from skills.cvm.financials.modes.quarterly import quarterly as fin_quarterly

    try:
        r = fin_quarterly(company=ticker, periods=8, consolidado=consolidado)
        if r.get("status") == "ok":
            return _compute_growth(r), None
        err = f"{ticker}: financials: {r.get('error', r.get('status', ''))}"
        return {}, err
    except Exception as e:
        return {}, f"{ticker}: financials: {e}"
