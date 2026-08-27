"""Mode: real_returns -- BCB real-interest-rate dashboard (Fisher equation).

Real return = (1 + nominal) / (1 + inflation) - 1

  - nominal   = Selic annualized (series 11, daily % a.d. x 252) -- % a.a.
  - inflation = IPCA 12-month acumulado (series 433, monthly %, sum last 12)

The Fisher equation gives the ex-post real return: what a Selic investor
actually earned after inflation. A negative real rate means inflation
outpaced nominal Selic -- capital is being eroded in real terms.

[v1.4] IPCA 12m acumulado is recomputed monthly (rolling sum of the last
12 monthly variations). The Selic daily series is joined to the IPCA
acumulado of its month: every day in a given month uses the same IPCA
figure, so the real-rate chart moves day-by-day with Selic but steps
month-by-month with IPCA.
[v1.7] Table now shows MONTHLY data (not daily) — daily changes are not
important for real returns. Table is collapsible=True.

Registered as "real_returns" in skills.bcb.macro._registry.MODES.
"""
from __future__ import annotations

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import annualize_rate, format_value, format_date, group_by_month
from skills.bcb.macro.report import (
    build_kpi_card, build_chart_section, build_table_section, build_error_section,
)

# Import the query_engine functions the dashboard calls. The test suite
# monkeypatches these module-level names, so they MUST be imported here
# (not inside the function body).
from data_sources.bcb.sgs.query_engine import series as query_series, last_value


# Series codes (defined in SERIES_CATALOG).
SELIC_DAILY = 11
IPCA_MENSAL = 433


def _ipca_12m_acumulado(monthly_obs: list[dict]) -> float | None:
    """Sum of the last 12 monthly IPCA variations.

    Input: list of {"ref_date", "value"} sorted ascending. Returns None if
    fewer than 12 valid observations. This is the standard IPCA 12m
    acumulado calculation (BCB convention: simple sum, not geometric).
    """
    vals = [o.get("value") for o in monthly_obs if o.get("value") is not None]
    if len(vals) < 12:
        return None
    return sum(vals[-12:])


def _ipca_acum_by_month(monthly_obs: list[dict]) -> dict[str, float | None]:
    """Map each YYYY-MM to its rolling 12m IPCA acumulado.

    For each monthly observation at index i (sorted ascending), the 12m
    acumulado is the sum of values[i-11..i]. We map by YYYY-MM (not the
    full ref date) so daily Selic observations can be joined by month.
    """
    out: dict[str, float | None] = {}
    for i, obs in enumerate(monthly_obs):
        rd = obs.get("ref_date", "")
        if len(rd) < 7:
            continue
        ym = rd[:7]  # YYYY-MM
        window = monthly_obs[max(0, i - 11): i + 1]
        nums = [w.get("value") for w in window if w.get("value") is not None]
        out[ym] = sum(nums) if len(nums) >= 12 else None
    return out


