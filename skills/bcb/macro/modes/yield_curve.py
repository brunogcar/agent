"""Mode: yield_curve -- BCB Focus expected Selic yield curve.

Builds an expectations-based yield curve from BCB Focus Selic annual
expectations. For each annual reference year (e.g. "2025", "2026", "2027"),
the latest Focus survey median is plotted against the year -- giving the
expected Selic path. The min/max band (dashed lines) shows the forecast
uncertainty range.

Sections:
  1. Curva de Juros Esperada chart -- DataReferencia (x) vs Mediana (y)
     with a min/max dashed band (uncertainty range).
  2. Expectativas Selic por ano -- table with Mediana, Minimo, Maximo,
     Respondentes, and the Focus survey date.

KPIs:
  - Selic atual (SGS series 432 = "Meta Selic Copom", % a.a.)
  - Selic esperada proximo ano (Focus annual median for current_year + 1)
  - Selic de longo prazo (Focus annual median for current_year + 5, or
    the farthest year available when +5 is not in the survey)

[v1.5] New mode registered as "yield_curve" in skills.bcb.macro._registry.
Reads from data_sources.bcb.focus.query_engine (Selic annual) +
data_sources.bcb.sgs.query_engine (series 432). Falls back gracefully when
the Focus DB is not synced (returns an error section + the current-Selic
KPI if SGS is available).
[v1.7] Removed price_range_selector (this is a forward-looking prediction
chart, not historical data — range selector doesn't apply). Table collapsible.

Option B (Focus expectations). Option A (BMF DI futures) deferred -- B3
does not publish BMF historical data at a public URL like COTAHIST. Needs
API portal investigation.
"""
from __future__ import annotations

from datetime import date as _date

from skills.bcb.macro._registry import register_mode
from data_sources.bcb.focus.query_engine import expectations as query_expectations
from data_sources.bcb.sgs.query_engine import last_value


# SGS series 432 = "Meta Selic Copom" (% a.a.) -- the Selic target rate set
# by Copom. Used for the "Selic atual" KPI.
_META_SELIC_SERIES = 432

# Focus indicator + frequency for the expected Selic path.
_FOCUS_INDICATOR = "Selic"
_FOCUS_FREQUENCY = "annual"

# How far ahead to look for the "long-term" KPI. If the year isn't in the
# Focus data, we fall back to the farthest available year.
_LONG_TERM_YEARS_AHEAD = 5


def _format_value(value, unit: str = "") -> str:
    """Format a float for display (PT-BR convention: '.' for decimals).

    Returns "-" if value is None.
    """
    if value is None:
        return "-"
    try:
        if isinstance(value, (int, float)):
            s = f"{float(value):.2f}"
            return f"{s} {unit}" if unit else s
        return str(value)
    except Exception:
        return str(value)


def _build_yield_chart(points: list[dict]) -> dict:
    """Build the expected-Selic yield-curve chart (mediana + min/max band).

    ``points`` is a list of {"year", "mediana", "minimo", "maximo"} dicts
    sorted ascending by year.

    [v1.7] Removed price_range_selector — this is a forward-looking prediction
    chart (years on x-axis), not historical data. Range selector doesn't apply.
    """
    labels = [p["year"] for p in points]
    medians = [p.get("mediana") for p in points]
    mins = [p.get("minimo") for p in points]
    maxs = [p.get("maximo") for p in points]

    return {
        "type": "chart",
        "title": "Curva de Juros Esperada - Selic (Focus)",
        "unit": "% a.a.",
        "description": (
            "Mediana das expectativas da Pesquisa Focus (BCB) para a taxa "
            "Selic em cada ano de referencia (linha solida) + faixa min/max "
            "(linhas tracejadas). Faixa larga = alta incerteza; faixa "
            "estreita = consenso. Cada ponto e a ultima expectativa "
            "registrada para o ano."
        ),
        "chart_data": {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Mediana",
                        "data": medians,
                        "borderColor": "#0d9488",
                        "backgroundColor": "#0d9488",
                        "borderWidth": 2,
                        "pointRadius": 3,
                        "pointHoverRadius": 5,
                        "tension": 0.2,
                        "fill": False,
                    },
                    {
                        "label": "Maximo",
                        "data": maxs,
                        "borderColor": "#ef4444",
                        "backgroundColor": "rgba(239,68,68,0.06)",
                        "borderWidth": 1,
                        "borderDash": [4, 4],
                        "pointRadius": 2,
                        "fill": False,
                        "tension": 0.2,
                    },
                    {
                        "label": "Minimo",
                        "data": mins,
                        "borderColor": "#22c55e",
                        "backgroundColor": "rgba(34,197,94,0.06)",
                        "borderWidth": 1,
                        "borderDash": [4, 4],
                        "pointRadius": 2,
                        "fill": False,
                        "tension": 0.2,
                    },
                ],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"mode": "index", "intersect": False},
                "scales": {
                    "x": {"title": {"display": True, "text": "Ano de referencia"}},
                    "y": {"title": {"display": True, "text": "% a.a."}},
                },
                "plugins": {
                    "title": {"display": True,
                              "text": "Curva de Juros Esperada - Selic"},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
        # [v1.7] NO price_range_selector — this is a forward-looking prediction
        # chart (years on x-axis), not historical data. Range selector doesn't apply.
    }


