"""skills/cvm/backtest/report.py -- Dashboard composition helpers.

[v1.4] Dashboard overhaul: split tables, tooltips, chart titles, config card.
"""
from __future__ import annotations
from typing import Any
from tools.report_ops.formats import apply_fmt

_EQUITY_COLOR = "#0d9488"

def _fmt(value: Any, spec: str) -> str:
    if value is None: return "—"
    try: return apply_fmt(value, spec)
    except Exception: return str(value)

def _cell(label: str, tooltip: str = "") -> dict:
    return {"text": label, "tooltip": tooltip} if tooltip else label

_TIPS = {
    "Total Return": "Retorno total da estratégia no período.",
    "CAGR": "CAGR = (Capital Final / Capital Inicial)^(1/anos) - 1.",
    "Max Drawdown": "Maior queda do patrimônio a partir do pico.",
    "Sharpe Ratio": "Sharpe = (Retorno - Rf) / Volatilidade. >1 bom, >2 excelente.",
    "Win Rate": "% de trades lucrativos.",
    "Number of Trades": "Total de trades executados.",
    "Buy & Hold Return": "Retorno de comprar e manter (benchmark).",
    "Alpha vs Buy & Hold": "Alpha = Retorno Estratégia - Buy & Hold. >0 superou.",
    "Entry Date": "Data de entrada no trade.",
    "Exit Date": "Data de saída do trade.",
    "Entry Price": "Preço de compra.",
    "Exit Price": "Preço de venda.",
    "Shares": "Quantidade de ações.",
    "PnL (R$)": "Lucro/Prejuízo em reais.",
    "Return %": "Retorno percentual do trade.",
    "Holding Days": "Dias na posição.",
    "Exit Reason": "Motivo da saída: signal / max_holding / end_of_period.",
}
def _tip(k): return _TIPS.get(k, "")

def build_overview_kpis(perf: dict) -> list[dict]:
    return [
        {"label": "CAGR", "value": _fmt(perf.get("cagr_pct"), "pct_raw"), "unit": "pct"},
        {"label": "Total Return", "value": _fmt(perf.get("total_return_pct"), "pct_raw"), "unit": "pct"},
        {"label": "Max Drawdown", "value": _fmt(perf.get("max_drawdown_pct"), "pct_raw"), "unit": "pct"},
        {"label": "Sharpe", "value": _fmt(perf.get("sharpe_ratio"), "num"), "unit": "num"},
        {"label": "Win Rate", "value": _fmt(perf.get("win_rate_pct"), "pct_raw"), "unit": "pct"},
        {"label": "Alpha", "value": _fmt(perf.get("alpha_vs_buy_hold"), "pct_raw"), "unit": "pct"},
    ]

def build_config_section(result: dict) -> dict:
    return {"title": "Configuração da Estratégia", "type": "table",
            "columns": ["Parâmetro", "Valor"],
            "rows": [["Ticker", result.get("ticker", "—")],
                     ["Estratégia", result.get("strategy", "—")],
                     ["Descrição", result.get("strategy_description", "—")],
                     ["Período", f"{result.get('start_date', '—')} → {result.get('end_date', '—')}"],
                     ["Capital Inicial", _fmt(result.get("initial_capital"), "brl_full")],
                     ["Capital Final", _fmt(result.get("final_equity"), "brl_full")]]}

def build_strategy_section(result: dict) -> dict:
    lines = [f"Ticker: {result.get('ticker','')}    Strategy: {result.get('strategy','')}",
             f"Description: {result.get('strategy_description','')}",
             f"Period: {result.get('start_date','')} -> {result.get('end_date','')}",
             f"Capital: R$ {result.get('initial_capital',0):,.2f} -> R$ {result.get('final_equity',0):,.2f}"]
    return {"title": "Strategy", "type": "text", "text": "\n".join(lines)}

