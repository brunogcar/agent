"""Mode: dashboard -- multi-tab BCB macro dashboard (thin composition mode).

Composes the rates / inflation / fx modes into a single 5-tab payload:
  - Resumo      (text overview)
  - Juros       (rates mode sections)
  - Inflacao    (inflation mode sections)
  - Cambio      (fx mode sections)
  - Atividade   (PIB + Salario minimo - thin, just last values + table)

When a sub-mode fails, the dashboard still returns status=ok with the failed
tab containing an error section - this mirrors the CVM financials dashboard
graceful-degradation contract.

[v3] Fixes from v2:
  - Tab field is `name` (was `label`) - the dashboard.html template reads
    tab.name, not tab.label.
  - Top-level `kpis` array (was: per-tab `kpis`). The template renders KPIs
    in a universal header above the tabs, not per-tab.
  - CDI KPI shows the DAILY rate (% a.d.), NOT annualized (per user request:
    "on top boxes, display CDI not anualizado, but current for the day").
    Selic KPI stays annualized.
  - Chart sections emit a Chart.js config in `chart_data` (was: separate
    `labels` + `values` arrays that the template ignored).
  - Table rows are a list of lists (was: list of dicts).

Registered as "dashboard" in skills.bcb.macro._registry.MODES.
"""
from __future__ import annotations

from skills.bcb.macro._registry import register_mode
from skills.bcb.macro.helpers import format_value, annualize_rate
from skills.bcb.macro.report import (
    build_kpi_card, build_chart_section, build_table_section,
    build_text_section, build_error_section,
)
from skills.bcb.macro.modes.rates import rates as rates_mode
from skills.bcb.macro.modes.inflation import inflation as inflation_mode
from skills.bcb.macro.modes.fx import fx as fx_mode

from data_sources.bcb.sgs.query_engine import last_value, series as query_series


# Series used in the Resumo tab KPI cards + the Atividade tab.
SELIC_DAILY = 11
CDI_DAILY   = 12
IPCA_MENSAL = 433
USD_BRL     = 1
PIB_NOMINAL = 4380
SALARIO_MIN = 1619


def _safe_call(fn, **kwargs):
    """Call a sub-mode and return its dict, or an error payload on failure."""
    try:
        return fn(**kwargs)
    except Exception as e:
        return {"status": "error", "error": str(e),
                "kpis": [], "sections": []}


def _build_resumo_kpis() -> list[dict]:
    """Build the 4 top-level KPI cards.

    [v3] CDI is shown as the DAILY rate (% a.d.) per user request - NOT
    annualized. Selic stays annualized (% a.a.). IPCA shows the latest
    monthly variation. USD/BRL shows the latest ptax venda.
    """
    kpis = []

    # Selic - annualized (% a.a.)
    selic = last_value(code=SELIC_DAILY)
    if selic.get("status") == "ok" and selic.get("value") is not None:
        kpis.append(build_kpi_card(
            "Selic (anualizada)", annualize_rate(selic["value"]), "% a.a.",
            subtitle=f"diaria: {format_value(selic['value'], '% a.d.')}",
        ))
    else:
        kpis.append(build_kpi_card("Selic (anualizada)", None, "% a.a."))

    # CDI - DAILY rate (% a.d.), NOT annualized (per user request)
    cdi = last_value(code=CDI_DAILY)
    if cdi.get("status") == "ok" and cdi.get("value") is not None:
        kpis.append(build_kpi_card(
            "CDI (diaria)", cdi["value"], "% a.d.",
            subtitle=f"ref: {cdi.get('ref_date', '')}",
        ))
    else:
        kpis.append(build_kpi_card("CDI (diaria)", None, "% a.d."))

    # IPCA - latest monthly variation (%)
    ipca = last_value(code=IPCA_MENSAL)
    if ipca.get("status") == "ok" and ipca.get("value") is not None:
        kpis.append(build_kpi_card(
            "IPCA (mes)", ipca["value"], "%",
            subtitle=f"ref: {ipca.get('ref_date', '')}",
        ))
    else:
        kpis.append(build_kpi_card("IPCA (mes)", None, "%"))

    # USD/BRL - latest ptax venda (R$)
    usd = last_value(code=USD_BRL)
    if usd.get("status") == "ok" and usd.get("value") is not None:
        kpis.append(build_kpi_card(
            "USD/BRL (ptax)", usd["value"], "R$",
            subtitle=f"ref: {usd.get('ref_date', '')}",
        ))
    else:
        kpis.append(build_kpi_card("USD/BRL (ptax)", None, "R$"))

    return kpis


