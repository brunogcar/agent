"""skills/cvm/screener/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the sector() + compare() results into a multi-tab dashboard
payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}
  - Chart section:  {"title", "type": "chart", "chart_data": <Chart.js config>}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt

# [v3] Shared tooltip registry — provides PT-BR formula explanations for
# standard financial metrics (P/L, P/VPA, EV/EBITDA, ROE, ...). Custom
# screener-specific tooltips (e.g. for Cresc. Receita) are inlined below.
from skills.cvm._shared_report.tooltips import get_tooltip as _get_tooltip


# ── Brand colors for chart builders ──────────────────────────────────────────
_TEAL = "#0d9488"
_ORANGE = "#f59e0b"
_RED = "#ef4444"
_BLUE = "#3b82f6"
_PURPLE = "#a855f7"


# ── Safe accessor + formatter ────────────────────────────────────────────────

def _fmt(value: Any, spec: str) -> str:
    """Format a value via apply_fmt, returning dash for None."""
    if value is None:
        return "—"
    try:
        return apply_fmt(value, spec)
    except Exception:
        return str(value)


def _cell(label: str, tooltip: str = "") -> dict | str:
    """Wrap a label in a dict cell carrying a tooltip when non-empty.

    Returns ``{"text": label, "tooltip": tooltip}`` when ``tooltip`` is
    truthy, otherwise returns ``label`` unchanged. Used by the Comparison
    tab metric-name column so the dashboard template can render a tooltip
    with the formula/explanation for each metric.
    """
    return {"text": label, "tooltip": tooltip} if tooltip else label


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


# ── Internal helpers ─────────────────────────────────────────────────────────

def _ok(result: dict) -> bool:
    """Return True if the result dict represents a successful call.

    Mirrors tools.report_ops.adapters._ok: status == "ok" and dict-typed.
    """
    return isinstance(result, dict) and result.get("status") == "ok"


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(medians: dict, my_data: dict | None = None) -> list[dict]:
    """Build 5 KPI cards for the dashboard top-level kpis list.

    Cards (all sourced from sector_result['medians']):
      - Median P/L       — num format
      - Median P/VPA     — num format
      - Median EV/EBITDA — num format
      - Median ROE       — pct format (stored as fraction 0.185 = 18.5%)
      - Median Div Yield — pct format

    Args:
        medians: sector medians dict (from sector_result['medians']).
        my_data: optional — kept for API symmetry with the dashboard mode;
                 currently unused (KPIs are sector-wide).
    """
    medians = medians or {}
    return [
        _kpi("Median P/L",       medians.get("p_l"),           "num", "num"),
        _kpi("Median P/VPA",     medians.get("p_vpa"),         "num", "num"),
        _kpi("Median EV/EBITDA", medians.get("ev_ebitda"),     "num", "num"),
        _kpi("Median ROE",       medians.get("roe"),           "pct", "pct"),
        _kpi("Median Div Yield", medians.get("dividend_yield"),"pct", "pct"),
    ]


# ── Overview tab section (text summary) ──────────────────────────────────────

def build_overview_section(sector_result: dict, compare_result: dict) -> dict:
    """Build the Overview tab's text section summarizing the screener data.

    Multi-line text showing setor, peer_count, the ticker being compared,
    and a cheap/expensive labels summary.

    Args:
        sector_result:  sector() result dict.
        compare_result: compare() result dict (may be a non-ok payload when
                        compare() failed; in that case the comparison summary
                        line is suppressed).
    """
    setor = (sector_result.get("setor") if _ok(sector_result) else "") or ""
    peer_count = (sector_result.get("peer_count") if _ok(sector_result) else 0) or 0

    # The ticker being compared — pulled from compare_result when present.
    ticker = compare_result.get("ticker", "") if _ok(compare_result) else ""
    company_name = compare_result.get("name", "") if _ok(compare_result) else ""

    # Cheap/expensive labels summary from the comparison dict.
    cheap_count = 0
    expensive_count = 0
    above_count = 0
    below_count = 0
    na_count = 0
    if _ok(compare_result):
        comp = compare_result.get("comparison") or {}
        for entry in comp.values():
            label = entry.get("vs_sector", "n/a")
            if label == "cheap":
                cheap_count += 1
            elif label == "expensive":
                expensive_count += 1
            elif label == "above":
                above_count += 1
            elif label == "below":
                below_count += 1
            else:
                na_count += 1

    text_lines = [
        f"Setor: {setor or '—'}",
        f"Peer Count: {peer_count}",
    ]
    if ticker:
        text_lines.append(f"Ticker Comparado: {ticker}" +
                          (f" ({company_name})" if company_name else ""))
    if _ok(compare_result):
        text_lines.append(
            f"Classificação vs Setor: cheap={cheap_count}, "
            f"expensive={expensive_count}, above={above_count}, "
            f"below={below_count}, n/a={na_count}"
        )
    else:
        # [v2] Show error context so the dashboard doesn't look empty.
        err = compare_result.get("error", "unknown error") if isinstance(compare_result, dict) else "unknown"
        text_lines.append(f"Erro: {err}")
    return {
        "title": "Summary",
        "type": "text",
        "text": "\n".join(text_lines),
    }


# ── Peers tab section (full peers table) ─────────────────────────────────────

# Column definitions: (display_label, peer_dict_key, format_spec)
# Mirrors tools/report_ops/adapters/screener.py::_PEER_COLS (subset — the
# task brief specifies these 13 columns).
_PEER_COLS: list[tuple[str, str, str]] = [
    ("Ticker",          "ticker",          "text"),
    ("Preço",           "price",           "brl_full"),
    ("Market Cap",      "market_cap",      "brl"),
    ("P/L",             "p_l",             "num"),
    ("P/VPA",           "p_vpa",           "num"),
    ("EV/EBITDA",       "ev_ebitda",       "num"),
    ("ROE",             "roe",             "pct"),
    ("Div Yield",       "dividend_yield",  "pct"),
    ("Receita Líquida", "receita_liquida", "brl"),
    ("EBITDA",          "ebitda",          "brl"),
    ("Marg. EBITDA",    "marg_ebitda",     "pct"),
    ("Cresc. Receita",  "receita_growth",  "pct"),
    ("Segmento",        "segmento",        "text"),
]


def build_peers_section(sector_result: dict) -> dict:
    """Build the Peers tab table from the sector() result.

    Columns: Ticker, Preço, Market Cap, P/L, P/VPA, EV/EBITDA, ROE,
    Div Yield, Receita Líquida, EBITDA, Marg. EBITDA, Cresc. Receita,
    Segmento.
    """
    peers = (sector_result.get("peers") if _ok(sector_result) else []) or []
    setor = (sector_result.get("setor") if _ok(sector_result) else "") or ""

    columns = [label for label, _key, _spec in _PEER_COLS]
    rows = []
    for p in peers:
        row = []
        for _label, key, _spec in _PEER_COLS:
            v = p.get(key)
            # None -> dash so the table renderer doesn't show "None".
            row.append("—" if v is None else v)
        rows.append(row)
    formats = {label: spec for label, _key, spec in _PEER_COLS}

    title = f"Sector: {setor} ({len(peers)} peers, sorted by P/L cheapest-first)" \
            if setor else f"Sector ({len(peers)} peers)"

    return {
        "title": title,
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (f"{len(peers)} peer(s) listados para o setor '{setor}'. "
                 "Ordenados por P/L (menor = mais barato)."),
    }


# ── Comparison tab section (my vs sector table) ──────────────────────────────

# (display_label, comparison_key, format_spec_for_my_value_and_median, tooltip_key)
# Mirrors the metric order from helpers._build_comparison (valuation_multiples
# then quality_metrics) so the dashboard's Comparison tab matches the
# screener compare() result's iteration order.
# [v3] Added tooltip_key — looked up via _get_tooltip for the standard
# financial metrics registry. For screener-only metrics (e.g. Marg. Líquida,
# Dívida/PL) we fall back to inline tooltip strings.
_COMP_METRICS: list[tuple[str, str, str, str]] = [
    ("P/L",            "p_l",            "num", _get_tooltip("lpa")),
    ("P/VPA",          "p_vpa",          "num", _get_tooltip("vpa")),
    ("EV/EBITDA",      "ev_ebitda",      "num", _get_tooltip("ev_ebitda")),
    ("Dívida/PL",      "divida_pl",      "num",
     "Dívida/PL = Dívida Bruta / Patrimônio Líquido. Menor = menos alavancado."),
    ("ROE",            "roe",            "pct", _get_tooltip("roe")),
    ("Div Yield",      "dividend_yield", "pct", _get_tooltip("dpa")),
    ("ROA",            "roa",            "pct", _get_tooltip("roa")),
    ("Marg. Líquida",  "margem_liquida", "pct", _get_tooltip("net_margin")),
]


def build_comparison_section(compare_result: dict) -> dict:
    """Build the Comparison tab table from the compare() result.

    Columns: Metric, My Value, Sector Median, Delta %, vs Sector.
    One row per metric in the comparison dict.

    [v3] The Metric column is now a dict cell carrying a tooltip with the
    formula/explanation for each metric (P/L, P/VPA, EV/EBITDA, ROE, ...).
    """
    comp = (compare_result.get("comparison") if _ok(compare_result) else {}) or {}

    columns = ["Metric", "My Value", "Sector Median", "Delta %", "vs Sector"]
    rows = []
    for label, key, spec, tooltip in _COMP_METRICS:
        entry = comp.get(key) or {}
        my_val = entry.get("my_value")
        med_val = entry.get("sector_median")
        delta = entry.get("delta_pct")
        vs = entry.get("vs_sector", "n/a")
        rows.append([
            _cell(label, tooltip),
            _fmt(my_val, spec) if my_val is not None else "—",
            _fmt(med_val, spec) if med_val is not None else "—",
            _fmt(delta, "pct") if delta is not None else "—",
            vs,
        ])

    formats = {
        "Metric":        "text",
        "My Value":      "text",   # pre-formatted via _fmt -> rendered as text
        "Sector Median": "text",   # pre-formatted via _fmt -> rendered as text
        "Delta %":       "text",   # pre-formatted via _fmt -> rendered as text
        "vs Sector":     "text",
    }

    return {
        "title": "My Ticker vs Sector Medians",
        "type": "table",
        "columns": columns,
        "rows": rows,
        "formats": formats,
        "note": (
            "Comparação métrica-a-métrica entre o ticker e a mediana do setor. "
            "cheap/expensive = múltiplos de valuation (menor = mais barato). "
            "above/below = métricas de qualidade (maior = melhor). "
            "n/a = valor indisponível ou mediana zero."
        ),
    }


# ── My Value vs Sector Median chart (v3) ─────────────────────────────────────

def build_comparison_chart(compare_result: dict) -> dict | None:
    """Build a grouped bar chart comparing ``My Value`` vs ``Sector Median``
    for each metric in the Comparison tab.

    One pair of bars per metric (My Value + Sector Median). Pct-kind metrics
    (ROE, Div Yield, ROA, Marg. Líquida) are scaled by 100 so the chart
    reads naturally as %; multiples (P/L, P/VPA, EV/EBITDA, Dívida/PL) are
    plotted as raw multiples.

    Returns None when the comparison dict is empty OR no metric has both a
    my_value AND a sector_median (the chart needs at least one pair to be
    meaningful).
    """
    comp = (compare_result.get("comparison") if _ok(compare_result) else {}) or {}
    if not comp:
        return None

    labels: list[str] = []
    my_values: list[float] = []
    med_values: list[float] = []
    for label, key, spec, _tooltip in _COMP_METRICS:
        entry = comp.get(key) or {}
        my_val = entry.get("my_value")
        med_val = entry.get("sector_median")
        if my_val is None and med_val is None:
            continue
        # Scale pct-kind metrics by 100 (stored as fraction 0.185 = 18.5%).
        scale = 100.0 if spec == "pct" else 1.0
        try:
            my_v = float(my_val) * scale if my_val is not None else 0.0
        except (TypeError, ValueError):
            my_v = 0.0
        try:
            med_v = float(med_val) * scale if med_val is not None else 0.0
        except (TypeError, ValueError):
            med_v = 0.0
        labels.append(label)
        my_values.append(round(my_v, 2))
        med_values.append(round(med_v, 2))

    if not labels:
        return None

    return {
        "title": "My Value vs Sector Median (per metric)",
        "description": (
            "Barras agrupadas mostrando o valor do ticker (teal) contra a "
            "mediana do setor (laranja) para cada métrica. Métricas em % "
            "estão escaladas (0.185 → 18.5); múltiplos em ×."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "My Value",
                        "data": my_values,
                        "backgroundColor": _TEAL,
                        "borderColor": _TEAL,
                        "borderWidth": 1,
                    },
                    {
                        "label": "Sector Median",
                        "data": med_values,
                        "backgroundColor": _ORANGE,
                        "borderColor": _ORANGE,
                        "borderWidth": 1,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "My Value vs Sector Median (per metric)"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }


# ── Top companies chart (v1.2) ────────────────────────────────────────────────

# Metric → (peer dict key, label, format_spec, sort_direction)
# direction = "asc" (cheapest/best first when lower is better — multiples),
#             "desc" (best first when higher is better — quality metrics).
# The chart sorts peers by the chosen metric and shows top N as bars.
_TOP_METRIC_DEFS: dict[str, tuple[str, str, str, str]] = {
    "p_l":            ("p_l",            "P/L",            "num", "asc"),
    "p_vpa":          ("p_vpa",          "P/VPA",          "num", "asc"),
    "ev_ebitda":      ("ev_ebitda",      "EV/EBITDA",      "num", "asc"),
    "roe":            ("roe",            "ROE",            "pct", "desc"),
    "dividend_yield": ("dividend_yield", "Div Yield",      "pct", "desc"),
}


def build_top_companies_chart(peers_data: dict | list,
                              metric: str = "p_l",
                              top_n: int = 10) -> dict | None:
    """Build a bar chart showing top-screened companies sorted by a key metric.

    Args:
        peers_data: either a sector() result dict (with a "peers" key) OR a
                    raw list of peer dicts. Each peer must have a "ticker"
                    field + the metric key (e.g. "p_l" / "roe" / ...).
        metric:     which metric to sort by (one of: p_l, p_vpa, ev_ebitda,
                    roe, dividend_yield). Default "p_l".
        top_n:      max number of companies to include in the chart. Default 10.

    Returns None if there is no peer data or no valid values for the metric.
    """
    if isinstance(peers_data, dict):
        peers = peers_data.get("peers") or []
    else:
        peers = list(peers_data or [])

    if not peers:
        return None

    metric_def = _TOP_METRIC_DEFS.get(metric)
    if metric_def is None:
        return None
    key, label, spec, direction = metric_def

    # Build (ticker, value) pairs, filtering out peers without a numeric value.
    pairs: list[tuple[str, float]] = []
    for p in peers:
        raw = p.get(key)
        if raw is None:
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        pairs.append((p.get("ticker", "") or "—", v))

    if not pairs:
        return None

    # Sort + slice.
    pairs.sort(key=lambda t: t[1],
               reverse=(direction == "desc"))
    pairs = pairs[:top_n]

    labels = [t for t, _ in pairs]
    values = [v for _, v in pairs]
    # Pct-kind metrics are stored as fractions (0.185 = 18.5%); scale by 100
    # so the chart reads naturally.
    if spec == "pct":
        values = [round(v * 100, 2) for v in values]
    else:
        values = [round(v, 2) for v in values]

    # Choose bar color by metric kind: teal for valuation (lower=better),
    # orange for quality (higher=better).
    bar_color = _ORANGE if direction == "desc" else _TEAL

    return {
        "title": f"Top {len(labels)} Companies by {label}",
        "description": (
            f"Empresas ordenadas por {label}. Múltiplos de valuation "
            f"(P/L, P/VPA, EV/EBITDA): menor = mais barato. Métricas de "
            f"qualidade (ROE, Div Yield): maior = melhor."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": f"{label} ({'%' if spec == 'pct' else '×'})",
                    "data": values,
                    "backgroundColor": bar_color,
                    "borderColor": bar_color,
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "indexAxis": "y",  # horizontal bar chart (ticker names on Y)
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": f"Top {len(labels)} Companies by {label}"},
                },
                "scales": {
                    "x": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                    "y": {"grid": {"display": False}},
                },
            },
        },
    }
