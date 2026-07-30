"""skills/cvm/screener/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the sector() + compare() results into a multi-tab dashboard
payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - Text section:   {"title", "type": "text", "text"}
  - KPI card:       {"label", "value", "unit"}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
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

# (display_label, comparison_key, format_spec_for_my_value_and_median)
# Mirrors the metric order from helpers._build_comparison (valuation_multiples
# then quality_metrics) so the dashboard's Comparison tab matches the
# screener compare() result's iteration order.
_COMP_METRICS: list[tuple[str, str, str]] = [
    ("P/L",            "p_l",            "num"),
    ("P/VPA",          "p_vpa",          "num"),
    ("EV/EBITDA",      "ev_ebitda",      "num"),
    ("Dívida/PL",      "divida_pl",      "num"),
    ("ROE",            "roe",            "pct"),
    ("Div Yield",      "dividend_yield", "pct"),
    ("ROA",            "roa",            "pct"),
    ("Marg. Líquida",  "margem_liquida", "pct"),
]


def build_comparison_section(compare_result: dict) -> dict:
    """Build the Comparison tab table from the compare() result.

    Columns: Metric, My Value, Sector Median, Delta %, vs Sector.
    One row per metric in the comparison dict.
    """
    comp = (compare_result.get("comparison") if _ok(compare_result) else {}) or {}

    columns = ["Metric", "My Value", "Sector Median", "Delta %", "vs Sector"]
    rows = []
    for label, key, spec in _COMP_METRICS:
        entry = comp.get(key) or {}
        my_val = entry.get("my_value")
        med_val = entry.get("sector_median")
        delta = entry.get("delta_pct")
        vs = entry.get("vs_sector", "n/a")
        rows.append([
            label,
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
