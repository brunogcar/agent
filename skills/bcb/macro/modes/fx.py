"""Mode: fx -- BCB exchange-rate dashboard (USD/BRL ptax).

Queries SGS series 1 (USD/BRL ptax venda diaria) and 24369 (USD/BRL ptax
mensal media) and shapes them into KPI cards + chart + table.

Registered as "fx" in skills.bcb.macro._registry.MODES.
"""
from __future__ import annotations

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import format_value, compute_stats
from skills.bcb.macro.report import (
    build_kpi_card, build_chart_section, build_table_section, build_error_section,
)

from data_sources.bcb.sgs.query_engine import series as query_series, last_value


USD_BRL_DAILY   = 1
USD_BRL_MONTHLY = 24369


@register_mode(
    "fx",
    description=(
        "BCB exchange-rate dashboard: USD/BRL ptax venda diaria (1) + "
        "USD/BRL ptax mensal media (24369)."
    ),
    params={
        "days": "int. Number of most-recent daily observations. Default: 30.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="fx")',
        'skill(domain="bcb", sub_domain="macro", mode="fx", params=\'{"days":90}\')',
    ],
)
def fx(days: int = 30) -> dict:
    """Build the FX dashboard."""
    sections = []
    kpis = []

    # Daily USD/BRL
    res = query_series(code=USD_BRL_DAILY, days=days)
    if res.get("status") == "ok":
        observations = res.get("observations", [])
        values = [o.get("value") for o in observations]
        stats = compute_stats(values)
        kpis.append(build_kpi_card(
            "USD/BRL (ptax venda)", stats["last"], "R$",
            subtitle=(f"min: {format_value(stats['min'], 'R$')} | "
                      f"max: {format_value(stats['max'], 'R$')} | "
                      f"media: {format_value(stats['mean'], 'R$')}"),
        ))
        sections.append(build_chart_section(
            f"USD/BRL diaria - ultimos {days} dias", observations, unit="R$",
            description=f"Cotacao USD/BRL ptax venda nos ultimos {days} dias.",
        ))
        sections.append(build_table_section(
            "USD/BRL diaria - tabela", observations, unit="R$", limit=10,
            description="Ultimas 10 cotacoes.",
        ))
    else:
        sections.append(build_error_section("USD/BRL diaria", res.get("error", "")))
        kpis.append(build_kpi_card("USD/BRL (ptax venda)", None, "R$"))

    # Monthly USD/BRL
    res_m = query_series(code=USD_BRL_MONTHLY, days=365)
    if res_m.get("status") == "ok":
        observations_m = res_m.get("observations", [])
        sections.append(build_chart_section(
            "USD/BRL mensal - ultimos 12 meses", observations_m, unit="R$",
            description="Taxa media mensal USD/BRL ptax.",
        ))
        sections.append(build_table_section(
            "USD/BRL mensal - tabela", observations_m, unit="R$", limit=12,
            description="Ultimas 12 cotacoes mensais.",
        ))
    else:
        sections.append(build_error_section("USD/BRL mensal", res_m.get("error", "")))

    return {
        "status":   "ok",
        "mode":     "fx",
        "kpis":     kpis,
        "sections": sections,
    }
