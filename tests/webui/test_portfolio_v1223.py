"""tests/webui/test_portfolio_v1223.py — the v1.22.3 money-roadmap suite.

One test per shipped capability, HAND-COMPUTED values (the v1.22.1
discipline — a refactor that changes any number here fails before the
user's portfolio does):

  1.  CORPORATE ACTIONS (roadmap 5): split/bonus/group re-base qty×f,
      PM÷f with the custo total invariant; corp sorts FIRST within its
      date; corp on a flat position is a ledger-only no-op; validation
      (split ≤ 1, group ≥ 1, factor 1, bad action); the IR walk
      re-bases the same way (the two walks never disagree); the ladder
      final state == _positions_raw (the no-forked-numerics pin).
  2.  REPLAY MEMOIZATION (roadmap 8): same rev = same answer; a
      mutation bumps the rev and the next read sees the new book.
  3.  STORE RECONCILIATION (roadmap 8): 1e999 (→ inf) quantity and a
      bad factor quarantine the file — never a partial load; string
      numbers normalize.
  4.  LEDGER (roadmap 7): GET /txs pages newest-last (page 1 = the
      newest N), beyond-last is empty, filters (ticker/type/window/q)
      narrow before paging; positions() ships page-1 + tx_total.
  5.  UNDO (roadmap 7): create/update/delete each return a token;
      undo restores (same id/seq on delete-undo); one-shot 404.
  6.  EXPORT/RESTORE (roadmap 7): round-trip counts; garbage refused
      with the store untouched.
  7.  ALERTS (roadmap 6): CRUD, one-per-(ticker, op) replacement,
      live trigger evaluation, 404 on missing.
  8.  PROVENTOS (roadmap 2): entitlement at the DATA COM (buys that
      day receive, sells that day don't), the short-pays bucket, the
      YOC math, per-account ladders feeding the join.
  9.  PERFORMANCE (roadmap 4): TWR of a held book = the market move
      (the sell-at-a-price alpha case), XIRR on hand-computed flows,
      CDI daily compounding, the curve grid.
  10. ALLOCATION (roadmap 6): weights over LONG values, HHI (2/3 +
      1/3 → 5.556), the short exposure line.
  11. WHAT-IF (roadmap 6): a feeless sell realizes against the live
      PM; the after-value uses the simulated price; nothing written.
  12. POSITIONS PAYLOAD (roadmap 7): gross long/short totals, the
      exposure cards only when a short exists, the stale-quote date
      flag.

Run:  python -m pytest tests/webui/test_portfolio_v1223.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.portfolio as pfmod                # noqa: E402
from webui.services.portfolio import PortfolioService    # noqa: E402


# ── fixtures (the engine-suite recipe) ───────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════
# 1. CORPORATE ACTIONS (roadmap 5)
# ══════════════════════════════════════════════════════════════════════════

def test_split_rebases_qty_and_pm_cost_invariant(svc):
    _, aid = _seed(svc)
    assert _tx(svc, aid, quantity=100, price=10.0)["ok"]
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                       "action": "split", "factor": 2.0,
                       "date": "2026-02-01"})
    assert r["ok"], r
    raw = svc._replay_for(aid, [t for t in svc._snapshot()["txs"]
                                if t["account_id"] == aid])[0]["PETR4"]
    assert raw["qty"] == pytest.approx(200.0)
    assert raw["pm"] == pytest.approx(5.0)
    assert raw["qty"] * raw["pm"] == pytest.approx(1000.0)   # custo invariant


def test_bonus_and_group(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0)                     # PM 10
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "bonus", "factor": 1.1, "date": "2026-02-01"})
    raw = svc._replay_for(aid, [t for t in svc._snapshot()["txs"]
                                if t["account_id"] == aid])[0]["PETR4"]
    # bonificação 10%: 110 shares, PM 10/1.1 — same cost 1000
    assert raw["qty"] == pytest.approx(110.0)
    assert raw["pm"] == pytest.approx(10.0 / 1.1)
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "group", "factor": 0.1, "date": "2026-03-01"})
    raw = svc._replay_for(aid, [t for t in svc._snapshot()["txs"]
                                if t["account_id"] == aid])[0]["PETR4"]
    # grupamento 10:1: 11 shares, PM ×10 — same cost
    assert raw["qty"] == pytest.approx(11.0)
    assert raw["pm"] == pytest.approx(10.0 / 1.1 / 0.1)
    assert raw["qty"] * raw["pm"] == pytest.approx(1000.0)


def test_corp_rebases_short_side(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, type="sell", quantity=100, price=20.0)        # short 100@20
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-02-01"})
    raw = svc._replay_for(aid, [t for t in svc._snapshot()["txs"]
                                if t["account_id"] == aid])[0]["PETR4"]
    assert raw["qty"] == pytest.approx(-200.0)
    assert raw["pm"] == pytest.approx(10.0)      # short entry 20 / 2


def test_corp_sorts_first_within_its_date(svc):
    # A split effective on D and a BUY on D: the buy already trades in
    # post-action quantities — the corp must re-base BEFORE the buy.
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")   # 100 @ 10
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-02-01"})
    # buy 200 on the split date at the post-split price 5.50
    _tx(svc, aid, quantity=200, price=5.5, date="2026-02-01")
    raw = svc._replay_for(aid, [t for t in svc._snapshot()["txs"]
                                if t["account_id"] == aid])[0]["PETR4"]
    # corp-first: 100→200 @5.00, then +200@5.50 → 400 @ 5.25
    assert raw["qty"] == pytest.approx(400.0)
    assert raw["pm"] == pytest.approx(5.25)


def test_corp_on_flat_position_is_noop(svc):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                       "action": "split", "factor": 2.0,
                       "date": "2026-01-01"})
    assert r["ok"], r                       # the ledger keeps the row…
    snap = svc._snapshot()
    raw = svc._replay_for(aid, [t for t in snap["txs"]
                                if t["account_id"] == aid])[0]
    assert raw["PETR4"]["qty"] == 0.0       # …but nothing to re-base


@pytest.mark.parametrize("action,factor", [
    ("split", 0.5), ("split", 1.0), ("group", 2.0), ("group", 1.0),
    ("bonus", 0.9), ("bonus", 1.0),
])
def test_corp_validation(svc, action, factor):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                       "action": action, "factor": factor,
                       "date": "2026-01-05"})
    assert not r["ok"] and "factor" in r["errors"], (action, factor, r)


def test_corp_bad_action_rejected(svc):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                       "action": "spin", "factor": 2.0,
                       "date": "2026-01-05"})
    assert not r["ok"] and "action" in r["errors"]


def test_ir_walk_rebases_corp_same_as_engine(svc):
    # The two walks must NEVER disagree (INSTRUCTIONS rule): a sell
    # after a split realizes against the POST-split PM.
    from webui.services.ir_helper import _walk_account
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-02-01"})
    _tx(svc, aid, type="sell", quantity=200, price=6.0,
        date="2026-03-01")      # closes the 200-share book at 6 vs PM 5
    snap = svc._snapshot()
    txs = [t for t in snap["txs"] if t["account_id"] == aid]
    buckets = _walk_account(txs)
    # swing result = 200 × (6 − 5) = +200 (the split's PM re-base:
    # without it the sell would realize against PM 10 → a phantom −800)
    assert buckets["2026-03"]["swing_res"] == pytest.approx(200.0)
    assert buckets["2026-03"]["swing_vol"] == pytest.approx(1200.0)


def test_ladder_final_equals_engine(svc):
    # The no-forked-numerics pin: the drawer's walk ends exactly where
    # the engine's walk ends (qty, pm, realized).
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, fees=1.0)
    _tx(svc, aid, type="sell", quantity=50, price=12.0, fees=1.0)
    _tx(svc, aid, type="sell", quantity=80, price=11.0)      # → short
    _tx(svc, aid, quantity=100, price=9.0, fees=2.0)         # cover + flip
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-02-15"})
    snap = svc._snapshot()
    txs = [t for t in snap["txs"] if t["account_id"] == aid]
    engine = svc._positions_raw(txs)["PETR4"]
    ladder = svc._ticker_ladder(txs, "PETR4")
    last = ladder[-1]
    assert last["run_qty"] == pytest.approx(engine["qty"])
    assert last["run_pm"] == pytest.approx(engine["pm"])
    assert sum(r["delta_realized"] for r in ladder) == pytest.approx(
        engine["realized"], abs=0.02)


# ══════════════════════════════════════════════════════════════════════════
# 2. REPLAY MEMOIZATION (roadmap 8)
# ══════════════════════════════════════════════════════════════════════════

def test_memo_invalidates_on_mutation(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0)
    snap = svc._snapshot()
    txs = [t for t in snap["txs"] if t["account_id"] == aid]
    first = svc._replay_for(aid, txs)[0]["PETR4"]
    rev_before = svc._rev
    # second read: memo hit, same numbers, rev unchanged
    again = svc._replay_for(aid, txs)[0]["PETR4"]
    assert again["qty"] == first["qty"]
    assert svc._rev == rev_before
    # mutation → new rev → new answer
    _tx(svc, aid, quantity=50, price=12.0, date="2026-03-01")
    assert svc._rev == rev_before + 1
    snap = svc._snapshot()
    txs = [t for t in snap["txs"] if t["account_id"] == aid]
    after = svc._replay_for(aid, txs)[0]["PETR4"]
    assert after["qty"] == pytest.approx(150.0)


def test_quoteset_is_immutable(svc):
    svc._refresh_quotes({"PETR4"})
    published = svc._quotes
    assert published is not None
    with pytest.raises(TypeError):
        published["HACK"] = {"close": 1.0}      # MappingProxyType: no write


# ══════════════════════════════════════════════════════════════════════════
# 3. STORE RECONCILIATION (roadmap 8)
# ══════════════════════════════════════════════════════════════════════════

def test_store_with_inf_quantity_quarantines(svc, tmp_path):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=10, price=2.0)
    path = pfmod._portfolio_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["txs"][0]["quantity"] = 1e999            # json → inf
    path.write_text(json.dumps(data), encoding="utf-8")
    svc._loaded_mtime = None                      # force the reload
    res = svc.positions("all")
    # degraded: reads serve the last good store, writes refused
    assert svc._load_error is not None
    assert res["status"] == "ok"                  # last-good reads live on
    r = _tx(svc, aid, quantity=1, price=1.0)
    assert not r["ok"] and r.get("status") == 503


def test_store_string_numbers_normalize(svc, tmp_path):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=10, price=2.0)
    path = pfmod._portfolio_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["txs"][0]["quantity"] = "77.5"           # a hand edit left a string
    path.write_text(json.dumps(data), encoding="utf-8")
    svc._loaded_mtime = None
    snap = svc._snapshot()                          # triggers the reload
    assert snap["txs"][0]["quantity"] == 77.5     # canonical float now


def test_store_bad_factor_is_corruption(svc, tmp_path):
    _, aid = _seed(svc)
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-01-05"})
    path = pfmod._portfolio_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    corp = next(t for t in data["txs"] if t["type"] == "corp")
    corp["factor"] = 1.0                          # a no-op factor hand-planted
    path.write_text(json.dumps(data), encoding="utf-8")
    svc._loaded_mtime = None
    svc._snapshot()                                # triggers the reload
    assert svc._load_error is not None            # quarantined, not loaded


# ══════════════════════════════════════════════════════════════════════════
# 4. LEDGER — pagination + filters (roadmap 7)
# ══════════════════════════════════════════════════════════════════════════

def test_txs_pagination(svc):
    _, aid = _seed(svc)
    for i in range(7):
        _tx(svc, aid, quantity=i + 1, price=10.0,
            date=f"2026-01-{i + 1:02d}")
    p1 = svc.txs_page("all", page=1, per_page=3)
    assert p1["total"] == 7 and p1["pages"] == 3
    assert [r["quantity"] for r in p1["rows"]] == [5.0, 6.0, 7.0]   # newest
    p2 = svc.txs_page("all", page=2, per_page=3)
    assert [r["quantity"] for r in p2["rows"]] == [2.0, 3.0, 4.0]
    p3 = svc.txs_page("all", page=3, per_page=3)
    assert [r["quantity"] for r in p3["rows"]] == [1.0]
    p9 = svc.txs_page("all", page=9, per_page=3)
    assert p9["rows"] == []                        # beyond the last page


def test_txs_filters(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="PETR4", quantity=1, price=10.0,
        date="2026-01-05", note="NC 1 · XP")
    _tx(svc, aid, ticker="VALE3", type="sell", quantity=2, price=60.0,
        date="2026-02-10")
    svc.create_tx({"account_id": aid, "ticker": "VALE3", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-03-01"})
    assert svc.txs_page("all", 1, 50, ticker="VALE3")["total"] == 2
    assert svc.txs_page("all", 1, 50, ttype="corp")["total"] == 1
    assert svc.txs_page("all", 1, 50, ttype="sell")["total"] == 1
    assert svc.txs_page("all", 1, 50,
                        date_from="2026-01-10")["total"] == 2
    assert svc.txs_page("all", 1, 50, date_from="2026-01-10",
                        date_to="2026-02-15")["total"] == 1
    assert svc.txs_page("all", 1, 50, query="nc 1")["total"] == 1


def test_positions_ships_page1_and_total(svc):
    _, aid = _seed(svc)
    for i in range(60):
        _tx(svc, aid, quantity=i + 1, price=10.0,
            date=f"2026-01-{(i % 27) + 1:02d}")
    svc._test_quotes["PETR4"] = 10.0
    svc._test_refdates["PETR4"] = "2026-11-21"
    p = svc.positions("all")
    assert p["tx_total"] == 60
    assert len(p["txs"]) == 50                    # page-1 seed


# ══════════════════════════════════════════════════════════════════════════
# 5. UNDO (roadmap 7)
# ══════════════════════════════════════════════════════════════════════════

def test_undo_create_update_delete(svc):
    _, aid = _seed(svc)
    # create → undo removes
    r = _tx(svc, aid, quantity=100, price=10.0)
    token = r["undo_token"]
    assert r["undo_label"]
    assert svc.undo_mutation(token)["ok"]
    assert svc._snapshot()["txs"] == []
    # update → undo restores the previous fields
    r = _tx(svc, aid, quantity=100, price=10.0)
    r2 = svc.update_tx(r["tx"]["id"], {"price": 99.0})
    assert r2["ok"], r2
    assert svc.undo_mutation(r2["undo_token"])["ok"]
    snap = svc._snapshot()
    assert snap["txs"][0]["price"] == 10.0
    # delete → undo re-inserts with the SAME id
    tx_id = snap["txs"][0]["id"]
    seq = snap["txs"][0]["seq"]
    r3 = svc.delete_tx(tx_id)
    assert svc.undo_mutation(r3["undo_token"])["ok"]
    snap = svc._snapshot()
    assert snap["txs"][0]["id"] == tx_id
    assert snap["txs"][0]["seq"] == seq
    # one-shot
    assert svc.undo_mutation(r3["undo_token"])["ok"] is False


# ══════════════════════════════════════════════════════════════════════════
# 6. EXPORT / RESTORE (roadmap 7)
# ══════════════════════════════════════════════════════════════════════════

def test_export_restore_roundtrip(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0)
    svc.add_alert({"ticker": "PETR4", "op": "above", "price": 12.0})
    exported = svc.export_store()
    assert exported["users"] and exported["txs"] and exported["alerts"]
    # wipe by hand (simulate a disaster) and restore
    svc._store = pfmod._empty_store()
    svc._save()
    assert svc._snapshot()["txs"] == []
    res = svc.restore_store(exported)
    assert res["ok"], res
    assert res["counts"]["txs"] == 1
    snap = svc._snapshot()
    assert snap["alerts"][0]["ticker"] == "PETR4"


def test_restore_garbage_refused(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=5, price=5.0)
    res = svc.restore_store({"users": "garbage", "txs": []})
    assert not res["ok"]
    assert len(svc._snapshot()["txs"]) == 1       # nothing changed


# ══════════════════════════════════════════════════════════════════════════
# 7. ALERTS (roadmap 6)
# ══════════════════════════════════════════════════════════════════════════

def test_alerts_crud_and_trigger(svc):
    _, aid = _seed(svc)
    r = svc.add_alert({"ticker": "PETR4", "op": "above", "price": 9.0})
    assert r["ok"], r
    # one alert per (ticker, op) — the second replaces the first
    r2 = svc.add_alert({"ticker": "PETR4", "op": "above", "price": 15.0})
    assert r2["ok"]
    svc._test_quotes["PETR4"] = 10.0
    svc._test_refdates["PETR4"] = "2026-11-21"
    svc._quotes = None                 # drop the memo so the fake reloads
    svc._quotes_seen = set()
    st = svc.alerts_status()
    alerts = [a for a in st["alerts"] if a["ticker"] == "PETR4"]
    assert len(alerts) == 1
    assert alerts[0]["price"] == 15.0
    assert alerts[0]["triggered"] is False          # 10 < 15
    # a below alert triggers at 10
    svc.add_alert({"ticker": "PETR4", "op": "below", "price": 11.0})
    st = svc.alerts_status()
    below = [a for a in st["alerts"] if a["op"] == "below"]
    assert below[0]["triggered"] is True
    # delete + 404
    assert svc.delete_alert(below[0]["id"])["ok"]
    assert svc.delete_alert(below[0]["id"])["ok"] is False


# ══════════════════════════════════════════════════════════════════════════
# 8. PROVENTOS (roadmap 2)
# ══════════════════════════════════════════════════════════════════════════

def _fake_events(monkeypatch, events):
    import webui.services.portfolio_provents as pp
    monkeypatch.setattr(pp, "_events", lambda tk: events.get(tk, []))


def test_proventos_entitlement_at_data_com(svc, monkeypatch):
    _, aid = _seed(svc)
    # 100 shares before the cum-date; 50 bought ON it (receive); 30
    # sold on the SECOND cum-date (don't receive).
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _tx(svc, aid, quantity=50, price=11.0, date="2026-02-10")
    _tx(svc, aid, type="sell", quantity=30, price=11.0, date="2026-05-10")
    _fake_events(monkeypatch, {"PETR4": [
        {"ex_date": "2026-02-10", "pay_date": "2026-03-01", "rate": 1.0,
         "type": "JCP"},
        {"ex_date": "2026-05-10", "pay_date": "2026-06-01", "rate": 2.0,
         "type": "Dividendo"},
    ]})
    from webui.services.portfolio_provents import proventos_report
    rep = proventos_report("all")
    row = next(r for r in rep["by_ticker"] if r["ticker"] == "PETR4")
    # ex 2026-02-10: 100 (before) + 50 (bought that day) = 150 × 1.00
    # ex 2026-05-10: 150 − 30 (sold that day) = 120 × 2.00
    assert row["received"] == pytest.approx(150.0 + 240.0)
    events = {(e["ex_date"], e["qty"]) for e in rep["events"]}
    assert ("2026-02-10", 150.0) in events
    assert ("2026-05-10", 120.0) in events


def test_proventos_short_pays_and_yoc(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _tx(svc, aid, type="sell", quantity=200, price=10.0,
        date="2026-04-01")          # short 100 on the cum-date
    _fake_events(monkeypatch, {"PETR4": [
        {"ex_date": "2026-02-10", "pay_date": "2026-03-01", "rate": 1.0,
         "type": "Dividendo"},      # long 100 → +100
        {"ex_date": "2026-05-10", "pay_date": "2026-06-01", "rate": 0.5,
         "type": "JCP"},            # short 100 → debited 50
    ]})
    from webui.services.portfolio_provents import proventos_report
    rep = proventos_report("all")
    row = rep["by_ticker"][0]
    assert row["received"] == pytest.approx(100.0)   # the long receipt only
    debit_event = next(e for e in rep["events"]
                       if e["ex_date"] == "2026-05-10")
    assert debit_event["short_qty"] == pytest.approx(100.0)
    assert debit_event["debit_br"] is not None
    assert any("debitados" in n for n in rep["notes"])


def test_proventos_corp_action_feeds_entitlement(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                   "action": "split", "factor": 2.0, "date": "2026-03-01"})
    _fake_events(monkeypatch, {"PETR4": [
        {"ex_date": "2026-04-10", "pay_date": "2026-05-01", "rate": 1.0,
         "type": "Dividendo"},
    ]})
    from webui.services.portfolio_provents import proventos_report
    rep = proventos_report("all")
    assert rep["events"][0]["qty"] == pytest.approx(200.0)  # post-split


# ══════════════════════════════════════════════════════════════════════════
# 9. PERFORMANCE (roadmap 4)
# ══════════════════════════════════════════════════════════════════════════

def _fake_prices(monkeypatch, series):
    import webui.services.portfolio_perf as pp

    def _pm(ticker, date_from, date_to):
        rows = [(d, c) for d, c in series.get(ticker, [])
                if date_from <= d <= date_to]
        return ([d for d, _ in rows], [c for _, c in rows])

    monkeypatch.setattr(pp, "_price_map", _pm)


def test_twr_single_position_tracks_market(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _fake_prices(monkeypatch, {"PETR4": [
        ("2026-01-05", 10.0), ("2026-06-30", 11.0), ("2026-11-01", 12.0)]})
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    # V(01-05)=1000 → final V(today)=1200 (last close ≤ today): +20%
    assert rep["twr_total"] == pytest.approx(0.20, abs=1e-6)


def test_twr_sell_alpha_case(svc, monkeypatch):
    # The verified case: sell half the book ABOVE the market path —
    # TWR captures the sell-price alpha, timing-free.
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _tx(svc, aid, type="sell", quantity=50, price=12.0, date="2026-03-10")
    _fake_prices(monkeypatch, {"PETR4": [
        ("2026-01-05", 10.0), ("2026-03-10", 10.5), ("2026-12-30", 10.5)]})
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    # sub-period 1: V(03-10)=525, CF=−600 → (525+600)/1000 − 1 = +12.5%
    # final leg: V(today)=525 / 525 → 0. Total = +12.5%
    assert rep["twr_total"] == pytest.approx(0.125, abs=1e-6)


def test_xirr_hand_computed(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _fake_prices(monkeypatch, {"PETR4": [("2026-01-05", 10.0)]})
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    # flows: −1000 (2026-01-05), +1000 (today, flat book). The annual
    # XIRR of a flat round-trip over N days ≈ 0 — the book returned
    # exactly its deposits.
    assert rep["xirr"] == pytest.approx(0.0, abs=0.02)


def test_cdi_daily_compounds(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _fake_prices(monkeypatch, {"PETR4": [("2026-01-05", 10.0)]})
    import webui.services.portfolio_perf as pp
    # 2 days of 0.05% a.d. → 1.0005² − 1
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [
        ("2026-01-05", 1.0005), ("2026-01-06", 1.0005)])
    rep = pp.performance_report("all")
    assert rep["cdi_total"] == pytest.approx(1.0005 ** 2 - 1.0, abs=1e-12)


def test_ibov_bova11_proxy(svc, monkeypatch):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _fake_prices(monkeypatch, {
        "PETR4": [("2026-01-05", 10.0), ("2026-11-01", 10.0)],
        "BOVA11": [("2026-01-05", 100.0), ("2026-11-01", 110.0)],
    })
    import webui.services.portfolio_perf as pp
    monkeypatch.setattr(pp, "_cdi_daily", lambda f, t: [])
    rep = pp.performance_report("all")
    assert rep["ibov_total"] == pytest.approx(0.10, abs=1e-6)
    assert rep["curve"]["ibov"][0] == rep["curve"]["patrimonio"][0]


# ══════════════════════════════════════════════════════════════════════════
# 10. ALLOCATION (roadmap 6)
# ══════════════════════════════════════════════════════════════════════════

def test_allocation_weights_hhi_short_line(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="PETR4", quantity=100, price=10.0,
        date="2026-01-05")
    _tx(svc, aid, ticker="VALE3", quantity=50, price=60.0,
        date="2026-01-06")
    _tx(svc, aid, ticker="ITUB4", type="sell", quantity=200, price=30.0,
        date="2026-01-07")            # short 200 ITUB4
    svc._test_quotes.update({"PETR4": 10.0, "VALE3": 10.0, "ITUB4": 10.0})
    for tk in ("PETR4", "VALE3", "ITUB4"):
        svc._test_refdates[tk] = "2026-11-21"
    svc._quotes = None
    svc._quotes_seen = set()
    from webui.services.portfolio_views import allocation_report
    rep = allocation_report("all")
    # LONG values: PETR4 1000, VALE3 500 → weights 2/3 and 1/3
    petr = next(r for r in rep["by_ticker"] if r["ticker"] == "PETR4")
    vale = next(r for r in rep["by_ticker"] if r["ticker"] == "VALE3")
    assert petr["weight"] == pytest.approx(2 / 3)
    assert vale["weight"] == pytest.approx(1 / 3)
    hhi = next(k for k in rep["kpis"] if k["label"] == "HHI")
    assert float(hhi["value"].replace(".", "").replace(",", ".")) == \
        pytest.approx((4 / 9 + 1 / 9) * 10_000, abs=1.0)
    # the short book has its own exposure line (not in the weights)
    tickers = {r["ticker"] for r in rep["by_ticker"]}
    assert "ITUB4" not in tickers
    short_kpi = next(k for k in rep["kpis"] if k["label"] == "Exposição short")
    assert short_kpi["value"] == "R$ 2.000,00"


# ══════════════════════════════════════════════════════════════════════════
# 11. WHAT-IF (roadmap 6)
# ══════════════════════════════════════════════════════════════════════════

def test_simulate_sell_nothing_written(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    svc._test_quotes["PETR4"] = 10.0
    svc._test_refdates["PETR4"] = "2026-11-21"
    svc._quotes = None
    svc._quotes_seen = set()
    from webui.services.portfolio_views import simulate
    res = simulate("all", [{"ticker": "PETR4", "type": "sell",
                            "quantity": 50, "price": 12.0}])
    assert res["ok"], res
    pat = next(k for k in res["kpis"] if k["label"] == "Patrimônio")
    # before: 100×10 = 1000 · after: 50×12 (sim price) = 600
    assert pat["before"] == "R$ 1.000,00"
    assert pat["after"] == "R$ 600,00"
    real = next(k for k in res["kpis"] if k["label"] == "Lucro realizado")
    assert real["after"] == "R$ 100,00"          # 50 × (12 − 10), feeless
    # NOTHING written — the store still has one tx, position intact.
    snap = svc._snapshot()
    assert len(snap["txs"]) == 1
    raw = svc._replay_for(aid, [t for t in snap["txs"]
                                if t["account_id"] == aid])[0]["PETR4"]
    assert raw["qty"] == pytest.approx(100.0)


def test_simulate_invalid_trade_rejected(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=10, price=10.0)
    from webui.services.portfolio_views import simulate
    res = simulate("all", [{"ticker": "PETR4", "type": "sell",
                            "quantity": 0, "price": 5.0}])
    assert not res["ok"]


# ══════════════════════════════════════════════════════════════════════════
# 12. POSITIONS PAYLOAD (roadmap 7)
# ══════════════════════════════════════════════════════════════════════════

def test_gross_exposure_and_stale_quote_flag(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="PETR4", quantity=100, price=10.0,
        date="2026-01-05")
    _tx(svc, aid, ticker="VALE3", type="sell", quantity=50, price=60.0,
        date="2026-01-06")            # short VALE3
    svc._test_quotes.update({"PETR4": 10.0, "VALE3": 20.0})
    # VALE3's last session is OLDER than PETR4's → stale flag + own date
    svc._test_refdates.update({"PETR4": "2026-11-21",
                               "VALE3": "2026-11-14"})
    svc._quotes = None
    svc._quotes_seen = set()
    p = svc.positions("all")
    assert p["totals"]["gross_long"] == "R$ 1.000,00"
    assert p["totals"]["gross_short"] == "R$ 1.000,00"
    labels = {k["label"] for k in p["kpis"]}
    assert "Exposição long" in labels and "Exposição short" in labels
    vale = next(r for r in p["positions"] if r["ticker"] == "VALE3")
    assert vale["stale_quote"] is True
    assert vale["quote_date"] == "2026-11-14"
    petr = next(r for r in p["positions"] if r["ticker"] == "PETR4")
    assert petr["stale_quote"] is False


def test_exposure_cards_absent_when_long_only(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0)
    svc._test_quotes["PETR4"] = 10.0
    svc._test_refdates["PETR4"] = "2026-11-21"
    svc._quotes = None
    svc._quotes_seen = set()
    p = svc.positions("all")
    labels = {k["label"] for k in p["kpis"]}
    assert "Exposição long" not in labels


# ══════════════════════════════════════════════════════════════════════════
# HTTP surface — the new endpoints, the CSRF posture included
# ══════════════════════════════════════════════════════════════════════════

def test_http_new_endpoints(client):
    H = {"Content-Type": "application/json"}
    # seed via the API
    r = client.post("/api/webui/portfolio/users", headers=H,
                    json={"name": "Ana"})
    uid = r.json()["user"]["id"]
    r = client.post("/api/webui/portfolio/accounts", headers=H,
                    json={"user_id": uid, "name": "XP"})
    aid = r.json()["account"]["id"]
    r = client.post("/api/webui/portfolio/txs", headers=H, json={
        "account_id": aid, "ticker": "PETR4", "type": "buy",
        "quantity": 100, "price": 10.0, "date": "2026-01-05"})
    assert r.status_code == 200
    undo_tok = r.json()["undo_token"]

    # undo via HTTP
    r = client.post("/api/webui/portfolio/undo", headers=H,
                    json={"token": undo_tok})
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post("/api/webui/portfolio/undo", headers=H,
                    json={"token": undo_tok})
    assert r.status_code == 404
    # the undo removed the tx — bring the book back for the rest
    r = client.post("/api/webui/portfolio/txs", headers=H, json={
        "account_id": aid, "ticker": "PETR4", "type": "buy",
        "quantity": 100, "price": 10.0, "date": "2026-01-05"})
    assert r.status_code == 200

    # txs endpoint + filters via HTTP
    r = client.get("/api/webui/portfolio/txs?scope=all&ticker=VALE3")
    assert r.status_code == 200 and r.json()["total"] == 0
    r = client.get("/api/webui/portfolio/txs?scope=all&page=0&per_page=99999")
    assert r.status_code == 200                    # clamped, never a 500
    r = client.get("/api/webui/portfolio/txs?scope=bogus")
    assert r.status_code == 400
    r = client.get("/api/webui/portfolio/txs?scope=all&type=weird")
    assert r.status_code == 400

    # alerts via HTTP
    r = client.post("/api/webui/portfolio/alerts", headers=H,
                    json={"ticker": "PETR4", "op": "above", "price": 5.0})
    assert r.status_code == 200
    r = client.get("/api/webui/portfolio/alerts")
    assert r.json()["ok"] and len(r.json()["alerts"]) == 1

    # export/restore via HTTP
    r = client.get("/api/webui/portfolio/export")
    store = r.json()
    assert store["users"]
    r = client.post("/api/webui/portfolio/restore", headers=H, json=store)
    assert r.status_code == 200 and r.json()["ok"]

    # simulate via HTTP (nothing written)
    r = client.post("/api/webui/portfolio/simulate", headers=H, json={
        "scope": "all",
        "trades": [{"ticker": "PETR4", "type": "sell",
                    "quantity": 10, "price": 11.0}]})
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post("/api/webui/portfolio/simulate", headers=H,
                    json={"scope": "all", "trades": "nope"})
    assert r.status_code == 400

    # scope validation on every new GET
    for path in ("/proventos", "/performance", "/allocation",
                 "/position-detail"):
        r = client.get(f"/api/webui/portfolio{path}?scope=bad")
        assert r.status_code == 400, path


def test_http_csrf_still_guards_mutations(client):
    # cross-site POST (Sec-Fetch-Site: cross-site) → 403, the store
    # untouched (the v1.22 posture, re-verified for the NEW routes).
    r = client.post("/api/webui/portfolio/alerts",
                    headers={"Content-Type": "application/json",
                             "Sec-Fetch-Site": "cross-site"},
                    json={"ticker": "PETR4", "op": "above", "price": 1.0})
    assert r.status_code == 403
    r = client.post("/api/webui/portfolio/undo",
                    headers={"Content-Type": "application/json",
                             "Sec-Fetch-Site": "cross-site"},
                    json={"token": "abc123"})
    assert r.status_code == 403
