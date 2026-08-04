"""skills/cvm/comparison/report.py -- Dashboard composition helpers.

Reusable section builders used by the `dashboard` mode (modes/dashboard.py)
to shape the side_by_side + growth comparison results into a multi-tab
dashboard payload.

Each builder produces a section dict in the canonical dashboard shape:
  - Table section:  {"title", "type": "table", "columns", "rows", "formats"}
  - KPI card:       {"label", "value", "unit"}
  - Chart section:  {"title", "type": "chart", "chart_data": <Chart.js config>}
  - Ratio grid:     {"title", "type": "ratio_grid", "categories": [...]}

The KPI cards are produced separately (build_overview_kpis) and placed at
the top level of the dashboard payload (not inside a section).
"""
from __future__ import annotations

from typing import Any

from tools.report_ops.formats import apply_fmt

# [v3] Shared tooltip registry — provides PT-BR formula explanations for
# standard financial metrics. Used to populate column_tooltips on the
# valuation/financials/dividends/growth side-by-side tables, and tooltips
# on the peer ratio_grid items.
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
    truthy, otherwise returns ``label`` unchanged.
    """
    return {"text": label, "tooltip": tooltip} if tooltip else label


# ── Column tooltip registry (v3) ─────────────────────────────────────────────
# Maps the column labels used in side_by_side sections to their PT-BR
# formula/tooltip string. Looked up via _get_tooltip for the standard
# financial metrics registry; for comparison-only labels (e.g. "Preço",
# "Market Cap", "EV") we fall back to inline strings.
_COLUMN_TOOLTIPS: dict[str, str] = {
    # Valuation
    "Preço":            "Preço atual da ação (B3 cotahist).",
    "Market Cap":       "Market Cap = Preço × Total de Ações.",
    "EV":               "Enterprise Value = Market Cap + Dívida Líquida.",
    "P/L":              _get_tooltip("lpa"),
    "P/VPA":            _get_tooltip("vpa"),
    "P/EBIT":           _get_tooltip("p_ebit"),
    "EV/EBITDA":        _get_tooltip("ev_ebitda"),
    "PSR":              _get_tooltip("rps"),
    "Div Yield":        _get_tooltip("dpa"),
    "DPA":              "Dividendos por Ação (TTM) = Dividendos pagos / Total de Ações.",
    "EPS":              "Lucro por Ação (LPA) = Lucro Líquido / Total de Ações.",
    "VPA":              "Valor Patrimonial por Ação = PL / Total de Ações.",
    "Total Ações":      "Total de ações outstanding (FRE).",
    "ROE (val)":        _get_tooltip("roe"),
    "ROA (val)":        _get_tooltip("roa"),
    "Marg. Líq. (val)": _get_tooltip("net_margin"),
    "Dívida/PL":        _get_tooltip("debt_equity"),
    "Liquidez Corrente": _get_tooltip("current_ratio"),
    "EV/Receita":       _get_tooltip("ev_sales"),
    "EV/FCF":           _get_tooltip("ev_fcf"),
    "Liquidez Seca":    _get_tooltip("quick_ratio"),
    "Índice Caixa":     _get_tooltip("cash_ratio"),
    "Marg. FCO":        _get_tooltip("ocf_margin"),
    "Marg. FCF":        _get_tooltip("fcf_margin"),
    "Cap. Giro":        _get_tooltip("working_capital"),
    "FCO/Dívida":       _get_tooltip("cash_flow_to_debt"),
    "Taxa Retenção":    _get_tooltip("retention_ratio"),
    "Cresc. Sust.":     _get_tooltip("sustainable_growth"),
    "Cobertura Juros":  _get_tooltip("interest_coverage"),
    "Giro Estoque":     _get_tooltip("inventory_turnover"),
    "Giro Receber":     _get_tooltip("receivables_turnover"),
    "Giro Imob.":       _get_tooltip("fixed_asset_turnover"),
    "P/VPA Tang.":      _get_tooltip("price_to_tangible_book"),
    # Financials
    "Receita Líquida":  "Receita total após deduções (DRE 3.01).",
    "Lucro Bruto":      "Lucro Bruto = Receita Líquida - CMV (DRE 3.03).",
    "EBIT":             "EBIT = Resultado antes de juros e impostos (DRE 3.05).",
    "EBITDA":           "EBITDA = EBIT + Depreciação & Amortização.",
    "Lucro Líquido":    "Lucro/Prejuízo Consolidado (DRE 3.11).",
    "Ativo Total":      "Total de ativos (BPA 1).",
    "Patrimônio Líq.":  "Capital próprio dos acionistas (BPP 2.03).",
    "Caixa":            "Caixa e Equivalentes (BPA 1.01.01).",
    "Dívida Bruta":     "Empréstimos Circ + Não Circ (2.01.04 + 2.02.01).",
    "FCO":              "Fluxo de Caixa Operacional (DFC 6.01).",
    "Marg. Bruta":      _get_tooltip("gross_margin"),
    "Marg. EBITDA":     _get_tooltip("ebitda_margin"),
    "Marg. Líquida":    _get_tooltip("net_margin"),
    "ROE":              _get_tooltip("roe"),
    "ROA":              _get_tooltip("roa"),
    "Payout":           "Payout = Dividendos / Lucro Líquido. % do lucro distribuído.",
    # Dividends
    "Eventos (B3)":         "Número de eventos de proventos (B3) no período.",
    "DPA (B3 médio)":       "Média de Dividendos por Ação (B3 histórico).",
    "Dividendos (últ ano)": "Total de dividendos pagos no último exercício (DVA 7.08.04.02).",
    "JCP (últ ano)":        "Total de Juros sobre Capital Próprio no último exercício (DVA 7.08.04.01).",
    "Total Remun. (últ a)": "Dividendos + JCP no último exercício (DVA 7.08.04).",
    # Growth
    "Receita QoQ":      "Receita: variação trimestre-sobre-trimestre = (atual - anterior) / |anterior|.",
    "Receita YoY":      "Receita: variação ano-sobre-ano = (atual - mesmo trim. ano pass.) / |mesmo trim.|.",
    "EBITDA QoQ":       "EBITDA: variação trimestre-sobre-trimestre.",
    "EBITDA YoY":       "EBITDA: variação ano-sobre-ano.",
    "Lucro Liq. QoQ":   "Lucro Líquido: variação trimestre-sobre-trimestre.",
    "Lucro Liq. YoY":   "Lucro Líquido: variação ano-sobre-ano.",
    "ROE (TTM)":        _get_tooltip("roe"),
}


def _column_tooltips_for(columns: list[str]) -> dict[str, str]:
    """Build a ``{column_label: tooltip}`` dict for the given column labels.

    Only labels present in ``_COLUMN_TOOLTIPS`` are included. Used by the
    side_by_side section builders to populate the ``column_tooltips`` field
    so the dashboard template can render tooltips on column headers.
    """
    return {c: _COLUMN_TOOLTIPS[c] for c in columns if c in _COLUMN_TOOLTIPS}


def _find_leader(section: dict, col_label: str, direction: str) -> tuple[str | None, float | None]:
    """Find the ticker with the min/max value for ``col_label``.

    ``direction`` is "min" or "max". Returns ``(ticker, value)`` where value
    is the raw number (NOT pre-formatted). Returns ``(None, None)`` when no
    row has a numeric value for the column.
    """
    columns = section.get("columns") or []
    rows = section.get("rows") or []
    if col_label not in columns:
        return None, None
    idx = columns.index(col_label)
    best_ticker, best_value = None, None
    for row in rows:
        if len(row) <= idx:
            continue
        value = row[idx]
        ticker = row[0] if row else ""
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if best_value is None:
            best_ticker, best_value = ticker, v
        elif direction == "min" and v < best_value:
            best_ticker, best_value = ticker, v
        elif direction == "max" and v > best_value:
            best_ticker, best_value = ticker, v
    return best_ticker, best_value


def _kpi(label: str, ticker: str | None, value: float | None,
         spec: str, unit: str) -> dict:
    """Build a single KPI card: {label, value, unit}.

    The value is pre-formatted as ``"<ticker> (<formatted>)"`` so the adapter
    can pass it through verbatim. When ticker/value is None, falls back to "—".
    """
    if ticker is None or value is None:
        return {"label": label, "value": "—", "unit": unit}
    formatted = _fmt(value, spec)
    return {"label": label, "value": f"{ticker} ({formatted})", "unit": unit}


# ── Overview KPI cards (top-level, not inside a section) ─────────────────────

def build_overview_kpis(side_by_side_result: dict) -> list[dict]:
    """Build the 4 KPI cards for the dashboard top-level kpis list.

    Cards (from the compared tickers):
      - Cheapest P/L         — lowest non-None P/L
      - Best ROE             — highest non-None ROE (financials section)
      - Best Div Yield       — highest non-None Div Yield (valuation section)
      - Cheapest EV/EBITDA   — lowest non-None EV/EBITDA
    """
    sections = side_by_side_result.get("sections") or {}
    valuation_section = sections.get("valuation") or {}
    financials_section = sections.get("financials") or {}

    pl_ticker, pl_value = _find_leader(valuation_section, "P/L", "min")
    roe_ticker, roe_value = _find_leader(financials_section, "ROE", "max")
    dy_ticker, dy_value = _find_leader(valuation_section, "Div Yield", "max")
    evebitda_ticker, evebitda_value = _find_leader(valuation_section, "EV/EBITDA", "min")

    return [
        _kpi("Cheapest P/L",       pl_ticker,       pl_value,       "num", "num"),
        _kpi("Best ROE",           roe_ticker,      roe_value,      "pct", "pct"),
        _kpi("Best Div Yield",     dy_ticker,       dy_value,       "pct", "pct"),
        _kpi("Cheapest EV/EBITDA", evebitda_ticker, evebitda_value, "num", "num"),
    ]


# ── Overview tab sections ────────────────────────────────────────────────────

def build_tickers_section(side_by_side_result: dict) -> dict:
    """Build the Compared Tickers table for the Overview tab.

    Two columns: Ticker, Setor (sector from CAD via _fetch_sectors).
    """
    tickers = side_by_side_result.get("tickers") or []
    sectors = side_by_side_result.get("sectors") or {}
    rows = [[t, sectors.get(t, "")] for t in tickers]
    return {
        "title": "Compared Tickers",
        "type": "table",
        "columns": ["Ticker", "Setor"],
        "rows": rows,
        "formats": {"Ticker": "text", "Setor": "text"},
    }


def build_errors_section(side_by_side_result: dict) -> dict | None:
    """If the comparison captured any per-ticker errors, surface them as a
    table section. Returns None when there are no errors.
    """
    errors = side_by_side_result.get("errors") or []
    if not errors:
        return None
    rows = [[i + 1, msg] for i, msg in enumerate(errors)]
    return {
        "title": "Per-Ticker Errors (best-effort)",
        "type": "table",
        "columns": ["#", "Error"],
        "rows": rows,
        "formats": {"#": "int", "Error": "text"},
    }


# ── Passthrough section builders ─────────────────────────────────────────────
# The side_by_side mode already builds each section in the generic table shape
# (columns/rows/formats). These helpers just re-tag the section with
# type="table" and pull it out of the sections dict for the dashboard tabs.

def _as_table_section(section: dict) -> dict:
    """Ensure a section has type='table' (dashboard sections are typed)."""
    out = dict(section)
    out.setdefault("type", "table")
    return out


def build_valuation_section(side_by_side_result: dict) -> dict:
    """Build the Valuation tab section from side_by_side()['sections']['valuation'].

    [v3] Adds ``column_tooltips`` so the dashboard template can render a
    formula tooltip on each metric column header (P/L, P/VPA, EV/EBITDA, ...).
    """
    sections = side_by_side_result.get("sections") or {}
    section = sections.get("valuation") or {
        "title": "Valuation Ratios", "type": "table",
        "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
    }
    out = _as_table_section(section)
    out["column_tooltips"] = _column_tooltips_for(out.get("columns") or [])
    return out


def build_financials_section(side_by_side_result: dict) -> dict:
    """Build the Financials tab section from side_by_side()['sections']['financials'].

    [v3] Adds ``column_tooltips`` so the dashboard template can render a
    formula tooltip on each metric column header (Receita, EBITDA, ROE, ...).
    """
    sections = side_by_side_result.get("sections") or {}
    section = sections.get("financials") or {
        "title": "Financial Metrics (latest annual)", "type": "table",
        "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
    }
    out = _as_table_section(section)
    out["column_tooltips"] = _column_tooltips_for(out.get("columns") or [])
    return out


def build_dividends_section(side_by_side_result: dict) -> dict:
    """Build the Dividends tab section from side_by_side()['sections']['dividends'].

    [v3] Adds ``column_tooltips`` so the dashboard template can render a
    formula tooltip on each metric column header (Eventos, DPA, JCP, ...).
    """
    sections = side_by_side_result.get("sections") or {}
    section = sections.get("dividends") or {
        "title": "Dividend Metrics", "type": "table",
        "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
    }
    out = _as_table_section(section)
    out["column_tooltips"] = _column_tooltips_for(out.get("columns") or [])
    return out


def build_growth_section(growth_result: dict) -> dict:
    """Build the Growth tab section from growth()['sections'][0].

    The growth mode returns sections as a list (single-element); this helper
    extracts that section and re-tags it with type='table'.

    [v3] Adds ``column_tooltips`` so the dashboard template can render a
    formula tooltip on each growth metric column header (Receita QoQ, YoY, ...).
    """
    sections = growth_result.get("sections") or []
    if not sections:
        return {
            "title": "Growth Metrics (QoQ + YoY + TTM)", "type": "table",
            "columns": ["Ticker"], "rows": [], "formats": {"Ticker": "text"},
        }
    out = _as_table_section(sections[0])
    out["column_tooltips"] = _column_tooltips_for(out.get("columns") or [])
    return out


# ── Peer comparison chart (v1.2) ─────────────────────────────────────────────

# Mapping of metric_name → (column_label_in_section, scale, color)
# scale = 100.0 for pct-kind (stored as fraction), 1.0 for raw multiples.
_PEER_METRIC_DEFS: dict[str, tuple[str, float, str]] = {
    "p_l":            ("P/L",              1.0,   _TEAL),
    "p_vpa":          ("P/VPA",            1.0,   _TEAL),
    "ev_ebitda":      ("EV/EBITDA",        1.0,   _TEAL),
    "roe":            ("ROE",              100.0, _ORANGE),
    "dividend_yield": ("Div Yield",        100.0, _ORANGE),
    "roa":            ("ROA",              100.0, _ORANGE),
    "margem_liquida": ("Marg. Líq. (val)", 100.0, _ORANGE),
    "divida_pl":      ("Dívida/PL",        1.0,   _RED),
}


def build_peer_comparison_chart(company: str, peers: dict,
                                metric_name: str = "p_l") -> dict | None:
    """Build a bar chart comparing the target company vs peers on a key metric.

    Args:
        company:     target ticker (highlighted with a different color).
        peers:       side_by_side() result dict (must contain "tickers" + a
                     "sections" dict with at least one of valuation/financials).
        metric_name: which metric to chart (p_l, p_vpa, ev_ebitda, roe,
                     dividend_yield, roa, margem_liquida, divida_pl).
                     Default "p_l".

    Returns None if no peer data exists or the metric isn't found in the
    valuation/financials section.
    """
    metric_def = _PEER_METRIC_DEFS.get(metric_name)
    if metric_def is None:
        return None
    col_label, scale, default_color = metric_def

    tickers = peers.get("tickers") or []
    if not tickers:
        return None

    sections = peers.get("sections") or {}
    # Try valuation section first (most metrics live there), fall back to
    # financials (for ROE/ROA/Marg. Líquida — they exist in both sections).
    section = sections.get("valuation") or sections.get("financials") or {}
    columns = section.get("columns") or []
    rows = section.get("rows") or []

    if col_label not in columns or not rows:
        return None

    col_idx = columns.index(col_label)
    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    for row in rows:
        if len(row) <= col_idx:
            continue
        value = row[col_idx]
        ticker = row[0] if row else ""
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        labels.append(str(ticker))
        values.append(round(v * scale, 2))
        # Highlight the target company in purple; peers use the metric color.
        colors.append(_PURPLE if str(ticker) == str(company) else default_color)

    if not labels:
        return None

    unit = "%" if scale == 100.0 else "×"
    return {
        "title": f"{col_label} — {company} vs Peers",
        "description": (
            f"Comparação de {col_label} entre {company} (destaque roxo) e "
            f"os demais tickers. {'Valores em %.' if scale == 100.0 else 'Valores em múltiplos (×).'}"
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": f"{col_label} ({unit})",
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": colors,
                    "borderWidth": 1,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": f"{col_label} — {company} vs Peers"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }


# ── Peer ratio grid (v1.2) ───────────────────────────────────────────────────

# (peer_label, section_key, col_label, display_label, scale, spec, tooltip)
# Group metrics into 3 categories: Valuation, Profitability, Leverage.
# [v3] Added tooltip field — sourced from _get_tooltip for standard metrics;
# for comparison-only labels we fall back to inline strings.
_PEER_GRID_DEFS: list[tuple[str, str, str, str, float, str, str]] = [
    # category_label, section_key, column_label, display_label, scale, spec, tooltip
    ("Valuation",     "valuation", "P/L",              "P/L",              1.0,   "num", _get_tooltip("lpa")),
    ("Valuation",     "valuation", "P/VPA",            "P/VPA",            1.0,   "num", _get_tooltip("vpa")),
    ("Valuation",     "valuation", "EV/EBITDA",        "EV/EBITDA",        1.0,   "num", _get_tooltip("ev_ebitda")),
    ("Profitability", "valuation", "ROE (val)",        "ROE",              100.0, "pct", _get_tooltip("roe")),
    ("Profitability", "valuation", "ROA (val)",        "ROA",              100.0, "pct", _get_tooltip("roa")),
    ("Profitability", "valuation", "Marg. Líq. (val)", "Marg. Líquida",    100.0, "pct", _get_tooltip("net_margin")),
    ("Profitability", "valuation", "Div Yield",        "Div Yield",        100.0, "pct", _get_tooltip("dpa")),
    ("Leverage",      "valuation", "Dívida/PL",        "Dívida/PL",        1.0,   "num", _get_tooltip("debt_equity")),
    ("Leverage",      "valuation", "Liquidez Corrente","Liquidez Corrente",1.0,   "num", _get_tooltip("current_ratio")),
]


def build_peer_ratio_grid(peers: dict) -> dict | None:
    """Build a ratio_grid section grouping peer metrics by category.

    Groups the comparison metrics (P/L, P/VPA, EV/EBITDA, ROE, ROA, Marg.
    Líquida, Div Yield, Dívida/PL, Liquidez Corrente) into 3 categories:
    Valuation, Profitability, Leverage. Each item shows the metric label +
    per-ticker formatted values.

    Args:
        peers: side_by_side() result dict (must contain "tickers" +
               "sections" with a valuation/financials section).

    Returns None if no peer data exists or no metrics can be resolved.
    """
    tickers = peers.get("tickers") or []
    if not tickers:
        return None

    sections = peers.get("sections") or {}
    valuation_section = sections.get("valuation") or {}
    financials_section = sections.get("financials") or {}
    val_cols = valuation_section.get("columns") or []
    val_rows = valuation_section.get("rows") or []
    fin_cols = financials_section.get("columns") or []
    fin_rows = financials_section.get("rows") or []

    # Build a {ticker: {col_label: raw_value}} lookup for fast access.
    val_lookup: dict[str, dict[str, Any]] = {}
    for row in val_rows:
        if not row:
            continue
        val_lookup[row[0]] = {c: row[i] if i < len(row) else None
                              for i, c in enumerate(val_cols)}
    fin_lookup: dict[str, dict[str, Any]] = {}
    for row in fin_rows:
        if not row:
            continue
        fin_lookup[row[0]] = {c: row[i] if i < len(row) else None
                              for i, c in enumerate(fin_cols)}

    categories: dict[str, list[dict]] = {}
    for cat_label, section_key, col_label, display_label, scale, spec, tooltip in _PEER_GRID_DEFS:
        lookup = val_lookup if section_key == "valuation" else fin_lookup
        cols = val_cols if section_key == "valuation" else fin_cols
        if col_label not in cols:
            continue
        values_per_ticker = []
        for t in tickers:
            raw = lookup.get(t, {}).get(col_label)
            if raw is None:
                values_per_ticker.append("—")
            else:
                try:
                    v = float(raw) * scale
                    values_per_ticker.append(_fmt(v, spec))
                except (TypeError, ValueError):
                    values_per_ticker.append("—")
        if all(v == "—" for v in values_per_ticker):
            continue  # skip metrics with no data for any ticker
        item: dict = {
            "label": f"{display_label} ({' / '.join(tickers)})",
            "value": " / ".join(values_per_ticker),
        }
        # [v3] Attach tooltip with the formula/explanation for each metric.
        if tooltip:
            item["tooltip"] = tooltip
        categories.setdefault(cat_label, [])
        categories[cat_label].append(item)

    if not categories:
        return None

    cats_out = [{"label": k, "items": v} for k, v in categories.items()]
    return {
        "title": "Peer Metrics by Category",
        "type": "ratio_grid",
        "categories": cats_out,
    }


# ── Growth chart (v3) ────────────────────────────────────────────────────────

def build_growth_chart(growth_result: dict) -> dict | None:
    """Build a grouped bar chart showing YoY growth per ticker.

    Uses the growth() result's ``sections[0]`` (the side-by-side growth table)
    to extract ``Receita YoY``, ``EBITDA YoY`` and ``Lucro Liq. YoY`` columns
    (stored as pct_raw fractions — scaled by 100 here for natural display).
    Each ticker gets a group of 3 bars.

    Returns None when there is no growth section, no tickers, or no ticker
    has any of the YoY metrics available.
    """
    sections = growth_result.get("sections") or []
    if not sections:
        return None
    section = sections[0]
    columns = section.get("columns") or []
    rows = section.get("rows") or []
    if not columns or not rows:
        return None

    yoy_metric_labels = ["Receita YoY", "EBITDA YoY", "Lucro Liq. YoY"]
    # Resolve column indices; skip any missing column.
    yoy_indices: list[tuple[str, int]] = []
    for label in yoy_metric_labels:
        if label in columns:
            yoy_indices.append((label, columns.index(label)))
    if not yoy_indices:
        return None

    tickers: list[str] = []
    datasets: dict[str, list[float]] = {label: [] for label, _ in yoy_indices}
    for row in rows:
        if not row:
            continue
        ticker = str(row[0]) if row[0] is not None else "—"
        has_any = False
        for label, idx in yoy_indices:
            v = row[idx] if idx < len(row) else None
            try:
                fv = float(v) * 100.0 if v is not None else None  # pct_raw → %
            except (TypeError, ValueError):
                fv = None
            if fv is not None:
                has_any = True
                datasets[label].append(round(fv, 2))
            else:
                datasets[label].append(0.0)
        if has_any:
            tickers.append(ticker)

    if not tickers:
        return None

    palette = [_TEAL, _ORANGE, _PURPLE]
    chart_datasets = []
    for i, (label, _) in enumerate(yoy_indices):
        chart_datasets.append({
            "label": label,
            "data": datasets[label],
            "backgroundColor": palette[i % len(palette)],
            "borderColor": palette[i % len(palette)],
            "borderWidth": 1,
        })

    return {
        "title": "YoY Growth — Receita vs EBITDA vs Lucro Líquido",
        "description": (
            "Crescimento ano-sobre-ano (%) por ticker: Receita (teal), "
            "EBITDA (laranja) e Lucro Líquido (roxo). Valores em %. "
            "Barras negativas indicam queda no trimestre corrente vs mesmo "
            "trimestre do ano anterior."
        ),
        "type": "chart",
        "chart_data": {
            "type": "bar",
            "data": {
                "labels": tickers,
                "datasets": chart_datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": True, "position": "bottom"},
                    "title": {"display": True,
                              "text": "YoY Growth — Receita vs EBITDA vs Lucro Líquido"},
                },
                "scales": {
                    "x": {"grid": {"display": False}},
                    "y": {"grid": {"color": "rgba(128,128,128,0.1)"}},
                },
            },
        },
    }
