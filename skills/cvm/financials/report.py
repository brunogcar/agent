"""skills/cvm/financials/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape data into the multi-tab payload (Overview / DRE / Balanço / DFC /
Ratios).

Each builder takes plain dicts (latest_annual_period, quarterly_periods,
ratios_payload, ...) and returns a section/tab dict ready for tab assembly.
Keeping these helpers separate from modes/dashboard.py keeps the dashboard
mode file under 300 lines and makes the section layout reusable should a
future mode want to embed (e.g.) just the DRE tab.

Public functions:
  - annual_metric         : safe metric accessor from latest annual period.
  - annual_ratio          : safe ratio accessor from latest annual period.
  - build_overview_kpis   : 6 KPI cards for the Overview tab.
  - build_overview_sections : Overview tab sections (kpis + freshness).
  - build_dre_sections    : DRE tab sections (latest annual + quarterly trend).
  - build_balanco_section : Balanço tab section (Ativo + Passivo).
  - build_dfc_sections    : DFC tab sections (latest annual + quarterly trend).
  - build_ratios_section  : Ratios tab section (categorized ratio grid).
"""
from __future__ import annotations

from typing import Any


# ── Safe accessors ───────────────────────────────────────────────────────────

def annual_metric(latest_annual_period: dict | None, name: str) -> float | None:
    """Pull a metric from the latest annual period safely.

    Returns None when latest_annual_period is None or the metric is missing.
    """
    if not latest_annual_period:
        return None
    return (latest_annual_period.get("metrics") or {}).get(name)


def annual_ratio(latest_annual_period: dict | None, name: str) -> float | None:
    """Pull a ratio from the latest annual period safely.

    Returns None when latest_annual_period is None or the ratio is missing.
    """
    if not latest_annual_period:
        return None
    return (latest_annual_period.get("ratios") or {}).get(name)


# ── Tab 1: Overview ──────────────────────────────────────────────────────────

def build_overview_kpis(
    latest_annual_period: dict | None,
    roe_val: float | None,
    net_debt_ebitda_val: float | None,
) -> list[dict]:
    """Build the 6 KPI cards for the Overview tab.

    The KPI labels + units are fixed per the dashboard spec:
      Receita Líquida / EBITDA / Lucro Líquido (BRL),
      Margem EBITDA (ratio),
      ROE (ratio),
      Dívida Líquida/EBITDA (x).
    """
    return [
        {"label": "Receita Líquida",
         "value": annual_metric(latest_annual_period, "receita_liquida"),
         "unit": "BRL"},
        {"label": "EBITDA",
         "value": annual_metric(latest_annual_period, "ebitda"),
         "unit": "BRL"},
        {"label": "Lucro Líquido",
         "value": annual_metric(latest_annual_period, "lucro_liquido"),
         "unit": "BRL"},
        {"label": "Margem EBITDA",
         "value": annual_ratio(latest_annual_period, "marg_ebitda"),
         "unit": "ratio"},
        {"label": "ROE",
         "value": roe_val,
         "unit": "ratio"},
        {"label": "Dívida Líquida/EBITDA",
         "value": net_debt_ebitda_val,
         "unit": "x"},
    ]


def build_overview_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
    kpis: list[dict],
) -> list[dict]:
    """Build the Overview tab sections (kpis + freshness metadata).

    The freshness section is best-effort — if skills.cvm._freshness can't
    be imported or add_freshness raises, the section is silently omitted.
    """
    overview_sections = [
        {"name": "kpis", "cards": kpis},
        {"name": "latest_annual", "period": (
            latest_annual_period.get("period") if latest_annual_period else None
        )},
        {"name": "latest_quarterly", "period": (
            quarterly_periods[-1].get("period") if quarterly_periods else None
        )},
    ]
    # Attach freshness metadata if available (best-effort).
    try:
        from skills.cvm._freshness import add_freshness
        overview_sections.append({"name": "freshness",
                                  "data": add_freshness({})["data_freshness"]})
    except Exception:
        pass
    return overview_sections


# ── Tab 2: DRE (income statement) ────────────────────────────────────────────

