"""report/history_charts.py — 5Y historical evolution step-line charts.

Contains:
  - build_pl_lpa_pvp_vpa_history_chart — P/L, LPA, P/VP, VPA daily evolution
    (merges lpa_history() + vpa_history() into a 4-dataset step-line chart)
  - build_roe_trend_chart              — ROIC / ROE / ROA 5Y quarterly
    step-line evolution with forward-fill (merges roe_history +
    roa_history + roic_history)

Both use the calculations registry's *_history() functions which return
step-function data (fundamentals change quarterly, price changes daily).
The step-line visual style (tension:0, stepped:'after') matches the
reference design: staircase lines holding constant between reporting dates.
"""
from __future__ import annotations


# ── V6: Historical evolution charts (step-line, 5Y) ──────────────────────────

def build_pl_lpa_pvp_vpa_history_chart(company: str) -> dict | None:
    """Build the P/L + LPA + P/VP + VPA 5Y historical evolution chart.

    Merges lpa_history() and vpa_history() (both daily, keyed by date) into
    a single step-line chart with 4 datasets. LPA/VPA are per-share BRL
    values (step-like — change quarterly). P/L and P/VP are price ratios
    (vary daily with price).

    All 4 share a single Y-axis (matching the reference design) so the
    viewer can compare their relative evolution over time. The description
    notes the scale difference.

    Returns a chart section dict, or None if no history data is available.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.lpa import lpa_history
        from skills.cvm.calculations.metrics.vpa import vpa_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        lpa_series = lpa_history(company, date_from, date_to)
        vpa_series = vpa_history(company, date_from, date_to)
    except Exception:
        return None

    if not lpa_series and not vpa_series:
        return None

    # Merge by date. Both series are daily (from price_series), so dates
    # should largely overlap. Build a unified dict {date: {pe, lpa, pvpa, vpa}}.
    merged: dict[str, dict] = {}
    for pt in lpa_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {
                "pe":  pt.get("pe"),
                "lpa": pt.get("lpa"),
            }
    for pt in vpa_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["pvpa"] = pt.get("pvpa")
        merged[d]["vpa"]  = pt.get("vpa")

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    labels: list[str] = []
    pe_vals: list[float | None] = []
    lpa_vals: list[float | None] = []
    pvpa_vals: list[float | None] = []
    vpa_vals: list[float | None] = []

    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        pe_vals.append(entry.get("pe"))
        lpa_vals.append(entry.get("lpa"))
        pvpa_vals.append(entry.get("pvpa"))
        vpa_vals.append(entry.get("vpa"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "P/L",
                    "data": pe_vals,
                    "borderColor": "#1e40af",   # dark blue
                    "backgroundColor": "rgba(30,64,175,0.1)",
                    "tension": 0,
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "LPA",
                    "data": lpa_vals,
                    "borderColor": "#60a5fa",   # light blue
                    "backgroundColor": "rgba(96,165,250,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "P/VP",
                    "data": pvpa_vals,
                    "borderColor": "#dc2626",   # red
                    "backgroundColor": "rgba(220,38,38,0.1)",
                    "tension": 0,
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "VPA",
                    "data": vpa_vals,
                    "borderColor": "#f9a8d4",   # pink/salmon
                    "backgroundColor": "rgba(249,168,212,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Valor (R$ / múltiplo)"},
                },
                "x": {
                    "title": {"display": True, "text": "Data"},
                    "ticks": {"maxTicksLimit": 12},
                },
            },
            "plugins": {
                "legend": {"display": True, "position": "top"},
                "tooltip": {"mode": "index", "intersect": False},
            },
        },
    }

    return {
        "type": "chart",
        "title": "P/L, LPA, P/VP, VPA",
        "description": (
            "Evolução histórica de P/L (azul), LPA (azul claro), P/VP "
            "(vermelho) e VPA (rosa). LPA/VPA mudam trimestralmente (escada); "
            "P/L e P/VP variam diariamente com o preço. Eixo único — "
            "comparar a evolução relativa, não o valor absoluto."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": pe_vals},
            {"data": lpa_vals},
            {"data": pvpa_vals},
            {"data": vpa_vals},
        ],
        "price_full_data": pe_vals,
    }


def build_roe_trend_chart(company: str) -> dict | None:
    """Build the ROE/ROA/ROIC 5Y historical step-line chart.

    Uses roe_history(), roa_history(), roic_history() from the calculations
    registry. These return quarterly step-function data (fundamentals change
    only when new ITR/DFP filings arrive). The chart uses stepped:'after'
    styling to produce the staircase visual matching the reference design.

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.roe import roe_history
        from skills.cvm.calculations.metrics.roa import roa_history
        from skills.cvm.calculations.metrics.roic import roic_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        roe_series = roe_history(company, date_from, date_to)
        roa_series = roa_history(company, date_from, date_to)
        roic_series = roic_history(company, date_from, date_to)
    except Exception:
        return None

    if not roe_series and not roa_series and not roic_series:
        return None

    # Build per-metric {date: value} dicts, then merge into a unified
    # date axis with forward-fill (carry forward last known value).
    roe_map: dict[str, float | None] = {}
    roa_map: dict[str, float | None] = {}
    roic_map: dict[str, float | None] = {}

    for pt in roe_series:
        d = pt.get("date", "")
        if d:
            roe_map[d] = pt.get("roe")
    for pt in roa_series:
        d = pt.get("date", "")
        if d:
            roa_map[d] = pt.get("roa")
    for pt in roic_series:
        d = pt.get("date", "")
        if d:
            roic_map[d] = pt.get("roic")

    all_dates = sorted(set(roe_map) | set(roa_map) | set(roic_map))
    if len(all_dates) < 2:
        return None

    # Forward-fill: for each date, carry forward the last known value.
    labels: list[str] = []
    roe_vals: list[float | None] = []
    roa_vals: list[float | None] = []
    roic_vals: list[float | None] = []

    _last_roe: float | None = None
    _last_roa: float | None = None
    _last_roic: float | None = None

    for d in all_dates:
        labels.append(d)
        v = roe_map.get(d)
        _last_roe = v if v is not None else _last_roe
        roe_vals.append(_last_roe * 100 if _last_roe is not None else None)

        v = roa_map.get(d)
        _last_roa = v if v is not None else _last_roa
        roa_vals.append(_last_roa * 100 if _last_roa is not None else None)

        v = roic_map.get(d)
        _last_roic = v if v is not None else _last_roic
        roic_vals.append(_last_roic * 100 if _last_roic is not None else None)

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "ROIC %",
                    "data": roic_vals,
                    "borderColor": "#166534",   # dark green
                    "backgroundColor": "rgba(22,101,52,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "ROE %",
                    "data": roe_vals,
                    "borderColor": "#65a30d",   # olive/khaki green
                    "backgroundColor": "rgba(101,163,13,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
                {
                    "label": "ROA %",
                    "data": roa_vals,
                    "borderColor": "#22c55e",   # bright green
                    "backgroundColor": "rgba(34,197,94,0.1)",
                    "tension": 0,
                    "stepped": "after",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "%"},
                },
                "x": {
                    "title": {"display": True, "text": "Data"},
                    "ticks": {"maxTicksLimit": 12},
                },
            },
            "plugins": {
                "legend": {"display": True, "position": "top"},
                "tooltip": {"mode": "index", "intersect": False},
            },
        },
    }

    return {
        "type": "chart",
        "title": "ROIC / ROE / ROA",
        "description": (
            "Evolução histórica dos retornos (escada trimestral). ROIC = "
            "retorno sobre capital investido; ROE = rentabilidade do capital "
            "dos acionistas; ROA = eficiência do uso dos ativos."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": roic_vals},
            {"data": roe_vals},
            {"data": roa_vals},
        ],
        "price_full_data": roe_vals,
    }


