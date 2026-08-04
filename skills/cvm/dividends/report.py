"""skills/cvm/dividends/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the summary() result into a multi-tab dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any
from datetime import date

from tools.report_ops.formats import apply_fmt

# Calculations engines — imported at module top so tests can monkeypatch them.
# These are used by build_overview_kpis to fetch Div Yield + Payout Ratio.
from skills.cvm.calculations.engines.dividends import dividends_at
from skills.cvm.calculations.engines.price import price_at
from skills.cvm.calculations.engines.earnings import ttm_earnings_at
from skills.cvm.calculations.engines.shares import shares_at


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _num(v: Any) -> Any:
    """Coerce numeric strings/values to int or float (passthrough None)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _kpi(label: str, value: Any, spec: str, unit: str) -> dict:
    """Build a single KPI card: {label, value, unit}.

    The value is pre-formatted via apply_fmt so the adapter can pass it
    through verbatim. When value is None, falls back to "—".
    """
    if value is None:
        return {"label": label, "value": "—", "unit": unit}
    return {"label": label, "value": _fmt(value, spec), "unit": unit}


def _cell(label: str, tooltip: str = "") -> dict | str:
    """Wrap a label in a dict cell carrying a tooltip when non-empty.

    Returns ``{"text": label, "tooltip": tooltip}`` when ``tooltip`` is
    truthy, otherwise returns ``label`` unchanged.
    """
    return {"text": label, "tooltip": tooltip} if tooltip else label


# ── Dividend type tooltips (v3) ──────────────────────────────────────────────
# Maps the B3 dividend ``label`` (Tipo) to a PT-BR explanation of what each
# type means. Used as cell-level tooltip on the "Tipo" column of the History
# tab so the user can hover to see the meaning of Dividendo / JCP / Restituição.
_DIVIDEND_TYPE_TOOLTIPS: dict[str, str] = {
    "Dividendo":   "Dividendo = distribuição de lucros aos acionistas (tributado).",
    "JCP":         "JCP = Juros sobre Capital Próprio (dedutível fiscalmente).",
    "Restituição": "Restituição = devolução de capital aos acionistas.",
    "DIVIDENDO":   "Dividendo = distribuição de lucros aos acionistas (tributado).",
    "Juros sobre Capital Próprio": "JCP = Juros sobre Capital Próprio (dedutível fiscalmente).",
}

# Tooltip for the "Valor/Ação" column — same explanation for every cell.
_VALUE_PER_SHARE_TOOLTIP = (
    "Valor/Ação = valor do provento por ação em BRL (R$). Para JCP, já líquido "
    "de impostos na fonte."
)


# ── Annual total extraction ──────────────────────────────────────────────────

