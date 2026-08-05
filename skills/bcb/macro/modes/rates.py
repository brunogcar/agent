"""Mode: rates -- BCB interest-rate dashboard (Selic / CDI / TR / Copom target).

Queries SGS series 11 (Selic diaria), 12 (CDI diaria), 226 (TR), 432 (Meta
Copom), 4389 (Selic acumulada mes base 252) and shapes them into KPI cards
+ a multi-series chart + a per-series table.

Daily % a.d. rates are annualized to % a.a. (x 252) for the KPI display -
the raw observations stay in their original unit.

Registered as "rates" in skills.bcb.macro._registry.MODES.
"""
from __future__ import annotations

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import annualize_rate, format_value
from skills.bcb.macro.report import (
    build_kpi_card, build_chart_section, build_table_section, build_error_section,
)

# Import the query_engine functions the dashboard calls. The test suite
# monkeypatches these module-level names, so they MUST be imported here
# (not inside the function body).
from data_sources.bcb.sgs.query_engine import series as query_series, last_value


# Series codes used by this mode (defined in SERIES_CATALOG).
SELIC_DAILY   = 11
CDI_DAILY     = 12
TR_DAILY      = 226
META_COPOM    = 432
SELIC_ACUM    = 4389


@register_mode(
    "rates",
    description=(
        "BCB interest-rate dashboard: Selic diaria, CDI diaria, TR, Meta Copom, "
        "Selic acumulada mes. KPI cards annualize % a.d. -> % a.a. (x 252)."
    ),
    params={
        "days": "int. Number of most-recent observations per series. Default: 30.",
    },
    include_in_all=True,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="rates")',
        'skill(domain="bcb", sub_domain="macro", mode="rates", params=\'{"days":90}\')',
    ],
)
def rates(days: int = 30) -> dict:
    """Build the interest-rates dashboard."""
    sections = []
    kpis = []

    for code, label, unit in [
        (SELIC_DAILY, "Selic diaria",          "% a.d."),
        (CDI_DAILY,   "CDI diaria",            "% a.d."),
        (TR_DAILY,    "TR (Taxa Referencial)", "%"),
        (META_COPOM,  "Meta Selic Copom",      "% a.a."),
        (SELIC_ACUM,  "Selic acumulada mes (base 252)", "% a.a."),
    ]:
        res = query_series(code=code, days=days)
        if res.get("status") != "ok":
            sections.append(build_error_section(label, res.get("error", "")))
            kpis.append(build_kpi_card(label, None, unit))
            continue

        observations = res.get("observations", [])
        values = [o.get("value") for o in observations]

        # KPI: latest value, annualized if % a.d.
        latest = values[-1] if values else None
        if unit == "% a.d." and latest is not None:
            kpis.append(build_kpi_card(
                f"{label} (anualizada)", annualize_rate(latest), "% a.a.",
                subtitle=f"ultimo: {format_value(latest, '% a.d.')}",
            ))
        else:
            kpis.append(build_kpi_card(label, latest, unit))

        sections.append(build_chart_section(
            f"{label} - ultimos {days} dias", observations, unit=unit,
            description=f"Variacao diaria de {label} nos ultimos {days} dias.",
        ))
        sections.append(build_table_section(
            f"{label} - tabela", observations, unit=unit, limit=10,
            description="Ultimas 10 observacoes.",
        ))

    return {
        "status":   "ok",
        "mode":     "rates",
        "kpis":     kpis,
        "sections": sections,
    }
