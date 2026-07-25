"""adapters/dividends.py — Flatten dividends skill JSON → table data.

Adapters:
  dividends_history   — individual B3 dividend events (dates, rate, label)
  dividends_annual    — annual declared totals per fiscal year (DVA 7.08.04.*)
  dividends_summary   — KPIs + recent events table + annual trend table

DVA codes (annual mode):
  7.08.04     total remuneração de capitais próprios
  7.08.04.01  JCP
  7.08.04.02  Dividendos
  7.08.04.03  Lucros Retidos
Per-share rates from B3 history use brl_full; annual totals use brl (compact).
"""
from __future__ import annotations

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _safe_num,
)

_DVA_CODES = [
    ("7.08.04.02", "Dividendos"),
    ("7.08.04.01", "JCP"),
    ("7.08.04",    "Total Remuneração"),
]


@register_adapter("dividends_history")
def history(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Dividend History")
    events = result.get("dividends") or []
    if not events:
        return _error_table(result, title="Dividend History")
    columns = ["Data Aprovação", "Data Ex", "Data Pagamento", "Valor/Ação", "Tipo", "Relativo a"]
    rows = []
    for e in events:
        rows.append([
            e.get("approved_on", "") or "—",
            e.get("last_date_prior", "") or "—",
            e.get("payment_date", "") or "—",
            _safe_num(e.get("rate")),
            e.get("label", "") or "—",
            e.get("related_to", "") or "—",
        ])
    return {
        "company": result.get("ticker", ""),
        "sections": [{
            "title": "Histórico de Proventos (B3)",
            "columns": columns,
            "rows": rows,
            "formats": {
                "Valor/Ação": "brl_full",
                "Data Aprovação": "text", "Data Ex": "text", "Data Pagamento": "text",
                "Tipo": "text", "Relativo a": "text",
            },
            "note": "Valores por ação (R$). Tipo distingue Dividendo de JCP.",
        }],
        "kpis": [
            {"label": "Total Eventos", "value": result.get("count", len(events)), "format": "int"},
        ],
        "sources": [],
    }


@register_adapter("dividends_annual")
def annual(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Annual Dividends")
    periods = result.get("periods") or []
    if not periods:
        return _error_table(result, title="Annual Dividends")
    columns = ["Ano"] + [label for _code, label in _DVA_CODES]
    rows = []
    for p in periods:
        accounts = p.get("accounts") or {}
        date = p.get("data_fim_exerc", "")
        year = date[:4] if date else ""
        row = [year]
        for code, _label in _DVA_CODES:
            entry = accounts.get(code) or {}
            row.append(_safe_num(entry.get("valor_brl")))
        rows.append(row)
    formats = {"Ano": "text"}
    for _code, label in _DVA_CODES:
        formats[label] = "brl"
    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": "Proventos Anuais Declarados (DVA 7.08.04.*)",
            "columns": columns,
            "rows": rows,
            "formats": formats,
            "note": "Totais anuais declarados em BRL por exercício social.",
        }],
        "kpis": [],
        "sources": [],
    }


@register_adapter("dividends_summary")
def summary(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Dividends Summary")
    sections_ = result.get("sections") or {}
    company = result.get("company", "")
    out_sections = []
    kpis: list[dict] = []

    # Recent events
    re_block = sections_.get("recent_events") or {}
    events = re_block.get("events") or []
    if events:
        columns = ["Data Aprovação", "Data Pagamento", "Valor/Ação", "Tipo", "Relativo a"]
        rows = []
        for e in events:
            rows.append([
                e.get("approved_on", "") or "—",
                e.get("payment_date", "") or "—",
                _safe_num(e.get("rate")),
                e.get("label", "") or "—",
                e.get("related_to", "") or "—",
            ])
        out_sections.append({
            "title": "Proventos Recentes (B3)",
            "columns": columns,
            "rows": rows,
            "formats": {"Valor/Ação": "brl_full",
                        "Data Aprovação": "text", "Data Pagamento": "text",
                        "Tipo": "text", "Relativo a": "text"},
        })
        kpis.append({"label": "Eventos Recentes", "value": re_block.get("count", len(events)), "format": "int"})

    # Annual trend
    at_block = sections_.get("annual_trend") or {}
    at_periods = at_block.get("periods") or []
    if at_periods:
        columns = ["Ano", "Dividendos", "JCP", "Total Remuneração"]
        rows = []
        for p in at_periods:
            accounts = p.get("accounts") or {}
            date = p.get("data_fim_exerc", "")
            year = date[:4] if date else ""
            row = [year]
            for code, _label in _DVA_CODES:
                entry = accounts.get(code) or {}
                row.append(_safe_num(entry.get("valor_brl")))
            rows.append(row)
        out_sections.append({
            "title": "Tendência Anual (DVA)",
            "columns": columns,
            "rows": rows,
            "formats": {"Ano": "text", "Dividendos": "brl", "JCP": "brl", "Total Remuneração": "brl"},
        })

    if not out_sections:
        return _error_table(result, title="Dividends Summary")

    return {
        "company": company,
        "sections": out_sections,
        "kpis": kpis,
        "sources": [],
    }
