"""Mode: dfc -- Demonstração dos Fluxos de Caixa (Cash Flow Statement).

Thin wrapper over `complete(grupo="DFC_MI")` that reshapes the per-period
accounts list into a `accounts: {codigo: {label, section, valor_brl}}` dict
keyed by account code, with a `section` field derived from the codigo
prefix (Operações / Investimento / Financiamento).

Default: latest annual period (periods=1).

Registered as "dfc" in skills.cvm.financials._registry.MODES via the
@register_mode decorator. Auto-discovered by __init__.py.
"""
from __future__ import annotations

from skills.cvm.financials._registry import register_mode
from skills.cvm.financials.modes.complete import complete
from skills.cvm.financials.modes._statement_sections import (
    dfc_section_for, reshape_statement_periods,
)


@register_mode(
    "dfc",
    description=(
        "Demonstração dos Fluxos de Caixa (DFC) — cash flow statement. "
        "Default period=annual, periods=1 (latest)."
    ),
    params={
        "company":     "str. Required.",
        "period":      "str. 'annual' (default) or 'quarterly'.",
        "consolidado": "int. Default: 1.",
        "periods":     "int. Default: 1 (annual) or 4 (quarterly).",
    },
    include_in_all=False,
    examples=[
        'skill(domain="cvm", sub_domain="financials", mode="dfc", params=\'{"company":"PETR4"}\')',
    ],
)
def dfc(
    company: str = "",
    period: str = "annual",
    consolidado: int = 1,
    periods: int | None = None,
) -> dict:
    """Demonstração dos Fluxos de Caixa (DFC) — cash flow statement.

    Args:
        company: Ticker, name, or CNPJ. Required.
        period: "annual" (default) or "quarterly".
        consolidado: 1=consolidated (default), 0=individual.
        periods: Number of periods. Default 1 (annual) or 4 (quarterly).

    Returns:
        ``{"status": "ok", "company": ..., "period_type": ..., "periods": [...]}``
        where each period has ``accounts: {codigo: {label, section, valor_brl}}``.
    """
    if not company:
        return {"status": "error", "error": "company is required"}

    if periods is None:
        periods = 1 if period == "annual" else 4

    # DFC has two method variants in CVM: DFC_MI (indirect) and DFC_MD (direct).
    # The complete() mode's grupo filter only accepts the registered names in
    # KEY_CODES_BY_GRUPO, which includes DFC_MI. DFC_MD codes are limited to
    # the D&A fallback paths in _extract_metrics (financials/metrics.py).
    raw = complete(company=company, period=period, grupo="DFC_MI",
                   consolidado=consolidado, periods=periods)
    if raw.get("status") != "ok":
        return raw

    return reshape_statement_periods(raw, section_fn=dfc_section_for,
                                     statement_label="DFC")
