"""Mode: inflation -- BCB inflation dashboard (IPCA / IGP-M).

Queries SGS series 433 (IPCA mensal) and 189 (IGP-M mensal) and shapes them
into KPI cards (latest monthly variation + rolling 12-month acumulado) +
a per-series chart + table.

Registered as "inflation" in skills.bcb.macro._registry.MODES.
"""
from __future__ import annotations

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import format_value, accumulate_12m
from skills.bcb.macro.report import (
    build_kpi_card, build_chart_section, build_table_section, build_error_section,
)

from data_sources.bcb.sgs.query_engine import series as query_series


IPCA_MENSAL = 433
IGPM_MENSAL = 189


@register_mode(
    "inflation",
    description=(
        "BCB inflation dashboard: IPCA mensal (433) + IGP-M mensal (189). "
        "KPIs show latest monthly variation + rolling 12-month acumulado."
    ),
    params={
        "months": "int. Number of most-recent monthly observations. Default: 12.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="inflation")',
        'skill(domain="bcb", sub_domain="macro", mode="inflation", params=\'{"months":24}\')',
    ],
)
def inflation(months: int = 12) -> dict:
    """Build the inflation dashboard."""
    sections = []
    kpis = []

    for code, label in [(IPCA_MENSAL, "IPCA mensal"), (IGPM_MENSAL, "IGP-M mensal")]:
        # Use days = months * 31 so the most-recent-N query returns enough
        # monthly observations (monthly series have ~1 row per month, but
        # the query engine filters by `days` which is a row-count cap).
        res = query_series(code=code, days=months * 31)
        if res.get("status") != "ok":
            sections.append(build_error_section(label, res.get("error", "")))
            kpis.append(build_kpi_card(label, None, "%"))
            continue

        observations = res.get("observations", [])
        # Compute rolling 12-month acumulado (sum of last 12 monthly values).
        enriched = accumulate_12m(observations)
        latest = enriched[-1] if enriched else {}
        acum_12m = latest.get("acum_12m")

        kpis.append(build_kpi_card(
            label, latest.get("value"), "%",
            subtitle=(f"acum 12m: {format_value(acum_12m, '%')}"
                      if acum_12m is not None else "acum 12m: -"),
        ))

        sections.append(build_chart_section(
            f"{label} - variacao mensal", observations, unit="%",
            description=f"Variacao mensal do {label}.",
        ))
        sections.append(build_table_section(
            f"{label} - acumulado 12 meses",
            [{"ref_date": r["ref_date"], "value": r.get("acum_12m")}
             for r in enriched],
            unit="%", limit=12,
            description="Acumulado nos ultimos 12 meses (rolling sum).",
        ))

    return {
        "status":   "ok",
        "mode":     "inflation",
        "kpis":     kpis,
        "sections": sections,
    }
