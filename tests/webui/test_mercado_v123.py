"""tests/webui/test_mercado_v123.py — the v1.23 Mercado suite.

Poupança family + the matrix-before-histório/collapsed-histórico
convention, HAND-COMPUTED values (the v1.22.1 discipline):

  1.  POUPANÇA OVERVIEW (all three sources): the KPI trio (mês/ano/12m
      — the uploaded dashboard's own cards), the two comparison charts
      (Poupança × IPCA monthly; Poupança × IPCA × CDI at 12m), the
      month table with the Poupança − IPCA difference column
      (hand-checked: 0,62 − 1,20 = −0,58) and the 12m tooltips.
  2.  THE CDI CONVERSION: _cdi_12m compounds the % a.a. monthly rate
      (12 months flat at 12% a.a. → EXACTLY 12,00% — a flat window
      compounds to its own annual rate); a window holding a None gets
      no reading; fewer than 12 months → nothing.
  3.  OVERVIEW DEGRADATION: no IPCA/CDI → poupança-only charts whose
      descriptions NAME the missing sources (ddm-inflation /
      ddm-juros), poupança-only table columns; no poupança at all →
      the _error naming ddm-poupanca.
  4.  POUPANÇA INDEX VIEW — THE V1.23 CONVENTION: sections ordered
      [Evolução, Matriz ano × mês, Histórico mensal], the table
      COLLAPSED + sortable, the note pointing at the matrix "acima"
      (above — it used to say "abaixo", below the table).
  5.  THE MATRIX: 14 columns (Ano + 12 months + Ano — the year column
      the source page doesn't carry), year rows newest-first, the Ano
      cell = the year's acumulado (1,94 for the 2026 fixture), gap
      months render "-" cells.
  6.  INFLAÇÃO + JUROS reorder: the per-index views (IPCA / CDI) ship
      the matrix BEFORE the Histórico mensal, the table collapsed —
      same convention, three families.
  7.  HTTP: GET /api/webui/mercado/sections/poupanca:{overview,
      poupanca} answers the generic renderer contract.

Run:  python -m pytest tests/webui/test_mercado_v123.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.poupanca as pmod                  # noqa: E402
import webui.services.inflation as imod                  # noqa: E402
import webui.services.juros as jmod                      # noqa: E402
from webui.services.poupanca import (                    # noqa: E402
    PoupancaService, _cdi_12m, _pp,
)


# ── fixtures (mocked query engines — no DB, the skills' own pattern) ─────────

# 15 months, 2025-01..2026-03. 2025-07 carries a None month_value (the
# matrix gap cell + the honest "-" in the ledger). acumulado_no_ano is
# a plain cumulative; the last obs (2026-03) is the KPI source.
_POUP_OBS = [
    {"ref_date": "2025-01", "month_value": 0.50, "acumulado_no_ano": 0.50, "acumulado_12m": 7.10},
    {"ref_date": "2025-02", "month_value": 0.50, "acumulado_no_ano": 1.00, "acumulado_12m": 7.20},
    {"ref_date": "2025-03", "month_value": 0.55, "acumulado_no_ano": 1.55, "acumulado_12m": 7.30},
    {"ref_date": "2025-04", "month_value": 0.60, "acumulado_no_ano": 2.15, "acumulado_12m": 7.40},
    {"ref_date": "2025-05", "month_value": 0.60, "acumulado_no_ano": 2.75, "acumulado_12m": 7.50},
    {"ref_date": "2025-06", "month_value": 0.62, "acumulado_no_ano": 3.37, "acumulado_12m": 7.60},
    {"ref_date": "2025-07", "month_value": None, "acumulado_no_ano": None, "acumulado_12m": None},
    {"ref_date": "2025-08", "month_value": 0.62, "acumulado_no_ano": 3.99, "acumulado_12m": 7.70},
    {"ref_date": "2025-09", "month_value": 0.62, "acumulado_no_ano": 4.61, "acumulado_12m": 7.80},
    {"ref_date": "2025-10", "month_value": 0.63, "acumulado_no_ano": 5.24, "acumulado_12m": 7.85},
    {"ref_date": "2025-11", "month_value": 0.65, "acumulado_no_ano": 5.89, "acumulado_12m": 7.88},
    {"ref_date": "2025-12", "month_value": 0.66, "acumulado_no_ano": 6.55, "acumulado_12m": 7.90},
    {"ref_date": "2026-01", "month_value": 0.67, "acumulado_no_ano": 0.67, "acumulado_12m": 7.92},
    {"ref_date": "2026-02", "month_value": 0.65, "acumulado_no_ano": 1.32, "acumulado_12m": 7.91},
    {"ref_date": "2026-03", "month_value": 0.62, "acumulado_no_ano": 1.94, "acumulado_12m": 7.90},
]

# IPCA overlaps the last three poupança months. 2026-03 = 1.20 → the
# diff column hand-check: 0,62 − 1,20 = −0,58 (the red "lost to
# inflation" month). 2026-04 exists ONLY here (the union-months test:
# the chart x axis must carry it while the table does not).
_IPCA_OBS = [
    {"ref_date": "2026-01", "month_value": 0.30, "year_acumulado": 0.30, "acumulado_12m": 4.50},
    {"ref_date": "2026-02", "month_value": 0.25, "year_acumulado": 0.55, "acumulado_12m": 4.60},
    {"ref_date": "2026-03", "month_value": 1.20, "year_acumulado": 1.75, "acumulado_12m": 5.60},
    {"ref_date": "2026-04", "month_value": 0.40, "year_acumulado": 2.15, "acumulado_12m": 5.70},
]

# 15 months of CDI flat at 12.00 % a.a. — every full 12-month window
# compounds to EXACTLY 12,00% (a flat window compounds to its own
# annual rate: (1,12)^(12/12) − 1). 2025-04 .. 2026-06.
_CDI_OBS = [
    {"ref_date": (f"2025-{m:02d}" if m <= 12 else f"2026-{m - 12:02d}"),
     "month_value": 12.00, "media_no_ano": 12.00, "media_12m": 12.00}
    for m in range(4, 19)
]


def _ok(obs, **extra):
    return {"status": "ok", "observations": obs, **extra}


def _poupanca_history(slug="", limit=60):
    assert slug == "poupanca"
    return _ok(_POUP_OBS, slug=slug)


def _index_history(slug="", limit=60):
    assert slug == "ipca"
    return _ok(_IPCA_OBS, slug=slug)


def _juros_history(slug="", limit=60):
    assert slug == "cdi"
    return _ok(_CDI_OBS, slug=slug)


def _fail(slug="", limit=60):
    return {"status": "not_synced", "error": "no db"}


@pytest.fixture()
def full(monkeypatch):
    """All three sources mocked."""
    monkeypatch.setattr(pmod, "_poupanca_history", _poupanca_history)
    monkeypatch.setattr(pmod, "_index_history", _index_history)
    monkeypatch.setattr(pmod, "_juros_history", _juros_history)
    return PoupancaService()


@pytest.fixture()
def lonely(monkeypatch):
    """Poupança only — the degrade path."""
    monkeypatch.setattr(pmod, "_poupanca_history", _poupanca_history)
    monkeypatch.setattr(pmod, "_index_history", _fail)
    monkeypatch.setattr(pmod, "_juros_history", _fail)
    return PoupancaService()


# ── 1. the overview — all three sources ─────────────────────────────────────

def test_overview_kpis(full):
    kpis = full.overview()["kpis"]
    assert [k["value"] for k in kpis] == ["0,62%", "1,94%", "7,90%"]
    assert [k["label"] for k in kpis] == [
        "Poupança — mês", "Poupança — ano", "Poupança — 12m"]
    # the KPI tooltip names the caderneta rule (0,5% + TR vs 70% Selic)
    assert "0,5%" in kpis[0]["tooltip"] and "70%" in kpis[0]["tooltip"]


def test_overview_charts(full):
    secs = full.overview()["sections"]
    charts = [s for s in secs if s["type"] == "chart"]
    assert len(charts) == 2

    # Chart 1 — monthly: Poupança × IPCA, x axis = the UNION of months
    # (2026-04 exists only in the IPCA series → 16 labels).
    c1 = charts[0]
    assert c1["title"] == "Rendimento mensal — Poupança × IPCA"
    assert [d["label"] for d in c1["chart_data"]["data"]["datasets"]] == \
        ["Poupança (%)", "IPCA (%)"]
    assert len(c1["chart_data"]["data"]["labels"]) == 16
    assert "2026-04" in c1["chart_data"]["data"]["labels"]

    # Chart 2 — 12m: the three returns, CDI COMPOUNDED (not the a.a.
    # average — same axis, same unit).
    c2 = charts[1]
    assert c2["title"] == "Acumulado 12 meses — Poupança × IPCA × CDI"
    assert [d["label"] for d in c2["chart_data"]["data"]["datasets"]] == \
        ["Poupança 12m (%)", "IPCA 12m (%)", "CDI 12m (%)"]
    cdi_ds = c2["chart_data"]["data"]["datasets"][2]["data"]
    idx = c2["chart_data"]["data"]["labels"].index("2026-06")
    assert cdi_ds[idx] == pytest.approx(12.00, abs=1e-9)
    # before the first full 12-month window there is no CDI reading
    assert cdi_ds[c2["chart_data"]["data"]["labels"].index("2025-05")] \
        is None


def test_overview_table_diff_math(full):
    tbl = [s for s in full.overview()["sections"] if s["type"] == "table"][0]
    assert tbl["columns"] == ["Mês", "Poupança (%)", "IPCA (%)",
                              "Poupança − IPCA (p.p.)"]
    # ≤24 months → every row, newest first
    assert len(tbl["rows"]) == 15
    first = tbl["rows"][0]                       # mar/2026
    assert first[0]["text"] == "mar/2026"
    assert first[1] == "0,62%"
    assert first[2] == "1,20%"
    # HAND-COMPUTED: 0,62 − 1,20 = −0,58 (the losing-to-inflation month)
    assert first[3] == "-0,58"
    # the tooltip carries BOTH 12m readings
    assert "Poupança 12m: 7,90%" in first[0]["tooltip"]
    assert "IPCA 12m: 5,60%" in first[0]["tooltip"]
    # a winning month carries the explicit +
    feb = tbl["rows"][1]                         # fev/2026
    assert feb[1] == "0,65%" and feb[2] == "0,25%"
    assert feb[3] == "+0,40"
    # the gap month (jul/2025) renders "-" honestly
    jul = [r for r in tbl["rows"] if
           (r[0]["text"] if isinstance(r[0], dict) else r[0]) == "jul/2025"][0]
    assert jul[1] == "-"


def test_overview_table_no_ipca_rows_for_poupanca_only_months(full):
    """The table walks the POUpança months — the IPCA-only 2026-04
    (a comparison series month with no caderneta reading) adds no row."""
    tbl = [s for s in full.overview()["sections"] if s["type"] == "table"][0]
    months = [r[0]["text"] if isinstance(r[0], dict) else r[0]
              for r in tbl["rows"]]
    assert "abr/2026" not in months
    assert "mar/2026" == months[0]


# ── 2. the CDI conversion ───────────────────────────────────────────────────

def test_cdi_12m_flat_window_compounds_to_the_annual_rate():
    """12 months flat at 12% a.a. → exactly 12,00% (the flat-window
    identity: (1+r)^(12/12) − 1 = r)."""
    obs = [{"ref_date": f"2025-{m:02d}", "month_value": 12.00}
           for m in range(1, 13)]
    out = _cdi_12m(obs)
    assert set(out) == {"2025-12"}
    assert out["2025-12"] == pytest.approx(12.00, abs=1e-9)


def test_cdi_12m_short_and_gapped_windows():
    # fewer than 12 months → nothing (no partial product)
    assert _cdi_12m([{"ref_date": f"2025-{m:02d}", "month_value": 10.0}
                     for m in range(1, 11)]) == {}
    # a None poisons EVERY window that contains it: with the gap at
    # 2025-01 and obs through 2026-01, only the 2026-01 window (2025-02
    # onwards) is clean.
    obs = ([{"ref_date": "2025-01", "month_value": None}] +
           [{"ref_date": f"2025-{m:02d}", "month_value": 12.00}
            for m in range(2, 13)] +
           [{"ref_date": "2026-01", "month_value": 12.00}])
    out = _cdi_12m(obs)
    assert set(out) == {"2026-01"}
    assert out["2026-01"] == pytest.approx(12.00, abs=1e-9)


def test_pp_formatting():
    assert _pp(0.32) == "+0,32"
    assert _pp(-0.05) == "-0,05"
    assert _pp(None) == "-"
    assert _pp(0.0) == "+0,00"


# ── 3. degradation ──────────────────────────────────────────────────────────

def test_overview_degrades_without_ipca_cdi(lonely):
    secs = lonely.overview()["sections"]
    charts = [s for s in secs if s["type"] == "chart"]
    # both charts carry the poupança line only…
    assert all(len(c["chart_data"]["data"]["datasets"]) == 1
               for c in charts)
    # …and their descriptions NAME the missing sources
    assert "ddm-inflation" in charts[0]["description"]
    assert "ddm-inflation" in charts[1]["description"]
    assert "ddm-juros" in charts[1]["description"]
    # the table drops the IPCA/diff columns and says why
    tbl = [s for s in secs if s["type"] == "table"][0]
    assert tbl["columns"] == ["Mês", "Poupança (%)"]
    assert "ddm-inflation" in tbl["note"]
    # every row still has exactly 2 cells
    assert all(len(r) == 2 for r in tbl["rows"])


def test_overview_missing_poupanca(monkeypatch):
    monkeypatch.setattr(pmod, "_poupanca_history", _fail)
    monkeypatch.setattr(pmod, "_index_history", _index_history)
    monkeypatch.setattr(pmod, "_juros_history", _juros_history)
    res = PoupancaService().overview()
    assert "ddm-poupanca" in res.get("_error", "")
    assert "sections" not in res


# ── 4+5. the index view — the v1.23 convention ──────────────────────────────

def test_index_view_section_order_and_collapse(full):
    secs = full.poupanca()["sections"]
    # [Evolução (chart), Matriz (heatmap), Histórico (table)] — the
    # matrix BEFORE the ledger, the ledger COLLAPSED
    assert [s["type"] for s in secs] == ["chart", "heatmap", "table"]
    assert secs[1]["title"] == "Matriz ano × mês"
    assert secs[2]["title"] == "Histórico mensal"
    assert secs[2].get("collapsed") is True
    assert secs[2].get("sortable") is True
    # the note points UP at the matrix (the old copy said "abaixo")
    assert "acima" in secs[2]["note"]
    # the evolução keeps the static's 3-line design
    ds = secs[0]["chart_data"]["data"]["datasets"]
    assert [d["label"] for d in ds] == [
        "Rendimento no mês (%)", "Acumulado no ano (%)",
        "Acumulado 12 meses (%)"]
    assert ds[1]["borderDash"] == [5, 5] and ds[2]["borderDash"] == [2, 4]


def test_index_view_matrix(full):
    mx = [s for s in full.poupanca()["sections"]
          if s["type"] == "heatmap"][0]
    # 14 columns: Ano + Jan..Dez + Ano (the year column the source
    # page doesn't carry — the DB has the acumulado)
    assert len(mx["columns"]) == 14
    assert mx["columns"][0] == "Ano" and mx["columns"][-1] == "Ano"
    # two year rows, newest first
    assert [r[0] for r in mx["rows"]] == ["2026", "2025"]
    row26 = mx["rows"][0]
    assert row26[1]["text"] == "0,67"      # jan/2026
    assert row26[3]["text"] == "0,62"      # mar/2026
    assert row26[4]["text"] == "-"         # abr/2026 — no data yet
    # the Ano cell = the year's acumulado (1,94 — the LAST 2026 obs wins)
    assert row26[-1]["text"] == "1,94"
    # the gap month (jul/2025) renders "-"
    row25 = mx["rows"][1]
    assert row25[7]["text"] == "-"


def test_index_view_ledger(full):
    tbl = [s for s in full.poupanca()["sections"]
           if s["type"] == "table"][0]
    assert tbl["columns"] == ["Mês", "Rendimento (%)",
                              "Acumulado no ano (%)",
                              "Acumulado 12m (%)"]
    # DESC — the newest first
    assert tbl["rows"][0][0] == "mar/2026"
    assert tbl["rows"][0][1] == "0,62%"
    assert len(tbl["rows"]) == 15
    assert "15 observações" in tbl["note"]


def test_index_view_missing_poupanca(monkeypatch):
    monkeypatch.setattr(pmod, "_poupanca_history", _fail)
    res = PoupancaService().poupanca()
    assert "ddm-poupanca" in res.get("_error", "")
    assert "sections" not in res


# ── 6. Inflação + Juros — the same convention ───────────────────────────────

def _infl_mock(slug="", limit=60):
    return _ok([
        {"ref_date": "2025-11", "month_value": 0.55,
         "year_acumulado": 5.89, "acumulado_12m": 4.80},
        {"ref_date": "2025-12", "month_value": 0.66,
         "year_acumulado": 6.55, "acumulado_12m": 4.90},
        {"ref_date": "2026-01", "month_value": 0.40,
         "year_acumulado": 0.40, "acumulado_12m": 4.70},
    ], slug=slug)


def _juros_mock(slug="", limit=60):
    return _ok([
        {"ref_date": "2025-12", "month_value": 12.00,
         "media_no_ano": 11.90, "media_12m": 11.80},
        {"ref_date": "2026-01", "month_value": 12.25,
         "media_no_ano": 12.25, "media_12m": 11.85},
    ], slug=slug)


def test_inflacao_matrix_before_collapsed_historico(monkeypatch):
    monkeypatch.setattr(imod, "_index_history", _infl_mock)
    secs = imod.InflationService().ipca()["sections"]
    assert [s["type"] for s in secs] == ["chart", "heatmap", "table"]
    assert secs[1]["title"] == "Matriz ano × mês"
    assert secs[2].get("collapsed") is True
    assert secs[2].get("sortable") is True
    assert "acima" in secs[2]["note"]
    # the inflação matrix keeps its OWN year column (14 cols)
    assert len(secs[1]["columns"]) == 14


def test_juros_matrix_before_collapsed_historico(monkeypatch):
    monkeypatch.setattr(jmod, "_juros_history", _juros_mock)
    secs = jmod.JurosService().cdi()["sections"]
    assert [s["type"] for s in secs] == ["chart", "heatmap", "table"]
    assert secs[1]["title"] == "Matriz ano × mês"
    assert secs[2].get("collapsed") is True
    assert "acima" in secs[2]["note"]
    # the juros matrix keeps NO year column (13 cols — rates, not
    # acumulados)
    assert len(secs[1]["columns"]) == 13


def test_overview_tables_untouched_by_collapse():
    """The inflação/juros OVERVIEWS (Comparativo mensal) never collapse —
    only the per-index Histórico mensal does (the flag is opt-in per
    section, not a global)."""
    # the comparison tables build from the same mocked engines
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(imod, "_index_history", _infl_mock)
        secs = imod.InflationService().overview()["sections"]
        comp = [s for s in secs if s["type"] == "table"][0]
        assert comp["title"] == "Comparativo mensal"
        assert not comp.get("collapsed")
    finally:
        monkeypatch.undo()


# ── 7. HTTP — the generic endpoint serves the family ────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    # memory_root isolated to tmp_path (the v1224 recipe — an app boot
    # against the real memory_db would leave global state that breaks
    # OTHER suites' mocked engines: the focus dashboard tests).
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    monkeypatch.setattr(pmod, "_poupanca_history", _poupanca_history)
    monkeypatch.setattr(pmod, "_index_history", _index_history)
    monkeypatch.setattr(pmod, "_juros_history", _juros_history)
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_poupanca_sections(client):
    r = client.get("/api/webui/mercado/sections/poupanca:overview")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["kpis"]) == 3
    assert [s["type"] for s in body["sections"]] == \
        ["chart", "chart", "table"]

    r2 = client.get("/api/webui/mercado/sections/poupanca:poupanca")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "ok"
    hist = [s for s in body2["sections"] if s["type"] == "table"][0]
    assert hist["collapsed"] is True
