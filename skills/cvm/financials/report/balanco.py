"""skills/cvm/financials/report/balanco.py -- Balanço tab builders.

Builds the Balanço tab (BPA + BPP + Completo subtabs with multi-period
comparison tables + per-subtab stacked-bar charts).

Public builders:
  - ``build_balanco_section(bpa_result, bpp_result, ...)`` — top-level
    subtabs section with Completo / BPA / BPP sub-tabs, each wrapped in a
    period_toggle (annual + quarterly).
  - ``build_balanco_chart(bpa_result, bpp_result, ...)`` — 9 charts for
    the Completo view (5-component abs+pct, ativo-passivo circulante
    abs+pct, ativo-passivo não circulante abs+pct, 5 single-series bars).
  - ``build_balanco_decomp_charts(bpa_result, bpp_result, ...)`` — 4
    single-series charts (Ativo Circ, Ativo Não Circ, Passivo Circ,
    Passivo Não Circ) for BPA + BPP subtabs.

[v7] Chart additions per user reference images:
  - Completo: was 2 charts (5-component abs+pct). Now 9 charts:
    1. Ativo-Passivo Circulante — Absoluto (2-component stacked)
    2. Ativo-Passivo Circulante — Percentual (100% stacked)
    3. Ativo-Passivo Não Circulante — Absoluto (2-component stacked)
    4. Ativo-Passivo Não Circulante — Percentual (100% stacked)
    5. Ativo Circulante (single bar)
    6. Ativo Não Circulante (single bar)
    7. Passivo Circulante (single bar)
    8. Passivo Não Circulante (single bar)
    9. Patrimônio Líquido (single bar)
  - BPA: was 2 charts (Ativo abs+pct). Now 2 single-series charts:
    Ativo Circulante, Ativo Não Circulante.
  - BPP: was 2 charts (Passivo+PL abs+pct). Now 2 single-series charts:
    Passivo Circulante, Passivo Não Circulante.
  - All Composição Percentual charts: y-axis ticks now show 0%, 25%, 50%,
    75%, 100% explicitly (was a callback "{}%" that Chart.js rendered as a
    JS function — didn't serialize. Now uses explicit stepSize + callback).
  - All chart-box CSS: min-height 380px so Absolutos + Percentual render
    at the same height → bars align for visual comparison.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _num_or_none
from skills.cvm.financials.report.statements import (
    _merge_bpa_bpp_periods,
    _build_period_toggle_sections,
)


# ── Colors matching reference images ─────────────────────────────────────────
_CIRC_A = "#1e3a5f"      # Navy blue (Ativo Circulante)
_NCIRC_A = "#60a5fa"     # Light blue (Ativo Não Circulante)
_CIRC_P = "#991b1b"      # Dark red (Passivo Circulante)
_NCIRC_P = "#fca5a5"     # Light pink (Passivo Não Circulante)
_PL = "#22c55e"          # Green (Patrimônio Líquido)


def build_balanco_section(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
    subtab_charts_annual: dict | None = None,
    subtab_charts_quarterly: dict | None = None,
) -> dict:
    """Build the Balanço tab as a `type: "subtabs"` section with BPA + BPP.

    [v1.25 v4] Per-subtab time-series charts are now INSIDE the
    period_toggle. ``subtab_charts_annual`` / ``subtab_charts_quarterly``
    are dicts mapping subtab name ("Completo" / "BPA" / "BPP") to a list
    of chart sections built from annual + quarterly BPA/BPP results
    respectively.
    """
    sub_tabs: list[dict] = []
    sca = subtab_charts_annual or {}
    scq = subtab_charts_quarterly or {}

    bpa_periods = (bpa_result or {}).get("periods") or []
    bpp_periods = (bpp_result or {}).get("periods") or []
    bpa_periods_q = (bpa_result_q or {}).get("periods") or []
    bpp_periods_q = (bpp_result_q or {}).get("periods") or []

    # ── "Completo" sub-tab: BPA + BPP merged, multi-period ──────────────
    if bpa_periods and bpp_periods:
        merged_annual = _merge_bpa_bpp_periods(bpa_periods, bpp_periods)
        merged_quarterly = (
            _merge_bpa_bpp_periods(bpa_periods_q, bpp_periods_q)
            if (bpa_periods_q and bpp_periods_q) else []
        )
        completo_sections = _build_period_toggle_sections(
            "Balanço Completo", merged_annual, merged_quarterly, "BPA+BPP",
            annual_chart=sca.get("Completo"),
            quarterly_chart=scq.get("Completo"))
        if completo_sections:
            sub_tabs.append({"name": "Completo", "sections": completo_sections})

    # ── BPA sub-tab ─────────────────────────────────────────────────────
    if bpa_periods:
        bpa_sections = _build_period_toggle_sections(
            "Ativo", bpa_periods, bpa_periods_q, "BPA",
            annual_chart=sca.get("BPA"),
            quarterly_chart=scq.get("BPA"))
        if bpa_sections:
            sub_tabs.append({"name": "BPA", "sections": bpa_sections})
    if not any(st["name"] == "BPA" for st in sub_tabs):
        sub_tabs.append({
            "name": "BPA",
            "sections": [{"type": "text",
                          "text": "BPA data unavailable for this company."}],
        })

    # ── BPP sub-tab ─────────────────────────────────────────────────────
    if bpp_periods:
        bpp_sections = _build_period_toggle_sections(
            "Passivo", bpp_periods, bpp_periods_q, "BPP",
            annual_chart=sca.get("BPP"),
            quarterly_chart=scq.get("BPP"))
        if bpp_sections:
            sub_tabs.append({"name": "BPP", "sections": bpp_sections})
    if not any(st["name"] == "BPP" for st in sub_tabs):
        sub_tabs.append({
            "name": "BPP",
            "sections": [{"type": "text",
                          "text": "BPP data unavailable for this company."}],
        })

    return {"type": "subtabs", "tabs": sub_tabs}


# ── Period extraction + sorting helpers (shared by both builders) ───────────

def _collect_periods(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None, bpp_result_q: dict | None,
):
    """Collect BPA + BPP period dicts, prefer quarterly when available.

    Returns (bpa_by_year, bpp_by_year, years) where bpa_by_year/bpp_by_year
    are {period_label: accounts_dict} and years is the sorted chronological
    list of period labels.
    """
    if bpa_result_q and bpp_result_q:
        bpa_periods = (bpa_result_q or {}).get("periods") or []
        bpp_periods = (bpp_result_q or {}).get("periods") or []
    else:
        bpa_periods = (bpa_result or {}).get("periods") or []
        bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return {}, {}, []

    bpa_by_year: dict[str, dict] = {}
    for p in bpa_periods:
        period_label = p.get("period") or p.get("data_fim_exerc") or ""
        if period_label:
            bpa_by_year[str(period_label)] = p.get("accounts") or {}

    bpp_by_year: dict[str, dict] = {}
    for p in bpp_periods:
        period_label = p.get("period") or p.get("data_fim_exerc") or ""
        if period_label:
            bpp_by_year[str(period_label)] = p.get("accounts") or {}

    def _label_sort_key(lbl: str) -> tuple:
        if "T" in lbl and len(lbl) >= 6:
            try:
                q = int(lbl.split("T")[0])
                y = int(lbl.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                pass
        try:
            return (int(lbl), 0)
        except ValueError:
            return (0, 0, lbl)

    years = sorted(set(bpa_by_year.keys()) & set(bpp_by_year.keys()),
                   key=_label_sort_key)
    if len(years) < 2:
        years = sorted(set(bpa_by_year.keys()) | set(bpp_by_year.keys()),
                       key=_label_sort_key)
    if len(years) < 2:
        return {}, {}, []
    return bpa_by_year, bpp_by_year, years


def _val(accounts: dict, *codes: str) -> float | None:
    """Get the first non-null valor_brl from a list of account codes."""
    for code in codes:
        acc = accounts.get(code)
        if acc and acc.get("valor_brl") is not None:
            try:
                return float(acc["valor_brl"])
            except (TypeError, ValueError):
                pass
    return None


def _extract_series(bpa_by_year, bpp_by_year, years):
    """Extract the 5 component series (Ativo Circ, Ativo Não Circ,
    Passivo Circ, Passivo Não Circ, PL) aligned with the years list."""
    ativo_circ, ativo_ncirc = [], []
    passivo_circ, passivo_ncirc, pl = [], [], []
    for year in years:
        bpa_acc = bpa_by_year.get(year, {})
        bpp_acc = bpp_by_year.get(year, {})
        ativo_circ.append(_num_or_none(_val(bpa_acc, "1.01")))
        ativo_ncirc.append(_num_or_none(_val(bpa_acc, "1.02")))
        passivo_circ.append(_num_or_none(_val(bpp_acc, "2.01")))
        passivo_ncirc.append(_num_or_none(_val(bpp_acc, "2.02")))
        pl_val = _val(bpp_acc, "2.03")
        if pl_val is None:
            pl_val = _val(bpp_acc, "2.08")
        pl.append(_num_or_none(pl_val))
    return ativo_circ, ativo_ncirc, passivo_circ, passivo_ncirc, pl


def _pct(*series_list):
    """Normalize multiple series to 100% per period. Returns list of series."""
    n = len(series_list[0])
    result = []
    for i in range(n):
        total = sum(s[i] or 0 for s in series_list)
        if total == 0:
            result.append([None] * len(series_list))
        else:
            result.append([(s[i] or 0) / total * 100 for s in series_list])
    return [[result[i][j] for i in range(n)] for j in range(len(series_list))]


def _to_millions(series):
    """Convert a series of raw BRL values to millions (divide by 1e6).

    [v9] Used by Absolutos charts so y-axis labels show "R$ 163.052 mi"
    instead of the raw "163.052.000.000" which broke the template width.
    None values pass through unchanged.
    """
    return [v / 1_000_000 if v is not None else None for v in series]


def _abs_chart(title, description, label, data, color, years):
    """Build a single-series absolute-value bar chart (values in R$ millions).

    [v9] Data divided by 1e6 → y-axis shows "R$ X mi" (millions) instead of
    raw BRL which broke the template width. _fixedYWidth=90 for alignment
    with Percentual. _absMillions flag → _applyAbsMillions JS attaches a
    tick callback formatting values as "X.XXX" (pt-BR comma decimal).
    """
    data_mi = _to_millions(data)
    return {
        "type": "chart",
        "title": title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": label, "data": data_mi, "backgroundColor": color},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "_fixedYWidth": 90,
                "_absMillions": True,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True,
                    "title": {"display": True, "text": "R$ (mi)"}}},
                "plugins": {
                    "title": {"display": True, "text": label},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
    }


def _stacked_abs_chart(title, description, datasets, years, chart_title):
    """Build a multi-series stacked absolute-value bar chart (values in R$ millions).

    [v9] All datasets divided by 1e6 → "R$ (mi)" y-axis. _fixedYWidth=90 +
    _absMillions flag for tick formatting.
    """
    datasets_mi = [
        {**ds, "data": _to_millions(ds["data"])} for ds in datasets
    ]
    return {
        "type": "chart",
        "title": title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": datasets_mi},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "_fixedYWidth": 90,
                "_absMillions": True,
                "scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True,
                          "title": {"display": True, "text": "R$ (mi)"}},
                },
                "plugins": {
                    "title": {"display": True, "text": chart_title},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
    }


def _stacked_pct_chart(title, description, datasets, years, chart_title):
    """Build a 100% stacked percentage bar chart.

    [v9] _pctYAxis flag → _applyPctYAxis JS attaches real callback for
    0%/25%/50%/75%/100% labels. _fixedYWidth flag → _applyFixedYWidth JS
    forces y-axis to same width as Absolutos charts so bars align.
    """
    return {
        "type": "chart",
        "title": title,
        "description": description,
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": datasets},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "_pctYAxis": True,
                "_fixedYWidth": 90,
                "scales": {
                    "x": {"stacked": True},
                    "y": {"stacked": True, "min": 0, "max": 100,
                          "ticks": {"stepSize": 25},
                          "title": {"display": True, "text": "%"}},
                },
                "plugins": {
                    "title": {"display": True, "text": chart_title},
                    "legend": {"display": True, "position": "top"},
                },
            },
        },
    }


def build_balanco_chart(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
) -> list[dict]:
    """Build the Balanço Completo charts: 11 charts.

    [v8] Restored the 2 original 5-component charts that v7 accidentally
    removed, then adds the 9 new charts after. Chart order:
      1. Balanço Completo — Valores Absolutos (5-component stacked) [original]
      2. Balanço Completo — Composição Percentual (5-component 100% stacked) [original]
      3. Ativo-Passivo Circulante — Absoluto (2-component stacked) [new]
      4. Ativo-Passivo Circulante — Composição Percentual (100% stacked) [new]
      5. Ativo-Passivo Não Circulante — Absoluto (2-component stacked) [new]
      6. Ativo-Passivo Não Circulante — Composição Percentual (100% stacked) [new]
      7. Ativo Circulante (single bar) [new]
      8. Ativo Não Circulante (single bar) [new]
      9. Passivo Circulante (single bar) [new]
      10. Passivo Não Circulante (single bar) [new]
      11. Patrimônio Líquido (single bar) [new]
    """
    bpa_by_year, bpp_by_year, years = _collect_periods(
        bpa_result, bpp_result, bpa_result_q, bpp_result_q)
    if not years:
        return []

    ativo_circ, ativo_ncirc, passivo_circ, passivo_ncirc, pl = _extract_series(
        bpa_by_year, bpp_by_year, years)

    charts: list[dict] = []

    # ── Original 2 charts (5-component, restored in v8) ────────────────
    datasets_abs_5 = [
        {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
        {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
        {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
        {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
        {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": _PL},
    ]
    pct_data_5 = _pct(ativo_circ, ativo_ncirc, passivo_circ, passivo_ncirc, pl)
    datasets_pct_5 = [
        {"label": "Ativo Circulante", "data": pct_data_5[0], "backgroundColor": _CIRC_A},
        {"label": "Ativo Não Circulante", "data": pct_data_5[1], "backgroundColor": _NCIRC_A},
        {"label": "Passivo Circulante", "data": pct_data_5[2], "backgroundColor": _CIRC_P},
        {"label": "Passivo Não Circulante", "data": pct_data_5[3], "backgroundColor": _NCIRC_P},
        {"label": "Patrimônio Líquido", "data": pct_data_5[4], "backgroundColor": _PL},
    ]
    # 1. Original: Balanço Completo — Valores Absolutos (5-component)
    charts.append(_stacked_abs_chart(
        "Balanço Completo — Valores Absolutos",
        "Ativo (Circ + Não Circ) e Passivo + PL (Circ + Não Circ + PL). Barras empilhadas mostram a evolução absoluta.",
        datasets_abs_5, years, "Balanço Patrimonial — Absoluto"))
    # 2. Original: Balanço Completo — Composição Percentual (5-component)
    charts.append(_stacked_pct_chart(
        "Balanço Completo — Composição Percentual",
        "Mesmos componentes, normalizados para 100% por período. Mostra a mudança na estrutura do balanço.",
        datasets_pct_5, years, "Balanço Patrimonial — % Composição"))

    # ── New 9 charts (added in v7, kept in v8) ──────────────────────────
    # 3. Ativo-Passivo Circulante — Absoluto
    charts.append(_stacked_abs_chart(
        "Ativo-Passivo Circulante — Absoluto",
        "Ativo Circulante + Passivo Circulante. Barras empilhadas mostram a evolução absoluta.",
        [
            {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
            {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
        ],
        years, "Ativo-Passivo Circulante — Absoluto"))

    # 4. Ativo-Passivo Circulante — Percentual
    circ_pct = _pct(ativo_circ, passivo_circ)
    charts.append(_stacked_pct_chart(
        "Ativo-Passivo Circulante — Composição Percentual",
        "Ativo Circulante vs Passivo Circulante, normalizado para 100% por período.",
        [
            {"label": "Ativo Circulante", "data": circ_pct[0], "backgroundColor": _CIRC_A},
            {"label": "Passivo Circulante", "data": circ_pct[1], "backgroundColor": _CIRC_P},
        ],
        years, "Ativo-Passivo Circulante — % Composição"))

    # 5. Ativo-Passivo Não Circulante — Absoluto
    charts.append(_stacked_abs_chart(
        "Ativo-Passivo Não Circulante — Absoluto",
        "Ativo Não Circulante + Passivo Não Circulante. Barras empilhadas mostram a evolução absoluta.",
        [
            {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
            {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
        ],
        years, "Ativo-Passivo Não Circulante — Absoluto"))

    # 6. Ativo-Passivo Não Circulante — Percentual
    ncirc_pct = _pct(ativo_ncirc, passivo_ncirc)
    charts.append(_stacked_pct_chart(
        "Ativo-Passivo Não Circulante — Composição Percentual",
        "Ativo Não Circulante vs Passivo Não Circulante, normalizado para 100% por período.",
        [
            {"label": "Ativo Não Circulante", "data": ncirc_pct[0], "backgroundColor": _NCIRC_A},
            {"label": "Passivo Não Circulante", "data": ncirc_pct[1], "backgroundColor": _NCIRC_P},
        ],
        years, "Ativo-Passivo Não Circulante — % Composição"))

    # 7. Ativo Circulante (single bar)
    charts.append(_abs_chart(
        "Ativo Circulante",
        "Ativo Circulante ao longo do tempo. Barra simples.",
        "Ativo Circulante", ativo_circ, _CIRC_A, years))

    # 8. Ativo Não Circulante (single bar)
    charts.append(_abs_chart(
        "Ativo Não Circulante",
        "Ativo Não Circulante ao longo do tempo. Barra simples.",
        "Ativo Não Circulante", ativo_ncirc, _NCIRC_A, years))

    # 9. Passivo Circulante (single bar)
    charts.append(_abs_chart(
        "Passivo Circulante",
        "Passivo Circulante ao longo do tempo. Barra simples.",
        "Passivo Circulante", passivo_circ, _CIRC_P, years))

    # 10. Passivo Não Circulante (single bar)
    charts.append(_abs_chart(
        "Passivo Não Circulante",
        "Passivo Não Circulante ao longo do tempo. Barra simples.",
        "Passivo Não Circulante", passivo_ncirc, _NCIRC_P, years))

    # 11. Patrimônio Líquido (single bar)
    charts.append(_abs_chart(
        "Patrimônio Líquido",
        "Patrimônio Líquido ao longo do tempo. Barra simples.",
        "Patrimônio Líquido", pl, _PL, years))

    return charts


def build_balanco_decomp_charts(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
) -> list[dict]:
    """Build BPA + BPP decomposition charts: 8 charts (4 BPA + 4 BPP).

    [v9] Restored the original 2 BPA stacked charts (Ativo abs+pct) and
    2 BPP stacked charts (Passivo+PL abs+pct) that v7 removed, then keeps
    the 2 BPA single-series + 2 BPP single-series charts. Total: 8 charts.
    dashboard.py must slice as bpa=[0:4], bpp=[4:8].

    Chart order:
      BPA[0]: Ativo — Valores Absolutos (Ativo Circ + Ativo Não Circ stacked) [original]
      BPA[1]: Ativo — Composição Percentual (100% stacked) [original]
      BPA[2]: Ativo Circulante (single bar) [new]
      BPA[3]: Ativo Não Circulante (single bar) [new]
      BPP[0]: Passivo + PL — Valores Absolutos (Passivo Circ + Passivo Não Circ + PL stacked) [original]
      BPP[1]: Passivo + PL — Composição Percentual (100% stacked) [original]
      BPP[2]: Passivo Circulante (single bar) [new]
      BPP[3]: Passivo Não Circulante (single bar) [new]
    """
    bpa_by_year, bpp_by_year, years = _collect_periods(
        bpa_result, bpp_result, bpa_result_q, bpp_result_q)
    if not years:
        return []

    ativo_circ, ativo_ncirc, passivo_circ, passivo_ncirc, pl = _extract_series(
        bpa_by_year, bpp_by_year, years)

    charts: list[dict] = []

    # ── BPA: 4 charts (2 original stacked + 2 single-series) ──────────
    bpa_pct = _pct(ativo_circ, ativo_ncirc)

    # BPA[0]: Ativo — Valores Absolutos (original, 2-component stacked)
    charts.append(_stacked_abs_chart(
        "Ativo — Valores Absolutos",
        "Ativo Circulante + Ativo Não Circulante. Barras empilhadas.",
        [
            {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
            {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
        ],
        years, "Ativo — Absoluto"))

    # BPA[1]: Ativo — Composição Percentual (original, 100% stacked)
    charts.append(_stacked_pct_chart(
        "Ativo — Composição Percentual",
        "Ativo Circulante vs Não Circulante, normalizado para 100%.",
        [
            {"label": "Ativo Circulante", "data": bpa_pct[0], "backgroundColor": _CIRC_A},
            {"label": "Ativo Não Circulante", "data": bpa_pct[1], "backgroundColor": _NCIRC_A},
        ],
        years, "Ativo — % Composição"))

    # BPA[2]: Ativo Circulante (single bar, new)
    charts.append(_abs_chart(
        "Ativo Circulante",
        "Ativo Circulante ao longo do tempo. Barra simples.",
        "Ativo Circulante", ativo_circ, _CIRC_A, years))

    # BPA[3]: Ativo Não Circulante (single bar, new)
    charts.append(_abs_chart(
        "Ativo Não Circulante",
        "Ativo Não Circulante ao longo do tempo. Barra simples.",
        "Ativo Não Circulante", ativo_ncirc, _NCIRC_A, years))

    # ── BPP: 4 charts (2 original stacked + 2 single-series) ──────────
    bpp_pct = _pct(passivo_circ, passivo_ncirc, pl)

    # BPP[0]: Passivo + PL — Valores Absolutos (original, 3-component stacked)
    charts.append(_stacked_abs_chart(
        "Passivo + PL — Valores Absolutos",
        "Passivo Circulante + Passivo Não Circulante + Patrimônio Líquido. Barras empilhadas.",
        [
            {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
            {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
            {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": _PL},
        ],
        years, "Passivo + PL — Absoluto"))

    # BPP[1]: Passivo + PL — Composição Percentual (original, 100% stacked)
    charts.append(_stacked_pct_chart(
        "Passivo + PL — Composição Percentual",
        "Passivo Circulante vs Não Circulante vs PL, normalizado para 100%.",
        [
            {"label": "Passivo Circulante", "data": bpp_pct[0], "backgroundColor": _CIRC_P},
            {"label": "Passivo Não Circulante", "data": bpp_pct[1], "backgroundColor": _NCIRC_P},
            {"label": "Patrimônio Líquido", "data": bpp_pct[2], "backgroundColor": _PL},
        ],
        years, "Passivo + PL — % Composição"))

    # BPP[2]: Passivo Circulante (single bar, new)
    charts.append(_abs_chart(
        "Passivo Circulante",
        "Passivo Circulante ao longo do tempo. Barra simples.",
        "Passivo Circulante", passivo_circ, _CIRC_P, years))

    # BPP[3]: Passivo Não Circulante (single bar, new)
    charts.append(_abs_chart(
        "Passivo Não Circulante",
        "Passivo Não Circulante ao longo do tempo. Barra simples.",
        "Passivo Não Circulante", passivo_ncirc, _NCIRC_P, years))

    return charts
