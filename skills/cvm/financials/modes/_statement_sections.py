"""skills/cvm/financials/modes/_statement_sections.py -- shared helpers.

Holds the section-classification functions used by the standalone statement
modes (bpa, bpp, dre, dfc, dva) and the reshape helper that converts a
`complete()` result into the dict-keyed shape expected by the dashboard.

Kept in modes/ (not in helpers.py) because it is statement-shape specific
and only consumed by the statement-mode files.
"""
from __future__ import annotations


# ── Section classifiers ──────────────────────────────────────────────────────
# Each function maps a CVM account codigo (e.g., "1.01.01") to a short
# human-readable section label used by the dashboard's table grouping.

def bpa_section_for(codigo: str) -> str:
    """BPA section: Ativo Circulante / Ativo Não Circulante / Ativo Total."""
    c = (codigo or "").strip()
    if c == "1" or c.startswith("1."):
        if c == "1":
            return "Ativo Total"
        if c.startswith("1.01"):
            return "Ativo Circulante"
        if c.startswith("1.02"):
            return "Ativo Não Circulante"
    return "Ativo"


def bpp_section_for(codigo: str) -> str:
    """BPP section: Passivo Circulante / Passivo Não Circulante / Patrimônio Líquido."""
    c = (codigo or "").strip()
    if c == "2":
        return "Passivo Total"
    if c.startswith("2.01"):
        return "Passivo Circulante"
    if c.startswith("2.02"):
        return "Passivo Não Circulante"
    if c.startswith("2.03"):
        return "Patrimônio Líquido"
    return "Passivo"


def dre_section_for(codigo: str) -> str:
    """DRE section: all codes belong to the income statement (single section)."""
    return "DRE"


def dfc_section_for(codigo: str) -> str:
    """DFC section: Operações / Investimento / Financiamento by codigo prefix."""
    c = (codigo or "").strip()
    if c.startswith("6.01"):
        return "Operações"
    if c.startswith("6.02"):
        return "Investimento"
    if c.startswith("6.03"):
        return "Financiamento"
    return "DFC"


def dva_section_for(codigo: str) -> str:
    """DVA section: Geração (codes 1-7) vs Distribuição (codes 8.*)."""
    c = (codigo or "").strip()
    # Distribution side: codes 8.* (wealth distributed to stakeholders)
    if c.startswith("8.") or c.startswith("7.08"):
        # 7.08.* in the CVM DVA taxonomy maps to "Remuneração de Capitais
        # Próprios" (own-capital remuneration = distribution to shareholders).
        return "Distribuição"
    # Generation side: codes 1-7 (wealth created)
    return "Geração"


# ── Reshape helper ───────────────────────────────────────────────────────────

def reshape_statement_periods(raw: dict, *, section_fn, statement_label: str) -> dict:
    """Reshape a complete() result into the standalone-statement-mode shape.

    Input shape (from complete()):
        {
          "status": "ok", "company": "...", "period_type": "annual",
          "grupo_filter": "DRE",
          "periods": [
            {"year": 2023, "data_fim_exerc": "2023-12-31",
             "accounts": [
                {"codigo": "3.01", "descricao": "...", "grupo": "DRE", "valor_brl": 1.0},
                ...
             ]},
            ...
          ]
        }

    Output shape (consumed by financials_statement adapter + dashboard):
        {
          "status": "ok", "company": "...", "period_type": "annual",
          "statement": "DRE",
          "periods": [
            {"data_fim_exerc": "2023-12-31", "meses": 12,
             "accounts": {
                "3.01": {"label": "...", "section": "DRE", "valor_brl": 1.0},
                ...
             }},
            ...
          ]
        }

    Args:
        raw: complete() result dict.
        section_fn: callable mapping codigo -> section label.
        statement_label: short label for the statement (BPA / BPP / DRE / DFC / DVA).

    Returns:
        Reshaped dict (same status as input on error, reshaped on success).
    """
    if raw.get("status") != "ok":
        return raw

    out_periods: list[dict] = []
    for p in raw.get("periods") or []:
        accounts_in = p.get("accounts") or []
        accounts_out: dict[str, dict] = {}
        for a in accounts_in:
            codigo = a.get("codigo")
            if not codigo:
                continue
            accounts_out[codigo] = {
                "label": a.get("descricao") or codigo,
                "section": section_fn(codigo),
                "valor_brl": a.get("valor_brl"),
            }
        # Period metadata: prefer data_fim_exerc, fall back to year.
        data_fim = p.get("data_fim_exerc")
        if not data_fim and p.get("year"):
            data_fim = f"{p['year']}-12-31"
        meses = p.get("meses")
        if meses is None:
            # Annual periods always have meses=12 in DFP; quarterly periods
            # carry the meses value through complete()'s _build_quarter_labels.
            meses = 12 if raw.get("period_type") == "annual" else None
        out_periods.append({
            "data_fim_exerc": data_fim,
            "meses": meses,
            "period": p.get("period"),
            "year": p.get("year"),
            "quarter": p.get("quarter"),
            "accounts": accounts_out,
        })

    return {
        "status": "ok",
        "company": raw.get("company", ""),
        "period_type": raw.get("period_type", "annual"),
        "statement": statement_label,
        "grupo_filter": raw.get("grupo_filter", statement_label),
        "periods": out_periods,
    }
