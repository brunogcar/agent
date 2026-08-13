"""skills/cvm/financials/report/balanco.py -- Balanço tab builders.

Builds the Balanço tab (BPA + BPP + Completo subtabs with multi-period
comparison tables + per-subtab stacked-bar charts).

Public builders:
  - ``build_balanco_section(bpa_result, bpp_result, ...)`` — top-level
    subtabs section with Completo / BPA / BPP sub-tabs, each wrapped in a
    period_toggle (annual + quarterly).
  - ``build_balanco_chart(bpa_result, bpp_result, ...)`` — 2 stacked-bar
    charts (absolute + percentage) for the Completo view.
  - ``build_balanco_decomp_charts(bpa_result, bpp_result, ...)`` — 4 charts
    (BPA abs+pct + BPP abs+pct) for the decomposition view.
"""
from __future__ import annotations

from skills.cvm.financials.report._helpers import _num_or_none
from skills.cvm.financials.report.statements import (
    _merge_bpa_bpp_periods,
    _build_period_toggle_sections,
)


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
    respectively. The 6 stacked-bar charts (2 Completo + 2 BPA + 2 BPP,
    each with absolute + percentage variants) are now passed into
    ``_build_period_toggle_sections`` so they switch with the toggle.
    Removed the dashboard's separate ``balanco_sections.extend(charts)``
    calls — those charts now live inside the toggle.

    [v1.24] Quarterly support:
      - Accepts optional ``bpa_result_q`` / ``bpp_result_q`` (quarterly
        statement results from ``_fetch_all_statements(period="quarterly")``).
      - Each sub-tab (Completo / BPA / BPP) wraps its multi-period table in a
        ``type: "period_toggle"`` section so the user can switch between
        annual + quarterly views. When no quarterly data is provided, the
        toggle is omitted (backward-compatible with v1.23 callers).
      - Removed the single-period ``_statement_table_section()`` call — the
        multi-period table is now the ONLY table per sub-tab. The Completo
        sub-tab now uses ``build_multi_period_table()`` with merged BPA+BPP
        periods (was a single-period merge in v1.23).
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