def _annual_total(period: dict) -> float | None:
    """Extract the total dividend (7.08.04) from a single annual period.

    Falls back to 7.08.04.02 (Dividendos) + 7.08.04.01 (JCP) if 7.08.04
    is missing. Returns None when no value is available.
    """
    accounts = period.get("accounts") or {}
    total = accounts.get("7.08.04") or {}
    val = total.get("valor_brl")
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    # Fallback: sum Dividendos + JCP
    total_val = 0.0
    found = False
    for code in ("7.08.04.02", "7.08.04.01"):
        entry = accounts.get(code) or {}
        v = entry.get("valor_brl")
        if v is not None:
            try:
                total_val += float(v)
                found = True
            except (TypeError, ValueError):
                pass
    return total_val if found else None


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(summary_result: dict, company: str = "") -> list[dict]:
    """Build the 4 KPI cards for the dashboard top-level kpis list.

    Cards:
      - Total Dividends Paid (latest year) — from annual_trend 7.08.04 (total)
      - Dividend Yield — from calculations dpa metric (dividends_at / price_at)
      - Payout Ratio — from calculations dpa metric (dividends / earnings)
      - Last Payment Date — from recent_events.events[0].payment_date
    """
    sections = summary_result.get("sections") or {}

    # 1. Total Dividends Paid (latest year)
    annual_trend = sections.get("annual_trend") or {}
    periods = annual_trend.get("periods") or []
    total_paid = _annual_total(periods[0]) if periods else None

    # 2. Dividend Yield + 3. Payout Ratio — fetch from calculations engines
    # (dividends_at returns DPA per-share TTM; we need price for yield and
    # earnings for payout).
    dividend_yield = None
    payout_ratio = None
    if company:
        try:
            today = date.today().isoformat()
            dpa = dividends_at(company, today)
            price = price_at(company, today)
            earnings = ttm_earnings_at(company, today)
            if dpa is not None and price is not None and price > 0:
                dividend_yield = dpa / price
            if dpa is not None and earnings is not None and earnings > 0:
                # dpa is per-share, earnings is total — need shares
                sh = shares_at(company, today)
                if sh is not None and sh > 0:
                    total_dividends = dpa * sh
                    payout_ratio = total_dividends / earnings
        except Exception:
            pass

    # 4. Last Payment Date — most recent event's payment_date.
    recent_events = sections.get("recent_events") or {}
    events = recent_events.get("events") or []
    last_payment_date = None
    if events:
        last_payment_date = events[0].get("payment_date") or None

    return [
        _kpi("Total Dividends Paid", total_paid,        "brl",  "BRL"),
        _kpi("Dividend Yield",       dividend_yield,    "pct",  "pct"),
        _kpi("Payout Ratio",         payout_ratio,      "pct",  "pct"),
        _kpi("Last Payment Date",    last_payment_date, "text", "date"),
    ]


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(summary_result: dict) -> dict:
    """Build the Overview tab's text section summarizing the dividends data.

    Multi-line text showing company, recent events count, years of history,
    and last payment date. Useful when the dashboard template renders the
    Overview tab below the KPI grid.
    """
    sections = summary_result.get("sections") or {}
    company = summary_result.get("company", "")

    recent_events = sections.get("recent_events") or {}
    events_count = recent_events.get("count", 0)
    ticker = recent_events.get("ticker", "") or company
    events = recent_events.get("events") or []
    last_payment_date = events[0].get("payment_date", "") if events else "—"

    annual_trend = sections.get("annual_trend") or {}
    periods = annual_trend.get("periods") or []
    years_count = len(periods)

    payable = sections.get("payable") or {}
    payable_status = payable.get("status", "ok")
    if payable_status == "ok":
        payable_line = "Payable: available"
    else:
        payable_line = f"Payable: {payable_status}"

    text_lines = [
        f"Company: {company}",
        f"Ticker: {ticker}",
        f"Recent events: {events_count}",
        f"Years of history: {years_count}",
        f"Last payment date: {last_payment_date}",
        payable_line,
    ]
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── History tab section (recent events table) ────────────────────────────────

def build_history_section(summary_result: dict) -> dict:
    """Build the History tab table from summary()['sections']['recent_events'].

    Columns: Data Aprovação, Data Ex, Data Pagamento, Valor/Ação, Tipo, Relativo a

    [v3] The "Valor/Ação" and "Tipo" column cells now carry tooltips — the
    former explaining "value per share in BRL", the latter explaining the
    difference between Dividendo / JCP / Restituição.
    """
    sections = summary_result.get("sections") or {}
    recent_events = sections.get("recent_events") or {}
    events = recent_events.get("events") or []

    columns = ["Data Aprovação", "Data Ex", "Data Pagamento",
               "Valor/Ação", "Tipo", "Relativo a"]
    rows = []
    for e in events:
        tipo = e.get("label", "") or "—"
        rate = _num(e.get("rate"))
        # Wrap the rate cell with a tooltip explaining "value per share".
        rate_cell = _cell(rate, _VALUE_PER_SHARE_TOOLTIP) if rate is not None else "—"
        # Wrap the Tipo cell with a tooltip explaining Dividendo/JCP/Restituição.
        tipo_cell = _cell(tipo, _DIVIDEND_TYPE_TOOLTIPS.get(tipo, ""))
        rows.append([
            e.get("approved_on", "") or "—",
            e.get("last_date_prior", "") or "—",
            e.get("payment_date", "") or "—",
            rate_cell,
            tipo_cell,
            e.get("related_to", "") or "—",
        ])
    return {
        "title": "Histórico de Proventos (B3)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": {
            "Valor/Ação": "brl_full",
            "Data Aprovação": "text", "Data Ex": "text", "Data Pagamento": "text",
            "Tipo": "text", "Relativo a": "text",
        },
        "note": (f"{len(events)} evento(s) recente(s). "
                 "Valor/Ação em R$. Tipo distingue Dividendo de JCP."),
    }