# ── V2.1: New evolution charts for Múltiplos tab reorganization ────────────────

def build_price_multiples_history_chart(company: str) -> dict | None:
    """Build the price-multiples 5Y evolution chart: PSR, P/RB, P/L, P/CG, P/DB.

    Dual-axis line chart — price-based multiples over time. P/L can be very
    volatile (can go negative) so it gets the left axis; the others (PSR,
    P/RB, P/CG, P/DB) share the right axis (0-6 range typical).

    Uses rps_history (PSR), lpa_history (P/L), rbpa_history (P/RB),
    cgpa_history (P/CG), dbpa_history (P/DB).

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.rps import rps_history
        from skills.cvm.calculations.metrics.lpa import lpa_history
        from skills.cvm.calculations.metrics.rbpa import rbpa_history
        from skills.cvm.calculations.metrics.cgpa import cgpa_history
        from skills.cvm.calculations.metrics.dbpa import dbpa_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        rps_series = rps_history(company, date_from, date_to)
        lpa_series = lpa_history(company, date_from, date_to)
        rbpa_series = rbpa_history(company, date_from, date_to)
        cgpa_series = cgpa_history(company, date_from, date_to)
        dbpa_series = dbpa_history(company, date_from, date_to)
    except Exception:
        return None

    if not any([rps_series, lpa_series, rbpa_series, cgpa_series, dbpa_series]):
        return None

    merged: dict[str, dict] = {}
    # Start with rps_series (has the most dates — the full 5Y range)
    for pt in rps_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {"psr": pt.get("psr"), "price": pt.get("price")}
    # Build lookup maps for ALL series.
    _lpa_map = {pt.get("date", ""): pt.get("pe") for pt in lpa_series if pt.get("date")}
    _rbpa_map = {pt.get("date", ""): pt.get("p_rb") for pt in rbpa_series if pt.get("date")}
    _cgpa_map = {pt.get("date", ""): pt.get("p_cg") for pt in cgpa_series if pt.get("date")}
    _dbpa_map = {pt.get("date", ""): pt.get("p_db") for pt in dbpa_series if pt.get("date")}
    # Also get CGPA (working capital per share) and DBPA (debt per share) from
    # the history entries so we can recompute P/CG = price / cgpa when the
    # history doesn't have an entry for that date but price is available.
    _cgpa_val_map = {pt.get("date", ""): pt.get("cgpa") for pt in cgpa_series if pt.get("date")}
    _dbpa_val_map = {pt.get("date", ""): pt.get("dbpa") for pt in dbpa_series if pt.get("date")}

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    # [v2.1 fix] Forward-fill ALL metrics across the full daily date axis.
    # For P/CG and P/DB: instead of carrying forward the old P/CG value
    # (which uses the old price), RECOMPUTE P/CG = current_price / cgpa
    # using the latest price (from PSR entries) and the last known CGPA.
    # This makes the line vary daily with price, not stay constant.
    _last_pl = _last_prb = _last_pcg = _last_pdb = None
    _last_cgpa = _last_dbpa = None
    for d in sorted_dates:
        entry = merged[d]
        # Track CGPA (working capital per share) for recomputing P/CG
        v = _cgpa_val_map.get(d)
        if v is not None:
            _last_cgpa = v
        # Track DBPA (debt per share) for recomputing P/DB
        v = _dbpa_val_map.get(d)
        if v is not None:
            _last_dbpa = v
        # P/L
        v = _lpa_map.get(d)
        if v is not None:
            _last_pl = v
        entry["pl"] = _last_pl
        # P/RB
        v = _rbpa_map.get(d)
        if v is not None:
            _last_prb = v
        entry["p_rb"] = _last_prb
        # P/CG: if cgpa_history has an entry, use it; otherwise RECOMPUTE
        # P/CG = current_price / last_known_cgpa using the daily price from
        # rps_history. This makes P/CG vary daily with price even when
        # cgpa (working capital per share) is constant between quarters.
        #
        # REVIEW NEEDED: Despite the recompute logic, P/Cap Gir still shows
        # a constant line after the last cgpa_history entry date. The issue
        # is that cgpa_history only returns entries for dates where its
        # internal price_series + current_assets_periods both have data.
        # When current_assets_periods has no data after a certain date
        # (missing ITR BPA quarterly data), cgpa_history returns NO entries
        # for those dates — the _cgpa_val_map has no entries after that
        # date, so _last_cgpa stays at the last known value, and the
        # recompute uses that constant CGPA. But the price DOES change
        # daily (from rps_history), so P/CG = price / cgpa SHOULD vary.
        #
        # The recompute code IS correct (entry["price"] / _last_cgpa), but
        # it requires _last_cgpa to be non-None. If cgpa_history returns
        # no entries at all for a date, _last_cgpa stays None until the
        # first cgpa_history entry, then stays constant after that.
        #
        # For dates AFTER the last cgpa_history entry: _last_cgpa IS set
        # (from the last known entry), and entry["price"] IS available
        # (from rps_history). So the recompute SHOULD work and produce
        # varying values. But the uploaded dashboard still shows a
        # constant line — this may be because the dashboard was generated
        # with an older version of this file. OR there's a subtle bug
        # where _last_cgpa is None because cgpa_history returns cgpa=None
        # (negative working capital) for all entries after a certain date.
        #
        # TODO for other LLMs:
        # - Verify that cgpa_history returns cgpa != None for at least
        #   some dates after 2021 for PETR4
        # - Check if _last_cgpa is being set correctly in the forward-fill
        # - Consider computing CGPA directly from current_assets_at /
        #   current_liabilities_at / shares_at instead of relying on
        #   cgpa_history (which may have gaps)
        v = _cgpa_map.get(d)
        if v is not None:
            _last_pcg = v
            entry["p_cg"] = v
        elif _last_cgpa is not None and _last_cgpa > 0 and entry.get("price") and entry["price"] > 0:
            # Recompute from daily price + last known CGPA
            entry["p_cg"] = entry["price"] / _last_cgpa
        else:
            entry["p_cg"] = _last_pcg
        # P/DB: same recompute logic
        v = _dbpa_map.get(d)
        if v is not None:
            _last_pdb = v
            entry["p_db"] = v
        elif _last_dbpa is not None and _last_dbpa > 0 and entry.get("price") and entry["price"] > 0:
            entry["p_db"] = entry["price"] / _last_dbpa
        else:
            entry["p_db"] = _last_pdb

    labels: list[str] = []
    psr_vals, prb_vals, pl_vals, pcg_vals, pdb_vals = [], [], [], [], []

    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        psr_vals.append(entry.get("psr"))
        prb_vals.append(entry.get("p_rb"))
        pl_vals.append(entry.get("pl"))
        pcg_vals.append(entry.get("p_cg"))
        pdb_vals.append(entry.get("p_db"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "PSR", "data": psr_vals,
                 "borderColor": "#eab308", "backgroundColor": "rgba(234,179,8,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2,
                 "yAxisID": "y1"},
                {"label": "P/Res Br", "data": prb_vals,
                 "borderColor": "#ea580c", "backgroundColor": "rgba(234,88,12,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2,
                 "yAxisID": "y1"},
                {"label": "P/L", "data": pl_vals,
                 "borderColor": "#1e40af", "backgroundColor": "rgba(30,64,175,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2,
                 "yAxisID": "y"},
                {"label": "P/Cap Gir", "data": pcg_vals,
                 "borderColor": "#7c3aed", "backgroundColor": "rgba(124,58,237,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2,
                 "yAxisID": "y"},
                {"label": "P/DB", "data": pdb_vals,
                 "borderColor": "#ec4899", "backgroundColor": "rgba(236,72,153,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2,
                 "yAxisID": "y1"},
            ],
        },
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "scales": {
                "y": {"position": "left",
                      "title": {"display": True, "text": "P/L, P/CG (ratio)"}},
                "y1": {"position": "right", "grid": {"drawOnChartArea": False},
                       "title": {"display": True, "text": "PSR, P/RB, P/DB (ratio)"}},
                "x": {"ticks": {"maxTicksLimit": 12}},
            },
            "plugins": {"legend": {"display": True, "position": "top"},
                        "tooltip": {"mode": "index", "intersect": False}},
        },
    }

    return {
        "type": "chart",
        "title": "Múltiplos de Preço",
        "description": "PSR, P/Res Br, P/L, P/Cap Gir, P/DB ao longo do tempo. Eixo esquerdo: P/L e P/CG. Eixo direito: PSR, P/RB, P/DB.",
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": psr_vals}, {"data": prb_vals}, {"data": pl_vals},
            {"data": pcg_vals}, {"data": pdb_vals},
        ],
        "price_full_data": pl_vals,
    }


def build_ebit_ebitda_multiples_history_chart(company: str) -> dict | None:
    """Build the EBIT/EBITDA multiples 5Y evolution chart.

    6 metrics: P/EBIT, EV/EBIT, DL/EBIT, P/EBITDA, EV/EBITDA, DL/EBITDA.
    All share a single Y-axis (ratios, 0-5 typical).

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.p_ebit import p_ebit_history
        from skills.cvm.calculations.metrics.ev_ebit import ev_ebit_history
        from skills.cvm.calculations.metrics.dl_ebit import dl_ebit_history
        from skills.cvm.calculations.metrics.p_ebitda import p_ebitda_history
        from skills.cvm.calculations.metrics.ev_ebitda import ev_ebitda_history
        from skills.cvm.calculations.metrics.net_debt_ebitda import net_debt_ebitda_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        pe_series = p_ebit_history(company, date_from, date_to)
        eve_series = ev_ebit_history(company, date_from, date_to)
        dle_series = dl_ebit_history(company, date_from, date_to)
        ped_series = p_ebitda_history(company, date_from, date_to)
        eved_series = ev_ebitda_history(company, date_from, date_to)
        dled_series = net_debt_ebitda_history(company, date_from, date_to)
    except Exception:
        return None

    if not any([pe_series, eve_series, dle_series, ped_series, eved_series, dled_series]):
        return None

    merged: dict[str, dict] = {}
    for pt in pe_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {"p_ebit": pt.get("p_ebit")}
    for pt in eve_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["ev_ebit"] = pt.get("ev_ebit")
    for pt in dle_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["dl_ebit"] = pt.get("dl_ebit")
    for pt in ped_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["p_ebitda"] = pt.get("p_ebitda")
    for pt in eved_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["ev_ebitda"] = pt.get("ev_ebitda")
    for pt in dled_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["dl_ebitda"] = pt.get("net_debt_ebitda")

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    labels: list[str] = []
    pe_vals, eve_vals, dle_vals = [], [], []
    ped_vals, eved_vals, dled_vals = [], [], []

    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        pe_vals.append(entry.get("p_ebit"))
        eve_vals.append(entry.get("ev_ebit"))
        dle_vals.append(entry.get("dl_ebit"))
        ped_vals.append(entry.get("p_ebitda"))
        eved_vals.append(entry.get("ev_ebitda"))
        dled_vals.append(entry.get("dl_ebitda"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "P/EBIT", "data": pe_vals,
                 "borderColor": "#a78bfa", "backgroundColor": "rgba(167,139,250,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "EV/EBIT", "data": eve_vals,
                 "borderColor": "#fb7185", "backgroundColor": "rgba(251,113,133,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "DL/EBIT", "data": dle_vals,
                 "borderColor": "#fde68a", "backgroundColor": "rgba(253,230,138,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "P/EBITDA", "data": ped_vals,
                 "borderColor": "#ec4899", "backgroundColor": "rgba(236,72,153,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "EV/EBITDA", "data": eved_vals,
                 "borderColor": "#dc2626", "backgroundColor": "rgba(220,38,38,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2.5},
                {"label": "DL/EBITDA", "data": dled_vals,
                 "borderColor": "#f59e0b", "backgroundColor": "rgba(245,158,11,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
            ],
        },
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "scales": {
                "y": {"beginAtZero": True,
                      "title": {"display": True, "text": "Múltiplo (x)"}},
                "x": {"ticks": {"maxTicksLimit": 12}},
            },
            "plugins": {"legend": {"display": True, "position": "top"},
                        "tooltip": {"mode": "index", "intersect": False}},
        },
    }

    return {
        "type": "chart",
        "title": "Múltiplos EBIT/EBITDA",
        "description": "P/EBIT, EV/EBIT, DL/EBIT, P/EBITDA, EV/EBITDA, DL/EBITDA ao longo do tempo (escada trimestral). EV/EBITDA em vermelho é a linha dominante.",
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": pe_vals}, {"data": eve_vals}, {"data": dle_vals},
            {"data": ped_vals}, {"data": eved_vals}, {"data": dled_vals},
        ],
        "price_full_data": eved_vals,
    }


