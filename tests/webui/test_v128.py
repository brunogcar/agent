"""tests/webui/test_v128.py — the v1.28 Screener tool suite.

[v1.28] The Ferramentas tab's second tool — hand-computed fixtures
mirroring the REAL data shapes and the PETR4_screener_dashboard.html
concept numbers (same recipe as test_v127):

  1. validate() — one ticker, the B3 shape, the PT-BR error messages.
  2. _median — odd/even counts, missing values never drag the median,
     positive-only (a negative P/L is a loss, not a bargain), NaN guard.
  3. _verdict — cheap/expensive (lower-better) vs above/below
     (higher-better), the negative-multiple → na rule, net-debt
     negative → cheap (caixa líquido), ties and missing medians → na.
  4. _sector_companies — the bridge setor_ativ discovery, the CNPJ-root
     dedupe (PETR3/PETR4 = ONE company, the most liquid class kept —
     suffix preference with no cotahist), the accent/case-insensitive
     sector key, subject-first ordering, the liquidity cap.
  5. _vs_rows — the concept dashboard's own numbers: the 3-company
     sector's median P/L 11,87 / P/VPA 1,78 / EV/EBITDA 6,47 /
     ROE 15,14%, PETR4's P/L delta -78,08% → cheap, ROE above.
  6. _build — the peers table P/L-cheapest-first with the subject row
     flagged, the 5 median KPI cards, the PT-BR partial-data contract
     (English internals logged, never leaked), price_hist subject-only.
  7. _build_charts — the P/L and ROE position charts (sorted, the
     subject in amber, the median dashed line, losses excluded) and
     the vs_mediana grouped bars (negative multiples skipped).
  8. screen() — the payload-cache roundtrip (build once → ⚡ note on
     the hit, fingerprint change → rebuild), the fingerprint composites
     the PEER LIST (membership changes invalidate), the degradation
     paths (unknown sector, single-company sector, no data at all →
     PT-BR sincronize hints).
  9. HTTP surface — /webui/tools renders BOTH pills, /api/webui/tools/
     screener validates and degrades in PT-BR.

Run:  python -m pytest tests/webui/test_v128.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── shared fixtures ──────────────────────────────────────────────────────────

PETR = "33000167000101"      # PETR3 + PETR4 (one company, two classes)
PRIO = "02187300000111"
UGPA = "33252800000100"
TEST = "11222333000181"

SECTOR = "Petróleo e Gás"


@pytest.fixture()
def memory_root(tmp_path, monkeypatch):
    """Isolated memory_root with a bridge.db carrying a WHOLE SECTOR —
    PETR3/PETR4 (one CNPJ root, two classes) + PRIO3 + UGPA3 in
    'Petróleo e Gás' (the concept dashboard's own trio); ITUB4 alone in
    'Bancos'; TEST4 with no sector. The other sources (DFP/ITR/
    cotahist) degrade to empty against an empty root — the no-data
    paths."""
    from core.config import cfg
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True)
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b = sqlite3.connect(str(cvm / "bridge.db"))
    b.execute("""CREATE TABLE IF NOT EXISTS ticker_map (
        ticker TEXT PRIMARY KEY, issuing TEXT, cd_cvm TEXT, trading_name TEXT,
        cnpj TEXT, denom_social TEXT, denom_comerc TEXT, sit TEXT,
        setor_ativ TEXT, tp_merc TEXT, synced_at TEXT)""")
    rows = [
        ("PETR4", "PETR", "9512", "PETROBRAS", PETR, SECTOR),
        ("PETR3", "PETR", "9512", "PETROBRAS", PETR, SECTOR),
        ("PRIO3", "PRIO", "22148", "PRIO", PRIO, SECTOR),
        ("UGPA3", "UGPA", "20646", "ULTRAPAR", UGPA, SECTOR),
        ("ITUB4", "ITUB", "54862", "ITAU UNIBANCO", "60872504000123", "Bancos"),
        ("TEST4", "TEST", "", "TEST COMPANY", TEST, None),
    ]
    for tk, iss, cd, name, cnpj, setor in rows:
        b.execute(
            "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, "
            "cnpj, setor_ativ) VALUES (?, ?, ?, ?, ?, ?)",
            (tk, iss, cd, name, cnpj, setor))
    b.commit()
    b.close()
    return tmp_path


def _entry(ticker: str, *, val=None, fin=None, grw=None, mkt=None,
           hist_monthly=None, hist_daily=None, error: str = "") -> dict:
    """One fake per-ticker fetch entry (the _fetch_one output shape)."""
    return {"ticker": ticker, "val": val or {}, "fin": fin or {},
            "grw": grw or {}, "mkt": mkt or {},
            "hist_monthly": hist_monthly or [], "hist_daily": hist_daily or [],
            "error": error}


# The PETR4 / PRIO3 / UGPA3 sector from the concept dashboard (fractions
# as fractions — apply_fmt does the ×100). PRIO3/UGPA3 carry only the
# metrics the concept table showed for them.
PETR_ENTRY = _entry(
    "PETR4",
    val={"price": 40.87, "market_cap": 338.85e9, "p_l": 2.60,
         "p_vpa": 0.81, "p_ebit": 1.85, "ev_ebitda": 2.56, "psr": 0.63,
         "roe": 0.3119, "roa": 0.1065, "margem_liquida": 0.2416,
         "marg_ebitda": 0.3123, "dividend_yield": 0.1061,
         "divida_pl": 0.92, "divida_liquida_ebitda": 0.66},
    fin={"receita_liquida": 497.55e9, "ebitda": 155.37e9},
    grw={"receita_yoy": 0.0042},
    mkt={"price": 40.87, "price_date": "2026-11-24", "var_day": 0.012},
    hist_monthly=[{"date": "2026-10", "close": 38.0},
                  {"date": "2026-11", "close": 40.87}],
    hist_daily=[{"date": "2026-11-21", "close": 38.0},
                {"date": "2026-11-24", "close": 40.87}],
)
PRIO_ENTRY = _entry(
    "PRIO3",
    val={"price": 60.54, "market_cap": 45.84e9, "p_l": 11.87,
         "p_vpa": 1.78, "ev_ebitda": 6.47, "roe": 0.1498,
         "marg_ebitda": 0.4919},
    fin={"receita_liquida": 15.58e9, "ebitda": 7.67e9},
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

# The whole deduped sector (PETR3 folded into PETR4) in fetch order.
SECTOR_ENTRIES = [PETR_ENTRY, PRIO_ENTRY, UGPA_ENTRY]


# ── 1. validate ──────────────────────────────────────────────────────────────

def test_validate_single_ticker():
    from webui.services.screener import ScreenerService
    assert ScreenerService.validate("petr4") == ("PETR4", "")
    assert ScreenerService.validate(" PETR4 ") == ("PETR4", "")
    tk, err = ScreenerService.validate("")
    assert tk == "" and "informe o ticker" in err
    tk, err = ScreenerService.validate("XX")
    assert tk == "" and "ticker inválido" in err


# ── 2. _median ───────────────────────────────────────────────────────────────

def test_median_odd_even_missing_and_positive_only():
    from webui.services.screener import ScreenerService
    m = ScreenerService._median
    assert m([2.95, 11.87, 13.29], positive_only=True) == 11.87
    assert m([2.60, 11.87, 13.29, 77.17]) == pytest.approx(
        (11.87 + 13.29) / 2)                     # even → mean of the middle two
    assert m([0.1061, None, 0.0389]) == pytest.approx(
        (0.0389 + 0.1061) / 2)                   # missing never drags the median
    assert m([-5.0, 10.0, 20.0], positive_only=True) == 15.0   # loss excluded
    assert m([-5.0, -10.0], positive_only=True) is None        # no eligible value
    assert m([]) is None
    assert m([None, "x", True]) is None          # garbage never counts
    assert m([1.0, float("nan"), 3.0]) == 2.0    # NaN guard


# ── 3. _verdict ──────────────────────────────────────────────────────────────

def test_verdict_directions_and_edge_rules():
    from webui.services.screener import ScreenerService
    v = ScreenerService._verdict
    # lower-better rows: below the median = cheap, above = expensive
    assert v("cheap", 2.60, 11.87, True) == "cheap"
    assert v("cheap", 13.29, 11.87, True) == "expensive"
    # a negative multiple is a loss, not a bargain → na
    assert v("cheap", -1.0, 11.87, True) == "na"
    # …but net debt (positive_only=False) negative = caixa líquido → cheap
    assert v("cheap", -0.5, 1.10, False) == "cheap"
    assert v("cheap", 2.0, 1.10, False) == "expensive"
    # higher-better rows: above / below
    assert v("above", 0.3119, 0.1514, False) == "above"
    assert v("above", 0.0221, 0.1514, False) == "below"
    # ties and missing values → na
    assert v("cheap", 11.87, 11.87, True) == "na"
    assert v("above", None, 0.1514, False) == "na"
    assert v("cheap", 2.60, None, True) == "na"


# ── 4. sector discovery + dedupe ─────────────────────────────────────────────

def test_sector_companies_dedupes_classes_and_filters_sector(memory_root):
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    sector, peers = svc._sector_companies("PETR4")
    assert sector == SECTOR
    tickers = [p["ticker"] for p in peers]
    # PETR3 folded into PETR4 (CNPJ root; no cotahist in the fixture
    # root → the suffix preference keeps the 4), ITUB4 (other sector)
    # and TEST4 (no sector) never appear. Subject first, then the
    # liquidity order (all 0 → alphabetical).
    assert tickers == ["PETR4", "PRIO3", "UGPA3"]
    assert peers[0]["is_subject"] is True
    assert [p["is_subject"] for p in peers[1:]] == [False, False]
    assert all(p["name"] for p in peers)


def test_sector_key_is_accent_and_case_insensitive(memory_root, monkeypatch):
    """A CAD-fallback sector string ('PETROLEO E GAS') still matches the
    bridge rows synced as 'Petróleo e Gás'."""
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    monkey_sector = "PETROLEO E GAS"
    monkeypatch.setattr(ScreenerService, "_sector_of",
                        staticmethod(lambda tk: monkey_sector))
    sector, peers = svc._sector_companies("PETR4")
    assert sector == monkey_sector
    # the subject's own row has no setor_ativ match — it still joins
    # its sector as the screened company (prepended).
    assert peers[0]["ticker"] == "PETR4" and peers[0]["is_subject"]
    assert "PRIO3" in [p["ticker"] for p in peers]


def test_sector_cap_keeps_subject(memory_root, monkeypatch):
    """A huge sector is capped by liquidity — the subject always stays."""
    import webui.services.screener as mod
    from webui.services.screener import ScreenerService
    monkeypatch.setattr(mod, "MAX_COMPANIES", 2)
    sector, peers = ScreenerService()._sector_companies("UGPA3")
    assert sector == SECTOR
    assert len(peers) == 2
    assert "UGPA3" in [p["ticker"] for p in peers]
    assert sum(1 for p in peers if p["is_subject"]) == 1


def test_liquidity_missing_db_is_zero(memory_root):
    from webui.services.screener import ScreenerService
    liq = ScreenerService._liquidity(["PETR4", "NOPE3"])
    assert liq == {"PETR4": 0.0, "NOPE3": 0.0}


# ── 5. the vs-median rows (the concept dashboard's own numbers) ──────────────

def test_vs_rows_medians_and_verdicts(memory_root):
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    rows = {r["label"]: r for r in svc._vs_rows(PETR_ENTRY, SECTOR_ENTRIES)}
    # medians over the deduped sector INCLUDING the subject (3 companies:
    # PETR4 2,60 / PRIO3 11,87 / UGPA3 13,29 — the concept numbers)
    assert rows["P/L"]["med"] == pytest.approx(11.87)
    assert rows["P/L"]["med_fmt"] == "11,87"
    assert rows["P/VPA"]["med"] == pytest.approx(1.78)
    assert rows["EV/EBITDA"]["med"] == pytest.approx(6.47)
    assert rows["ROE"]["med"] == pytest.approx(0.1514)
    assert rows["ROE"]["med_fmt"] == "15,14%"
    # Div Yield: PETR4 10,61% / PRIO3 — / UGPA3 3,89% → median 7,25%
    assert rows["Div Yield"]["med"] == pytest.approx(0.0725)
    # PETR4's verdicts: cheap multiples, above-median quality
    assert rows["P/L"]["verdict"] == "cheap"
    assert rows["P/L"]["delta"] == pytest.approx(2.60 / 11.87 - 1)
    assert rows["P/L"]["delta_fmt"] == "-78,10%"       # 2,60 vs 11,87
    assert rows["ROE"]["verdict"] == "above"
    assert rows["Div Yield"]["verdict"] == "above"
    # a metric only PETR4 carries: the median IS its value → tie → na
    assert rows["Dívida Líq./EBITDA"]["med"] == pytest.approx(0.66)
    assert rows["Dívida Líq./EBITDA"]["verdict"] == "na"
    assert rows["PSR"]["verdict"] == "na"


def test_vs_rows_negative_multiple_is_na_not_cheap():
    """A subject with a NEGATIVE P/L (a loss) gets na — never 'cheap'."""
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    subject = _entry("LOSS3", val={"p_l": -4.2, "roe": 0.10})
    peers = [subject, _entry("A", val={"p_l": 10.0, "roe": 0.20}),
             _entry("B", val={"p_l": 20.0, "roe": 0.30})]
    rows = {r["label"]: r for r in svc._vs_rows(subject, peers)}
    assert rows["P/L"]["verdict"] == "na"
    assert rows["P/L"]["med"] == 15.0          # the loss never drags the median
    assert rows["ROE"]["verdict"] == "below"


# ── 6. payload assembly ──────────────────────────────────────────────────────

def _screened(memory_root, monkeypatch, entries=None):
    """screen() with the engines faked — the bridge sector stays real."""
    from webui.services.screener import ScreenerService
    if entries is not None:
        monkeypatch.setattr(ScreenerService, "_fetch_all",
                            lambda self, peers: entries)
    monkeypatch.setattr(ScreenerService, "_fingerprint",
                        lambda self, tks: None)   # cache OFF for unit paths
    return ScreenerService().screen("PETR4")


def test_build_payload_shape(memory_root, monkeypatch):
    r = _screened(memory_root, monkeypatch, SECTOR_ENTRIES)
    assert r["status"] == "ok"
    assert r["ticker"] == "PETR4" and r["sector"] == SECTOR
    assert r["company_count"] == 3
    assert r["name"] == "PETROBRAS"
    assert r["price"] == 40.87 and r["price_date"] == "2026-11-24"
    # the 5 median KPI cards (formatted server-side)
    assert [(k["label"], k["value"]) for k in r["kpis"]] == [
        ("Mediana P/L", "11,87"), ("Mediana P/VPA", "1,78"),
        ("Mediana EV/EBITDA", "6,47"), ("Mediana ROE", "15,14%"),
        ("Mediana Div Yield", "7,25%"),
    ]
    # the peers table: P/L cheapest-first, the subject flagged
    assert [t["ticker"] for t in r["table"]] == ["PETR4", "PRIO3", "UGPA3"]
    assert r["table"][0]["is_subject"] is True
    assert r["table"][0]["p_l"] == "2,60"
    assert r["table"][0]["market_cap"].startswith("R$")
    assert r["table"][0]["segmento"] == ""          # no FCA/B3 db in the root
    # the price history ships for the SUBJECT only
    assert list(r["price_hist"]["monthly"].keys()) == ["PETR4"]
    assert r["price_hist"]["monthly"]["PETR4"][0] == {
        "date": "2026-10", "close": 38.0}
    # vs rows + charts present
    assert any(row["verdict"] == "cheap" for row in r["vs_rows"])
    assert {c["id"] for c in r["charts"]} == {
        "pl_setor", "roe_setor", "vs_mediana"}


def test_build_partial_data_is_ptbr_not_english(memory_root, monkeypatch, capsys):
    broken = _entry("UGPA3", error="Financials unavailable: no data from calculations engines")
    entries = [PETR_ENTRY, PRIO_ENTRY, broken]
    r = _screened(memory_root, monkeypatch, entries)
    assert r["status"] == "ok"
    assert [t["ticker"] for t in r["table"]] == ["PETR4", "PRIO3", "UGPA3"]
    assert r["table"][-1]["partial"] is True
    assert r["errors"] == [
        "UGPA3: algumas fontes falharam (indicadores parciais — "
        "veja o log do sistema)"]
    assert "calculations engines" not in str(r)      # no English leak
    assert "calculations engines" in capsys.readouterr().err  # logged instead


def test_build_no_data_at_all(memory_root, monkeypatch):
    r = _screened(memory_root, monkeypatch,
                  [_entry("PETR4"), _entry("PRIO3"), _entry("UGPA3")])
    assert r["status"] == "error" and "sincronize" in r["error"].lower()


# ── 7. charts ────────────────────────────────────────────────────────────────

def test_position_charts_sort_highlight_and_median_line(memory_root, monkeypatch):
    r = _screened(memory_root, monkeypatch, SECTOR_ENTRIES)
    charts = {c["id"]: c for c in r["charts"]}
    pl = charts["pl_setor"]["cd"]
    # cheapest-first: PETR4 2,60 → PRIO3 11,87 → UGPA3 13,29
    assert pl["data"]["labels"] == ["PETR4", "PRIO3", "UGPA3"]
    assert pl["data"]["datasets"][0]["data"] == [2.60, 11.87, 13.29]
    # the subject's bar is amber, the others teal
    assert pl["data"]["datasets"][0]["backgroundColor"][0] == "#f59e0b"
    assert pl["data"]["datasets"][0]["backgroundColor"][1] == "#0d9488cc"
    # the sector median as a dashed line over every bar
    line = pl["data"]["datasets"][1]
    assert line["type"] == "line" and line["borderDash"] == [6, 4]
    assert line["data"] == [11.87, 11.87, 11.87]
    # ROE: descending, fractions ×100
    roe = charts["roe_setor"]["cd"]
    assert roe["data"]["labels"] == ["PETR4", "UGPA3", "PRIO3"]
    assert roe["data"]["datasets"][0]["data"] == [31.19, 15.14, 14.98]


def test_position_chart_excludes_losses_and_vs_bars_skip_negative():
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    # the SUBJECT carries a negative P/VPA (broken multiple) and one
    # peer carries a loss — neither charts; the P/L bars run over the
    # positives only and the vs_mediana P/VPA "my" value is skipped.
    subject = _entry("NEG3", val={"p_l": 10.0, "p_vpa": -0.5, "roe": 0.10})
    entries = [
        subject,
        _entry("OKAY3", val={"p_l": 20.0, "p_vpa": 2.0, "roe": 0.30}),
        _entry("LOSS3", val={"p_l": -5.0, "p_vpa": 1.0, "roe": 0.20}),
    ]
    vs_rows = svc._vs_rows(subject, entries)
    charts = {c["id"]: c for c in svc._build_charts("NEG3", entries, vs_rows)}
    pl = charts["pl_setor"]["cd"]
    assert pl["data"]["labels"] == ["NEG3", "OKAY3"]     # LOSS3 out
    assert pl["data"]["datasets"][0]["data"] == [10.0, 20.0]
    assert pl["data"]["datasets"][1]["data"] == [15.0, 15.0]  # median line
    # the negative P/VPA never bars — my value is None, the median runs
    # over the positive peers (1,0 / 2,0 → 1,5)
    vs = charts["vs_mediana"]["cd"]
    i = vs["data"]["labels"].index("P/VPA")
    assert vs["data"]["datasets"][0]["data"][i] is None   # NEG3's -0.5
    assert vs["data"]["datasets"][1]["data"][i] == 1.5


def test_vs_mediana_chart_scales_and_values(memory_root, monkeypatch):
    r = _screened(memory_root, monkeypatch, SECTOR_ENTRIES)
    vs = [c for c in r["charts"] if c["id"] == "vs_mediana"][0]["cd"]
    assert vs["data"]["labels"] == [
        "P/L", "P/VPA", "EV/EBITDA", "ROE", "Div Yield", "Marg. Líquida"]
    # PETR4 (teal) vs the median (amber) — % metrics ×100, multiples ×1
    assert vs["data"]["datasets"][0]["data"] == [
        2.60, 0.81, 2.56, 31.19, 10.61, 24.16]
    assert vs["data"]["datasets"][1]["data"] == [
        11.87, 1.78, 6.47, 15.14, 7.25, 24.16]
    # Marg. Líquida: only PETR4 carries it → the median IS its value.


# ── 8. screen() — cache + degradation ────────────────────────────────────────

def test_screen_payload_cache_roundtrip(memory_root, monkeypatch):
    from webui.services.screener import ScreenerService
    calls = {"n": 0}

    def fake_fetch_all(self, peers):
        calls["n"] += 1
        return SECTOR_ENTRIES

    monkeypatch.setattr(ScreenerService, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(ScreenerService, "_fingerprint",
                        lambda self, tks: "fp-A")
    svc = ScreenerService()

    r1 = svc.screen("PETR4")
    assert calls["n"] == 1 and r1["status"] == "ok"
    assert "cache_note" not in r1

    r2 = svc.screen("PETR4")
    assert calls["n"] == 1                       # HIT — no rebuild
    assert "Pré-calculado" in r2["cache_note"]
    assert r2["ticker"] == "PETR4" and r2["company_count"] == 3

    monkeypatch.setattr(ScreenerService, "_fingerprint",
                        lambda self, tks: "fp-B")   # any peer's data moved
    r3 = svc.screen("PETR4")
    assert calls["n"] == 2 and "cache_note" not in r3


def test_fingerprint_composites_the_peer_list(memory_root, monkeypatch):
    """The fingerprint carries the PEER LIST — a bridge resync that
    changes the sector membership invalidates the cached payload."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(memory_root), raising=False)
    import data_sources._cache as _dc
    from webui.services.screener import ScreenerService
    monkeypatch.setattr(_dc, "webui_fingerprint", lambda tk: "x")
    fp = ScreenerService._fingerprint(["PETR4", "PRIO3", "UGPA3"])
    assert fp == "PETR4:x|PRIO3:x|UGPA3:x|members=PETR4,PRIO3,UGPA3"
    # ANY unknown ticker → None → the cache is skipped entirely
    monkeypatch.setattr(_dc, "webui_fingerprint",
                        lambda tk: None if tk == "UGPA3" else "x")
    assert ScreenerService._fingerprint(["PETR4", "PRIO3", "UGPA3"]) is None


def test_screen_unknown_sector_and_single_company_sector(memory_root, monkeypatch):
    from webui.services.screener import ScreenerService
    svc = ScreenerService()
    # TEST4 carries no setor_ativ and no CAD → the sync hint
    r = svc.screen("TEST4")
    assert r["status"] == "error" and "setor" in r["error"].lower()
    assert "Bridge" in r["error"]
    # a sector with a SINGLE company → no medians to compare
    r = svc.screen("ITUB4")
    assert r["status"] == "error" and "não tem outras companhias" in r["error"]


# ── 9. HTTP surface ──────────────────────────────────────────────────────────

@pytest.fixture()
def client(memory_root):
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_tools_page_renders_both_pills(client):
    r = client.get("/webui/tools")
    assert r.status_code == 200
    body = r.text
    assert ">Comparação<" in body                # the first tool stays
    assert ">Screener<" in body                  # the new pill
    assert "cmp-search" in body and "scr-search" in body
    assert "family-pill-screener" in body
    assert 'id="family-screener"' in body        # the panel (hidden until pill)
    assert "scr-result" in body


def test_http_screener_validation(client):
    r = client.get("/api/webui/tools/screener")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error" and "informe o ticker" in body["error"]

    r = client.get("/api/webui/tools/screener", params={"ticker": "XX"})
    assert "ticker inválido" in r.json()["error"]


def test_http_screener_no_sector_degrades_in_ptbr(client):
    r = client.get("/api/webui/tools/screener", params={"ticker": "TEST4"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "sincronize a Bridge" in body["error"]


def test_http_screener_full_payload(client):
    """The full path over HTTP against the seeded bridge: the sector
    resolves (PETR3 folded into PETR4) but the engines degrade (empty
    DFP/ITR in the fixture root) → the PT-BR sincronize hint."""
    r = client.get("/api/webui/tools/screener", params={"ticker": "PETR4"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "sincronize" in body["error"].lower()