def build_dre_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
) -> list[dict]:
    """Build the DRE tab sections: latest annual metrics + ratios, plus the
    quarterly trend (revenue / ebitda / lucro_liquido per period).
    """
    dre_section = {"name": "latest_annual", "metrics": {}}
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        dre_section["metrics"] = {
            "receita_liquida":      m.get("receita_liquida"),
            "lucro_bruto":          m.get("lucro_bruto"),
            "ebit":                 m.get("ebit"),
            "ebitda":               m.get("ebitda"),
            "ebitda_method":        m.get("ebitda_method"),
            "resultado_financeiro": m.get("resultado_financeiro"),
            "lucro_liquido":        m.get("lucro_liquido"),
            "da":                   m.get("da"),
        }
        dre_section["ratios"] = {
            "marg_bruta":   (latest_annual_period.get("ratios") or {}).get("marg_bruta"),
            "marg_ebit":    (latest_annual_period.get("ratios") or {}).get("marg_ebit"),
            "marg_ebitda":  (latest_annual_period.get("ratios") or {}).get("marg_ebitda"),
            "marg_liquida": (latest_annual_period.get("ratios") or {}).get("marg_liquida"),
        }
    dre_trend = {
        "name": "quarterly_trend",
        "periods": [
            {
                "period":        p.get("period"),
                "receita":       (p.get("metrics") or {}).get("receita_liquida"),
                "ebitda":        (p.get("metrics") or {}).get("ebitda"),
                "lucro_liquido": (p.get("metrics") or {}).get("lucro_liquido"),
            }
            for p in quarterly_periods
        ],
    }
    return [dre_section, dre_trend]


# ── Tab 3: Balanço (Ativo + Passivo) ─────────────────────────────────────────

def build_balanco_section(latest_annual_period: dict | None) -> dict:
    """Build the Balanço tab section: Ativo + Passivo from latest annual."""
    balanco_section = {"name": "latest_annual", "ativo": {}, "passivo": {}}
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        balanco_section["ativo"] = {
            "ativo_total": m.get("ativo_total"),
            "caixa":       m.get("caixa"),
        }
        balanco_section["passivo"] = {
            "patrimonio_liquido": m.get("patrimonio_liquido"),
            "divida_bruta":       m.get("divida_bruta"),
            "divida_liquida":     (latest_annual_period.get("ratios") or {}).get("divida_liquida"),
        }
    return balanco_section


# ── Tab 4: DFC (cash flow statement) ─────────────────────────────────────────

def build_dfc_sections(
    latest_annual_period: dict | None,
    quarterly_periods: list[dict],
) -> list[dict]:
    """Build the DFC tab sections: latest annual FCO/FCI/FCF + quarterly trend."""
    dfc_section = {"name": "latest_annual", "metrics": {}}
    if latest_annual_period:
        m = latest_annual_period.get("metrics") or {}
        dfc_section["metrics"] = {
            "fco": m.get("fco"),
            "fci": m.get("fci"),
            "fcf": m.get("fcf"),
        }
    dfc_trend = {
        "name": "quarterly_trend",
        "periods": [
            {
                "period": p.get("period"),
                "fco":    (p.get("metrics") or {}).get("fco"),
                "fci":    (p.get("metrics") or {}).get("fci"),
                "fcf":    (p.get("metrics") or {}).get("fcf"),
            }
            for p in quarterly_periods
        ],
    }
    return [dfc_section, dfc_trend]


# ── Tab 5: Ratios (categorized ratio grid) ───────────────────────────────────

def build_ratios_section(today: str, ratios_payload: dict) -> dict:
    """Build the Ratios tab section: categorized ratio grid.

    Groups the compute_all_ratios() output by metric category using the
    calculations registry. Per-share metrics (lpa/vpa/dpa/rps) are excluded.
    Falls back to a flat "_all" bucket if the registry isn't available.
    """
    ratio_grid: dict[str, dict[str, float | None]] = {}
    try:
        # Re-import here — the import in dashboard may have failed; this is
        # an independent fall-through for the grid grouping only.
        from skills.cvm.calculations._registry import METRICS, list_metrics_by_category
        for category in ("profitability", "liquidity", "leverage",
                         "efficiency", "growth", "tax"):
            ratio_grid[category] = {}
            for metric_name in list_metrics_by_category(category):
                if metric_name in ("lpa", "vpa", "dpa", "rps"):
                    continue
                ratio_grid[category][metric_name] = ratios_payload.get(metric_name)
    except Exception:
        # Fall back to a flat dict if the registry isn't available.
        ratio_grid = {"_all": {k: v for k, v in ratios_payload.items()
                               if k not in ("date", "error")}}

    return {
        "name": "ratio_grid",
        "date": today,
        "categories": ratio_grid,
    }