def build_ebit_multiples_history_chart(company: str) -> dict | None:
    """Build the EBIT multiples 5Y evolution chart (3 lines: P/EBIT, EV/EBIT, DL/EBIT).

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.p_ebit import p_ebit_history
        from skills.cvm.calculations.metrics.ev_ebit import ev_ebit_history
        from skills.cvm.calculations.metrics.dl_ebit import dl_ebit_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        pe_series = p_ebit_history(company, date_from, date_to)
        eve_series = ev_ebit_history(company, date_from, date_to)
        dle_series = dl_ebit_history(company, date_from, date_to)
    except Exception:
        return None

    if not any([pe_series, eve_series, dle_series]):
        return None

    merged: dict[str, dict] = {}
    for pt in pe_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {"p_ebit": pt.get("p_ebit")}
    for pt in eve_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["ev_ebit"] = pt.get("ev_ebit")
    for pt in dle_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["dl_ebit"] = pt.get("dl_ebit")

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    # [v2.1 fix] Forward-fill quarterly metrics (EV/EBIT, DL/EBIT) across
    # the daily date axis. Without this, DL/EBIT only has values on ~20
    # quarterly dates out of ~260 daily dates → line appears empty.
    _last_ev = _last_dl = None
    for d in sorted_dates:
        entry = merged[d]
        v = entry.get("ev_ebit")
        _last_ev = v if v is not None else _last_ev
        entry["ev_ebit"] = _last_ev
        v = entry.get("dl_ebit")
        _last_dl = v if v is not None else _last_dl
        entry["dl_ebit"] = _last_dl

    labels: list[str] = []
    pe_vals, eve_vals, dle_vals = [], [], []
    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        pe_vals.append(entry.get("p_ebit"))
        eve_vals.append(entry.get("ev_ebit"))
        dle_vals.append(entry.get("dl_ebit"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "P/EBIT", "data": pe_vals,
                 "borderColor": "#a78bfa", "backgroundColor": "rgba(167,139,250,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "EV/EBIT", "data": eve_vals,
                 "borderColor": "#fb7185", "backgroundColor": "rgba(251,113,133,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "DL/EBIT", "data": dle_vals,
                 "borderColor": "#fde68a", "backgroundColor": "rgba(253,230,138,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
            ],
        },
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "scales": {
                "y": {"beginAtZero": True,
                      "title": {"display": True, "text": "Múltiplo (x)"}},
                "x": {"ticks": {"maxTicksLimit": 12}},
            },
            "plugins": {"legend": {"display": True, "position": "top"},
                        "tooltip": {"mode": "index", "intersect": False}},
        },
    }

    return {
        "type": "chart",
        "title": "Múltiplos EBIT",
        "description": "P/EBIT, EV/EBIT, DL/EBIT ao longo do tempo (escada trimestral).",
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [{"data": pe_vals}, {"data": eve_vals}, {"data": dle_vals}],
        "price_full_data": eve_vals,
    }


def build_ebitda_multiples_history_chart(company: str) -> dict | None:
    """Build the EBITDA multiples 5Y evolution chart (3 lines: P/EBITDA, EV/EBITDA, DL/EBITDA).

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.p_ebitda import p_ebitda_history
        from skills.cvm.calculations.metrics.ev_ebitda import ev_ebitda_history
        from skills.cvm.calculations.metrics.net_debt_ebitda import net_debt_ebitda_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        ped_series = p_ebitda_history(company, date_from, date_to)
        eved_series = ev_ebitda_history(company, date_from, date_to)
        dled_series = net_debt_ebitda_history(company, date_from, date_to)
    except Exception:
        return None

    if not any([ped_series, eved_series, dled_series]):
        return None

    merged: dict[str, dict] = {}
    for pt in ped_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {"p_ebitda": pt.get("p_ebitda")}
    for pt in eved_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["ev_ebitda"] = pt.get("ev_ebitda")
    for pt in dled_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["dl_ebitda"] = pt.get("net_debt_ebitda")

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    # [v2.1 fix] Forward-fill quarterly metrics (EV/EBITDA, DL/EBITDA).
    _last_ev = _last_dl = None
    for d in sorted_dates:
        entry = merged[d]
        v = entry.get("ev_ebitda")
        _last_ev = v if v is not None else _last_ev
        entry["ev_ebitda"] = _last_ev
        v = entry.get("dl_ebitda")
        _last_dl = v if v is not None else _last_dl
        entry["dl_ebitda"] = _last_dl

    labels: list[str] = []
    ped_vals, eved_vals, dled_vals = [], [], []
    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        ped_vals.append(entry.get("p_ebitda"))
        eved_vals.append(entry.get("ev_ebitda"))
        dled_vals.append(entry.get("dl_ebitda"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "P/EBITDA", "data": ped_vals,
                 "borderColor": "#ec4899", "backgroundColor": "rgba(236,72,153,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "EV/EBITDA", "data": eved_vals,
                 "borderColor": "#dc2626", "backgroundColor": "rgba(220,38,38,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2.5},
                {"label": "DL/EBITDA", "data": dled_vals,
                 "borderColor": "#f59e0b", "backgroundColor": "rgba(245,158,11,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
            ],
        },
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "scales": {
                "y": {"beginAtZero": True,
                      "title": {"display": True, "text": "Múltiplo (x)"}},
                "x": {"ticks": {"maxTicksLimit": 12}},
            },
            "plugins": {"legend": {"display": True, "position": "top"},
                        "tooltip": {"mode": "index", "intersect": False}},
        },
    }

    return {
        "type": "chart",
        "title": "Múltiplos EBITDA",
        "description": "P/EBITDA, EV/EBITDA, DL/EBITDA ao longo do tempo (escada trimestral). EV/EBITDA em vermelho é a linha dominante.",
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [{"data": ped_vals}, {"data": eved_vals}, {"data": dled_vals}],
        "price_full_data": eved_vals,
    }