def _build_atividade_sections() -> list[dict]:
    """Build the Atividade tab sections: PIB + Salario minimo.

    [v4] Salario minimo shown annually (query 2 years of monthly data,
    display as chart + table). PIB shown quarterly.
    """
    sections = []

    for code, label, unit, days in [
        (PIB_NOMINAL, "PIB nominal trimestral", "R$ mil", 730),
        (SALARIO_MIN, "Salario minimo (anual)", "R$", 730),
    ]:
        res = query_series(code=code, days=days)
        if res.get("status") == "ok":
            observations = res.get("observations", [])
            sections.append(build_chart_section(
                f"{label} - evolucao", observations, unit=unit,
                description=f"Ultimas observacoes de {label}.",
            ))
            sections.append(build_table_section(
                f"{label} - tabela", observations, unit=unit, limit=8,
                description="Dados brutos.",
            ))
        else:
            sections.append(build_error_section(label, res.get("error", "")))

    return sections


@register_mode(
    "dashboard",
    description=(
        "BCB macro dashboard - 5 tabs: Resumo (KPIs), Juros, Inflacao, Cambio, "
        "Atividade. Composes rates + inflation + fx modes. KPIs at top level."
    ),
    params={
        "days":   "int. Daily-series window. Default: 30.",
        "months": "int. Monthly-series window. Default: 12.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="dashboard")',
    ],
)
def dashboard(days: int = 30, months: int = 12) -> dict:
    """Build the multi-tab BCB macro dashboard."""
    rates_res     = _safe_call(rates_mode,     days=days)
    inflation_res = _safe_call(inflation_mode, months=months)
    fx_res        = _safe_call(fx_mode,        days=days)

    # Top-level KPIs (rendered in the universal header above tabs).
    kpis = _build_resumo_kpis()

    # Build Visao geral with actual latest values
    overview_lines = []
    for code, label in [(11, "Selic"), (12, "CDI"), (432, "Meta Selic"), (433, "IPCA"), (189, "IGP-M"), (1, "USD/BRL"), (226, "TR"), (1619, "Salario minimo")]:
        lv = last_value(code=code)
        if lv.get("status") == "ok" and lv.get("value") is not None:
            val_str = format_value(lv["value"], lv.get("unit", ""))
            overview_lines.append(f"- {label}: {val_str} (ref: {lv.get('ref_date', '-')})")
        else:
            overview_lines.append(f"- {label}: indisponivel")

    tabs = [
        {
            "name":     "Resumo",
            "group":    "Resumo",
            "sections": [
                build_text_section(
                    "Visao geral",
                    "Indicadores macroeconomicos do Banco Central do Brasil (BCB SGS).\n\n"
                    + "\n".join(overview_lines)
                    + "\n\nAtualize via data_source(domain='bcb', sub_domain='sgs', mode='sync_all').",
                ),
            ],
        },
        {
            "name":     "Juros",
            "group":    "Indicadores",
            "sections": rates_res.get("sections", []) or [
                build_error_section("Juros", rates_res.get("error", "sem dados")),
            ],
        },
        {
            "name":     "Inflacao",
            "group":    "Indicadores",
            "sections": inflation_res.get("sections", []) or [
                build_error_section("Inflacao", inflation_res.get("error", "sem dados")),
            ],
        },
        {
            "name":     "Cambio",
            "group":    "Indicadores",
            "sections": fx_res.get("sections", []) or [
                build_error_section("Cambio", fx_res.get("error", "sem dados")),
            ],
        },
        {
            "name":     "Atividade",
            "group":    "Indicadores",
            "sections": _build_atividade_sections(),
        },
    ]

    # Surface sub-mode errors as a note (but keep status=ok so the dashboard
    # still renders - mirrors CVM financials graceful-degradation contract).
    errors = []
    for name, res in [("rates", rates_res), ("inflation", inflation_res),
                       ("fx", fx_res)]:
        if res.get("status") not in ("ok", None):
            errors.append(f"{name}: {res.get('error', '')}")

    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
        "errors": errors,
    }