def build_balanco_chart(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
) -> list[dict]:
    """Build the Balanço Completo charts: absolute + percentage stacked bars.

    [v1.22 v2] REWRITE per user reference images:
    - 2 stacked bar charts (not line charts):
      1. Absolute values: 5 components stacked (Ativo Circ, Ativo Não Circ,
         Passivo Circ, Passivo Não Circ, PL)
      2. 100% percentage composition: same 5 components, normalized to 100%
    - Colors match reference: Navy blue (Ativo Circ), Light blue (Ativo Não
      Circ), Dark red (Passivo Circ), Light pink (Passivo Não Circ), Green (PL)
    - Returns a LIST of 2 chart sections (was 1 dict).

    [v1.24] Quarterly support: when ``bpa_result_q`` + ``bpp_result_q`` are
    provided, the chart uses quarterly periods (up to 20) instead of annual.
    Quarterly data shows finer-grained balance-sheet evolution. Falls back
    to annual when quarterly is unavailable.
    """
    # [v1.24] Prefer quarterly periods when available
    if bpa_result_q and bpp_result_q:
        bpa_periods = (bpa_result_q or {}).get("periods") or []
        bpp_periods = (bpp_result_q or {}).get("periods") or []
    else:
        bpa_periods = (bpa_result or {}).get("periods") or []
        bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return []

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

    # [v1.24] Sort period labels chronologically (handles both "2023" annual
    # and "2T2026" quarterly — alphabetical sort would put "1T2026" before
    # "4T2025" which is wrong).
    def _label_sort_key(lbl: str) -> tuple:
        # Quarterly labels look like "2T2026" → (year, quarter)
        if "T" in lbl and len(lbl) >= 6:
            try:
                q = int(lbl.split("T")[0])
                y = int(lbl.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                pass
        # Annual labels look like "2023" → (year, 0)
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
        return []

    def _val(accounts: dict, *codes: str) -> float | None:
        for code in codes:
            acc = accounts.get(code)
            if acc and acc.get("valor_brl") is not None:
                try:
                    return float(acc["valor_brl"])
                except (TypeError, ValueError):
                    pass
        return None

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

    # Colors matching reference images
    _CIRC_A = "#1e3a5f"      # Navy blue (Ativo Circulante)
    _NCIRC_A = "#60a5fa"     # Light blue (Ativo Não Circulante)
    _CIRC_P = "#991b1b"      # Dark red (Passivo Circulante)
    _NCIRC_P = "#fca5a5"     # Light pink (Passivo Não Circulante)
    _PL = "#22c55e"          # Green (Patrimônio Líquido)

    datasets_abs = [
        {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
        {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
        {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
        {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
        {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": _PL},
    ]

    # Compute percentage datasets (normalize each period to 100%)
    def _pct_series(*series_list):
        """Normalize multiple series to 100% per period."""
        result = []
        for i in range(len(years)):
            total = sum(s[i] or 0 for s in series_list)
            if total == 0:
                result.append([None] * len(series_list))
            else:
                result.append([(s[i] or 0) / total * 100 for s in series_list])
        # Transpose: return list of series, each with per-period values
        return [[result[i][j] for i in range(len(years))] for j in range(len(series_list))]

    pct_data = _pct_series(ativo_circ, ativo_ncirc, passivo_circ, passivo_ncirc, pl)
    datasets_pct = [
        {"label": "Ativo Circulante", "data": pct_data[0], "backgroundColor": _CIRC_A},
        {"label": "Ativo Não Circulante", "data": pct_data[1], "backgroundColor": _NCIRC_A},
        {"label": "Passivo Circulante", "data": pct_data[2], "backgroundColor": _CIRC_P},
        {"label": "Passivo Não Circulante", "data": pct_data[3], "backgroundColor": _NCIRC_P},
        {"label": "Patrimônio Líquido", "data": pct_data[4], "backgroundColor": _PL},
    ]

    return [
        {
            "type": "chart",
            "title": "Balanço Completo — Valores Absolutos",
            "description": "Ativo (Circ + Não Circ) e Passivo + PL (Circ + Não Circ + PL). Barras empilhadas mostram a evolução absoluta.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": years, "datasets": datasets_abs},
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "scales": {
                        "x": {"stacked": True},
                        "y": {"stacked": True, "ticks": {},
                              "title": {"display": True, "text": "R$"}},
                    },
                    "plugins": {
                        "title": {"display": True, "text": "Balanço Patrimonial — Absoluto"},
                        "legend": {"display": True, "position": "top"},
                    },
                },
            },
        },
        {
            "type": "chart",
            "title": "Balanço Completo — Composição Percentual",
            "description": "Mesmos componentes, normalizados para 100% por período. Mostra a mudança na estrutura do balanço.",
            "chart_data": {
                "type": "bar",
                "data": {"labels": years, "datasets": datasets_pct},
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "scales": {
                        "x": {"stacked": True},
                        "y": {"stacked": True, "min": 0, "max": 100,
                              "ticks": {"callback": "{}%"},
                              "title": {"display": True, "text": "%"}},
                    },
                    "plugins": {
                        "title": {"display": True, "text": "Balanço Patrimonial — % Composição"},
                        "legend": {"display": True, "position": "top"},
                        "tooltip": {"callbacks": {"label": "{}%"}},
                    },
                },
            },
        },
    ]


def build_balanco_decomp_charts(
    bpa_result: dict, bpp_result: dict,
    bpa_result_q: dict | None = None,
    bpp_result_q: dict | None = None,
) -> list[dict]:
    """Build BPA + BPP decomposition charts: 4 stacked bars (absolute + percentage each).

    [v1.22 v2] REWRITE per user reference images:
    - BPA: 2 charts (absolute + percentage) — Ativo Circ + Ativo Não Circ
    - BPP: 2 charts (absolute + percentage) — Passivo Circ + Passivo Não Circ + PL
    - Returns 4 chart sections total.

    [v1.24] Quarterly support: when ``bpa_result_q`` + ``bpp_result_q`` are
    provided, the chart uses quarterly periods (up to 20) instead of annual.
    Falls back to annual when quarterly is unavailable.
    """
    # [v1.24] Prefer quarterly periods when available
    if bpa_result_q and bpp_result_q:
        bpa_periods = (bpa_result_q or {}).get("periods") or []
        bpp_periods = (bpp_result_q or {}).get("periods") or []
    else:
        bpa_periods = (bpa_result or {}).get("periods") or []
        bpp_periods = (bpp_result or {}).get("periods") or []
    if not bpa_periods or not bpp_periods:
        return []

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

    # [v1.24] Sort period labels chronologically (handles both "2023" annual
    # and "2T2026" quarterly — alphabetical sort would put "1T2026" before
    # "4T2025" which is wrong).
    def _label_sort_key(lbl: str) -> tuple:
        # Quarterly labels look like "2T2026" → (year, quarter)
        if "T" in lbl and len(lbl) >= 6:
            try:
                q = int(lbl.split("T")[0])
                y = int(lbl.split("T")[1])
                return (y, q)
            except (ValueError, IndexError):
                pass
        # Annual labels look like "2023" → (year, 0)
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
        return []

    def _val(accounts: dict, *codes: str) -> float | None:
        for code in codes:
            acc = accounts.get(code)
            if acc and acc.get("valor_brl") is not None:
                try:
                    return float(acc["valor_brl"])
                except (TypeError, ValueError):
                    pass
        return None

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

    # Colors matching reference
    _CIRC_A = "#1e3a5f"      # Navy blue
    _NCIRC_A = "#60a5fa"     # Light blue
    _CIRC_P = "#991b1b"      # Dark red
    _NCIRC_P = "#fca5a5"     # Light pink
    _PL = "#22c55e"          # Green

    def _pct(*series_list):
        result = []
        for i in range(len(years)):
            total = sum(s[i] or 0 for s in series_list)
            if total == 0:
                result.append([None] * len(series_list))
            else:
                result.append([(s[i] or 0) / total * 100 for s in series_list])
        return [[result[i][j] for i in range(len(years))] for j in range(len(series_list))]

    bpa_pct = _pct(ativo_circ, ativo_ncirc)
    bpp_pct = _pct(passivo_circ, passivo_ncirc, pl)

    charts: list[dict] = []

    # BPA Absolute
    charts.append({
        "type": "chart",
        "title": "Ativo — Valores Absolutos",
        "description": "Ativo Circulante + Ativo Não Circulante. Barras empilhadas.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Ativo Circulante", "data": ativo_circ, "backgroundColor": _CIRC_A},
                {"label": "Ativo Não Circulante", "data": ativo_ncirc, "backgroundColor": _NCIRC_A},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True,
                    "title": {"display": True, "text": "R$"}}},
                "plugins": {"title": {"display": True, "text": "Ativo — Absoluto"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    # BPA Percentage
    charts.append({
        "type": "chart",
        "title": "Ativo — Composição Percentual",
        "description": "Ativo Circulante vs Não Circulante, normalizado para 100%.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Ativo Circulante", "data": bpa_pct[0], "backgroundColor": _CIRC_A},
                {"label": "Ativo Não Circulante", "data": bpa_pct[1], "backgroundColor": _NCIRC_A},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True, "min": 0, "max": 100,
                    "ticks": {"callback": "{}%"}, "title": {"display": True, "text": "%"}}},
                "plugins": {"title": {"display": True, "text": "Ativo — % Composição"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    # BPP Absolute
    charts.append({
        "type": "chart",
        "title": "Passivo + PL — Valores Absolutos",
        "description": "Passivo Circulante + Passivo Não Circulante + Patrimônio Líquido. Barras empilhadas.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Passivo Circulante", "data": passivo_circ, "backgroundColor": _CIRC_P},
                {"label": "Passivo Não Circulante", "data": passivo_ncirc, "backgroundColor": _NCIRC_P},
                {"label": "Patrimônio Líquido", "data": pl, "backgroundColor": _PL},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True,
                    "title": {"display": True, "text": "R$"}}},
                "plugins": {"title": {"display": True, "text": "Passivo + PL — Absoluto"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    # BPP Percentage
    charts.append({
        "type": "chart",
        "title": "Passivo + PL — Composição Percentual",
        "description": "Passivo Circulante vs Não Circulante vs PL, normalizado para 100%.",
        "chart_data": {
            "type": "bar",
            "data": {"labels": years, "datasets": [
                {"label": "Passivo Circulante", "data": bpp_pct[0], "backgroundColor": _CIRC_P},
                {"label": "Passivo Não Circulante", "data": bpp_pct[1], "backgroundColor": _NCIRC_P},
                {"label": "Patrimônio Líquido", "data": bpp_pct[2], "backgroundColor": _PL},
            ]},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"x": {"stacked": True}, "y": {"stacked": True, "min": 0, "max": 100,
                    "ticks": {"callback": "{}%"}, "title": {"display": True, "text": "%"}}},
                "plugins": {"title": {"display": True, "text": "Passivo + PL — % Composição"},
                            "legend": {"display": True, "position": "top"}},
            },
        },
    })

    return charts
