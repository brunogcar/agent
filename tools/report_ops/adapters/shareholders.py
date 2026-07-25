"""adapters/shareholders.py — Flatten shareholders skill JSON → table data.

Adapters:
  shareholders_shareholders    — named shareholders table (%ON/%PN/%Total, qty)
  shareholders_free_float      — free float % + shareholder counts per period
  shareholders_equity_structure— equity breakdown (BRL) per fiscal year
  shareholders_summary         — KPIs + top shareholders + equity components

FRE ownership percentages (pct_on/pct_pn/pct_total) are stored by CVM as
plain percent numbers (45.23 = 45.23%), so they use the "pct_raw" spec.
Equity values (BPP 2.03.*) use "brl".
"""
from __future__ import annotations

from tools.report_ops.adapters import (
    register_adapter, _ok, _error_table, _kv_section, _safe_num,
)

# BPP 2.03.* code -> display column
_EQUITY_CODES = [
    ("2.03",    "PL Total"),
    ("2.03.01", "Capital Social"),
    ("2.03.02", "Reservas de Capital"),
    ("2.03.04", "Reservas de Lucros"),
    ("2.03.05", "Lucros Acumulados"),
    ("2.03.09", "Minority Interest"),
]


@register_adapter("shareholders_shareholders")
def shareholders(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Shareholders")
    sh = result.get("shareholders") or []
    if not sh:
        return _error_table(result, title="Shareholders")
    columns = ["Acionista", "CPF/CNPJ", "Tipo", "% Total", "% ON", "% PN", "Qtde Total", "Controlador"]
    rows = []
    for s in sh:
        rows.append([
            s.get("acionista", ""),
            s.get("cpf_cnpj", "") or "—",
            s.get("tipo_pessoa", "") or "—",
            _safe_num(s.get("pct_total")),
            _safe_num(s.get("pct_on")),
            _safe_num(s.get("pct_pn")),
            _safe_num(s.get("qtd_total")),
            "Sim" if s.get("controlador") else "Não",
        ])
    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": "Posição Acionária",
            "columns": columns,
            "rows": rows,
            "formats": {
                "% Total": "pct_raw", "% ON": "pct_raw", "% PN": "pct_raw",
                "Qtde Total": "int",
                "Acionista": "text", "CPF/CNPJ": "text", "Tipo": "text", "Controlador": "text",
            },
            "note": f"Data de referência: {result.get('data_referencia', '—')}",
        }],
        "kpis": [
            {"label": "Total Acionistas", "value": len(sh), "format": "int"},
        ],
        "sources": [],
    }


@register_adapter("shareholders_free_float")
def free_float(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Free Float")
    periods = result.get("periods") or []
    if not periods:
        return _error_table(result, title="Free Float")
    columns = ["Data Referência", "% Circulação", "Acionistas PF", "Acionistas PJ", "Acionistas Inst."]
    rows = []
    for p in periods:
        rows.append([
            p.get("data_referencia", ""),
            _safe_num(p.get("pct_total_circulacao")),
            _safe_num(p.get("qtd_acionistas_pf")),
            _safe_num(p.get("qtd_acionistas_pj")),
            _safe_num(p.get("qtd_acionistas_inst")),
        ])
    latest = periods[0]
    total_owners = (_safe_num(latest.get("qtd_acionistas_pf")) or 0) \
        + (_safe_num(latest.get("qtd_acionistas_pj")) or 0) \
        + (_safe_num(latest.get("qtd_acionistas_inst")) or 0)
    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": "Free Float / Distribuição de Acionistas",
            "columns": columns,
            "rows": rows,
            "formats": {
                "% Circulação": "pct_raw",
                "Acionistas PF": "int", "Acionistas PJ": "int", "Acionistas Inst.": "int",
                "Data Referência": "text",
            },
        }],
        "kpis": [
            {"label": "% Free Float", "value": _safe_num(latest.get("pct_total_circulacao")), "format": "pct_raw"},
            {"label": "Total Acionistas", "value": total_owners, "format": "int"},
        ],
        "sources": [],
    }


@register_adapter("shareholders_equity_structure")
def equity_structure(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Equity Structure")
    periods = result.get("periods") or []
    if not periods:
        return _error_table(result, title="Equity Structure")
    columns = ["Período"] + [label for _, label in _EQUITY_CODES]
    rows = []
    for p in periods:
        accounts = p.get("accounts") or {}
        row = [p.get("data_fim_exerc", "")]
        for code, _label in _EQUITY_CODES:
            entry = accounts.get(code) or {}
            row.append(_safe_num(entry.get("valor_brl")))
        rows.append(row)
    formats = {"Período": "text"}
    for _code, label in _EQUITY_CODES:
        formats[label] = "brl"
    latest = periods[0]
    latest_pl = (latest.get("accounts") or {}).get("2.03", {}).get("valor_brl")
    return {
        "company": result.get("company", ""),
        "sections": [{
            "title": "Estrutura Patrimonial (BPP 2.03.*)",
            "columns": columns,
            "rows": rows,
            "formats": formats,
            "note": "Valores de balanço (snapshot) em BRL por exercício.",
        }],
        "kpis": [
            {"label": "PL Total (mais recente)", "value": _safe_num(latest_pl), "format": "brl"},
        ],
        "sources": [],
    }


@register_adapter("shareholders_summary")
def summary(result: dict) -> dict:
    if not _ok(result):
        return _error_table(result, title="Shareholders Summary")
    sections_ = result.get("sections") or {}
    company = result.get("company", "")
    out_sections = []
    kpis: list[dict] = []

    # Top shareholders
    sh_block = sections_.get("shareholders") or {}
    top = sh_block.get("top") or []
    if top:
        columns = ["Acionista", "% Total", "Qtde Total", "Controlador"]
        rows = []
        for s in top:
            rows.append([
                s.get("acionista", ""),
                _safe_num(s.get("pct_total")),
                _safe_num(s.get("qtd_total")),
                "Sim" if s.get("controlador") else "Não",
            ])
        out_sections.append({
            "title": "Principais Acionistas",
            "columns": columns,
            "rows": rows,
            "formats": {"% Total": "pct_raw", "Qtde Total": "int",
                        "Acionista": "text", "Controlador": "text"},
            "note": f"Data de referência: {sh_block.get('data_referencia', '—')}",
        })

    # Free float KPI
    ff = sections_.get("free_float") or {}
    if ff.get("pct_total_circulacao") is not None:
        kpis.append({"label": "% Free Float", "value": _safe_num(ff.get("pct_total_circulacao")), "format": "pct_raw"})

    # Equity components (key-value)
    eq = sections_.get("equity") or {}
    components = eq.get("components") or {}
    label_map = dict(_EQUITY_CODES)
    if components:
        kv_rows = []
        for code, label in _EQUITY_CODES:
            if code in components:
                kv_rows.append((label, _safe_num(components.get(code)), "brl"))
        if kv_rows:
            out_sections.append(_kv_section(
                f"Composição do PL ({eq.get('data_fim_exerc', '—')})", kv_rows))
        if components.get("2.03") is not None:
            kpis.append({"label": "PL Total", "value": _safe_num(components.get("2.03")), "format": "brl"})

    if not out_sections:
        return _error_table(result, title="Shareholders Summary")

    return {
        "company": company,
        "sections": out_sections,
        "kpis": kpis,
        "sources": [],
    }