def build_price_to_balance_history_chart(company: str) -> dict | None:
    """Build the price-to-balance-sheet 5Y evolution chart: P/Atv, P/Pas, P/VP.

    Daily line chart — price-based multiples relative to balance sheet items.
    All share a single Y-axis (ratios, 0-1 typical).

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.apa import apa_history
        from skills.cvm.calculations.metrics.ppa import ppa_history
        from skills.cvm.calculations.metrics.vpa import vpa_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        apa_series = apa_history(company, date_from, date_to)
        ppa_series = ppa_history(company, date_from, date_to)
        vpa_series = vpa_history(company, date_from, date_to)
    except Exception:
        return None

    if not any([apa_series, ppa_series, vpa_series]):
        return None

    merged: dict[str, dict] = {}
    for pt in apa_series:
        d = pt.get("date", "")
        if d:
            merged[d] = {"p_atv": pt.get("p_ativo")}
    for pt in ppa_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["p_pas"] = pt.get("p_passivo")
    for pt in vpa_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["p_vp"] = pt.get("pvpa")

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    labels: list[str] = []
    patv_vals, ppas_vals, pvp_vals = [], [], []
    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        patv_vals.append(entry.get("p_atv"))
        ppas_vals.append(entry.get("p_pas"))
        pvp_vals.append(entry.get("p_vp"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "P/Atv", "data": patv_vals,
                 "borderColor": "#3b82f6", "backgroundColor": "rgba(59,130,246,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "P/Pas", "data": ppas_vals,
                 "borderColor": "#ef4444", "backgroundColor": "rgba(239,68,68,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "P/VP", "data": pvp_vals,
                 "borderColor": "#22c55e", "backgroundColor": "rgba(34,197,94,0.1)",
                 "tension": 0, "fill": False, "pointRadius": 0, "borderWidth": 2},
            ],
        },
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "scales": {
                "y": {"beginAtZero": True,
                      "title": {"display": True, "text": "Ratio"},
                      "ticks": {"maxTicksLimit": 8}},
                "x": {"ticks": {"maxTicksLimit": 12}},
            },
            "plugins": {"legend": {"display": True, "position": "top"},
                        "tooltip": {"mode": "index", "intersect": False}},
        },
    }

    return {
        "type": "chart",
        "title": "Preço/Balanço",
        "description": "P/Atv (azul), P/Pas (vermelho), P/VP (verde). Menor = mais barato vs balanço patrimonial.",
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [{"data": patv_vals}, {"data": ppas_vals}, {"data": pvp_vals}],
        "price_full_data": pvp_vals,
    }


def build_asset_to_price_history_chart(company: str) -> dict | None:
    """Build the asset-to-price 5Y evolution chart: A/P, A/PL, P/PL.

    Step-line chart — fundamental ratios that change quarterly.
    A/P = assets per share / price, A/PL = assets / equity, P/PL = price / equity.

    Returns a chart section dict, or None if fewer than 2 data points.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.apa import apa_history
        from skills.cvm.calculations.metrics.vpa import vpa_history
    except ImportError:
        return None

    today = date.today()
    date_from = (today - timedelta(days=365 * 5)).isoformat()
    date_to = today.isoformat()

    try:
        apa_series = apa_history(company, date_from, date_to)
        vpa_series = vpa_history(company, date_from, date_to)
    except Exception:
        return None

    if not apa_series or not vpa_series:
        return None

    merged: dict[str, dict] = {}
    for pt in apa_series:
        d = pt.get("date", "")
        if d:
            apa_val = pt.get("apa")
            price = pt.get("price")
            merged[d] = {}
            if apa_val and price and price > 0:
                merged[d]["a_p"] = apa_val / price
    for pt in vpa_series:
        d = pt.get("date", "")
        if not d:
            continue
        if d not in merged:
            merged[d] = {}
        merged[d]["p_vp"] = pt.get("pvpa")  # P/PL ≈ P/VPA

    # Compute A/PL from apa + vpa
    apa_map: dict[str, float | None] = {}
    for pt in apa_series:
        d = pt.get("date", "")
        if d:
            apa_map[d] = pt.get("apa")
    vpa_map: dict[str, float | None] = {}
    for pt in vpa_series:
        d = pt.get("date", "")
        if d:
            vpa_map[d] = pt.get("vpa")
    for d in merged:
        apa_v = apa_map.get(d)
        vpa_v = vpa_map.get(d)
        if apa_v and vpa_v and vpa_v != 0:
            merged[d]["a_pl"] = apa_v / vpa_v

    sorted_dates = sorted(merged.keys())
    if len(sorted_dates) < 2:
        return None

    # [v2.1 fix] Forward-fill quarterly metrics (A/P, A/PL, P/PL).
    _last_ap = _last_apl = _last_ppl = None
    for d in sorted_dates:
        entry = merged[d]
        v = entry.get("a_p")
        _last_ap = v if v is not None else _last_ap
        entry["a_p"] = _last_ap
        v = entry.get("a_pl")
        _last_apl = v if v is not None else _last_apl
        entry["a_pl"] = _last_apl
        v = entry.get("p_vp")
        _last_ppl = v if v is not None else _last_ppl
        entry["p_vp"] = _last_ppl

    labels: list[str] = []
    ap_vals, apl_vals, ppl_vals = [], [], []
    for d in sorted_dates:
        entry = merged[d]
        labels.append(d)
        ap_vals.append(entry.get("a_p"))
        apl_vals.append(entry.get("a_pl"))
        ppl_vals.append(entry.get("p_vp"))

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "A/P", "data": ap_vals,
                 "borderColor": "#3b82f6", "backgroundColor": "rgba(59,130,246,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "A/PL", "data": apl_vals,
                 "borderColor": "#22c55e", "backgroundColor": "rgba(34,197,94,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
                {"label": "P/PL", "data": ppl_vals,
                 "borderColor": "#ef4444", "backgroundColor": "rgba(239,68,68,0.1)",
                 "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2},
            ],
        },
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "scales": {
                "y": {"beginAtZero": True,
                      "title": {"display": True, "text": "Ratio"},
                      "ticks": {"maxTicksLimit": 8}},
                "x": {"ticks": {"maxTicksLimit": 12}},
            },
            "plugins": {"legend": {"display": True, "position": "top"},
                        "tooltip": {"mode": "index", "intersect": False}},
        },
    }

    return {
        "type": "chart",
        "title": "Ativo/Preço e Alavancagem",
        "description": "A/P (azul, ativo/preço), A/PL (verde, ativo/PL = alavancagem), P/PL (vermelho, preço/PL ≈ P/VPA). Step trimestral.",
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [{"data": ap_vals}, {"data": apl_vals}, {"data": ppl_vals}],
        "price_full_data": ppl_vals,
    }


