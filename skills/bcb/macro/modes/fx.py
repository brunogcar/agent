"""Mode: fx -- BCB exchange-rate dashboard (USD/BRL ptax).

[v1.3] Removed series 24369 (was NOT USD/BRL). Now computes monthly averages
from the daily series 1.
[v1.3-v2] Charts now show USD/BRL (1/rate = ~0.19, "how many dollars per
real"). KPI cards stay as BRL/USD (5.x, "how many reais per dollar" — the
common Brazilian convention). Added price_full_datasets so the range selector
buttons (Tudo/10A/5A/1A/6M/3M/1M) render correctly. Monthly chart now fetches
2 years of data (not 1) + shows all months via range selector.
[v1.7] Merged the 2 daily charts (BRL/USD + USD/BRL) into 1 chart showing
BRL/USD (the common Brazilian convention). Kept 2 separate collapsible
tables: one for BRL/USD (5.x reais per dollar), one for USD/BRL (1/rate).
Monthly chart + table also collapsible. Bumped days to 3650.

Registered as "fx" in skills.bcb.macro._registry.MODES.
"""
from __future__ import annotations

from collections import defaultdict

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import format_value, compute_stats
from skills.bcb.macro.report import (
    build_kpi_card, build_chart_section, build_table_section, build_error_section,
)

from data_sources.bcb.sgs.query_engine import series as query_series


USD_BRL_DAILY = 1


def _compute_monthly_averages(observations: list[dict], n_months: int = 24) -> list[dict]:
    """Compute monthly average USD/BRL from daily observations.

    Groups daily observations by YYYY-MM, averages the values, and returns
    the most recent ``n_months`` months as observation dicts.
    """
    by_month: dict[str, list[float]] = defaultdict(list)
    for obs in observations:
        ref_date = obs.get("ref_date", "")
        if len(ref_date) >= 7:
            month_key = ref_date[:7]
            val = obs.get("value")
            if val is not None and val > 0:
                by_month[month_key].append(val)

    monthly = []
    for month_key in sorted(by_month.keys()):
        vals = by_month[month_key]
        if vals:
            avg = sum(vals) / len(vals)
            monthly.append({"ref_date": f"{month_key}-01", "value": avg})

    if n_months > 0 and len(monthly) > n_months:
        monthly = monthly[-n_months:]
    return monthly


@register_mode(
    "fx",
    description=(
        "BCB exchange-rate dashboard: USD/BRL ptax venda diaria (1) + "
        "monthly averages computed from daily data. Charts show BRL/USD "
        "(reais per dollar). KPIs show BRL/USD (rate)."
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
    """Build the FX dashboard.

    [v1.7] Merged 2 daily charts into 1 (BRL/USD). Kept 2 collapsible tables
    (BRL/USD + USD/BRL). Monthly chart + table also collapsible. days=3650.
    """
    sections = []
    kpis = []

    # Daily USD/BRL (BRL/USD for KPI + chart, USD/BRL for second table)
    res = query_series(code=USD_BRL_DAILY, days=days)
    if res.get("status") == "ok":
        observations = res.get("observations", [])
        values = [o.get("value") for o in observations]
        stats = compute_stats(values)

        # KPI: BRL/USD (5.x — reais per dollar, Brazilian convention)
        kpis.append(build_kpi_card(
            "USD/BRL (ptax venda)", stats["last"], "R$",
            subtitle=(f"min: {format_value(stats['min'], 'R$')} | "
                      f"max: {format_value(stats['max'], 'R$')} | "
                      f"media: {format_value(stats['mean'], 'R$')}"),
        ))

        # [v1.7] Single chart: BRL/USD (reais per dollar — the common convention)
        sections.append(build_chart_section(
            f"USD/BRL diaria - ultimos {days} dias",
            observations, unit="R$",
            description=(
                "Cotacao BRL/USD (reais por dolar). Valor ~5.x = 1 dolar "
                "custa ~5 reais. Menor = real mais forte. Maior = real "
                "mais fraco."
            ),
        ))

        # [v1.7] Table 1: BRL/USD (reais per dollar) — collapsible
        sections.append(build_table_section(
            "USD/BRL diaria - tabela (BRL/USD)",
            observations, unit="R$", limit=10,
            description="Ultimas 10 cotacoes BRL/USD (reais por dolar).",
            collapsible=True,
        ))

        # [v1.7] Table 2: USD/BRL (1/rate = dollars per real) — collapsible
        inverted_obs = [
            {"ref_date": o.get("ref_date", ""),
             "value": (1.0 / o["value"]) if (o.get("value") and o["value"] > 0) else None}
            for o in observations
        ]
        sections.append(build_table_section(
            "USD/BRL diaria - tabela (USD/BRL)",
            inverted_obs, unit="", limit=10,
            description="Ultimas 10 cotacoes USD/BRL (1/ptax = dolares por real).",
            collapsible=True,
        ))
    else:
        sections.append(build_error_section("USD/BRL diaria", res.get("error", "")))
        kpis.append(build_kpi_card("USD/BRL (ptax venda)", None, "R$"))

    # Monthly USD/BRL — computed from daily data
    # [v1.7] Bumped from 730 → 3650 to show all available data (~5 years).
    res_m = query_series(code=USD_BRL_DAILY, days=3650)
    if res_m.get("status") == "ok":
        daily_obs = res_m.get("observations", [])
        monthly_obs = _compute_monthly_averages(daily_obs, n_months=60)
        if monthly_obs:
            sections.append(build_chart_section(
                "USD/BRL mensal - ultimos 60 meses",
                monthly_obs, unit="R$",
                description=(
                    "Taxa media mensal BRL/USD (reais por dolar). "
                    "Computada a partir da media das cotacoes diarias de cada mes."
                ),
            ))
            sections.append(build_table_section(
                "USD/BRL mensal - tabela",
                monthly_obs, unit="R$", limit=60,
                description="Ultimas 60 cotacoes mensais BRL/USD.",
                collapsible=True,
            ))
    else:
        sections.append(build_error_section("USD/BRL mensal", res_m.get("error", "")))

    return {
        "status":   "ok",
        "mode":     "fx",
        "kpis":     kpis,
        "sections": sections,
    }
