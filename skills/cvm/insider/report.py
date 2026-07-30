"""skills/cvm/insider/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the summary() + history() + by_role() results into a multi-tab
dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


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


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(summary_result: dict) -> list[dict]:
    """Build 4 KPI cards for the dashboard top-level kpis list.

    Cards (from the summary() result):
      - Sentimento       — sentiment string uppercased ("BUYING"/"SELLING"/
                            "NEUTRAL"/"—") as text
      - Volume Comprado  — total_volume_bought formatted as brl
      - Volume Vendido   — total_volume_sold formatted as brl
      - Net Volume       — net_volume formatted as brl
    """
    sentiment = (summary_result.get("sentiment") if _ok(summary_result)
                 else None)
    if isinstance(sentiment, str) and sentiment:
        sentiment_kpi_value = sentiment.upper()
    elif sentiment is None or not sentiment:
        sentiment_kpi_value = "—"
    else:
        sentiment_kpi_value = str(sentiment).upper()

    total_bought = (summary_result.get("total_volume_bought")
                    if _ok(summary_result) else None)
    total_sold = (summary_result.get("total_volume_sold")
                  if _ok(summary_result) else None)
    net_volume = (summary_result.get("net_volume")
                  if _ok(summary_result) else None)

    return [
        {"label": "Sentimento",      "value": sentiment_kpi_value, "unit": "text"},
        _kpi("Volume Comprado", total_bought, "brl", "brl"),
        _kpi("Volume Vendido",  total_sold,   "brl", "brl"),
        _kpi("Net Volume",      net_volume,   "brl", "brl"),
    ]


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(summary_result: dict) -> dict:
    """Build the Overview tab's text section summarizing the insider data.

    Multi-line text showing company, total transactions, total bought/sold,
    net volume, and the sentiment interpretation.
    """
    company = (summary_result.get("company", "") if _ok(summary_result)
               else "")
    cnpj = (summary_result.get("cnpj", "") if _ok(summary_result)
            else "")

    if _ok(summary_result):
        monthly = summary_result.get("monthly") or []
        total_transactions = sum(m.get("transaction_count", 0) for m in monthly)
        total_bought = summary_result.get("total_volume_bought")
        total_sold = summary_result.get("total_volume_sold")
        net_volume = summary_result.get("net_volume")
        sentiment = summary_result.get("sentiment", "")
    else:
        total_transactions = "—"
        total_bought = None
        total_sold = None
        net_volume = None
        sentiment = ""

    if isinstance(sentiment, str) and sentiment:
        sentiment_label = sentiment.upper()
    else:
        sentiment_label = "—"

    text_lines = [
        f"Company: {company}",
        f"CNPJ: {cnpj or '—'}",
        f"Total de Transações: {total_transactions}",
        f"Volume Comprado: {_fmt(total_bought, 'brl')}",
        f"Volume Vendido: {_fmt(total_sold, 'brl')}",
        f"Net Volume: {_fmt(net_volume, 'brl')}",
        f"Sentimento: {sentiment_label}",
    ]
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── Recent Transactions tab section (history table) ─────────────────────────

def build_recent_transactions_section(history_result: dict) -> dict:
    """Build the Recent Transactions tab table from the history() result.

    Columns: Data, Cargo, Tipo, Ativo, Qtd, Preço, Volume
    Limited to the 10 most recent transactions (history() already returns
    newest-first).
    """
    movements = (history_result.get("movements")
                 if _ok(history_result) else []) or []

    # Limit to 10 most recent rows (history() returns newest-first).
    recent = movements[:10]

    columns = ["Data", "Cargo", "Tipo", "Ativo", "Qtd", "Preço", "Volume"]
    rows = []
    for m in recent:
        rows.append([
            m.get("Data_Movimentacao", "") or "—",
            m.get("Tipo_Cargo", "") or "—",
            m.get("Tipo_Movimentacao", "") or "—",
            m.get("Tipo_Ativo", "") or "—",
            m.get("Quantidade") if m.get("Quantidade") is not None else "—",
            m.get("Preco_Unitario") if m.get("Preco_Unitario") is not None else "—",
            m.get("Volume") if m.get("Volume") is not None else "—",
        ])

    formats = {
        "Data": "text", "Cargo": "text", "Tipo": "text",
        "Ativo": "text", "Qtd": "num", "Preço": "brl_full",
        "Volume": "brl",
    }

    return {
        "title": f"Insider Transactions ({len(recent)} recent)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Movimentações recentes de insiders (newest-first).",
    }


# ── By Role tab section ──────────────────────────────────────────────────────

def build_by_role_section(by_role_result: dict) -> dict:
    """Build the By Role tab table from the by_role() result.

    Columns: Cargo, Transações, Qtd Comprada, Qtd Vendida,
             Vol Comprado, Vol Vendido, Net Volume
    """
    roles = (by_role_result.get("by_role")
             if _ok(by_role_result) else []) or []

    columns = ["Cargo", "Transações", "Qtd Comprada", "Qtd Vendida",
               "Vol Comprado", "Vol Vendido", "Net Volume"]
    rows = []
    for r in roles:
        vol_bought = r.get("volume_bought") or 0
        vol_sold = r.get("volume_sold") or 0
        rows.append([
            r.get("Tipo_Cargo", "") or "—",
            r.get("transaction_count") if r.get("transaction_count") is not None else "—",
            r.get("total_bought") if r.get("total_bought") is not None else "—",
            r.get("total_sold") if r.get("total_sold") is not None else "—",
            vol_bought if vol_bought is not None else "—",
            vol_sold if vol_sold is not None else "—",
            (vol_bought - vol_sold) if (vol_bought is not None
                                        and vol_sold is not None) else "—",
        ])

    formats = {
        "Cargo": "text", "Transações": "int",
        "Qtd Comprada": "num", "Qtd Vendida": "num",
        "Vol Comprado": "brl", "Vol Vendido": "brl",
        "Net Volume": "brl",
    }

    return {
        "title": f"Insider Trading by Role ({len(roles)} roles)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Movimentações agrupadas por cargo (Tipo_Cargo).",
    }


# ── Monthly Net tab section ──────────────────────────────────────────────────

def build_monthly_section(summary_result: dict) -> dict:
    """Build the Monthly Net tab table from the summary() result.

    Columns: Mês, Transações, Comprado, Vendido,
             Vol Comprado, Vol Vendido, Net Volume
    """
    monthly = (summary_result.get("monthly")
               if _ok(summary_result) else []) or []

    columns = ["Mês", "Transações", "Comprado", "Vendido",
               "Vol Comprado", "Vol Vendido", "Net Volume"]
    rows = []
    for m in monthly:
        rows.append([
            m.get("month", "") or "—",
            m.get("transaction_count") if m.get("transaction_count") is not None else "—",
            m.get("bought") if m.get("bought") is not None else "—",
            m.get("sold") if m.get("sold") is not None else "—",
            m.get("volume_bought") if m.get("volume_bought") is not None else "—",
            m.get("volume_sold") if m.get("volume_sold") is not None else "—",
            m.get("net_volume") if m.get("net_volume") is not None else "—",
        ])

    formats = {
        "Mês": "text", "Transações": "int",
        "Comprado": "num", "Vendido": "num",
        "Vol Comprado": "brl", "Vol Vendido": "brl",
        "Net Volume": "brl",
    }

    return {
        "title": f"Insider Net Buy/Sell per Month ({len(monthly)} months)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Resumo mensal de compra/venda de insiders.",
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    """Return True if the result dict represents a successful call.

    Mirrors tools.report_ops.adapters._ok: status == "ok" and dict-typed.
    """
    return isinstance(result, dict) and result.get("status") == "ok"