def _build_yield_table(points: list[dict]) -> dict:
    """Build the table of latest Focus expectations per year.

    [v1.6] Added sortable params + DD/MM/YYYY date format.
    [v1.7] Collapsible=True.
    """
    from skills.bcb.macro.helpers import format_date as _fmt_date
    rows = []
    for p in points:
        data_str = p.get("data", "-")
        rows.append([
            p["year"],
            _format_value(p.get("mediana"), "% a.a."),
            _format_value(p.get("minimo"), "% a.a."),
            _format_value(p.get("maximo"), "% a.a."),
            str(p.get("numero_respondentes") or "-"),
            {"text": _fmt_date(data_str), "data-value": data_str} if data_str != "-" else {"text": "-"},
        ])
    return {
        "type": "table",
        "title": "Expectativas Selic por ano - tabela",
        "description": "Ultima expectativa Focus registrada para cada ano de referencia.",
        "columns": ["Ano", "Mediana", "Minimo", "Maximo", "Resp.", "Data Focus"],
        "rows": rows,
        "column_align": ["left", "right", "right", "right", "right", "left"],
        "sortable": True,
        "default_sort": {"column": 0, "direction": "asc"},
        "sort_types": ["text", "number", "number", "number", "number", "text"],
        "collapsible": True,
    }


def _build_error_section(title: str, message: str) -> dict:
    """Build a graceful-degradation text section (mirrors the macro report
    builder's build_error_section)."""
    return {"type": "text", "title": title, "text": message}


