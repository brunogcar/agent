"""tests/webui/test_historical_v124.py — the v1.24 Histórico suite.

Focused (the user's v1.24 ask: "no need to worry too much about the
tests, just add important ones if really needed"). HAND-COMPUTED values
(the v1.22.1 discipline):

  1.  METRIC DEFS integrity — 17 metrics, unique names, valid
      directions/categories, KPI + chart rosters ⊆ defs.
  2.  _verdict — the direction-aware coloring: P/L 93º = "Cara vs
      histórico" RED (low is favorable, high percentile = bad) vs
      ROE 90º = "Acima da faixa" GREEN (high is favorable) vs
      Dívida/PL 10º = "Abaixo da faixa" GREEN (low = good). This is
      the fix the static dashboard's language lacked (it said "cheap"
      for ANY low percentile — nonsense for ROE/DY).
  3.  _month_end — month-end downsampling keeps the LAST valid
      observation per month, skips None, sorts.
  4.  THE HEATMAP — P/L fixture (series 5,6,7,8,10 → quartiles
      5/6/7/8/10 via the REAL compute_quartiles): row = label+tooltip,
      Atual "10,00" colored by the 80º verdict, Percentil "80,0º",
      Leitura "Cara vs histórico"; the degraded metric (error summary)
      renders "—"/"—".
  5.  THE BAND CHART — datasets [Faixa (fill '+1', visible), Faixa máx
      (hideLegend), Mediana (dashed), the metric]; labels YYYY-MM; pct
      metrics ship ×100 + tooltipUnit "%" (no double-scaling — the
      2294,00% bug).
  6.  TREND MATH — Δ = (atual − média)/média: (10−8)/8 = +25,00%,
      (10−12)/12 = −16,67%, (10−15)/15 = −33,33%.
  7.  LEVERAGE ADVANCED — patched WACC/DuPont/Altman: "15,89%",
      "22,94%", "2.42 (Cinza)".
  8.  PAYLOAD CONTRACT — overview {kpis 6, heatmap, trend COLLAPSED},
      valuation 4 charts + trend, degradation → _error.
  9.  HTTP — the generic /sections/historical:{overview,valuation}
      endpoint + the tab shell fragment + the page route.

Run:  python -m pytest tests/webui/test_historical_v124.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.historical as hmod                  # noqa: E402
from webui.services.historical import (                   # noqa: E402
    HistoricalService, _METRIC_DEFS, _GOOD, _BAD, _NEUTRAL,
)


# ── the mocked seam ─────────────────────────────────────────────────────────
# The service imports summary/resolve_metric/compute_quartiles INSIDE its
# methods (the valuation-service pattern) — patching the source modules
# covers every call site. compute_quartiles stays REAL (hand-checkable).

class _Spec(SimpleNamespace):
    """The MetricSpec subset the service touches."""
    def __init__(self, ratio_key, history_fn, allow_negative=False):
        super().__init__(
            ratio_key=ratio_key, history_fn=history_fn,
            allow_negative=allow_negative, name=ratio_key,
            ratio_label=ratio_key, per_share_key=None,
            per_share_label=None,
        )


# P/L daily series across 3 months — month-ends 6.0 / 8.0 / 10.0.
# compute_quartiles([5,6,7,8,10]) = min 5, p25 6, mediana 7, p75 8, máx 10.
_PL_SERIES = [
    {"date": "2026-01-05", "pe": 5.0},
    {"date": "2026-01-28", "pe": 6.0},
    {"date": "2026-02-10", "pe": 7.0},
    {"date": "2026-02-25", "pe": 8.0},
    {"date": "2026-03-15", "pe": 10.0},
]
_PL_SUMMARY = {
    "status": "ok",
    "current": {"date": "2026-03-15", "pe": 10.0},
    "averages": {"1y": 8.0, "3y": 12.0, "5y": 15.0},
    "percentile": 80.0,
}

# Dividend Yield — a pct, high-is-favorable metric. Fractions, as the
# real engines emit them (0.05 = 5%). Series has a None (skipped).
_DY_SERIES = [
    {"date": "2026-01-20", "dy": 0.03},
    {"date": "2026-01-31", "dy": 0.04},
    {"date": "2026-02-15", "dy": None},
    {"date": "2026-02-27", "dy": 0.045},
    {"date": "2026-03-15", "dy": 0.05},
]
_DY_SUMMARY = {
    "status": "ok",
    "current": {"date": "2026-03-15", "dy": 0.05},
    "averages": {"1y": 0.04, "3y": 0.045, "5y": 0.05},
    "percentile": 90.0,
}

_ERROR_SUMMARY = {"status": "error", "error": "boom"}


def _fake_summary(company="", metric="lpa", months=60):
    """Dispatch table: lpa/dpa hand-fixtures; inventory_turnover fails
    (the degraded row); everything else a generic ok."""
    if metric == "lpa":
        return dict(_PL_SUMMARY)
    if metric == "dpa":
        return dict(_DY_SUMMARY)
    if metric == "inventory_turnover":
        return dict(_ERROR_SUMMARY)
    pct = hmod._METRICS_BY_NAME[metric][2] == "pct"
    cur = 0.10 if pct else 10.0
    return {
        "status": "ok",
        "current": {"date": "2026-03-15", "x": cur},
        "averages": {"1y": cur, "3y": cur, "5y": cur},
        "percentile": 50.0,
    }


def _fake_history(company, date_from, date_to):
    """One series per metric kind (ratio / pct), keyed by closure."""
    def fn(_company, _from, _to):
        return list(series)
    return fn


def _fake_resolve_metric(name):
    if name == "lpa":
        return _Spec("pe", lambda c, f, t: list(_PL_SERIES))
    if name == "dpa":
        return _Spec("dy", lambda c, f, t: list(_DY_SERIES))
    pct = hmod._METRICS_BY_NAME[name][2] == "pct" if name in \
        hmod._METRICS_BY_NAME else False
    base = 0.10 if pct else 10.0
    series = [
        {"date": "2026-01-10", "x": base},
        {"date": "2026-01-31", "x": base},
        {"date": "2026-02-12", "x": base * 1.1},
        {"date": "2026-02-27", "x": base * 1.1},
        {"date": "2026-03-15", "x": base * 1.2},
    ]
    return _Spec("x", lambda c, f, t: list(series))


@pytest.fixture()
def mocked(monkeypatch):
    """Patch the summary/resolve_metric seam + the advanced trio."""
    import skills.cvm.historical.modes.summary as summod
    import skills.cvm.calculations._registry as regmod
    monkeypatch.setattr(summod, "summary", _fake_summary)
    monkeypatch.setattr(regmod, "resolve_metric", _fake_resolve_metric)
    import skills.cvm.calculations.metrics.wacc as wmod
    import skills.cvm.calculations.metrics.dupont as dmod
    import skills.cvm.calculations.metrics.altman_z as amod
    monkeypatch.setattr(wmod, "wacc_at", lambda c, d: 0.1589)
    monkeypatch.setattr(dmod, "dupont_at", lambda c, d: 0.2294)
    monkeypatch.setattr(amod, "altman_z_at", lambda c, d: 2.42)
    return HistoricalService()


# ── 1. metric defs integrity ────────────────────────────────────────────────

def test_metric_defs_integrity():
    assert len(_METRIC_DEFS) == 17
    names = [m[0] for m in _METRIC_DEFS]
    assert len(names) == len(set(names))
    assert all(m[3] in hmod._CATEGORY_LABELS for m in _METRIC_DEFS)
    assert all(m[4] in ("low", "high") for m in _METRIC_DEFS)
    assert all(m[2] in ("ratio", "pct") for m in _METRIC_DEFS)
    # every roster ⊆ defs
    for n, _l in hmod._KPI_METRICS:
        assert n in hmod._METRICS_BY_NAME
    for roster in (hmod._VALUATION_CHARTS, hmod._PROFIT_CHARTS,
                   hmod._LEVERAGE_CHARTS):
        assert all(n in hmod._METRICS_BY_NAME for n in roster)
    # the P/L family reads low; the returns family reads high
    assert hmod._METRICS_BY_NAME["lpa"][4] == "low"
    assert hmod._METRICS_BY_NAME["dpa"][4] == "high"
    assert hmod._METRICS_BY_NAME["debt_equity"][4] == "low"
    assert hmod._METRICS_BY_NAME["roe"][4] == "high"


# ── 2. _verdict — the direction-aware coloring ─────────────────────────────

def test_verdict_direction_aware():
    v = HistoricalService._verdict
    # P/L (low + valuation): the Barata/Cara language.
    assert v("low", 10.0, True) == ("Barata vs histórico", _GOOD)
    assert v("low", 90.0, True) == ("Cara vs histórico", _BAD)
    assert v("low", 50.0, True) == ("Na faixa", _NEUTRAL)
    # ROE (high): high percentile is the GOOD side.
    assert v("high", 90.0, False) == ("Acima da faixa", _GOOD)
    assert v("high", 10.0, False) == ("Abaixo da faixa", _BAD)
    # Dívida/PL (low, non-valuation): low percentile is good, but the
    # language is faixa-based, not price-based.
    assert v("low", 10.0, False) == ("Abaixo da faixa", _GOOD)
    assert v("low", 90.0, False) == ("Acima da faixa", _BAD)
    # boundaries: exactly 25 / 75 land in the extremes
    assert v("low", 25.0, True)[1] == _GOOD
    assert v("low", 75.0, True)[1] == _BAD
    assert v("high", 75.0, False)[1] == _GOOD
    # missing percentile
    assert v("low", None, True) == ("—", ("", ""))


# ── 3. month-end downsampling ───────────────────────────────────────────────

def test_month_end():
    out = HistoricalService._month_end(_PL_SERIES, "pe")
    assert out == [("2026-01-28", 6.0), ("2026-02-25", 8.0),
                   ("2026-03-15", 10.0)]
    # None values skip (the DY fixture's 2026-02-15)
    dy = HistoricalService._month_end(_DY_SERIES, "dy")
    assert dy == [("2026-01-31", 0.04), ("2026-02-27", 0.045),
                  ("2026-03-15", 0.05)]
    assert HistoricalService._month_end([], "pe") == []
    assert HistoricalService._month_end([{"date": "2026-01-01",
                                          "pe": None}], "pe") == []


# ── 4+5+6. the payload builders ─────────────────────────────────────────────

def test_overview_payload(mocked):
    r = mocked.overview("PETR4")
    assert r["status"] == "ok"
    assert len(r["kpis"]) == 6
    kpi = {k["label"]: k["value"] for k in r["kpis"]}
    assert kpi["P/L"] == "10,00"          # ratio → num
    assert kpi["Dividend Yield"] == "5,00%"  # pct → ×100 ONCE
    assert all(k.get("tooltip") for k in r["kpis"])

    hm = r["sections"][0]
    assert hm["type"] == "heatmap"
    assert hm["title"] == "Heatmap de Valoração — Indicadores Coloridos"
    assert len(hm["rows"]) == 17
    rows = {row[0]["text"]: row for row in hm["rows"]}
    pl = rows["P/L"]
    # col 0 = {text, tooltip}; quartiles hand-checked (5/6/7/8/10)
    assert pl[0] == {"text": "P/L", "tooltip": pl[0]["tooltip"]}
    assert pl[0]["tooltip"]  # the formula tooltip is present
    assert pl[1] == {"text": "10,00", "bg": _BAD[0], "color": _BAD[1]}
    assert [pl[i] for i in (2, 3, 4, 5, 6)] == \
        ["5,00", "6,00", "7,00", "8,00", "10,00"]
    assert pl[7]["text"] == "80,0º"
    assert pl[8] == {"text": "Cara vs histórico", "bg": _BAD[0],
                     "color": _BAD[1]}
    # DY — pct ×100 once, high direction → GREEN at 90º
    dy = rows["Dividend Yield"]
    assert dy[1] == {"text": "5,00%", "bg": _GOOD[0], "color": _GOOD[1]}
    assert dy[8]["text"] == "Acima da faixa"
    # the degraded metric renders dashes, no crash
    inv = rows["Giro Estoque"]
    assert inv[1]["text"] == "—"
    assert inv[8]["text"] == "—"

    # the trend table — COLLAPSED (the v1.23 convention), Δ hand-checked
    tr = r["sections"][1]
    assert tr["collapsed"] is True
    assert len(tr["rows"]) == 17
    tpl = [row for row in tr["rows"]
           if (row[0]["text"] if isinstance(row[0], dict) else row[0])
           == "P/L"][0]
    assert tpl[1] == "10,00"
    assert tpl[2] == "8,00"
    assert tpl[3] == "+25,00%"      # (10−8)/8
    assert tpl[4] == "12,00"
    assert tpl[5] == "-16,67%"      # (10−12)/12
    assert tpl[6] == "15,00"
    assert tpl[7] == "-33,33%"      # (10−15)/15
    assert "note" in tr


def test_valuation_band_charts(mocked):
    r = mocked.valuation("PETR4")
    assert r["status"] == "ok"
    charts = [s for s in r["sections"] if s["type"] == "chart"]
    assert [c["title"] for c in charts] == \
        ["P/L — 5A", "P/VPA — 5A", "EV/EBITDA — 5A", "Dividend Yield — 5A"]
    pl = charts[0]["chart_data"]
    assert pl["type"] == "line"
    assert pl["data"]["labels"] == ["2026-01", "2026-02", "2026-03"]
    ds = pl["data"]["datasets"]
    assert len(ds) == 4
    assert ds[0]["label"] == "Faixa 5A (mín–máx)"
    assert ds[0]["data"] == [5.0, 5.0, 5.0]
    assert ds[0]["fill"] == "+1"
    assert not ds[0].get("hideLegend")
    assert ds[1]["label"] == "Faixa máx"
    assert ds[1]["data"] == [10.0, 10.0, 10.0]
    assert ds[1]["hideLegend"] is True      # the single-legend trick
    assert ds[2]["label"] == "Mediana 5A"
    assert ds[2]["data"] == [7.0, 7.0, 7.0]
    assert ds[2]["borderDash"] == [6, 4]
    assert ds[3]["label"] == "P/L"
    assert ds[3]["data"] == [6.0, 8.0, 10.0]  # month-ends
    assert ds[3]["borderColor"] == "#0d9488"
    # ratio chart: NO tooltipUnit, NO ×100
    assert "options" not in pl or "tooltipUnit" not in (pl.get("options")
                                                        or {})
    # the pct chart ships ×100 + tooltipUnit "%"
    dy = charts[3]["chart_data"]
    assert dy["options"]["tooltipUnit"] == "%"
    assert dy["data"]["datasets"][3]["data"] == [4.0, 4.5, 5.0]
    # trend subset follows the charts (4 metrics, not collapsed)
    tr = r["sections"][-1]
    assert len(tr["rows"]) == 4
    assert not tr.get("collapsed")


def test_leverage_advanced(mocked):
    r = mocked.leverage("PETR4")
    assert r["status"] == "ok"
    adv = [s for s in r["sections"] if s.get("title") == "Avançado (hoje)"]
    assert len(adv) == 1
    rows = {row[0]: row for row in adv[0]["rows"]}
    assert rows["WACC"][1] == "15,89%"
    assert rows["DuPont ROE"][1] == "22,94%"
    assert rows["Altman Z-Score"][1] == "2.42 (Cinza)"
    # 5 charts + trend + advanced
    charts = [s for s in r["sections"] if s["type"] == "chart"]
    assert len(charts) == 5


def test_degradation_all_metrics_fail(monkeypatch):
    import skills.cvm.historical.modes.summary as summod
    import skills.cvm.calculations._registry as regmod
    monkeypatch.setattr(summod, "summary",
                        lambda **kw: dict(_ERROR_SUMMARY))
    monkeypatch.setattr(regmod, "resolve_metric",
                        lambda n: _Spec("x", lambda c, f, t: []))
    svc = HistoricalService()
    r = svc.overview("PETR4")
    # heatmap + trend still render (all-— rows); the chart subtabs error.
    assert r["status"] == "ok"
    v = svc.valuation("PETR4")
    assert "_error" in v and "valuation" in v["_error"]


def test_cache_shared_across_subtabs(mocked):
    mocked.overview("PETR4")
    assert "PETR4" in mocked._cache
    # the second subtab reuses the SAME build (fresh instance data, no
    # re-summary calls — prove via a call counter).
    import skills.cvm.historical.modes.summary as summod
    calls = {"n": 0}
    real = summod.summary
    def counting(**kw):
        calls["n"] += 1
        return _fake_summary(**kw)
    summod.summary = counting
    try:
        mocked.valuation("PETR4")
        assert calls["n"] == 0      # 100% cache hit
    finally:
        summod.summary = real


# ── 9. HTTP surface ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    # memory_root isolated (the v1224/v123 recipe — an app boot against
    # the real memory_db leaves global state that breaks other suites).
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import skills.cvm.historical.modes.summary as summod
    import skills.cvm.calculations._registry as regmod
    import skills.cvm.calculations.metrics.wacc as wmod
    import skills.cvm.calculations.metrics.dupont as dmod
    import skills.cvm.calculations.metrics.altman_z as amod
    monkeypatch.setattr(summod, "summary", _fake_summary)
    monkeypatch.setattr(regmod, "resolve_metric", _fake_resolve_metric)
    monkeypatch.setattr(wmod, "wacc_at", lambda c, d: 0.1589)
    monkeypatch.setattr(dmod, "dupont_at", lambda c, d: 0.2294)
    monkeypatch.setattr(amod, "altman_z_at", lambda c, d: 2.42)
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_historical_sections(client):
    r = client.get("/api/webui/company/PETR4/sections/historical:overview")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["kpis"]) == 6
    assert [s["type"] for s in body["sections"]] == ["heatmap", "table"]
    assert body["sections"][1]["collapsed"] is True

    r2 = client.get("/api/webui/company/PETR4/sections/historical:valuation")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "ok"
    assert len([s for s in body2["sections"] if s["type"] == "chart"]) == 4

    # unknown key → 404 PT-BR plain text (the v1.7 rule)
    r3 = client.get("/api/webui/company/PETR4/sections/historical:nope")
    assert r3.status_code == 404


def test_http_historical_tab_and_page(client):
    # the tab shell fragment — 4 subtab panes with the right ids
    r = client.get("/api/webui/company/PETR4/tab/historical")
    assert r.status_code == 200
    for pane in ("tab-hist-overview", "tab-hist-valuation",
                 "tab-hist-profitability", "tab-hist-leverage"):
        assert pane in r.text
    assert "loadHistSubtab" in r.text
    # the page route (server-rendered shell, active_tab=historical)
    r2 = client.get("/webui/company/PETR4/historical")
    assert r2.status_code == 200
    assert "tab/historical" in r2.text
    # unknown tab still redirects to the overview (v1.5 rule)
    r3 = client.get("/webui/company/PETR4/gibberish", follow_redirects=False)
    assert r3.status_code == 302
