"""skills/investsite/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the indicators() + events() results into a multi-tab dashboard
payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).

[v1.1] NEW — added as part of the modular split. The original investsite.py
monolith had no dashboard mode; this module + modes/dashboard.py +
tools/report_ops/adapters/investsite_dashboard.py are all new.
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _num(v: Any) -> Any:
    """Coerce numeric strings/values to int or float (passthrough None)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _kpi(label: str, value: Any, spec: str, unit: str) -> dict:
    """Build a single KPI card: {label, value, unit}.

    The value is pre-formatted via apply_fmt so the adapter can pass it
    through verbatim. When value is None, falls back to "—".
    """
    if value is None:
        return {"label": label, "value": "—", "unit": unit}
    return {"label": label, "value": _fmt(value, spec), "unit": unit}


def _first_value(v: Any) -> Any:
    """If v is a list, return the first non-None element; otherwise return v.

    The indicators parser stores a scalar when a row has one value column
    and a list when it has multiple (e.g. "Consolidado" + "Atual"). For KPI
    purposes we just want the first non-None value.
    """
    if isinstance(v, list):
        for item in v:
            if item is not None:
                return item
        return None
    return v


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

# Map of KPI label -> (section_key, [metric_key candidates], format_spec, unit).
# Section keys come from parsers._INDICATOR_SECTIONS.
# Metric keys are ASCII-normalized by parsers._normalize_key.
# [v2] Each KPI now has a LIST of candidate keys — investsite's page labels
# vary slightly (e.g. "Retorno s/ Patrimônio Líquido" vs "Retorno sobre
# Patrimônio Líquido" vs "ROE"), so we try each in order and use the first
# non-None value found.
_KPI_SPECS = [
    # (display_label, section_key, [metric_key candidates], spec, unit)
    ("P/L",             "precos_relativos",  ["Preco/Lucro", "P/L", "PL"],                                  "num", "num"),
    ("P/VPA",           "precos_relativos",  ["Preco/VPA", "P/VPA", "PVPA", "Preco/Valor Patrimonial"],     "num", "num"),
    ("EV/EBITDA",       "precos_relativos",  ["EV/EBITDA", "EV Ebitda", "Enterprise Value/EBITDA"],         "num", "num"),
    ("ROE",             "retornos_margens",  ["Retorno s/ Patrimonio Liquido",
                                              "Retorno sobre Patrimonio Liquido",
                                              "Retorno sobre o Patrimonio Liquido",
                                              "Retorno s/ o Patrimonio Liquido",
                                              "ROE",
                                              "ROE (Retorno s/ Patrimonio Liquido)"],                       "pct", "pct"),
    ("Dividend Yield",  "precos_relativos",  ["Dividend Yield", "Div Yield", "DY"],                          "pct", "pct"),
]


def build_overview_kpis(indicators_result: dict) -> list[dict]:
    """Build 5 KPI cards for the dashboard top-level kpis list.

    Cards (from the indicators() result sections):
      - P/L             — Preco/Lucro from precos_relativos (num)
      - P/VPA           — Preco/VPA from precos_relativos (num)
      - EV/EBITDA       — EV/EBITDA from precos_relativos (num)
      - ROE             — Retorno s/ Patrimonio Liquido from retornos_margens (pct)
      - Dividend Yield  — Dividend Yield from precos_relativos (pct)

    [v2] Each KPI tries multiple candidate metric keys (investsite page
    labels vary between stocks/periods). When a section or all metric
    candidates are missing, the KPI value renders as "—".

    When a section or metric is missing (e.g. EV/EBITDA not on the page),
    the KPI value renders as "—".
    """
    if not _ok(indicators_result):
        sections: dict = {}
    else:
        sections = indicators_result.get("sections", {}) or {}

    kpis: list[dict] = []
    for label, section_key, metric_keys, spec, unit in _KPI_SPECS:
        sec = sections.get(section_key, {}) or {}
        # [v2] Try each candidate key; use the first non-None value.
        value = None
        for mk in metric_keys:
            v = _first_value(sec.get(mk))
            if v is not None:
                value = v
                break
        kpis.append(_kpi(label, value, spec, unit))
    return kpis


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(indicators_result: dict) -> dict:
    """Build the Overview tab's text section summarizing the indicators.

    Multi-line text showing ticker, company name (from dados_basicos when
    present), and the 5 headline price/return metrics.
    """
    if not _ok(indicators_result):
        sections: dict = {}
        ticker = ""
    else:
        sections = indicators_result.get("sections", {}) or {}
        ticker = indicators_result.get("ticker", "")

    dados = sections.get("dados_basicos", {}) or {}
    company = (dados.get("Empresa")
               or dados.get("Razao Social")
               or "")

    precos = sections.get("precos_relativos", {}) or {}
    retornos = sections.get("retornos_margens", {}) or {}

    pl = _first_value(precos.get("Preco/Lucro"))
    pvpa = _first_value(precos.get("Preco/VPA"))
    evebitda = _first_value(precos.get("EV/EBITDA"))
    roe = _first_value(retornos.get("Retorno s/ Patrimonio Liquido"))
    dy = _first_value(precos.get("Dividend Yield"))

    text_lines = [
        f"Ticker: {ticker}",
        f"Empresa: {company or '—'}",
        f"P/L: {_fmt(pl, 'num')}",
        f"P/VPA: {_fmt(pvpa, 'num')}",
        f"EV/EBITDA: {_fmt(evebitda, 'num')}",
        f"ROE: {_fmt(roe, 'pct')}",
        f"Dividend Yield: {_fmt(dy, 'pct')}",
    ]
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── Key Indicators tab section (table) ───────────────────────────────────────