@register_mode(
    "yield_curve",
    description=(
        "Curva de juros esperada (Selic) baseada na Pesquisa Focus do BCB. "
        "Mediana + faixa min/max por ano de referencia. Le de "
        "data_sources.bcb.focus (Olinda OData) + SGS serie 432 (Meta Selic). "
        "Option B (Focus). Option A (BMF DI futures) deferred -- B3 nao "
        "publica BMF historico em URL publica como COTAHIST."
    ),
    params={},
    include_in_all=False,
    examples=[
        'skill(domain="bcb", sub_domain="macro", mode="yield_curve")',
    ],
)
def yield_curve() -> dict:
    """Build the Focus expected-Selic yield curve dashboard.

    [v1.5] New mode. Charts DataReferencia (year) vs Mediana (expected Selic)
    with a min/max uncertainty band. KPIs: current Selic (SGS 432), expected
    Selic next year, long-term expectation.

    Graceful degradation:
      - If Focus DB not synced, returns an error section (still emits the
        current-Selic KPI if SGS is available).
      - If no Selic annual expectations, returns an error section.
    """
    sections: list[dict] = []
    kpis: list[dict] = []

    # -- 1. Fetch current Selic (Meta Selic, SGS series 432) ----------------
    current_selic_res = last_value(code=_META_SELIC_SERIES)
    current_selic_val = None
    if current_selic_res.get("status") == "ok" and current_selic_res.get("value") is not None:
        current_selic_val = current_selic_res["value"]
        kpis.append({
            "label": "Selic atual (Meta Copom)",
            "value": _format_value(current_selic_val, "% a.a."),
            "raw": current_selic_val,
            "unit": "% a.a.",
            "subtitle": f"ref: {current_selic_res.get('ref_date', '-')}",
        })
    else:
        kpis.append({
            "label": "Selic atual (Meta Copom)",
            "value": None,
            "unit": "% a.a.",
            "subtitle": "SGS serie 432 indisponivel",
        })

    # -- 2. Fetch Focus Selic annual expectations ---------------------------
    focus_res = query_expectations(
        indicador=_FOCUS_INDICATOR,
        frequency=_FOCUS_FREQUENCY,
        limit=2000,  # large enough to cover all years in the survey
    )
    if focus_res.get("status") != "ok":
        sections.append(_build_error_section(
            "Curva de Juros",
            f"Erro ao consultar Focus: {focus_res.get('error', 'sem dados')}. "
            "Rode o sync do bcb.focus para popular o focus.db.",
        ))
        return {
            "status": "ok",
            "mode": "yield_curve",
            "kpis": kpis,
            "sections": sections,
        }

    observations = focus_res.get("observations", [])
    if not observations:
        sections.append(_build_error_section(
            "Curva de Juros",
            "Sem expectativas Selic anuais no Focus. Rode o sync do bcb.focus.",
        ))
        return {
            "status": "ok",
            "mode": "yield_curve",
            "kpis": kpis,
            "sections": sections,
        }

    # -- 3. Group by data_referencia (year) + keep the latest observation --
    # `observations` is sorted DESC by `data` (date the expectation was
    # made). So the FIRST occurrence of each year is the latest expectation
    # for it.
    latest_by_year: dict[str, dict] = {}
    for o in observations:
        year = o.get("data_referencia") or ""
        if not year or year in latest_by_year:
            continue
        latest_by_year[year] = o

    # Sort years ascending. Year is a 4-digit string like "2026".
    sorted_years = sorted(
        [y for y in latest_by_year.keys() if y.isdigit()],
        key=lambda y: int(y),
    )
    if not sorted_years:
        sections.append(_build_error_section(
            "Curva de Juros",
            "Expectativas Focus nao possuem anos de referencia validos.",
        ))
        return {
            "status": "ok",
            "mode": "yield_curve",
            "kpis": kpis,
            "sections": sections,
        }

    points = [
        {
            "year": y,
            "mediana": latest_by_year[y].get("mediana"),
            "minimo": latest_by_year[y].get("minimo"),
            "maximo": latest_by_year[y].get("maximo"),
            "numero_respondentes": latest_by_year[y].get("numero_respondentes"),
            "data": latest_by_year[y].get("data", ""),
        }
        for y in sorted_years
    ]

    # -- 4. Build the chart + table sections --------------------------------
    sections.append(_build_yield_chart(points))
    sections.append(_build_yield_table(points))

    # -- 5. Build the remaining KPIs (next year + long-term) ----------------
    current_year = _date.today().year
    next_year = str(current_year + 1)
    long_term_year = str(current_year + _LONG_TERM_YEARS_AHEAD)

    next_year_point = next((p for p in points if p["year"] == next_year), None)
    if next_year_point is not None and next_year_point.get("mediana") is not None:
        kpis.append({
            "label": f"Selic esperada {next_year}",
            "value": _format_value(next_year_point["mediana"], "% a.a."),
            "raw": next_year_point["mediana"],
            "unit": "% a.a.",
            "subtitle": f"Focus mediana | ref: {next_year_point.get('data', '-')}",
        })
    else:
        kpis.append({
            "label": f"Selic esperada {next_year}",
            "value": None,
            "unit": "% a.a.",
            "subtitle": "sem expectativa Focus para o ano",
        })

    # Long-term: prefer current_year + 5; if missing, fall back to the
    # farthest available year.
    long_term_point = next((p for p in points if p["year"] == long_term_year), None)
    if long_term_point is None:
        long_term_point = points[-1] if points else None
    if long_term_point is not None and long_term_point.get("mediana") is not None:
        kpis.append({
            "label": f"Selic longo prazo ({long_term_point['year']})",
            "value": _format_value(long_term_point["mediana"], "% a.a."),
            "raw": long_term_point["mediana"],
            "unit": "% a.a.",
            "subtitle": f"Focus mediana | ref: {long_term_point.get('data', '-')}",
        })
    else:
        kpis.append({
            "label": "Selic longo prazo",
            "value": None,
            "unit": "% a.a.",
            "subtitle": "sem expectativa Focus de longo prazo",
        })

    return {
        "status": "ok",
        "mode": "yield_curve",
        "kpis": kpis,
        "sections": sections,
    }
