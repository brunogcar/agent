"""adapters/valuation.py — Flatten valuation skill JSON → table data.

Adapters:
  valuation_ratios   — KPI strip + full indicator table (includes ROIC, Graham)
  valuation_summary  — ratios table + data-availability table

v1.0.14: Added ROIC + Graham number to the indicator table.
"""
from __future__ import annotations

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _kv_section, _safe_num,
)


def _ratios_section(ratios: dict) -> dict:
    """Full indicator table — market metrics first, then financials + value metrics."""
    rows = [
        ("Market Cap",            _safe_num(ratios.get("market_cap")),        "brl"),
        ("Enterprise Value (EV)", _safe_num(ratios.get("ev")),                "brl"),
        ("Preço",                 _safe_num(ratios.get("price")),             "brl_full"),
        ("Lucro por Ação (EPS)",  _safe_num(ratios.get("eps")),               "brl_full"),
        ("Valor Patrimonial/Ação (VPA)", _safe_num(ratios.get("vpa")),        "brl_full"),
        ("Dividendo/Ação (DPA)",  _safe_num(ratios.get("dpa")),               "brl_full"),
        ("P/L",                   _safe_num(ratios.get("p_l")),               "num"),
        ("P/VPA",                 _safe_num(ratios.get("p_vpa")),             "num"),
        ("P/EBIT",                _safe_num(ratios.get("p_ebit")),            "num"),
        ("P/FCO",                 _safe_num(ratios.get("p_fco")),             "num"),
        ("P/FCF",                 _safe_num(ratios.get("p_fcf")),             "num"),
        ("PSR",                   _safe_num(ratios.get("psr")),               "num"),
        ("EV/EBITDA",             _safe_num(ratios.get("ev_ebitda")),         "num"),
        ("Dividend Yield",        _safe_num(ratios.get("dividend_yield")),    "pct"),
        ("Dívida Líq/EBITDA",     _safe_num(ratios.get("divida_liquida_ebitda")), "num"),
        # [v1.0.14] Value metrics
        ("ROIC",                  _safe_num(ratios.get("roic")),              "pct"),
        ("Graham Number",         _safe_num(ratios.get("graham_number")),     "brl_full"),
        ("Total de Ações",        _safe_num(ratios.get("total_shares")),      "int"),
        ("Lucro Líquido (TTM)",   _safe_num(ratios.get("lucro_liquido")),     "brl"),
        ("EBITDA (TTM)",          _safe_num(ratios.get("ebitda")),            "brl"),
        ("EBIT (TTM)",            _safe_num(ratios.get("ebit")),              "brl"),
        ("Receita Líquida (TTM)", _safe_num(ratios.get("receita_liquida")),   "brl"),
        ("Patrimônio Líquido",    _safe_num(ratios.get("patrimonio_liquido")),"brl"),
        ("Dívida Bruta",          _safe_num(ratios.get("divida_bruta")),      "brl"),
        ("Caixa",                 _safe_num(ratios.get("caixa")),             "brl"),
        ("FCO (TTM)",             _safe_num(ratios.get("fco")),               "brl"),
        ("FCF (TTM)",             _safe_num(ratios.get("fcf")),               "brl"),
        ("Dividendos Anuais",     _safe_num(ratios.get("annual_dividends")),  "brl"),
    ]
    return _kv_section("Valuation Ratios", rows)


def _kpis(ratios: dict) -> list[dict]:
    return [
        {"label": "Preço",       "value": _safe_num(ratios.get("price")),         "format": "brl_full"},
        {"label": "P/L",         "value": _safe_num(ratios.get("p_l")),           "format": "num"},
        {"label": "P/VPA",       "value": _safe_num(ratios.get("p_vpa")),         "format": "num"},
        {"label": "EV/EBITDA",   "value": _safe_num(ratios.get("ev_ebitda")),     "format": "num"},
        {"label": "ROIC",        "value": _safe_num(ratios.get("roic")),          "format": "pct"},
        {"label": "Graham",      "value": _safe_num(ratios.get("graham_number")), "format": "brl_full"},
        {"label": "Div Yield",   "value": _safe_num(ratios.get("dividend_yield")),"format": "pct"},
        {"label": "Market Cap",  "value": _safe_num(ratios.get("market_cap")),    "format": "brl"},
    ]


def _availability_section(result: dict) -> dict:
    da = result.get("data_availability") or {}
    if not da:
        sources = result.get("sources") or {}
        rows = []
        for key in ("price", "financials", "shares"):
            s = sources.get(key) or {}
            rows.append([key.capitalize(),
                         s.get("status", "missing"),
                         s.get("source", "") or s.get("error", "")])
        return {
            "title": "Data Source Availability",
            "columns": ["Source", "Status", "Detail"],
            "rows": rows,
            "formats": {"Source": "text", "Status": "text", "Detail": "text"},
        }
    rows = [[k, str(v)] for k, v in da.items()]
    return {
        "title": "Data Source Availability",
        "columns": ["Source", "Status"],
        "rows": rows,
        "formats": {"Source": "text", "Status": "text"},
    }


@register_adapter("valuation_ratios")
def ratios(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Valuation Ratios")
    r = result.get("ratios") or {}
    if not r:
        return _error_table(result, title="Valuation Ratios")
    note = ""
    if r.get("price_date"):
        note = f"Preço em {r.get('price_date')} (fonte: {r.get('price_source', '?')})."
    if r.get("ebitda_method"):
        note = (note + " " if note else "") + f"EBITDA method: {r.get('ebitda_method')}."
    # [v1.0.14] Note about TTM + approximate ROIC
    note = (note + " " if note else "") + "Financials: TTM (trailing 12 months). ROIC uses 34% tax rate (approximate)."
    sec = _ratios_section(r)
    if note:
        sec["note"] = note
    return {
        "company": result.get("ticker", ""),
        "sections": [sec],
        "kpis": _kpis(r),
        "sources": [],
    }


@register_adapter("valuation_summary")
def summary(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Valuation Summary")
    r = result.get("ratios") or {}
    sections = []
    kpis = []
    if r:
        sections.append(_ratios_section(r))
        kpis = _kpis(r)
    sections.append(_availability_section(result))
    return {
        "company": result.get("ticker", ""),
        "sections": sections,
        "kpis": kpis,
        "sources": [],
    }