@register_mode(
    "real_returns",
    description=(
        "BCB real-interest-rate dashboard (Fisher equation). Real = "
        "(1+nominal)/(1+inflacao)-1. Nominal = Selic anualizada (serie 11). "
        "Inflacao = IPCA 12m acumulado (serie 433)."
    ),
    params={
        "days":   "int. Daily-series window (Selic). Default: 365.",
        "months": "int. Monthly-series window (IPCA). Default: 24 (need >=12 for acumulado).",
    },
    include_in_all=False,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="real_returns")',
        'skill(domain="bcb", sub_domain="macro", mode="real_returns", params=\'{"days":180}\')',
    ],
)
def real_returns(days: int = 365, months: int = 24) -> dict:
    """Build the real-interest-rate dashboard.

    [v1.7] Table shows monthly data (not daily). Collapsible=True.
    """
    sections: list[dict] = []
    kpis: list[dict] = []

    # -- 1. Fetch Selic daily + IPCA monthly --
    selic_res = query_series(code=SELIC_DAILY, days=days)
    # IPCA needs at least 12 observations for the 12m acumulado. months=24
    # returns the most recent 24 monthly observations.
    ipca_res = query_series(code=IPCA_MENSAL, days=max(months, 13))

    if selic_res.get("status") != "ok":
        sections.append(build_error_section(
            "Selic diaria", selic_res.get("error", "sem dados")))
        kpis.append(build_kpi_card("Taxa Real (atual)", None, "% a.a."))
        return {"status": "ok", "mode": "real_returns",
                "kpis": kpis, "sections": sections}

    if ipca_res.get("status") != "ok":
        sections.append(build_error_section(
            "IPCA mensal", ipca_res.get("error", "sem dados")))
        kpis.append(build_kpi_card("Taxa Real (atual)", None, "% a.a."))
        return {"status": "ok", "mode": "real_returns",
                "kpis": kpis, "sections": sections}

    selic_obs = selic_res.get("observations", [])
    ipca_obs = ipca_res.get("observations", [])

    if not selic_obs or not ipca_obs:
        sections.append(build_error_section(
            "Retorno Real", "observacoes insuficientes"))
        kpis.append(build_kpi_card("Taxa Real (atual)", None, "% a.a."))
        return {"status": "ok", "mode": "real_returns",
                "kpis": kpis, "sections": sections}

    # -- 2. Build YYYY-MM -> IPCA 12m acumulado map --
    ipca_acum_by_month = _ipca_acum_by_month(ipca_obs)

    # -- 3. Compute real rate per Selic daily observation --
    # real = (1 + selic_anualizada/100) / (1 + ipca_12m_acum/100) - 1
    # Both rates are in percent; convert to decimal for the Fisher formula.
    real_obs: list[dict] = []
    for obs in selic_obs:
        rd = obs.get("ref_date", "")
        if not rd or len(rd) < 7:
            continue
        ym = rd[:7]
        nominal_daily = obs.get("value")
        if nominal_daily is None:
            continue
        nominal_annual = annualize_rate(nominal_daily)  # % a.a.
        ipca_12m = ipca_acum_by_month.get(ym)
        if ipca_12m is None:
            continue
        # Fisher equation (percent -> decimal -> percent).
        real_dec = (1.0 + nominal_annual / 100.0) / (1.0 + ipca_12m / 100.0) - 1.0
        real_pct = real_dec * 100.0  # back to percent
        real_obs.append({
            "ref_date": rd,
            "value": real_pct,
            "nominal": nominal_annual,
            "inflation": ipca_12m,
        })

    if not real_obs:
        sections.append(build_error_section(
            "Retorno Real", "IPCA 12m acumulado indisponivel para o periodo"))
        kpis.append(build_kpi_card("Taxa Real (atual)", None, "% a.a."))
        return {"status": "ok", "mode": "real_returns",
                "kpis": kpis, "sections": sections}

    # -- 4. KPI: current real rate (latest) --
    latest_real = real_obs[-1].get("value")
    latest_nominal = real_obs[-1].get("nominal")
    latest_inflation = real_obs[-1].get("inflation")
    kpis.append(build_kpi_card(
        "Taxa Real (atual)", latest_real, "% a.a.",
        subtitle=(
            f"nominal: {format_value(latest_nominal, '% a.a.')} | "
            f"IPCA 12m: {format_value(latest_inflation, '%')}"
        ),
    ))

    # -- 5. Real-rate chart over time (daily) --
    sections.append(build_chart_section(
        "Retorno Real - evolucao",
        real_obs,
        unit="% a.a.",
        description=(
            "Taxa real de juros (equacao de Fisher) usando Selic anualizada "
            "e IPCA 12m acumulado. Valores negativos indicam que a inflacao "
            "superou a taxa nominal -- o capital perde poder de compra."
        ),
    ))

    # -- 6. Real-rate table (monthly, last 24 months) --
    # [v1.7] Group by month (last value per month) instead of daily.
    # Daily changes are not important for real returns — monthly view is
    # more meaningful and easier to read.
    monthly_real = group_by_month(real_obs)
    # Also group nominal + inflation by month for the table.
    monthly_nominal = group_by_month(
        [{"ref_date": o["ref_date"], "value": o.get("nominal")} for o in real_obs])
    monthly_inflation = group_by_month(
        [{"ref_date": o["ref_date"], "value": o.get("inflation")} for o in real_obs])

    # Build merged monthly rows: [{ref_date, value, nominal, inflation}]
    monthly_merged = []
    for m in monthly_real:
        ref = m["ref_date"]
        nominal_val = next((mn["value"] for mn in monthly_nominal if mn["ref_date"] == ref), None)
        inflation_val = next((mi["value"] for mi in monthly_inflation if mi["ref_date"] == ref), None)
        monthly_merged.append({
            "ref_date": ref,
            "value": m["value"],
            "nominal": nominal_val,
            "inflation": inflation_val,
        })

    # Build table rows (last 24 months, sorted DESC = newest first)
    table_rows = []
    last_24 = sorted(monthly_merged[-24:], key=lambda o: o.get("ref_date", ""),
                     reverse=True)
    for o in last_24:
        ref = o.get("ref_date", "")
        real_val = o.get("value")
        real_str = format_value(real_val, "% a.a.")
        # Add red color for negative real rates.
        real_cell = {"text": real_str}
        if real_val is not None:
            real_cell["data-value"] = f"{real_val:.6f}"
            if real_val < 0:
                real_cell["color"] = "#ef4444"
        table_rows.append([
            {"text": format_date(ref), "data-value": ref} if ref else {"text": "-"},
            real_cell,
            format_value(o.get("nominal"), "% a.a."),
            format_value(o.get("inflation"), "%"),
        ])
    sections.append({
        "type":        "table",
        "title":       "Retorno Real - ultimos 24 meses",
        "unit":        "% a.a.",
        "description": "Taxa real, nominal (Selic anualizada) e IPCA 12m acumulado (mensal).",
        "columns":     ["Data", "Taxa Real", "Nominal", "IPCA 12m"],
        "rows":        table_rows,
        "column_align": ["left", "right", "right", "right"],
        "sortable":     True,
        "default_sort": {"column": 0, "direction": "desc"},
        "sort_types":   ["text", "number", "text", "text"],
        "negative_red": True,
        "collapsible":  True,
    })

    return {
        "status":   "ok",
        "mode":     "real_returns",
        "kpis":     kpis,
        "sections": sections,
        # Surface the latest values for the dashboard composer / debugging.
        "latest": {
            "real":      latest_real,
            "nominal":   latest_nominal,
            "inflation": latest_inflation,
            "ref_date":  real_obs[-1].get("ref_date", ""),
        },
    }
