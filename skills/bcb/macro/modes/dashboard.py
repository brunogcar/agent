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
from datetime import datetime as _dt

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

    [v3.1] Removed _batch_last_values() (direct DB SQL query) — it bypassed
    the test mock for last_value(), causing test_dashboard_cdi_kpi_is_daily
    to fail when a real BCB DB existed. Reverted to direct last_value()
    calls (mockable, still efficient on local SQLite).
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
        (SALARIO_MIN, "Salario minimo (mensal)", "R$", 730),
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
        "days":   "int. Daily-series window. Default: 365.",
        "months": "int. Monthly-series window. Default: 24.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="dashboard")',
    ],
)
def dashboard(days: int = 365, months: int = 24) -> dict:
    """Build the multi-tab BCB macro dashboard.

    [v3] Default days=365 (was 30) and months=24 (was 12) for meaningful trends.
    """
    _t0 = _dt.now()
    print(f"[bcb.macro] Starting dashboard...", flush=True)
    print(f"[bcb.macro] Fetching rates / inflation / fx...", flush=True)
    rates_res     = _safe_call(rates_mode,     days=days)
    inflation_res = _safe_call(inflation_mode, months=months)
    fx_res        = _safe_call(fx_mode,        days=days)
    _fetch_elapsed = (_dt.now() - _t0).total_seconds()
    print(f"[bcb.macro] Data fetched ({_fetch_elapsed:.1f}s).", flush=True)

    # Top-level KPIs (rendered in the universal header above tabs).
    kpis = _build_resumo_kpis()

    # [v5] One-line section timers (ratios pattern): 5 sections.
    _SEC_TOTAL = 5
    _sec_count = 0
    _sec_t0 = _dt.now()

    # ── Section 1/5: Resumo ────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    # [v3] Build Resumo as a TABLE (not text) so the template renders it
    overview_rows = []
    for code, label in [(11, "Selic"), (12, "CDI"), (432, "Meta Selic"), (433, "IPCA"), (189, "IGP-M"), (1, "USD/BRL"), (226, "TR"), (1619, "Salario minimo")]:
        lv = last_value(code=code)
        if lv.get("status") == "ok" and lv.get("value") is not None:
            unit = lv.get("unit", "")
            val_str = format_value(lv["value"], unit)
            overview_rows.append([label, val_str, lv.get("ref_date", "-"), unit])
        else:
            overview_rows.append([label, "-", "-", ""])
    resumo_sections = [{
        "type": "table",
        "title": "Indicadores Atuais",
        "columns": ["Indicador", "Valor", "Data Ref.", "Unidade"],
        "rows": overview_rows,
    }]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Resumo ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 2/5: Juros ─────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    juros_sections = rates_res.get("sections", []) or [
        build_error_section("Juros", rates_res.get("error", "sem dados")),
    ]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Juros ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 3/5: Inflacao ──────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    inflacao_sections = inflation_res.get("sections", []) or [
        build_error_section("Inflacao", inflation_res.get("error", "sem dados")),
    ]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Inflacao ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 4/5: Cambio ────────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    cambio_sections = fx_res.get("sections", []) or [
        build_error_section("Cambio", fx_res.get("error", "sem dados")),
    ]
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Cambio ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    # ── Section 5/5: Atividade ─────────────────────────────────────
    _sec_count += 1
    _s_t0 = _dt.now()
    atividade_sections = _build_atividade_sections()
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    _sec_elapsed = (_dt.now() - _sec_t0).total_seconds()
    print(f"  [sections] {_sec_count}/{_SEC_TOTAL} Atividade ({_s_elapsed:.1f}s, total {_sec_elapsed:.1f}s)", flush=True)

    tabs = [
        {"name": "Resumo",    "group": "Resumo",      "sections": resumo_sections},
        {"name": "Juros",     "group": "Indicadores", "sections": juros_sections},
        {"name": "Inflacao",  "group": "Indicadores", "sections": inflacao_sections},
        {"name": "Cambio",    "group": "Indicadores", "sections": cambio_sections},
        {"name": "Atividade", "group": "Indicadores", "sections": atividade_sections},
    ]

    # Surface sub-mode errors as a note (but keep status=ok so the dashboard
    # still renders - mirrors CVM financials graceful-degradation contract).
    errors = []
    for name, res in [("rates", rates_res), ("inflation", inflation_res),
                       ("fx", fx_res)]:
        if res.get("status") not in ("ok", None):
            errors.append(f"{name}: {res.get('error', '')}")

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[bcb.macro] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
    return {
        "status": "ok",
        "mode":   "dashboard",
        "tabs":   tabs,
        "kpis":   kpis,
        "errors": errors,
    }