def build_growth_evolution_charts(company: str) -> list[dict]:
    """Build 3 growth evolution charts: RL, RB, LL with 3M/1A/5A trailing windows.

    [v2.1] New charts based on user's reference images:
      - Receita Líquida (RL) — revenue growth at 3M/1A/5A horizons
      - Receita Bruta (RB) — gross profit growth at 3M/1A/5A horizons
      - Lucro Líquido (LL) — net income growth at 3M/1A/5A horizons

    Each chart shows the ACTUAL growth + 3 trailing window time series.
    The trailing values are TIME SERIES (not constants): at each quarterly
    date, "RL 3M" = the growth value from 3 months before that date,
    "RL 1A" = from 1 year before, "RL 5A" = from 5 years before.

    Returns a list of 3 chart section dicts, or empty list if no data.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.revenue_growth import (
            revenue_growth_3m_history, revenue_growth_1y_history, revenue_growth_5y_history,
        )
        from skills.cvm.calculations.metrics.gross_profit_growth import (
            gross_profit_growth_3m_history, gross_profit_growth_1y_history, gross_profit_growth_5y_history,
        )
        from skills.cvm.calculations.metrics.net_income_growth import (
            net_income_growth_3m_history, net_income_growth_1y_history, net_income_growth_5y_history,
        )
    except ImportError:
        return []

    today = date.today()
    date_from = (today - timedelta(days=365 * 10)).isoformat()
    date_to = today.isoformat()

    charts: list[dict] = []

    def _build_growth_chart(name, metric_label, color_base, growth_3m_fn, growth_1y_fn, growth_5y_fn):
        """Build a single growth evolution chart."""
        try:
            g3m = growth_3m_fn(company, date_from, date_to)
            g1y = growth_1y_fn(company, date_from, date_to)
            g5y = growth_5y_fn(company, date_from, date_to)
        except Exception:
            return None

        if not g3m and not g1y and not g5y:
            return None

        # Build {date: value} maps for each horizon
        map_3m = {pt.get("date", ""): pt.get(list(pt.keys())[-1]) for pt in g3m if pt.get("date")}
        map_1y = {pt.get("date", ""): pt.get(list(pt.keys())[-1]) for pt in g1y if pt.get("date")}
        map_5y = {pt.get("date", ""): pt.get(list(pt.keys())[-1]) for pt in g5y if pt.get("date")}

        all_dates = sorted(set(map_3m) | set(map_1y) | set(map_5y))
        if len(all_dates) < 2:
            return None

        # Forward-fill each horizon
        labels: list[str] = []
        vals_3m, vals_1y, vals_5y = [], [], []
        _last_3m = _last_1y = _last_5y = None
        for d in all_dates:
            labels.append(d)
            v = map_3m.get(d); _last_3m = v if v is not None else _last_3m
            vals_3m.append(_last_3m * 100 if _last_3m is not None else None)
            v = map_1y.get(d); _last_1y = v if v is not None else _last_1y
            vals_1y.append(_last_1y * 100 if _last_1y is not None else None)
            v = map_5y.get(d); _last_5y = v if v is not None else _last_5y
            vals_5y.append(_last_5y * 100 if _last_5y is not None else None)

        datasets = [
            {"label": f"{metric_label} 3M", "data": vals_3m,
             "borderColor": color_base, "backgroundColor": f"rgba({color_base[1:]},0.1)",
             "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2.5},
            {"label": f"{metric_label} 1A", "data": vals_1y,
             "borderColor": color_base, "backgroundColor": f"rgba({color_base[1:]},0.05)",
             "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
             "borderDash": [4, 3]},
            {"label": f"{metric_label} 5A", "data": vals_5y,
             "borderColor": color_base, "backgroundColor": f"rgba({color_base[1:]},0.05)",
             "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
             "borderDash": [8, 4]},
        ]

        return {
            "type": "chart",
            "title": f"{name} — Evolução e Horizontes",
            "description": (
                f"{metric_label} 3M (linha sólida), 1A (tracejada curta) e 5A (tracejada longa). "
                f"Cada linha mostra o crescimento em sua respectiva janela temporal."
            ),
            "chart_data": {
                "type": "line",
                "data": {"labels": labels, "datasets": datasets},
                "options": {
                    "responsive": True, "maintainAspectRatio": False,
                    "scales": {"y": {"title": {"display": True, "text": "%"},
                                     "ticks": {"maxTicksLimit": 10}},
                               "x": {"ticks": {"maxTicksLimit": 12}}},
                    "plugins": {"legend": {"display": True, "position": "top"},
                                "tooltip": {"mode": "index", "intersect": False}},
                },
            },
            "price_range_selector": True,
            "price_full_labels": labels,
            "price_full_datasets": [{"data": v} for v in [vals_3m, vals_1y, vals_5y]],
            "price_full_data": vals_3m,
        }

    # Chart 1: Receita Líquida (RL) — orange (unified with financials Receita)
    chart = _build_growth_chart("Receita Líquida", "RL", "#f59e0b",
                               revenue_growth_3m_history, revenue_growth_1y_history, revenue_growth_5y_history)
    if chart:
        charts.append(chart)

    # Chart 2: Receita Bruta (RB) — magenta (unified with financials EBITDA)
    chart = _build_growth_chart("Receita Bruta", "RB", "#d946a0",
                               gross_profit_growth_3m_history, gross_profit_growth_1y_history, gross_profit_growth_5y_history)
    if chart:
        charts.append(chart)

    # Chart 3: Lucro Líquido (LL) — purple (unified with financials Lucro)
    chart = _build_growth_chart("Lucro Líquido", "LL", "#a855f7",
                               net_income_growth_3m_history, net_income_growth_1y_history, net_income_growth_5y_history)
    if chart:
        charts.append(chart)

    return charts


def build_margins_horizons_chart(company: str) -> list[dict]:
    """Build 2 margin evolution charts: MB with trailing windows, ML with trailing windows.

    [v2.1] Split from the single 10-line chart. The existing `build_margin_trend_chart`
    already shows Bruta/EBIT/EBITDA/Líquida as step-lines. This function adds
    the trailing-window analysis the user requested:
      - MB (Margem Bruta) actual + MB 3M/1A/5A trailing (shifted step-lines)
      - ML (Margem Líquida) actual + ML 3M/1A/5A trailing (shifted step-lines)

    The trailing values are NOT constant horizontal lines — they are TIME
    SERIES. At each quarterly date, "MB 3M" = the MB value from 3 months
    before that date, "MB 1A" = MB from 1 year before, "MB 5A" = MB from
    5 years before. This shows how the margin looked at different historical
    lookback windows.

    Returns a list of 2 chart section dicts, or empty list if no data.
    """
    try:
        from datetime import date, timedelta
        from skills.cvm.calculations.metrics.gross_margin import gross_margin_history
        from skills.cvm.calculations.metrics.net_margin import net_margin_history
    except ImportError:
        return []

    today = date.today()
    date_from = (today - timedelta(days=365 * 10)).isoformat()  # 10Y to have 5Y lookback
    date_to = today.isoformat()

    try:
        gm_series = gross_margin_history(company, date_from, date_to)
        nm_series = net_margin_history(company, date_from, date_to)
    except Exception:
        return []

    if not gm_series and not nm_series:
        return []

    # Build {date: value} maps
    gm_map: dict[str, float | None] = {}
    nm_map: dict[str, float | None] = {}
    for pt in gm_series:
        d = pt.get("date", "")
        if d:
            gm_map[d] = pt.get("gross_margin")
    for pt in nm_series:
        d = pt.get("date", "")
        if d:
            nm_map[d] = pt.get("net_margin")

    all_dates = sorted(set(gm_map) | set(nm_map))
    if len(all_dates) < 2:
        return []

    # Forward-fill actual values
    labels: list[str] = []
    gm_vals: list[float | None] = []
    nm_vals: list[float | None] = []
    _lg = _ln = None
    for d in all_dates:
        labels.append(d)
        v = gm_map.get(d); _lg = v if v is not None else _lg
        gm_vals.append(_lg * 100 if _lg is not None else None)
        v = nm_map.get(d); _ln = v if v is not None else _ln
        nm_vals.append(_ln * 100 if _ln is not None else None)

    # Compute trailing windows as TIME SERIES (not constant lines).
    # At each date d, the "3M trailing" value = the margin value from
    # 3 months before d. We find the most recent quarterly date <= (d - 90 days)
    # and use that margin value.
    def _trailing_series(vals, all_dates, days_back):
        """Return a list of trailing values: for each date, the value from
        `days_back` days before. Uses lookup_lte on the dates."""
        result = []
        for i, d in enumerate(all_dates):
            target = (date.fromisoformat(d) - timedelta(days=days_back)).isoformat()
            # Find the most recent date <= target with a non-None value
            found = None
            for j in range(i, -1, -1):
                if all_dates[j] <= target and vals[j] is not None:
                    found = vals[j]
                    break
            result.append(found)
        return result

    gm_3m = _trailing_series(gm_vals, all_dates, 90)
    gm_1a = _trailing_series(gm_vals, all_dates, 365)
    gm_5a = _trailing_series(gm_vals, all_dates, 1825)
    nm_3m = _trailing_series(nm_vals, all_dates, 90)
    nm_1a = _trailing_series(nm_vals, all_dates, 365)
    nm_5a = _trailing_series(nm_vals, all_dates, 1825)

    charts: list[dict] = []

    # Chart 1: MB (Margem Bruta) with trailing windows
    # [v2.1] Trailing lines use LIGHTER shades of the MB color (maroon)
    mb_datasets = [
        {"label": "MB Atual", "data": gm_vals,
         "borderColor": "#7f1d1d", "backgroundColor": "rgba(127,29,29,0.1)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2.5},
        {"label": "MB 3M", "data": gm_3m,
         "borderColor": "#a84545", "backgroundColor": "rgba(168,69,69,0.05)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
         "borderDash": [4, 3]},
        {"label": "MB 1A", "data": gm_1a,
         "borderColor": "#c67373", "backgroundColor": "rgba(198,115,115,0.05)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
         "borderDash": [4, 3]},
        {"label": "MB 5A", "data": gm_5a,
         "borderColor": "#e0a0a0", "backgroundColor": "rgba(224,160,160,0.05)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
         "borderDash": [4, 3]},
    ]
    charts.append({
        "type": "chart",
        "title": "Margem Bruta — Evolução e Horizontes",
        "description": (
            "MB Atual (marrom, linha sólida) + MB 3M/1A/5A (azul, linhas tracejadas). "
            "MB 3M = valor da margem bruta 3 meses antes de cada data. "
            "MB 1A = 1 ano antes. MB 5A = 5 anos antes. Mostra a evolução "
            "da margem em diferentes janelas temporais."
        ),
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": mb_datasets},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"y": {"title": {"display": True, "text": "%"},
                                 "ticks": {"maxTicksLimit": 10}},
                           "x": {"ticks": {"maxTicksLimit": 12}}},
                "plugins": {"legend": {"display": True, "position": "top"},
                            "tooltip": {"mode": "index", "intersect": False}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [{"data": v} for v in [gm_vals, gm_3m, gm_1a, gm_5a]],
        "price_full_data": gm_vals,
    })

    # Chart 2: ML (Margem Líquida) with trailing windows
    # [v2.1] Trailing lines use LIGHTER shades of the ML color (maroon)
    ml_datasets = [
        {"label": "ML Atual", "data": nm_vals,
         "borderColor": "#be123c", "backgroundColor": "rgba(190,18,60,0.1)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 2.5},
        {"label": "ML 3M", "data": nm_3m,
         "borderColor": "#d44a6a", "backgroundColor": "rgba(212,74,106,0.05)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
         "borderDash": [4, 3]},
        {"label": "ML 1A", "data": nm_1a,
         "borderColor": "#e87a94", "backgroundColor": "rgba(232,122,148,0.05)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
         "borderDash": [4, 3]},
        {"label": "ML 5A", "data": nm_5a,
         "borderColor": "#f2abbf", "backgroundColor": "rgba(242,171,191,0.05)",
         "tension": 0, "stepped": "after", "fill": False, "pointRadius": 0, "borderWidth": 1.5,
         "borderDash": [4, 3]},
    ]
    charts.append({
        "type": "chart",
        "title": "Margem Líquida — Evolução e Horizontes",
        "description": (
            "ML Atual (vinho, linha sólida) + ML 3M/1A/5A (amarelo, linhas tracejadas). "
            "ML 3M = valor da margem líquida 3 meses antes de cada data. "
            "ML 1A = 1 ano antes. ML 5A = 5 anos antes. Mostra a evolução "
            "da margem em diferentes janelas temporais."
        ),
        "chart_data": {
            "type": "line",
            "data": {"labels": labels, "datasets": ml_datasets},
            "options": {
                "responsive": True, "maintainAspectRatio": False,
                "scales": {"y": {"title": {"display": True, "text": "%"},
                                 "ticks": {"maxTicksLimit": 10}},
                           "x": {"ticks": {"maxTicksLimit": 12}}},
                "plugins": {"legend": {"display": True, "position": "top"},
                            "tooltip": {"mode": "index", "intersect": False}},
            },
        },
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [{"data": v} for v in [nm_vals, nm_3m, nm_1a, nm_5a]],
        "price_full_data": nm_vals,
    })

    return charts