def build_equity_curve_section(equity_curve: list) -> dict:
    labels = [pt.get("date", "") for pt in equity_curve]
    values = [pt.get("equity") for pt in equity_curve]
    return {"title": "Curva de Capital", "description": "Evolução do patrimônio ao longo do tempo.",
            "type": "chart",
            "chart_data": {"type": "line", "data": {"labels": labels,
                "datasets": [{"label": "Patrimônio (R$)", "data": values,
                    "borderColor": _EQUITY_COLOR, "backgroundColor": "rgba(13,148,136,0.15)",
                    "borderWidth": 2, "tension": 0.3, "fill": True}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                    "plugins": {"legend": {"display": True, "position": "bottom"},
                                "title": {"display": True, "text": "Curva de Capital"}},
                    "scales": {"x": {"grid": {"display": False}},
                               "y": {"grid": {"color": "rgba(128,128,128,0.1)"}}}}}}

def build_trades_section(trades: list) -> dict:
    columns = ["Entry Date", "Entry Price", "Exit Date", "Exit Price",
               "Shares", "PnL (R$)", "Return %", "Holding Days", "Exit Reason"]
    rows = []
    for t in trades:
        rows.append([_cell(t.get("entry_date",""), _tip("Entry Date")), t.get("entry_price"),
                     _cell(t.get("exit_date",""), _tip("Exit Date")), t.get("exit_price"),
                     t.get("shares"), t.get("pnl"), t.get("return_pct"),
                     t.get("holding_days"), _cell(t.get("exit_reason",""), _tip("Exit Reason"))])
    return {"title": "Trade Log", "type": "table", "columns": columns, "rows": rows,
            "formats": {"Entry Price": "brl_full", "Exit Price": "brl_full",
                        "PnL (R$)": "brl_full", "Return %": "pct_raw",
                        "Shares": "int", "Holding Days": "int",
                        "Entry Date": "text", "Exit Date": "text", "Exit Reason": "text"},
            "note": f"{len(rows)} trade(s) executado(s)."}

def build_performance_section(perf: dict) -> list[dict]:
    sections = []
    sections.append({"title": "Retornos", "type": "table", "columns": ["Métrica", "Valor"],
        "rows": [[_cell("Total Return", _tip("Total Return")), _fmt(perf.get("total_return_pct"), "pct_raw")],
                 [_cell("CAGR", _tip("CAGR")), _fmt(perf.get("cagr_pct"), "pct_raw")],
                 [_cell("Buy & Hold Return", _tip("Buy & Hold Return")), _fmt(perf.get("buy_hold_return_pct"), "pct_raw")],
                 [_cell("Alpha vs Buy & Hold", _tip("Alpha vs Buy & Hold")), _fmt(perf.get("alpha_vs_buy_hold"), "pct_raw")]]})
    sections.append({"title": "Risco", "type": "table", "columns": ["Métrica", "Valor"],
        "rows": [[_cell("Max Drawdown", _tip("Max Drawdown")), _fmt(perf.get("max_drawdown_pct"), "pct_raw")],
                 [_cell("Sharpe Ratio", _tip("Sharpe Ratio")), _fmt(perf.get("sharpe_ratio"), "num")]]})
    sections.append({"title": "Qualidade", "type": "table", "columns": ["Métrica", "Valor"],
        "rows": [[_cell("Win Rate", _tip("Win Rate")), _fmt(perf.get("win_rate_pct"), "pct_raw")],
                 [_cell("Number of Trades", _tip("Number of Trades")), _fmt(perf.get("num_trades"), "int")]]})
    return sections

def build_drawdown_section(equity_curve: list) -> dict | None:
    if not equity_curve or len(equity_curve) < 2: return None
    labels, drawdowns, running_max = [], [], float("-inf")
    for pt in equity_curve:
        eq = pt.get("equity")
        if eq is None: continue
        running_max = max(running_max, eq)
        dd = ((eq - running_max) / running_max * 100) if running_max > 0 else 0
        labels.append(pt.get("date", ""))
        drawdowns.append(round(dd, 2))
    if not labels: return None
    return {"title": "Drawdown (Underwater Equity)",
            "description": "Queda percentual do patrimônio a partir do pico.",
            "type": "chart",
            "chart_data": {"type": "line", "data": {"labels": labels,
                "datasets": [{"label": "Drawdown %", "data": drawdowns,
                    "borderColor": "#ef4444", "backgroundColor": "rgba(239,68,68,0.15)",
                    "borderWidth": 2, "tension": 0.3, "fill": True}]},
                "options": {"responsive": True, "maintainAspectRatio": False,
                    "plugins": {"legend": {"display": True, "position": "bottom"},
                                "title": {"display": True, "text": "Drawdown (%)"}},
                    "scales": {"x": {"grid": {"display": False}},
                               "y": {"grid": {"color": "rgba(128,128,128,0.1)"}}}}}}
