"""Mode: fx -- BCB exchange-rate dashboard (USD/BRL ptax).

[v1.3] Removed series 24369 (was NOT USD/BRL). Now computes monthly averages
from the daily series 1.
[v1.3-v2] Charts now show USD/BRL (1/rate = ~0.19, "how many dollars per
real"). KPI cards stay as BRL/USD (5.x, "how many reais per dollar" — the
common Brazilian convention). Added price_full_datasets so the range selector
buttons (Tudo/10A/5A/1A/6M/3M/1M) render correctly. Monthly chart now fetches
2 years of data (not 1) + shows all months via range selector.

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


def _invert_values(observations: list[dict]) -> list[dict]:
    """Convert BRL/USD values (5.x) to USD/BRL (1/value = ~0.19).

    Returns a new list with inverted values. None/zero values are kept as-is.
    """
    out = []
    for o in observations:
        v = o.get("value")
        new_v = (1.0 / v) if (v is not None and v > 0) else None
        out.append({"ref_date": o.get("ref_date", ""), "value": new_v})
    return out


@register_mode(
    "fx",
    description=(
        "BCB exchange-rate dashboard: USD/BRL ptax venda diaria (1) + "
        "monthly averages computed from daily data. Charts show USD/BRL "
        "(1/rate). KPIs show BRL/USD (rate)."
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

    [v1.3-v2] Charts show USD/BRL (1/rate = ~0.19, dollars per real).
    KPI cards show BRL/USD (rate = ~5.x, reais per dollar).
    Both daily + monthly charts have range selector buttons.
    Monthly chart fetches 2 years (730 days) of daily data + groups by month.
    """
    sections = []
    kpis = []

    # Daily USD/BRL (BRL/USD for KPI, inverted for chart)
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

        # Chart: USD/BRL (1/rate = ~0.19 — dollars per real)
        inverted_obs = _invert_values(observations)
        sections.append(build_chart_section(
            f"USD/BRL diaria - ultimos {days} dias",
            inverted_obs, unit="",
            description=(
                "Cotacao USD/BRL (1/ptax = dolares por real). "
                "Valor ~0.19 = 1 real compra ~0.19 dolares. "
                "Menor = real mais fraco. Maior = real mais forte."
            ),
        ))
        sections.append(build_table_section(
            "USD/BRL diaria - tabela",
            inverted_obs, unit="", limit=10,
            description="Ultimas 10 cotacoes USD/BRL (1/ptax).",
        ))
    else:
        sections.append(build_error_section("USD/BRL diaria", res.get("error", "")))
        kpis.append(build_kpi_card("USD/BRL (ptax venda)", None, "R$"))

    # Monthly USD/BRL — computed from daily data, inverted for chart
    res_m = query_series(code=USD_BRL_DAILY, days=730)
    if res_m.get("status") == "ok":
        daily_obs = res_m.get("observations", [])
        monthly_obs = _compute_monthly_averages(daily_obs, n_months=24)
        if monthly_obs:
            # Invert for USD/BRL chart (1/avg_rate)
            monthly_inverted = _invert_values(monthly_obs)
            sections.append(build_chart_section(
                "USD/BRL mensal - ultimos 24 meses",
                monthly_inverted, unit="",
                description=(
                    "Taxa media mensal USD/BRL (1/ptax media = dolares por real). "
                    "Computada a partir da media das cotacoes diarias de cada mes."
                ),
            ))
            sections.append(build_table_section(
                "USD/BRL mensal - tabela",
                monthly_inverted, unit="", limit=24,
                description="Ultimas 24 cotacoes mensais USD/BRL (1/ptax media).",
            ))
    else:
        sections.append(build_error_section("USD/BRL mensal", res_m.get("error", "")))

    return {
        "status":   "ok",
        "mode":     "fx",
        "kpis":     kpis,
        "sections": sections,
    }
