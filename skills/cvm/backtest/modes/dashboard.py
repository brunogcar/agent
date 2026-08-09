"""Mode: dashboard -- multi-tab backtest dashboard with sidebar groups.

[v1.4] 3 tabs in 3 groups: Resumo / Operações / Desempenho.
"""
from __future__ import annotations
from datetime import datetime as _dt
from skills.cvm.backtest._registry import register_mode
from skills.cvm.backtest.modes.run import run
from skills.cvm.backtest.report import (
    build_overview_kpis, build_config_section, build_strategy_section,
    build_equity_curve_section, build_trades_section,
    build_performance_section, build_drawdown_section,
)

def _safe_call(fn, *args, **kwargs):
    try: return fn(*args, **kwargs)
    except Exception as e: return {"status": "error", "error": str(e)}

@register_mode("dashboard",
    description="Multi-tab backtest dashboard with sidebar groups.",
    params={"ticker": "str. Required.", "strategy": "str. Default: value_pe.",
            "start_date": "str. Default: 3 years ago.", "end_date": "str. Default: today.",
            "initial_capital": "float. Default: 10000.", "max_positions": "int. Default: 1."},
    include_in_all=False,
    examples=['skill(domain="cvm", sub_domain="backtest", mode="dashboard", params=\'{"ticker":"PETR4","strategy":"value_pe"}\')'],
)
def dashboard(ticker: str = "", strategy: str = "value_pe", start_date: str = "",
              end_date: str = "", initial_capital: float = 10000.0, max_positions: int = 1) -> dict:
    if not ticker:
        return {"status": "error", "error": "ticker is required"}
    _t0 = _dt.now()
    print(f"[backtest] Starting: {ticker} / {strategy}...", flush=True)
    print(f"[backtest] Running backtest...", flush=True)
    try:
        run_result = run(ticker=ticker, strategy=strategy, start_date=start_date,
                         end_date=end_date, initial_capital=initial_capital, max_positions=max_positions)
    except Exception as e:
        return {"status": "error", "error": str(e)}
    if run_result.get("status") != "ok":
        return run_result
    perf = run_result.get("performance") or {}
    trades = run_result.get("trades") or []
    equity_curve = run_result.get("equity_curve") or []
    _ticker = run_result.get("ticker", ticker)
    _bt_elapsed = (_dt.now() - _t0).total_seconds()
    print(f"[backtest] Backtest done ({_bt_elapsed:.1f}s): {len(trades)} trades, return={perf.get('total_return_pct',0):.2f}%", flush=True)

    kpis = build_overview_kpis(perf)

    # [v5] One-line section timers (ratios pattern): 3 sections.
    _SEC_TOTAL = 3
    _sec_count = 0
    _sec_t0 = _dt.now()

    # Company header + price chart
    company_header, price_chart = {}, None
    try:
        from skills.cvm._shared_report.company_header import build_company_header
        company_header = build_company_header(_ticker)
    except Exception: pass
    try:
        from skills.cvm._shared_report.price_chart import build_price_chart
        price_chart = build_price_chart(_ticker)
    except Exception: pass

    # ── Section 1/3: Overview ─────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    overview_sections = [build_config_section(run_result), build_strategy_section(run_result),
                         build_equity_curve_section(equity_curve)]
    if company_header.get("name"):
        overview_sections.insert(0, {"type": "company_info", "company_header": company_header})
    if price_chart:
        overview_sections.append(price_chart)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Overview ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/3: Trades ───────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    trades_sections = [build_trades_section(trades)]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Trades ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/3: Performance ──────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    performance_sections = build_performance_section(perf)
    dd = build_drawdown_section(equity_curve)
    if dd: performance_sections.append(dd)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Performance ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # Freshness footer
    freshness_footer = ""
    try:
        from skills.cvm._freshness import get_freshness
        fresh = get_freshness()
        cot = fresh.get("cotahist", "")
        freshness_footer = f"COTAHIST: {cot[:10] if cot else '—'}"
    except Exception: pass

    tabs = [
        {"name": "Overview", "group": "Resumo", "sections": overview_sections},
        {"name": "Trades", "group": "Operações", "sections": trades_sections},
        {"name": "Performance", "group": "Desempenho", "sections": performance_sections},
    ]
    _total = (_dt.now() - _t0).total_seconds()
    print(f"[backtest] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
    return {"status": "ok", "ticker": _ticker, "strategy": run_result.get("strategy",""),
            "company_header": company_header, "tabs": tabs, "kpis": kpis,
            "freshness_footer": freshness_footer}