# ── Annual tab section ───────────────────────────────────────────────────────

_DVA_CODES = [
    ("7.08.04.02", "Dividendos"),
    ("7.08.04.01", "JCP"),
    ("7.08.04",    "Total Remuneração"),
]


def build_annual_section(summary_result: dict) -> dict:
    """Build the Annual tab table from summary()['sections']['annual_trend'].

    Columns: Ano, Dividendos, JCP, Total Remuneração
    """
    sections = summary_result.get("sections") or {}
    annual_trend = sections.get("annual_trend") or {}
    periods = annual_trend.get("periods") or []

    columns = ["Ano"] + [label for _code, label in _DVA_CODES]
    rows = []
    for p in periods:
        accounts = p.get("accounts") or {}
        date = p.get("data_fim_exerc", "")
        year = date[:4] if date else ""
        row = [year]
        for code, _label in _DVA_CODES:
            entry = accounts.get(code) or {}
            row.append(_num(entry.get("valor_brl")))
        rows.append(row)

    formats = {"Ano": "text"}
    for _code, label in _DVA_CODES:
        formats[label] = "brl"

    return {
        "title": "Proventos Anuais Declarados (DVA 7.08.04.*)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Totais anuais declarados em BRL por exercício social.",
    }


# ── Chart builders (v1.2) ────────────────────────────────────────────────────
# Each chart builder returns {"type": "chart", "chart_data": <Chart.js config>}
# or None when no data. The dashboard template passes chart_data verbatim to
# `new Chart(ctx, chart_data)`.

# Brand palette (matches the report theme).
_TEAL   = "#0d9488"
_ORANGE = "#f59e0b"
_RED    = "#ef4444"
_BLUE   = "#3b82f6"
_PURPLE = "#a855f7"


