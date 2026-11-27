"""tests/webui/test_v128_4.py — the v1.28.4 suite.

The cross-tool round (the user's six-item list + the docs maintenance):

  1. POSIÇÃO — the subject's rank per metric inside the sector
     ("P/L: 12º de 38"): the _position math (direction, ties,
     positive-only eligibility, missing values) and the vs_rows keys
     (pos_rank/pos_of/pos_fmt) on the concept trio's own numbers.
  2. NAMESPACE — tools_screener_v4 (the vs_rows carry the position
     keys; cached v3 payloads lack them) + the medians' own
     tools_sector_medians_v1.
  3. MEDIANA DO SETOR — the Comparação's new column: its own payload
     (ONE median per comparison _ROWS metric, positive-only rows
     positive-only, unavailable metrics skipped), its API route, and
     the dividends bucket joining the fetch (the grid's Dividendos
     rows need it).
  4. JS/CSS SURFACE — the cross-tool glue (toolOpenScreener /
     toolOpenBacktest / toolCompare), the Posição column + 📋 copiar
     resumo, the range-filter bar, Cancelar on the Comparação and BOTH
     Backtest loads, the medians' progressive fill — and the ?v=90
     asset bump.
  5. DOCS — the ROADMAP pruned to future work only (no shipped
     strikethroughs) and the CHANGELOG condensed (no "In Progress"
     section, the v1.28.4 row present).

Run:  python -m pytest tests/webui/test_v128_4.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


PETR = "33000167000101"      # PETR3 + PETR4 (one company, two classes)
PRIO = "02187300000111"
UGPA = "33252800000100"
SECTOR = "Petróleo e Gás"


def _entry(ticker: str, *, val=None, fin=None, grw=None, mkt=None,
           error: str = "") -> dict:
    return {"ticker": ticker, "val": val or {}, "fin": fin or {},
            "grw": grw or {}, "mkt": mkt or {},
            "hist_monthly": [], "hist_daily": [], "error": error}


PETR_ENTRY = _entry(
    "PETR4",
    val={"price": 40.87, "market_cap": 338.85e9, "p_l": 2.60,
         "p_vpa": 0.81, "ev_ebitda": 2.56, "roe": 0.3119,
         "dividend_yield": 0.1061, "dpa": 4.20, "total_shares": 8.29e9,
         "ev": 500.0e9, "divida_pl": 0.92, "divida_liquida_ebitda": 0.66},
    fin={"receita_liquida": 497.55e9, "ebitda": 155.37e9, "payout": 0.55},
    grw={"receita_yoy": 0.0042},
    mkt={"price": 40.87, "price_date": "2026-11-24", "var_day": 0.012},
)
PRIO_ENTRY = _entry(
    "PRIO3",
    val={"price": 60.54, "market_cap": 45.84e9, "p_l": 11.87,
         "p_vpa": 1.78, "ev_ebitda": 6.47, "roe": 0.1498,
         "dividend_yield": 0.0, "dpa": 0.0, "total_shares": 0.76e9,
         "ev": 90.0e9},
    fin={"receita_liquida": 15.58e9, "ebitda": 7.67e9, "payout": 0.10},
    grw={"receita_yoy": 0.0852},
    mkt={"price": 60.54, "price_date": "2026-11-24", "var_day": -0.004},
)
UGPA_ENTRY = _entry(
    "UGPA3",
    val={"price": 33.39, "market_cap": 35.66e9, "p_l": 13.29,
         "p_vpa": 2.01, "ev_ebitda": 6.84, "roe": 0.1514,
         "marg_ebitda": 0.0361, "dividend_yield": 0.0389},
    fin={"receita_liquida": 142.37e9, "ebitda": 5.14e9},
    grw={"receita_yoy": 0.0664},
    mkt={"price": 33.39, "price_date": "2026-11-24", "var_day": 0.003},
)

SECTOR_ENTRIES = [PETR_ENTRY, PRIO_ENTRY, UGPA_ENTRY]


@pytest.fixture()
def memory_root(tmp_path, monkeypatch):
    """Isolated root + bridge.db carrying the concept trio's sector."""
    from core.config import cfg
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True)
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b = sqlite3.connect(str(cvm / "bridge.db"))
    b.execute("""CREATE TABLE IF NOT EXISTS ticker_map (
        ticker TEXT PRIMARY KEY, issuing TEXT, cd_cvm TEXT, trading_name TEXT,
        cnpj TEXT, denom_social TEXT, denom_comerc TEXT, sit TEXT,
        setor_ativ TEXT, tp_merc TEXT, synced_at TEXT)""")
    for tk, iss, cd, name, cnpj, setor in [
        ("PETR4", "PETR", "9512", "PETROBRAS", PETR, SECTOR),
        ("PETR3", "PETR", "9512", "PETROBRAS", PETR, SECTOR),
        ("PRIO3", "PRIO", "22148", "PRIO", PRIO, SECTOR),
        ("UGPA3", "UGPA", "20646", "ULTRAPAR", UGPA, SECTOR),
    ]:
        b.execute(
            "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, "
            "cnpj, setor_ativ) VALUES (?, ?, ?, ?, ?, ?)",
            (tk, iss, cd, name, cnpj, setor))
    b.commit()
    b.close()
    return tmp_path


# ── 1. the _position math ────────────────────────────────────────────────────

def test_position_rank_math():
    """Cheap = smallest first; above = largest first; ties share the
    better rank (standard competition ranking)."""
    from webui.services.screener import ScreenerService
    pos = ScreenerService._position
    vals = [5.0, 10.0, 10.0, 20.0]
    # "cheap" (multiples): only the 5.0 is strictly better than 10.0
    assert pos(10.0, vals, "cheap", False) == (2, 4)
    # "above" (quality): only the 20.0 is strictly better than 10.0
    assert pos(10.0, vals, "above", False) == (2, 4)
    # the extremes
    assert pos(5.0, vals, "cheap", False) == (1, 4)
    assert pos(20.0, vals, "cheap", False) == (4, 4)
    assert pos(20.0, vals, "above", False) == (1, 4)
    # a tie on the podium: two 5.0s both rank 1º
    assert pos(5.0, [5.0, 5.0, 8.0], "cheap", False) == (1, 3)


def test_position_positive_only_eligibility():
    """A loss never ranks (positive-only multiples); the ineligible
    values leave the denominator too."""
    from webui.services.screener import ScreenerService
    pos = ScreenerService._position
    vals = [-4.2, 10.0, 20.0]
    # the loss itself carries no position — but the count is honest
    assert pos(-4.2, vals, "cheap", True) == (None, 2)
    # 10.0 ranks among the POSITIVE values only
    assert pos(10.0, vals, "cheap", True) == (1, 2)
    assert pos(20.0, vals, "cheap", True) == (2, 2)
    # positive_only off: the loss is just the cheapest
    assert pos(-4.2, vals, "cheap", False) == (1, 3)


def test_position_missing_and_garbage_values():
    """None/NaN/bool/garbage peers never enter the ranking; a subject
    with no value carries no rank — but an honest denominator when
    eligible peers exist (None, N)."""
    from webui.services.screener import ScreenerService
    pos = ScreenerService._position
    nan = float("nan")
    # the subject itself has nothing — the count stays honest
    assert pos(None, [1.0, 2.0], "cheap", False) == (None, 2)
    assert pos(nan, [1.0, 2.0], "cheap", False) == (None, 2)
    assert pos("n/a", [1.0, 2.0], "cheap", False) == (None, 2)
    # garbage peers are skipped, the rank still counts the clean ones
    assert pos(2.0, [None, nan, True, "x", 1.0, 2.0], "cheap", False) == (2, 2)
    # nothing eligible at all
    assert pos(1.0, [None, None], "cheap", False) == (None, None)


# ── 2. the vs_rows carry the position keys ───────────────────────────────────

def test_vs_rows_carry_position_keys():
    """The concept trio's own numbers: PETR4 tops P/L, P/VPA, EV/EBITDA,
    ROE and DY; trails on Cresc. Receita; owns Dívida Líq./EBITDA
    alone; and Marg. EBITDA (which it lacks) carries no position."""
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    rows = {r["label"]: r for r in svc._vs_rows(PETR_ENTRY, SECTOR_ENTRIES)}

    # cheapest of {2,60 · 11,87 · 13,29}
    assert rows["P/L"]["pos_rank"] == 1
    assert rows["P/L"]["pos_of"] == 3
    assert rows["P/L"]["pos_fmt"] == "1º de 3"
    # cheapest of {0,81 · 1,78 · 2,01}
    assert rows["P/VPA"]["pos_fmt"] == "1º de 3"
    # cheapest of {2,56 · 6,47 · 6,84}
    assert rows["EV/EBITDA"]["pos_fmt"] == "1º de 3"
    # highest ROE of {31,19% · 14,98% · 15,14%}
    assert rows["ROE"]["pos_rank"] == 1
    assert rows["ROE"]["pos_fmt"] == "1º de 3"
    # DY (not positive-only): highest of {10,61% · 0% · 3,89%}
    assert rows["Div Yield"]["pos_fmt"] == "1º de 3"
    # growth (above): SLOWEST of {0,42% · 8,52% · 6,64%}
    assert rows["Cresc. Receita YoY"]["pos_rank"] == 3
    assert rows["Cresc. Receita YoY"]["pos_of"] == 3
    assert rows["Cresc. Receita YoY"]["pos_fmt"] == "3º de 3"
    # only PETR4 carries net debt → 1º de 1
    assert rows["Dívida Líq./EBITDA"]["pos_fmt"] == "1º de 1"
    # PETR4 has no marg_ebitda → no position at all
    assert rows["Marg. EBITDA"]["pos_rank"] is None
    assert rows["Marg. EBITDA"]["pos_fmt"] == "—"


def test_vs_rows_position_of_a_negative_pL_subject():
    """A loss-making subject: no P/L position (positive-only), but a
    rank on the metrics it does carry."""
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    subject = _entry("LOSS3", val={"p_l": -4.2, "roe": 0.10})
    peers = [subject, _entry("A", val={"p_l": 10.0, "roe": 0.20}),
             _entry("B", val={"p_l": 20.0, "roe": 0.30})]
    rows = {r["label"]: r for r in svc._vs_rows(subject, peers)}
    assert rows["P/L"]["pos_rank"] is None
    assert rows["P/L"]["pos_fmt"] == "—"
    assert rows["ROE"]["pos_rank"] == 3
    assert rows["ROE"]["pos_fmt"] == "3º de 3"


def test_namespace_bumped_to_v4():
    from webui.services.screener import ScreenerService
    # [v1.28.4] v4 — the vs_rows carry the Posição keys (pos_rank/
    # pos_of/pos_fmt); cached v3 payloads lack them.
    assert ScreenerService._NS == "tools_screener_v4"
    # the Comparação's Mediana do Setor rides its own namespace
    assert ScreenerService._MED_NS == "tools_sector_medians_v1"


# ── 3. the Comparação's Mediana do Setor payload ─────────────────────────────

def _medians_stub(monkeypatch, entries, peers=None, subject="PETR4"):
    """sector_medians() over a stubbed sector (no engines, no cache)."""
    from webui.services.screener import ScreenerService
    if peers is None:
        peers = [{"ticker": e["ticker"], "is_subject": e["ticker"] == subject}
                 for e in entries]
    monkeypatch.setattr(ScreenerService, "_sector_companies",
                        lambda self, tk: (SECTOR, peers), raising=False)
    monkeypatch.setattr(ScreenerService, "_fetch_all",
                        lambda self, p: entries, raising=False)
    # None → the webui_payloads read/write is skipped entirely
    monkeypatch.setattr(ScreenerService, "_fingerprint",
                        staticmethod(lambda tks: None), raising=False)
    return ScreenerService().sector_medians(subject)


def test_sector_medians_payload_shape(monkeypatch):
    r = _medians_stub(monkeypatch, SECTOR_ENTRIES)

    assert r["status"] == "ok"
    assert r["ticker"] == "PETR4"
    assert r["sector"] == SECTOR
    assert r["company_count"] == 3
    meds = r["medians"]
    # P/L: median of {2,60 · 11,87 · 13,29} = 11,87
    assert meds["P/L"]["raw"] == pytest.approx(11.87)
    assert meds["P/L"]["fmt"] == "11,87"
    # ROE: median of {31,19% · 14,98% · 15,14%} = 15,14%
    assert meds["ROE"]["raw"] == pytest.approx(0.1514)
    assert meds["ROE"]["fmt"] == "15,14%"
    # Última Cotação (the comparison's own row): median price 40,87
    assert meds["Última Cotação"]["raw"] == pytest.approx(40.87)
    # the Dividendos rows (the dividends bucket the fetch now reads):
    # DPA {4,20 · 0,00 · —} → median 2,10 (DPA is not positive-only)
    assert meds["DPA"]["raw"] == pytest.approx(2.10)
    # Payout {55% · 10% · —} → median 32,5%
    assert meds["Payout"]["raw"] == pytest.approx(0.325)
    assert meds["Payout"]["fmt"] == "32,50%"
    # a metric NOBODY carries (Eventos reads the dividends bucket the
    # stub entries lack) is simply absent — no cell, not a fake zero
    assert "Eventos (B3)" not in meds
    assert "Remun. Total (últ. ano)" not in meds


def test_sector_medians_positive_only_rows(monkeypatch):
    """The P/L median counts POSITIVE values only (the v1.27 rule) — a
    loss-making peer never drags the sector's P/L median."""
    entries = [_entry("AAAA", val={"p_l": 10.0, "price": 10.0}),
               _entry("BBBB", val={"p_l": 20.0, "price": 20.0}),
               _entry("LOSS", val={"p_l": -5.0, "price": 5.0})]
    r = _medians_stub(monkeypatch, entries, subject="AAAA")
    assert r["status"] == "ok"
    # median of {10 · 20} — the -5 never enters
    assert r["medians"]["P/L"]["raw"] == pytest.approx(15.0)
    # prices are NOT positive-only: {10 · 20 · 5} → 10
    assert r["medians"]["Última Cotação"]["raw"] == pytest.approx(10.0)


def test_sector_medians_validation_and_error_paths(monkeypatch):
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    # bad ticker → the canonical error payload
    r = svc.sector_medians("XX")
    assert r == {"status": "error", "error": "ticker inválido: XX"}
    assert svc.sector_medians("")["status"] == "error"
    # unresolvable sector → the PT-BR sync hint
    monkeypatch.setattr(ScreenerService, "_sector_companies",
                        lambda self, tk: ("", []), raising=False)
    r = svc.sector_medians("PETR4")
    assert r["status"] == "error"
    assert "setor" in r["error"]
    # a sector with NO data at all → the PT-BR sources hint
    empty = [_entry("AAAA"), _entry("BBBB")]
    monkeypatch.setattr(ScreenerService, "_sector_companies",
                        lambda self, tk: (SECTOR, [{"ticker": "AAAA"},
                                                  {"ticker": "BBBB"}]),
                        raising=False)
    monkeypatch.setattr(ScreenerService, "_fetch_all",
                        lambda self, p: empty, raising=False)
    monkeypatch.setattr(ScreenerService, "_fingerprint",
                        staticmethod(lambda tks: None), raising=False)
    r = svc.sector_medians("AAAA")
    assert r["status"] == "error"
    assert "indicador" in r["error"]


def test_sector_medians_route_registered(memory_root):
    """/api/webui/tools/comparison/medians answers (not 404) with the
    canonical error payload on a bad ticker."""
    import webui.app as m
    from fastapi.testclient import TestClient
    client = TestClient(m.create_app(), base_url="http://127.0.0.1:8000")
    r = client.get("/api/webui/tools/comparison/medians?ticker=XX")
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    # the screener route stays as it was
    r = client.get("/api/webui/tools/screener?ticker=XX")
    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_fetch_all_reads_the_dividends_bucket(memory_root, monkeypatch):
    """The [v1.28.4] fetch line: _fetch_all also runs the dividends
    bucket — the comparison grid's Dividendos rows (DPA, payout,
    eventos, remun.) need it, and the medians payload asks for every
    _ROWS metric."""
    from webui.services import comparison as cmp_mod
    from webui.services.screener import ScreenerService

    called = []

    def _rec(name):
        def _f(entry):
            called.append(name)
        return _f

    for fname in ("_fetch_ratios", "_fetch_financials", "_fetch_growth",
                  "_fetch_dividends"):
        monkeypatch.setattr(cmp_mod.ComparisonService, fname,
                            staticmethod(_rec(fname)), raising=False)
    peers = [{"ticker": "PETR4", "is_subject": True}]
    entries = ScreenerService()._fetch_all(peers)
    assert entries, "the fetch pipeline still assembles entries"
    for fname in ("_fetch_ratios", "_fetch_financials", "_fetch_growth",
                  "_fetch_dividends"):
        assert fname in called, f"{fname} never ran"


