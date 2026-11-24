"""tests/webui/test_portfolio_v1224.py — the v1.22.4 fix-wave suite.

One test per user-reported bug, HAND-COMPUTED values (the v1.22.1
discipline — a regression here fails before the user's portfolio does):

  1.  EVOLUÇÃO 500 (the "Unexpected token 'I'" report): a buy priced
      far above that day's close flips the TWR chain negative → the
      old code annualized a complex number into json.dumps → 500
      plain-text. Now: twr_total/twr_annual None + the sign-flip note
      + a JSON-serializable payload; _annualize refuses base ≤ 0.
  2.  THE NEVER-PLAIN-TEXT RULE: a report builder that RAISES answers
      JSON {"ok": false} (the route-level _report belt).
  3.  IVVB11 — the S&P 500 (BRL) proxy joins the benchmarks + curve.
  4.  TICKER FILTER PREFIX: "KL" lists KLBN4 AND KLBN11 while typing;
      a 2-char filter no longer 400s (the old exact-match rule nuked
      the whole view mid-keystroke).
  5.  CORP TX SELF-DESCRIPTION: corporate actions store quantity 0 /
      price 0 / fees 0; a corp tx WITHOUT the event selected gets the
      PT-BR field error.
  6.  PROVENTOS SECOND SOURCE: the DDM agenda merges in — DDM-only
      rows appear, B3 rows win collisions (same type + near ex-date +
      close rate ⇒ NO duplicate).
  7.  BOOT META BACKFILL: tickers stored with empty name/sector spawn
      ONE staggered re-fetch pass; complete metadata never does.
  8.  HEADER FALLBACK: build_company_header survives a total DB miss
      (all fields empty, no exception — the carteira meta degrades to
      the cotahist seed instead of crashing the first transaction).

Run:  python -m pytest tests/webui/test_portfolio_v1224.py -v
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.portfolio as pfmod                # noqa: E402
from webui.services.portfolio import PortfolioService    # noqa: E402


# ── fixtures (the v1223 recipe) ──────────────────────────────────────────────

def _fake_quotes_factory(quotes: dict[str, float], refdates: dict[str, str]):
    def _fake(tickers):
        return {
            "status": "ok",
            "session_date": max(refdates.values()) if refdates else "",
            "symbols": [{"ticker": t, "close": quotes[t],
                         "refdate": refdates.get(t, "2026-11-21")}
                        for t in tickers if t in quotes],
        }
    return _fake


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    quotes: dict[str, float] = {}
    refdates: dict[str, str] = {}
    monkeypatch.setattr(pfmod, "_quotes_for",
                        _fake_quotes_factory(quotes, refdates))
    monkeypatch.setattr(pfmod.PortfolioService,
                        "_maybe_backfill_meta", lambda self: None)
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    s._test_quotes = quotes
    s._test_refdates = refdates
    return s


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    monkeypatch.setattr(pfmod, "_quotes_for",
                        _fake_quotes_factory({}, {}))
    monkeypatch.setattr(pfmod.PortfolioService,
                        "_maybe_backfill_meta", lambda self: None)
    from webui.routes import portfolio as _pfroute
    monkeypatch.setattr(_pfroute._svc, "_spawn_meta_refresh",
                        lambda ticker: None)
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def _seed(svc, user="Ana", account="Principal"):
    u = svc.create_user({"name": user})
    assert u["ok"], u
    a = svc.create_account({"user_id": u["user"]["id"], "name": account})
    assert a["ok"], a
    return u["user"]["id"], a["account"]["id"]


def _tx(svc, aid, **kw):
    body = {"account_id": aid, "ticker": "PETR4", "type": "buy",
            "quantity": 100, "price": 10.0, "fees": 0.0,
            "date": "2026-01-05"}
    body.update(kw)
    return svc.create_tx(body)


def _fake_prices(monkeypatch, series):
    import webui.services.portfolio_perf as pp

    def _pm(ticker, date_from, date_to):
        rows = [(d, c) for d, c in series.get(ticker, [])
                if date_from <= d <= date_to]
        return ([d for d, _ in rows], [c for _, c in rows])

    monkeypatch.setattr(pp, "_price_map", _pm)


# ══════════════════════════════════════════════════════════════════════════
# 1. EVOLUÇÃO 500 — the complex-power TWR (the reported bug)
# ══════════════════════════════════════════════════════════════════════════

def test_annualize_refuses_negative_base():
    from webui.services.portfolio_perf import _annualize
    assert _annualize(None, 100) is None
    assert _annualize(-2.0, 100) is None          # 1+total < 0 → complex
    assert _annualize(-1.0, 100) is None          # base exactly 0
    assert _annualize(0.0, 365) == pytest.approx(0.0)
    assert _annualize(0.10, 365) == pytest.approx(0.10)
    assert _annualize(0.21, 730) == pytest.approx(0.10, abs=1e-9)


def test_twr_sign_flip_is_json_not_500(svc, monkeypatch):
    """The reproduction: buy 1000 @ 1,00 on a day that CLOSED at 0,50.

    V(d_i) = 550 < CF = 1000 with V(d_{i-1}) = 100 → the sub-period
    ratio (550−1000)/100 = −4,5 is NEGATIVE → the chain went below
    zero. v1.22.3 annualized (−4,5)**(365/dias) → complex →
    TypeError in json.dumps → plain-text 500 → "Erro: Unexpected
    token 'I'…". v1.22.4: TWR None + the honest note + JSON serializes.
    """
    _, aid = _seed(svc)
    today = date.today()
    d1 = (today - timedelta(days=120)).isoformat()
    d2 = (today - timedelta(days=60)).isoformat()
    _tx(svc, aid, quantity=100, price=1.0, date=d1)
    _tx(svc, aid, quantity=1000, price=1.0, date=d2)   # buy @ 1,00
    _fake_prices(monkeypatch, {"PETR4": [
        (d1, 1.0), (d2, 0.50), (today.isoformat(), 0.50)]})  # closed 0,50
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    assert rep["twr_total"] is None          # undefined, not a number
    assert rep["twr_annual"] is None
    assert any("trocou de sinal" in n for n in rep["notes"])
    json.dumps(rep)                          # THE regression: no TypeError


def test_twr_normal_case_unchanged(svc, monkeypatch):
    # The verified v1.22.3 case must keep its number: +20% market move.
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _fake_prices(monkeypatch, {"PETR4": [
        ("2026-01-05", 10.0), ("2026-06-30", 11.0), ("2026-11-01", 12.0)]})
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    assert rep["twr_total"] == pytest.approx(0.20, abs=1e-6)
    assert rep["twr_annual"] is not None


def test_report_endpoints_answer_json_even_when_broken(client, monkeypatch):
    """[v1.22.4] the never-plain-text rule: a raising report builder
    answers {"ok": false, "_error": …} — the client can always render
    a PT-BR error instead of dying on r.json()."""
    import webui.services.portfolio_perf as pp

    def _boom(scope):
        raise RuntimeError("data-shaped bug")

    monkeypatch.setattr(pp, "performance_report", _boom)
    r = client.get("/api/webui/portfolio/performance?scope=all")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["ok"] is False
    assert "Falha ao calcular" in body["_error"]
    assert "RuntimeError" in body["_error"]


# ══════════════════════════════════════════════════════════════════════════
# 2. IVVB11 — the S&P 500 (BRL) benchmark
# ══════════════════════════════════════════════════════════════════════════

def test_ivvb11_proxy_and_curve(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _fake_prices(monkeypatch, {
        "PETR4": [("2026-01-05", 10.0), ("2026-11-01", 10.0)],
        "IVVB11": [("2026-01-05", 400.0), ("2026-11-01", 440.0)],
    })
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    assert rep["ivvb_total"] == pytest.approx(0.10, abs=1e-6)
    assert rep["curve"]["ivvb"][0] == rep["curve"]["patrimonio"][0]
    labels = [k["label"] for k in rep["kpis"]]
    assert any("IVVB11" in lab for lab in labels)


# ══════════════════════════════════════════════════════════════════════════
# 3. TICKER FILTER — prefix match while typing
# ══════════════════════════════════════════════════════════════════════════

def test_txs_ticker_filter_is_prefix(client):
    r = client.post("/api/webui/portfolio/users", json={"name": "Ana"})
    uid = r.json()["user"]["id"]
    r = client.post("/api/webui/portfolio/accounts",
                    json={"user_id": uid, "name": "X"})
    aid = r.json()["account"]["id"]
    for tk in ("KLBN4", "KLBN11", "PETR4"):
        assert client.post("/api/webui/portfolio/txs", json={
            "account_id": aid, "ticker": tk, "type": "buy",
            "quantity": 10, "price": 10.0, "fees": 0.0,
            "date": "2026-02-02"}).json()["ok"]

    # the reported bug: "KL" mid-typing 400'd and wiped the view
    r = client.get("/api/webui/portfolio/txs?ticker=KL")
    assert r.status_code == 200
    j = r.json()
    assert j["total"] == 2
    assert {row["ticker"] for row in j["rows"]} == {"KLBN4", "KLBN11"}

    # one letter still works (prefix), full ticker narrows to one
    assert client.get("/api/webui/portfolio/txs?ticker=K").json()["total"] == 2
    assert client.get(
        "/api/webui/portfolio/txs?ticker=KLBN4").json()["total"] == 1
    assert client.get(
        "/api/webui/portfolio/txs?ticker=KLBN11").json()["total"] == 1

    # garbage is still refused — but as JSON
    r = client.get("/api/webui/portfolio/txs?ticker=K%21")
    assert r.status_code == 400
    assert r.json()["_error"] == "Ticker inválido."


def test_txs_ticker_filter_prefix_service_side(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="KLBN4", date="2026-01-10")
    _tx(svc, aid, ticker="KLBN11", date="2026-01-11")
    _tx(svc, aid, ticker="VALE3", date="2026-01-12")
    page = svc.txs_page("all", 1, 50, ticker="kl")
    assert page["total"] == 2               # case-insensitive prefix
    page = svc.txs_page("all", 1, 50, ticker="KLBN4")
    assert page["total"] == 1


# ══════════════════════════════════════════════════════════════════════════
# 4. CORP TX — self-describing zeros + the required event
# ══════════════════════════════════════════════════════════════════════════

def test_corp_tx_stores_zero_qty_price_fees(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0)
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4",
                       "type": "corp", "action": "split", "factor": 2.0,
                       "date": "2026-02-01"})
    assert r["ok"], r
    corp = next(t for t in svc._snapshot()["txs"] if t["type"] == "corp")
    assert corp["quantity"] == 0.0
    assert corp["price"] == 0.0
    assert corp["fees"] == 0.0
    assert corp["action"] == "split" and corp["factor"] == 2.0


def test_corp_tx_requires_the_event(svc):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4",
                       "type": "corp", "factor": 2.0,
                       "date": "2026-02-01"})
    assert not r["ok"]
    assert "Selecione o tipo de evento" in r["errors"]["action"]


def test_reconcile_backfills_corp_zeros():
    # A pre-v1.22.4 corp row (no quantity/price keys) reconciles to 0s.
    t = {"type": "corp", "action": "bonus", "factor": 1.1}
    pfmod._reconcile_tx(t)
    assert t["quantity"] == 0.0 and t["price"] == 0.0 and t["fees"] == 0.0


# ══════════════════════════════════════════════════════════════════════════
# 5. PROVENTOS — the DDM agenda merge (second source, no duplicates)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def fake_ddm(tmp_path, monkeypatch):
    """A tiny ddm dividends.db + the catalog connect pointed at it."""
    p = tmp_path / "ddm-dividends.db"
    conn = sqlite3.connect(p)
    conn.execute("""CREATE TABLE dividends (
        ticker TEXT NOT NULL, tipo TEXT, value REAL,
        record_date TEXT, ex_date TEXT, payment_date TEXT,
        synced_at TEXT,
        PRIMARY KEY (ticker, record_date, tipo))""")
    rows = [
        # DDM-only event the B3 provents API missed
        ("PETR4", "Dividendo", 0.90, "2026-09-01", "2026-09-02",
         "2026-09-20"),
        # duplicate of the B3 row below (±1 day, same rate) → dropped
        ("PETR4", "JCP", 0.30, "2026-06-04", "2026-06-05",
         "2026-06-30"),
        # different type on the same date as the B3 JCP → kept
        ("PETR4", "Dividendo", 0.55, "2026-06-04", "2026-06-05",
         "2026-06-30"),
    ]
    conn.executemany(
        "INSERT INTO dividends VALUES (?,?,?,?,?,?,?)",
        [(*r, "2026-11-01") for r in rows])
    conn.commit()
    conn.close()

    import data_sources.ddm.dividends.catalog as catalog

    def _connect(read_only=True):
        c = sqlite3.connect(p)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(catalog, "connect", _connect)
    return p


def _seed_b3_events(tmp_path, monkeypatch, rows):
    """A tiny b3 dividends.db with cash_dividends rows for PETR4."""
    p = tmp_path / "b3-dividends.db"
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE cash_dividends (
        ticker TEXT, label TEXT, isin_code TEXT, approved_on TEXT,
        last_date_prior TEXT, rate REAL, related_to TEXT,
        payment_date TEXT, remarks TEXT)""")
    conn.executemany("INSERT INTO cash_dividends VALUES (?,?,?,?,?,?,?,?)"
                     if False else
                     "INSERT INTO cash_dividends "
                     "(ticker,label,isin_code,approved_on,last_date_prior,"
                     "rate,related_to,payment_date,remarks) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    import data_sources.b3.dividends.catalog as b3cat

    def _connect(read_only=True):
        c = sqlite3.connect(p)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(b3cat, "connect", _connect)
    return p


def test_ddm_merge_adds_and_dedupes(tmp_path, monkeypatch, fake_ddm):
    _seed_b3_events(tmp_path, monkeypatch, [
        ("PETR4", "JRS CAP PROPRIO", "BRPETRACNPR6", "2026-05-10",
         "2026-06-04", 0.30, "", "2026-06-30", "AGO 2026"),
        ("PETR4", "DIVIDENDO", "BRPETRACNPR6", "2026-04-10",
         "2026-05-02", 1.10, "", "2026-05-30", ""),
    ])
    from webui.services.proventos import ProventosService
    events = ProventosService()._fetch_events("PETR4")
    kinds = [(e["type"], e["ex_date"], round(e["rate"], 4), e["source"])
             for e in events]
    # B3 rows kept verbatim (2), DDM-only Dividendo added (1), the
    # DDM JCP duplicate dropped (same type, 1 day apart, same rate).
    assert ("JCP", "2026-06-04", 0.30, "b3") in kinds
    assert ("Dividendo", "2026-05-02", 1.10, "b3") in kinds
    assert ("Dividendo", "2026-09-02", 0.90, "ddm") in kinds
    assert ("Dividendo", "2026-06-05", 0.55, "ddm") in kinds
    assert len([k for k in kinds if k[0] == "JCP"]) == 1   # no dup
    assert len(events) == 4


def test_ddm_only_when_b3_missing(tmp_path, monkeypatch, fake_ddm):
    # No B3 dividends.db at all → the DDM events still surface.
    import data_sources.b3.dividends.catalog as b3cat

    def _missing(read_only=True):
        raise FileNotFoundError("no b3 dividends.db")

    monkeypatch.setattr(b3cat, "connect", _missing)
    from webui.services.proventos import ProventosService
    events = ProventosService()._fetch_events("PETR4")
    assert {e["source"] for e in events} == {"ddm"}
    assert len(events) == 3


# ══════════════════════════════════════════════════════════════════════════
# 6. BOOT META BACKFILL — one staggered pass for incomplete metadata
# ══════════════════════════════════════════════════════════════════════════

def test_backfill_targets_incomplete_meta(tmp_path, monkeypatch):
    import time as _time
    from core.config import cfg
    cfg.memory_root = str(tmp_path)
    monkeypatch.setattr(pfmod, "_quotes_for", _fake_quotes_factory({}, {}))
    svc = PortfolioService()
    # Two incomplete tickers + one complete — record the spawn calls.
    calls: list[str] = []
    monkeypatch.setattr(svc, "_spawn_meta_refresh", calls.append)
    svc._store["tickers"] = {
        "KLBN4": {"name": "Klabin", "sector": "", "updated_at": ""},
        "MBRF3": {"name": "", "sector": "", "updated_at": ""},
        "PETR4": {"name": "Petro", "sector": "Petróleo", "updated_at": ""},
    }
    svc._save()                     # persist — a missing file wipes to empty
    svc._meta_backfill_done = False
    svc._snapshot()
    # The sequencer staggers its spawns (0,35s apart) — poll for both
    # instead of racing the daemon thread.
    deadline = _time.monotonic() + 5.0
    while _time.monotonic() < deadline:
        if len(calls) >= 2:
            break
        _time.sleep(0.05)
    assert sorted(calls) == ["KLBN4", "MBRF3"]   # complete one skipped
    svc._snapshot()                               # once per process
    assert len(calls) == 2


# ══════════════════════════════════════════════════════════════════════════
# 7. HEADER FALLBACK — a total DB miss degrades, never raises
# ══════════════════════════════════════════════════════════════════════════

def test_header_survives_total_db_miss(monkeypatch):
    monkeypatch.setattr("data_sources.cvm._db.fca_db_path",
                        lambda: Path("/nonexistent/fca.db"))
    monkeypatch.setattr("data_sources.cvm._db.cad_db_path",
                        lambda: Path("/nonexistent/cad.db"))
    monkeypatch.setattr("data_sources.cvm._db.bridge_db_path",
                        lambda: Path("/nonexistent/bridge.db"))
    from skills.cvm._shared_report.company_header import build_company_header
    h = build_company_header("ZZZZ4")
    assert isinstance(h, dict)
    assert h.get("sector", "") == ""          # empty, not a crash