def build_dividend_history_chart(history_data: Any) -> dict | None:
    """Build a Chart.js line chart showing dividend payments over time.

    history_data is the events list from summary()['sections']
    ['recent_events']['events']. Each event has payment_date + rate.
    The chart shows rate per share (R$) over time.

    Returns None when the events list is empty or no events carry both
    a payment_date + a numeric rate.
    """
    if not history_data:
        return None

    labels: list[str] = []
    values: list[float] = []
    for e in history_data:
        pay_date = e.get("payment_date") or ""
        rate = e.get("rate")
        if not pay_date or rate is None:
            continue
        try:
            rate_f = float(rate)
        except (TypeError, ValueError):
            continue
        labels.append(pay_date)
        values.append(rate_f)

    if not labels:
        return None

    return {
        "title": "Dividend Payments Over Time",
        "description": (
            "Valor por ação (R$) pago em cada data de pagamento. "
            "Inclui dividendos e JCP."
        ),
        "type": "chart",
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Value per Share (R$)",
                    "data": values,
                    "borderColor": _TEAL,
                    "backgroundColor": "rgba(13, 148, 136, 0.15)",
                    "borderWidth": 2,
                    "tension": 0.3,
                    "fill": True,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Dividend Payments Over Time"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }


def build_annual_dividend_chart(annual_data: Any) -> dict | None:
    """Build a Chart.js bar chart showing total dividends per year.

    annual_data is the periods list from summary()['sections']
    ['annual_trend']['periods']. Each period has data_fim_exerc +
    accounts['7.08.04'] (or 7.08.04.02 + 7.08.04.01 fallback). The chart
    shows the total dividend value (BRL) per fiscal year.

    Returns None when the periods list is empty or no periods yield a
    numeric total.
    """
    if not annual_data:
        return None

    labels: list[str] = []
    values: list[float] = []
    for p in annual_data:
        date = p.get("data_fim_exerc") or ""
        year = date[:4] if date else ""
        if not year:
            continue
        total = _annual_total(p)
        if total is None:
            continue
        labels.append(year)
        values.append(total)

    if not labels:
        return None

    return {
        "title": "Total Dividends per Year",
        "description": (
            "Total de proventos pagos por exercício social (BRL), "
            "somando dividendos + JCP (DVA 7.08.04)."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Total Dividends (BRL)",
                    "data": values,
                    "backgroundColor": _TEAL,
                    "borderColor": _TEAL,
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Total Dividends per Year"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }


# ── Stacked Dividendo vs JCP per year chart (v3) ─────────────────────────────

def build_annual_dividend_stacked_chart(annual_data: Any) -> dict | None:
    """Build a stacked bar chart showing Dividendo vs JCP per year.

    annual_data is the periods list from summary()['sections']
    ['annual_trend']['periods']. For each period the chart extracts:
      - Dividendos = accounts['7.08.04.02'] (DVA Dividendos)
      - JCP        = accounts['7.08.04.01'] (DVA JCP)

    The two are stacked per fiscal year so the user can see at a glance
    both the total remuneração and its composition.

    Returns None when the periods list is empty or no period has a numeric
    Dividendo or JCP value.
    """
    if not annual_data:
        return None

    labels: list[str] = []
    dividendos: list[float] = []
    jcp: list[float] = []
    for p in annual_data:
        date = p.get("data_fim_exerc") or ""
        year = date[:4] if date else ""
        if not year:
            continue
        accounts = p.get("accounts") or {}
        div_val = (accounts.get("7.08.04.02") or {}).get("valor_brl")
        jcp_val = (accounts.get("7.08.04.01") or {}).get("valor_brl")
        if div_val is None and jcp_val is None:
            continue
        try:
            div_f = float(div_val) if div_val is not None else 0.0
        except (TypeError, ValueError):
            div_f = 0.0
        try:
            jcp_f = float(jcp_val) if jcp_val is not None else 0.0
        except (TypeError, ValueError):
            jcp_f = 0.0
        labels.append(year)
        dividendos.append(round(div_f, 2))
        jcp.append(round(jcp_f, 2))

    if not labels:
        return None

    return {
        "title": "Dividendo vs JCP per Year (stacked)",
        "description": (
            "Composição da remuneração por exercício social (BRL): "
            "Dividendos (teal, DVA 7.08.04.02) e JCP (laranja, DVA 7.08.04.01) "
            "empilhados. A altura total = remuneração total; a proporção entre "
            "as cores mostra o mix entre dividendos e Juros sobre Capital Próprio."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Dividendos (BRL)",
                        "data": dividendos,
                        "backgroundColor": _TEAL,
                        "borderColor": _TEAL,
                        "borderWidth": 1,
                    },
                    {
                        "label": "JCP (BRL)",
                        "data": jcp,
                        "backgroundColor": _ORANGE,
                        "borderColor": _ORANGE,
                        "borderWidth": 1,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "Dividendo vs JCP per Year (stacked)"},
                },
                "scales": {
                    "x": {"stacked": True, "grid": {"display": False}},
                    "y": {"stacked": True,
                          "grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }
