"""tests/webui/test_v127.py — the v1.27 Comparação tool suite.

[v1.27] The Ferramentas main tab + its first tool — hand-computed
fixtures mirroring the REAL data shapes (same recipe as test_v1261):

  1. validate() — the 2-4 bound, order-preserving dedupe, the B3 shape,
     the string parsing (comma / space / dot separated).
  2. _best_indices — the ranking heart: min/max directions, the
     positive-only eligibility (a negative P/L is a loss, not a
     bargain), ties (both win), < 2 eligible values → no highlight.
  3. _build_groups — rows assembled from fake per-ticker entries: raw +
     apply_fmt-formatted values, all-None rows dropped, best wired.
  4. Demonstrativos ranking — the annual-statement rows rank MAX like
     every other row (the user's ask); the Mercado size rows never do.
  5. _normalize_pct — the radar 0-100 normalization (max → 100,
     negatives clamp to 0, all-non-positive axis → dropped).
  6. _build_price_hist — the two-resolution series (month-ends over
     the whole history + the last ~13 months of dailies).
  7. _build_charts — the multiples chart skips non-positive values; the
     margin bars scale fractions ×100.
  8. compare() — the payload-cache roundtrip (build once → ⚡ note on
     the hit, fingerprint change → rebuild, ANY unknown ticker → cache
     skipped entirely); the graceful degradation paths (validation
     error, no data at all → the PT-BR "sincronize" error, partial data
     → "dados parciais" with the English internals logged, not leaked).
  9. HTTP surface — /webui/tools renders, /api/webui/tools/comparison
     validates, /api/webui/tools/comparison/search hits the bridge DB.

Run:  python -m pytest tests/webui/test_v127.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── shared fixtures ──────────────────────────────────────────────────────────

PETR = "33000167000101"
TEST = "11222333000181"


@pytest.fixture()
def memory_root(tmp_path, monkeypatch):
    """Isolated memory_root with a bridge.db (ticker_map) — never touches
    the real memory_db. The comparison service's other sources all
    degrade to empty against an empty root (the no-data paths)."""
    from core.config import cfg
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True)
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b = sqlite3.connect(str(cvm / "bridge.db"))
    b.execute("""CREATE TABLE IF NOT EXISTS ticker_map (
        ticker TEXT PRIMARY KEY, issuing TEXT, cd_cvm TEXT, trading_name TEXT,
        cnpj TEXT, denom_social TEXT, denom_comerc TEXT, sit TEXT,
        setor_ativ TEXT, tp_merc TEXT, synced_at TEXT)""")
    b.execute("INSERT INTO ticker_map (ticker, trading_name, cnpj) VALUES ('PETR4', 'PETROBRAS', ?)", (PETR,))
    b.execute("INSERT INTO ticker_map (ticker, trading_name, cnpj) VALUES ('TEST4', 'TEST COMPANY', ?)", (TEST,))
    b.commit()
    b.close()
    return tmp_path


def _entry(ticker: str, *, val=None, fin=None, div=None, grw=None, mkt=None,
           hist_monthly=None, hist_daily=None, error: str = "") -> dict:
    """One fake per-ticker fetch entry (the _fetch_one output shape)."""
    return {"ticker": ticker, "val": val or {}, "fin": fin or {},
            "div": div or {}, "grw": grw or {}, "mkt": mkt or {},
            "hist_monthly": hist_monthly or [], "hist_daily": hist_daily or [],
            "error": error}


# The PETR4/VALE3 pair from the real engines (fractions as fractions —
# apply_fmt does the ×100; pct values like growth too).
PETR_ENTRY = _entry(
    "PETR4",
    val={"price": 40.87, "market_cap": 338.85e9, "ev": 687.27e9,
         "total_shares": 7_889_444_211,
         "p_l": 2.60, "p_vpa": 0.81, "p_ebit": 1.85, "ev_ebitda": 2.56,
         "psr": 0.63, "ev_sales": 1.24,
         "roe": 0.3119, "roa": 0.1065, "margem_liquida": 0.2416,
         "marg_ebitda": 0.3123, "ocf_margin": 0.3976,
         "dividend_yield": 0.1061, "dpa": 4.56,
         "divida_pl": 0.92, "liquidez_corrente": 0.71},
    fin={"receita_liquida": 497.55e9, "ebitda": 155.37e9,
         "lucro_liquido": 110.61e9, "marg_bruta": 0.4763, "payout": 1.0},
    div={"event_count": 10},
    grw={"receita_yoy": 0.0042, "lucro_yoy": 0.0096},
    mkt={"price": 40.87, "price_date": "2026-11-24", "var_day": 0.012},
    hist_monthly=[{"date": "2026-10", "close": 38.0},
                  {"date": "2026-11", "close": 40.87}],
    hist_daily=[{"date": "2026-10-31", "close": 38.0},
                {"date": "2026-11-28", "close": 40.87}],
)
VALE_ENTRY = _entry(
    "VALE3",
    val={"price": 75.68, "market_cap": 322.66e9,
         "p_l": 77.17, "p_vpa": 1.71, "ev_ebitda": 8.49, "psr": 1.54,
         "roe": 0.0221, "roa": 0.0088, "margem_liquida": 0.0199,
         "marg_ebitda": 0.1551, "dividend_yield": 0.0724},
    fin={"receita_liquida": 213.59e9, "ebitda": 33.14e9,
         "lucro_liquido": 11.81e9, "marg_bruta": 0.3498, "payout": 1.0},
    div={"event_count": 4},
    grw={"receita_yoy": -0.0006},
    mkt={"price": 75.68, "price_date": "2026-11-24", "var_day": -0.008},
    hist_monthly=[{"date": "2026-11", "close": 75.68}],
    hist_daily=[{"date": "2026-11-28", "close": 75.68}],
)


# ── 1. validate ──────────────────────────────────────────────────────────────

def test_validate_bounds_and_dedupe():
    from webui.services.comparison import ComparisonService
    cs = ComparisonService()
    # dedupe keeps FIRST occurrence, uppercases
    assert cs.validate(["petr4", "VALE3", "PETR4"]) == (["PETR4", "VALE3"], "")
    assert cs.validate(["PETR4"])[1].startswith("escolha ao menos 2")
    assert cs.validate(["A", "B", "C", "D", "E"])[1].startswith("máximo de 4")
    assert "ticker inválido" in cs.validate(["PETR4", "XX"])[1]
    # B3SA3 (digit in the stem) and BOVA11 are legal
    assert cs.validate(["B3SA3", "BOVA11"]) == (["B3SA3", "BOVA11"], "")


def test_validate_string_parsing():
    from webui.services.comparison import ComparisonService
    cs = ComparisonService()
    # comma, whitespace and dot all separate (the URL param uses dots)
    assert cs.validate("PETR4,VALE3 ITUB4")[0] == ["PETR4", "VALE3", "ITUB4"]
    assert cs.validate("PETR4.VALE3")[0] == ["PETR4", "VALE3"]
    assert cs.validate("")[1]  # empty → PT-BR error, never a crash


# ── 2. the ranking heart ─────────────────────────────────────────────────────

def test_best_indices_directions_ties_and_eligibility():
    from webui.services.comparison import _best_indices
    # min among positives
    assert _best_indices([2.6, 77.17, None], "min", True) == [0]
    # negative P/L is a LOSS, not a bargain → skipped; 2 positives still rank
    assert _best_indices([-5.0, 2.6, 77.17], "min", True) == [1]
    # only ONE positive → nothing to rank
    assert _best_indices([-5.0, 2.6, None], "min", True) == []
    # max direction, pct rows allow negatives to compete
    assert _best_indices([0.0042, -0.0006], "max", False) == [0]
    assert _best_indices([-0.05, -0.02, None], "max", False) == [1]
    # tie → both highlighted
    assert _best_indices([2.6, 2.6, 3.0], "min", True) == [0, 1]
    # no direction → never highlights
    assert _best_indices([1.0, 2.0], None, False) == []
    # all None → nothing
    assert _best_indices([None, None], "max", False) == []


# ── 3. the grid rows ─────────────────────────────────────────────────────────

def test_build_groups_formats_and_ranks():
    from webui.services.comparison import _build_groups
    groups = _build_groups([PETR_ENTRY, VALE_ENTRY])
    by_key = {g["key"]: g for g in groups}
    assert list(by_key) == ["mercado", "valuation", "rentabilidade",
                            "crescimento", "dividendos", "endividamento",
                            "demonstrativos"]

    pl = next(r for r in by_key["valuation"]["rows"] if r["label"] == "P/L")
    assert pl["raw"] == [2.60, 77.17]
    assert pl["values"] == ["2,60", "77,17"]       # apply_fmt PT-BR
    assert pl["best"] == [0]                        # cheaper wins

    roe = next(r for r in by_key["rentabilidade"]["rows"] if r["label"] == "ROE")
    assert roe["values"] == ["31,19%", "2,21%"]     # fractions ×100
    assert roe["best"] == [0]

    var_day = next(r for r in by_key["mercado"]["rows"] if r["label"] == "Var. Dia")
    assert var_day["best"] == [0]                   # +1,2% beats −0,8%
    mcap = next(r for r in by_key["mercado"]["rows"] if r["label"] == "Market Cap")
    assert mcap["best"] == []                       # size never ranks
    assert mcap["values"][0].startswith("R$ 338,")  # compact bi


def test_build_groups_drops_inapplicable_rows():
    from webui.services.comparison import _build_groups
    # rows NOBODY has are dropped: entries carrying only p_l → exactly one
    # row survives (the all-None majority never reaches the payload)
    a = _entry("AAAA3", val={"p_l": 5.0})
    b = _entry("BBBB3", val={"p_l": 7.0})
    groups = _build_groups([a, b])
    labels = [r["label"] for g in groups for r in g["rows"]]
    assert labels == ["P/L"]
    # one-sided rows survive with a single value — but no ranking
    groups = _build_groups([PETR_ENTRY, _entry("XXXX3")])
    pl = next(r for g in groups for r in g["rows"] if r["label"] == "P/L")
    assert pl["values"] == ["2,60", "—"]
    assert pl["best"] == []                          # 1 value can't win


# ── 4. Demonstrativos ranking (the annual-statement rows rank MAX) ─────────

def test_demonstrativos_rank_like_every_other_row():
    from webui.services.comparison import _build_groups
    groups = _build_groups([PETR_ENTRY, VALE_ENTRY])
    by_key = {g["key"]: g for g in groups}
    # the annual-statement rows carry the ✓ the others do — biggest wins
    demo = by_key["demonstrativos"]["rows"]
    lucro = next(r for r in demo if r["label"] == "Lucro Líquido")
    assert lucro["best"] == [0]           # 110,61 bi > 11,81 bi
    receita = next(r for r in demo if r["label"] == "Receita Líquida")
    assert receita["best"] == [0]         # 497,55 bi > 213,59 bi
    # …while the MERCADO size rows still never rank
    mcap = next(r for r in by_key["mercado"]["rows"]
                if r["label"] == "Market Cap")
    assert mcap["best"] == []
    # a one-sided Demonstrativos row keeps its column but can't rank
    groups = _build_groups([PETR_ENTRY, _entry("XXXX3")])
    demo = next(g for g in groups if g["key"] == "demonstrativos")["rows"]
    lucro = next(r for r in demo if r["label"] == "Lucro Líquido")
    assert lucro["values"][1] == "—" and lucro["best"] == []


# ── 5. radar normalization ───────────────────────────────────────────────────

def test_normalize_pct():
    from webui.services.comparison import _normalize_pct
    assert _normalize_pct([0.3119, 0.0221]) == [100.0, 7.1]  # 0.0221/0.3119
    assert _normalize_pct([-0.05, 0.10]) == [0.0, 100.0]     # negative clamps
    assert _normalize_pct([None, 0.10]) == [None, 100.0]
    assert _normalize_pct([-0.1, -0.2]) == [None, None]      # no positive max
    assert _normalize_pct([None, None]) == [None, None]


# ── 6. price history (two resolutions) ───────────────────────────────────────

def test_build_price_hist_two_resolutions():
    from webui.services.comparison import _build_price_hist
    ph = _build_price_hist([PETR_ENTRY, VALE_ENTRY])
    # monthly: month-end closes over the whole history (the long pills)
    assert ph["monthly"]["PETR4"] == [
        {"date": "2026-10", "close": 38.0},
        {"date": "2026-11", "close": 40.87}]
    assert ph["monthly"]["VALE3"] == [{"date": "2026-11", "close": 75.68}]
    # daily: the recent dailies (the 1A/6M/3M/1M pills)
    assert ph["daily"]["VALE3"] == [{"date": "2026-11-28", "close": 75.68}]
    # an entry without cotações degrades to empty series, never a crash
    empty = _build_price_hist([_entry("XXXX3")])
    assert empty["monthly"]["XXXX3"] == [] and empty["daily"]["XXXX3"] == []


# ── 7. charts ────────────────────────────────────────────────────────────────

def test_build_charts_shapes_and_scales():
    from webui.services.comparison import _build_charts
    charts = {c["id"]: c for c in _build_charts([PETR_ENTRY, VALE_ENTRY],
                                                ["PETR4", "VALE3"])}
    # radar: normalized axes, one dataset per company
    radar = charts["radar"]["cd"]
    assert radar["type"] == "radar"
    assert len(radar["data"]["datasets"]) == 2
    roe_axis = radar["data"]["labels"].index("ROE")
    assert radar["data"]["datasets"][0]["data"][roe_axis] == 100.0
    assert radar["data"]["datasets"][1]["data"][roe_axis] == 7.1

    # multiples: ×1 scale, non-positives dropped
    mult = charts["multiplos"]["cd"]
    pl_idx = mult["data"]["labels"].index("P/L")
    assert mult["data"]["datasets"][0]["data"][pl_idx] == 2.6
    neg = _entry("NEG3", val={"p_l": -3.0, "p_vpa": 1.0})
    neg_charts = {c["id"]: c for c in _build_charts(
        [PETR_ENTRY, neg], ["PETR4", "NEG3"])}
    neg_mult = neg_charts["multiplos"]["cd"]
    assert neg_mult["data"]["datasets"][1]["data"][pl_idx] is None

    # margins: fractions ×100 into percent units
    marg = charts["margens"]["cd"]
    bruta_idx = marg["data"]["labels"].index("Marg. Bruta")
    assert marg["data"]["datasets"][0]["data"][bruta_idx] == 47.63

    # a company with no chart data at all contributes no dataset
    lone = _build_charts([PETR_ENTRY, _entry("XXXX3")], ["PETR4", "XXXX3"])
    for ch in lone:
        assert len(ch["cd"]["data"]["datasets"]) == 1


# ── 8. compare() — cache + degradation ───────────────────────────────────────

def test_compare_payload_cache_roundtrip(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.comparison import ComparisonService

    calls = {"n": 0}

    def fake_fetch_all(self, tks):
        calls["n"] += 1
        return [PETR_ENTRY, VALE_ENTRY]

    monkeypatch.setattr(ComparisonService, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(ComparisonService, "_fingerprint",
                        lambda self, tks: "fp-A")

    svc = ComparisonService()
    r1 = svc.compare(["PETR4", "VALE3"])
    assert calls["n"] == 1 and r1["status"] == "ok"
    assert "cache_note" not in r1
    assert "kpis" not in r1                       # the leader cards are gone
    assert r1["price_hist"]["monthly"]["PETR4"][0] == {
        "date": "2026-10", "close": 38.0}

    r2 = svc.compare(["PETR4", "VALE3"])
    assert calls["n"] == 1                       # HIT — no rebuild
    assert "Pré-calculado" in r2["cache_note"]
    assert r2["tickers"] == ["PETR4", "VALE3"]   # payload intact

    monkeypatch.setattr(ComparisonService, "_fingerprint",
                        lambda self, tks: "fp-B")   # any ticker's data moved
    r3 = svc.compare(["PETR4", "VALE3"])
    assert calls["n"] == 2 and "cache_note" not in r3

    # a different ORDER is a different comparison (cache key = join order)
    monkeypatch.setattr(ComparisonService, "_fingerprint",
                        lambda self, tks: "fp-A")
    svc.compare(["VALE3", "PETR4"])
    assert calls["n"] == 3


def test_compare_no_fingerprint_skips_cache(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.comparison import ComparisonService

    calls = {"n": 0}

    def fake_fetch_all(self, tks):
        calls["n"] += 1
        return [PETR_ENTRY, VALE_ENTRY]

    monkeypatch.setattr(ComparisonService, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(ComparisonService, "_fingerprint",
                        lambda self, tks: None)   # ANY unknown ticker
    svc = ComparisonService()
    svc.compare(["PETR4", "VALE3"])
    svc.compare(["PETR4", "VALE3"])
    assert calls["n"] == 2                        # never cached


def test_compare_validation_and_no_data(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.comparison import ComparisonService
    svc = ComparisonService()

    # < 2 tickers → PT-BR error, nothing fetched
    r = svc.compare(["PETR4"])
    assert r["status"] == "error" and "ao menos 2" in r["error"]

    # no data at all → the sync hint names the sources
    monkeypatch.setattr(ComparisonService, "_fetch_all",
                        lambda self, tks: [_entry("PETR4"), _entry("VALE3")])
    r = svc.compare(["PETR4", "VALE3"])
    assert r["status"] == "error" and "sincronize" in r["error"].lower()


def test_compare_partial_data_is_ptbr_not_english(monkeypatch, tmp_path):
    """A ticker whose engines failed keeps its column — the UI sees
    'dados parciais', the English internals go to stderr only."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.comparison import ComparisonService

    broken = _entry("VALE3", error="Financials unavailable: no data from calculations engines")
    monkeypatch.setattr(ComparisonService, "_fetch_all",
                        lambda self, tks: [PETR_ENTRY, broken])
    monkeypatch.setattr(ComparisonService, "_fingerprint",
                        lambda self, tks: None)
    r = ComparisonService().compare(["PETR4", "VALE3"])
    assert r["status"] == "ok"
    assert r["companies"][1]["error"] == "dados parciais"
    assert "calculations engines" not in str(r)     # no English leak


# ── 9. HTTP surface ──────────────────────────────────────────────────────────

@pytest.fixture()
def client(memory_root):
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_tools_page_renders(client):
    r = client.get("/webui/tools")
    assert r.status_code == 200
    body = r.text
    assert "Comparação" in body
    assert "cmp-search" in body            # the picker input
    assert "nav.tools" not in body         # t() resolved, not raw key
    assert ">Ferramentas<" in body         # the sidebar item (both locales)


def test_http_comparison_validation(client):
    # 1 ticker → the canonical error payload (HTTP 200, client renders it)
    r = client.get("/api/webui/tools/comparison", params={"tickers": "PETR4"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "ao menos 2" in body["error"]

    r = client.get("/api/webui/tools/comparison",
                   params={"tickers": "PETR4,VALE3,ITUB4,WEGE3,BBAS3"})
    assert "máximo de 4" in r.json()["error"]


def test_http_comparison_search_hits_bridge(client):
    r = client.get("/api/webui/tools/comparison/search", params={"q": "PETR"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results and results[0]["ticker"] == "PETR4"
    assert results[0]["name"] == "PETROBRAS"

    r = client.get("/api/webui/tools/comparison/search", params={"q": "ZZZZ"})
    assert r.json()["results"] == []