# (display_label, section_key, metric_key, spec)
# Used by build_key_indicators_section to flatten precos_relativos +
# retornos_margens into a 2-column [Indicador, Valor] table.
_KEY_INDICATOR_ROWS = [
    # Valuation ratios (Preços Relativos)
    ("P/L",                         "precos_relativos",  "Preco/Lucro"),
    ("P/VPA",                       "precos_relativos",  "Preco/VPA"),
    ("EV/EBITDA",                   "precos_relativos",  "EV/EBITDA"),
    ("Dividend Yield",              "precos_relativos",  "Dividend Yield"),
    # Returns & margins (Retornos, Margens e Outras Medidas)
    ("ROE",                         "retornos_margens",  "Retorno s/ Patrimonio Liquido"),
    ("ROA",                         "retornos_margens",  "Retorno s/ Ativo"),
    ("Margem EBITDA",               "retornos_margens",  "Margem EBITDA"),
    ("Margem Líquida",              "retornos_margens",  "Margem Liquida"),
]


def _spec_for_metric(metric_key: str) -> str:
    """Pick a format spec for a metric_key (pct for returns/margins, num otherwise)."""
    if metric_key.startswith("Retorno") or metric_key.startswith("Margem"):
        return "pct"
    if metric_key == "Dividend Yield":
        return "pct"
    return "num"


def build_key_indicators_section(indicators_result: dict) -> dict:
    """Build the Key Indicators tab table from the indicators() result.

    Columns: Indicador, Valor (2-column table flattening precos_relativos +
    retornos_margens sections). Values are pre-formatted via apply_fmt with
    the appropriate spec (num for valuation ratios, pct for returns/margins).
    """
    if not _ok(indicators_result):
        sections: dict = {}
    else:
        sections = indicators_result.get("sections", {}) or {}

    precos = sections.get("precos_relativos", {}) or {}
    retornos = sections.get("retornos_margens", {}) or {}

    columns = ["Indicador", "Valor"]
    rows = []
    for label, section_key, metric_key in _KEY_INDICATOR_ROWS:
        sec = precos if section_key == "precos_relativos" else retornos
        v = _first_value(sec.get(metric_key))
        spec = _spec_for_metric(metric_key)
        formatted = _fmt(v, spec) if v is not None else "—"
        rows.append([label, formatted])

    formats = {"Indicador": "text", "Valor": "text"}

    return {
        "title": f"Key Indicators ({len(rows)} metrics)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": ("Valuation (preços relativos) + retornos/margens extraídos "
                 "da página principais_indicadores.php."),
    }


# ── Latest Events tab section (events table) ────────────────────────────────

def build_latest_events_section(events_result: dict) -> dict:
    """Build the Latest Events tab table from the events() result.

    Columns: Data, Categoria, Descrição, Link — limited to 10 most recent
    events (events() already returns newest-first).
    """
    events = (events_result.get("events")
              if _ok(events_result) else []) or []

    # Limit to 10 most recent rows (events() returns newest-first).
    recent = events[:10]

    columns = ["Data", "Categoria", "Descrição", "Link"]
    rows = []
    for e in recent:
        rows.append([
            e.get("data_entrega", "") or "—",
            e.get("categoria", "") or "—",
            e.get("assuntos", "") or "—",
            e.get("link_cvm", "") or "—",
        ])

    formats = {c: "text" for c in columns}

    return {
        "title": f"Latest Events ({len(recent)} recent)",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": "Fatos Relevantes recentes com links diretos para o CVM (rad.cvm.gov.br).",
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    """Return True if the result dict represents a successful call.

    Mirrors tools.report_ops.adapters._ok: status == "ok" and dict-typed.
    """
    return isinstance(result, dict) and result.get("status") == "ok"