# ── 4. the JS/CSS surface ────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]
_JS = (_ROOT / "webui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
_CSS = (_ROOT / "webui" / "static" / "css" / "app.css").read_text(encoding="utf-8")
_BASE = (_ROOT / "webui" / "templates" / "base.html").read_text(encoding="utf-8")


def test_js_cross_tool_navigation():
    assert "window.toolOpenScreener" in _JS
    assert "window.toolOpenBacktest" in _JS
    assert "window.toolCompare" in _JS
    # the three destinations validate the B3 shape before switching
    assert "_toolTk" in _JS
    # the comparison column cards + the screener head carry the links
    assert "cmp-tool-link" in _JS
    assert "simular no Backtest" in _JS
    assert "scr-head-tools" in _JS


def test_js_posicao_column_and_copy_summary():
    # the verdict table's new column
    assert ">Posição</th>" in _JS
    assert "scr-pos" in _JS and "scr-pos-top" in _JS
    assert "pos_fmt" in _JS
    # 📋 copiar resumo — the markdown clipboard
    assert "scrCopySummary" in _JS
    assert "copiar resumo" in _JS
    assert "navigator.clipboard" in _JS
    # the markdown table carries the position column too
    assert "| Métrica | Meu Valor | Mediana do Setor | Posição |" in _JS


def test_js_range_filters():
    assert "SCR_FILTER_KEYS" in _JS
    assert "scrFilterInput" in _JS and "scrClearFilters" in _JS
    assert "scr-filterbar" in _JS and "scr-filter-input" in _JS
    # DY reads a fraction (×100), market cap reads R$ (÷1e9)
    assert "['dy_raw', 100, 'dyMin', 'dyMax']" in _JS
    assert "['mktcap_raw', 1 / 1e9, 'mcMin', 'mcMax']" in _JS
    # the subject stays visible when the filters exclude it
    assert "subjectOutside" in _JS


def test_js_cancelar_everywhere():
    assert "window.cmpCancel" in _JS          # Comparação
    assert "window.btToolCancel" in _JS       # Backtest meta
    assert "window.btCancelRun" in _JS        # Backtest run
    assert "cmpMedStop" in _JS                # the medians fetch dies too
    # every loader's cancel path aborts its fetch
    assert _JS.count(".abort()") >= 10


def test_js_mediana_do_setor_progressive_fill():
    assert "cmpLoadMedians" in _JS
    assert 'data-cmp-med' in _JS
    assert "cmp-med-cell" in _JS and "cmp-med-pending" in _JS
    assert "/api/webui/tools/comparison/medians" in _JS
    assert "cmp-med-sector" in _JS


def test_css_and_asset_versions():
    for cls in (".cmp-tool-link", ".cmp-med-cell", ".cmp-med-pending",
                ".scr-pos-top", ".scr-filterbar", ".scr-filter-input",
                ".scr-head-tools", ".scr-copy-btn"):
        assert cls in _CSS, f"{cls} missing from app.css"
    # the cache-busting bump
    assert "app.js?v=90" in _BASE
    assert "app.css?v=90" in _BASE
    assert "v1.28.4" in _BASE


# ── 5. the docs maintenance ──────────────────────────────────────────────────

_ROADMAP = (_ROOT / "docs" / "webui" / "ROADMAP.md").read_text(encoding="utf-8")
_CHANGELOG = (_ROOT / "docs" / "webui" / "CHANGELOG.md").read_text(encoding="utf-8")


def test_roadmap_is_future_work_only():
    # no shipped strikethroughs left, no shipped-item essays
    assert "~~" not in _ROADMAP
    assert "SHIPPED" not in _ROADMAP
    # the open items survive
    for item in ("Theme accent color", "Agent chat tab", "Download report",
                 "Deferred / Out of Scope"):
        assert item in _ROADMAP, f"{item} lost from the roadmap"


def test_changelog_condensed():
    # the "In Progress / Next Up" section is gone (the ROADMAP owns it)
    assert "In Progress" not in _CHANGELOG
    # the v1.28.4 row exists and carries the round's headlines
    assert "v1.28.4" in _CHANGELOG
    for marker in ("Posição", "Mediana do Setor", "copiar resumo",
                   "range filters", "Cancelar"):
        assert marker in _CHANGELOG, f"{marker} missing from the v1.28.4 row"
