"""tests/webui/test_v128_5.py — the v1.28.5 suite (hand-computed values).

The two asks of this round, one test per capability:

  A. BACKTEST — the exit-rule UI lives in app.js (JS cannot be tested
     here), but the ENGINE guarantees the pairing it advertises: every
     entrada has its saída (a leftover position is force-closed at the
     last close, reason "fim do período") — pinned here so the Trade
     Log's audit line ("✔ Cada entrada tem sua saída") is never a lie.
     The exit_on_signal path with its thresholds is re-pinned too (the
     fields the fixed UI now toggles below the checkbox).

  B. CARTEIRA CORPORATE ACTIONS, the v1.28.5 family:
     1.  INPLIT — grupamento COM TROCA DE TICKER (the RAIZ4 → RAIZ55
         case): 1.000.000 RAIZ4 @ R$0,30 (custo R$300.000) + inplit
         0,01 → 10.000 RAIZ55 @ PM R$30,00, custo R$300.000 intact;
         factor 1 = pure rename; blend with a pre-existing target
         position; flat = ledger-only no-op; the REALIZED stays on the
         origin ticker; validation (same/invalid new ticker, factor
         bounds); edit sanitation (action switch drops stale keys);
         the store reconcile round-trip.
     2.  LADDER — the no-forked-numerics pin EXTENDED to the new
         actions: the origin's ladder ends flat, the target's ladder
         shows the arrival row and its final state == the engine's
         (the target-side arrival is replayed by the engine itself on
         the prefix — tested against a hand-computed blend).
     3.  RIGHTS — direitos de subscrição recebidos de graça: the qty
         lands at PM R$0,00 on the rights ticker; a market sell
         realizes 100%; the EXPIRY (venda a R$ 0,00) is legal on the
         zero-cost position (books exactly zero) and STILL refused on
         a costful position or beyond the qty (the v1.22 phantom-loss
         guard lives on); validation (qty > 0).
     4.  THE IR WALK — the two walks never disagree, now across
         tickers: a RAIZ55 sell after the inplit realizes against the
         migrated PM; rights sells are 100% swing profit.
     5.  LEDGER/UNDO/LABELS — the corp cells (rights shows the qty,
         inplit shows OLD → NEW ×f) and the undo label text.
     6.  PROVENTOS — the entitlement rides the ladder: an ex-date
         after the inplit sees the MIGRATED quantity on the new code.

Run:  python -m pytest tests/webui/test_v128_5.py -v
"""
from __future__ import annotations

import sys
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
    r = svc.create_tx(body)
    assert r["ok"], r
    return r["tx"]


def _raw(svc, aid):
    """The account's replay positions {ticker: {qty, pm, realized}}."""
    snap = svc._snapshot()
    acc_txs = [t for t in snap["txs"] if t["account_id"] == aid]
    return svc._replay_for(aid, acc_txs)[0]


def _ladder(svc, aid, ticker):
    snap = svc._snapshot()
    acc_txs = [t for t in snap["txs"] if t["account_id"] == aid]
    return svc._ticker_ladder(acc_txs, ticker)


# ════════════════════════════════════════════════════════════════════════════
# A. BACKTEST — the pairing the Trade Log audit line advertises
# ════════════════════════════════════════════════════════════════════════════

PRICES = [(f"2026-01-{d:02d}", 10.0) for d in range(1, 26)]
RANGE = ("2026-01-01", "2026-01-25")


def _bt(monkeypatch, prices, rng):
    from webui.services.backtest import BacktestService
    s = BacktestService()
    monkeypatch.setattr(s, "_clean_prices", lambda t, f, e: list(prices))
    monkeypatch.setattr(s, "_price_range", lambda t: rng)
    return s


def test_bt_meta_carries_exit_conditions():
    """The exit thresholds the fixed UI toggles below the checkbox are
    in the strategy catalog — labeled, bounded, defaulted (they were
    always in the payload; the form just drew them above the toggle).
    Asserted on STRATEGY_SPECS (the catalog meta() serves verbatim)
    so the test stays DB-free."""
    from webui.services.backtest import STRATEGY_SPECS
    assert STRATEGY_SPECS["value_pe"]["exit"][0]["key"] == "pe_exit"
    assert STRATEGY_SPECS["value_pe"]["exit"][0]["label"] == "Sair se P/L acima de"
    assert STRATEGY_SPECS["value_pe"]["exit"][0]["default"] == 10.0
    assert STRATEGY_SPECS["composite"]["exit"][0]["key"] == "pe_exit"
    assert len(STRATEGY_SPECS["composite"]["exit"]) == 2
    # technical/buy_hold carry no exit conditions — the toggle itself
    # hides for those kinds (the UI's hasExitConds gate).
    assert STRATEGY_SPECS["ma_cross"]["exit"] == []
    assert STRATEGY_SPECS["buy_hold"]["exit"] == []


def test_bt_every_entry_has_its_exit(monkeypatch):
    """[v1.28.5] The pairing audit: the trade log's entradas/saídas
    counts match BY CONSTRUCTION — a trade is only booked when a
    position CLOSES, and a position still open at the last bar is
    force-closed there (reason end_of_period). A buy at bar 0 with no
    exit rule and no max-holding must end as exactly one paired trade.
    """
    from skills.cvm.backtest import helpers
    s = _bt(monkeypatch, PRICES, RANGE)
    # hermetic signals: pe 4.0 every bar → the entry condition (pe < 5)
    # fires on bar 0 regardless of any DB state
    monkeypatch.setattr(helpers, "_precompute_signals",
                        lambda t, f, e, m: {"pe": {d: 4.0
                                                   for d, _ in PRICES}})
    r = s.run("PETR4", {
        "strategy": "value_pe", "start_date": "2026-01-01",
        "end_date": "2026-01-25", "initial_capital": 10000.0,
        "position_pct": 100.0, "max_holding_days": 0,
        "stop_loss_pct": 0.0, "take_profit_pct": 0.0, "fee_brl": 0.0,
        "exit_on_signal": False, "thresholds": {"pe_max": 5.0},
    })
    assert r.get("status") == "ok", r
    trades = r["trades"]
    assert trades, "the entry must fire (pe < 5 every bar)"
    assert len(trades) == 1
    t = trades[0]
    # one entrada, one saída — same shares, exit at the LAST bar
    assert t["entry_date"] == "2026-01-01"
    assert t["exit_date"] == "2026-01-25"
    assert t["exit_reason"] == "end_of_period"
    assert t["shares"] > 0
    assert t["entry_price"] == pytest.approx(10.0)
    assert t["exit_price"] == pytest.approx(10.0)


def test_bt_exit_on_signal_paired_trades(monkeypatch):
    """With exit_on_signal + the exit thresholds, entries and exits
    alternate — every trade closed by the signal, none left open."""
    s = _bt(monkeypatch, PRICES, RANGE)
    import webui.services.backtest as btm
    from skills.cvm.backtest import helpers

    def _signals(ticker, start, end, metrics):
        # pe 4.0 (entry) on even days, 12.0 (exit) on odd days
        days = [f"2026-01-{d:02d}" for d in range(1, 26)]
        return {"pe": {d: (4.0 if i % 2 == 0 else 12.0)
                       for i, d in enumerate(days)}}

    monkeypatch.setattr(helpers, "_precompute_signals", _signals)
    r = s.run("PETR4", {
        "strategy": "value_pe", "start_date": "2026-01-01",
        "end_date": "2026-01-25", "initial_capital": 10000.0,
        "position_pct": 100.0, "max_holding_days": 0,
        "stop_loss_pct": 0.0, "take_profit_pct": 0.0, "fee_brl": 0.0,
        "exit_on_signal": True,
        "thresholds": {"pe_max": 5.0, "pe_exit": 10.0},
    })
    assert r.get("status") == "ok", r
    trades = r["trades"]
    assert len(trades) >= 2
    # every trade closed by the reversal signal — except a position
    # still open on the LAST bar, which the engine force-closes there
    # (end_of_period; entry and exit share the last session's date)
    reasons = {t["exit_reason"] for t in trades}
    assert reasons <= {"signal", "end_of_period"}
    assert reasons == {"signal", "end_of_period"}
    assert trades[-1]["exit_reason"] == "end_of_period"
    assert trades[-1]["exit_date"] == "2026-01-25"
    assert all(t["entry_date"] <= t["exit_date"] for t in trades)
    # entry(i+1) comes at/after exit(i) — a buy only exists flat
    for a, b in zip(trades, trades[1:]):
        assert a["exit_date"] <= b["entry_date"]


# ════════════════════════════════════════════════════════════════════════════
# B1. INPLIT — grupamento com troca de ticker (RAIZ4 → RAIZ55)
# ════════════════════════════════════════════════════════════════════════════

def test_inplit_raiz4_to_raiz55(svc):
    """THE user case: 1.000.000 RAIZ4 @ R$0,30 (custo R$300.000) →
    inplit 1:100 (fator 0,01) → 10.000 RAIZ55 @ PM R$30,00 — same
    custo, same patrimônio, no phantom venda/compra."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                       "action": "inplit", "factor": 0.01,
                       "new_ticker": "RAIZ55", "date": "2026-02-01"})
    assert r["ok"], r
    raw = _raw(svc, aid)
    assert "RAIZ4" not in raw or raw["RAIZ4"]["qty"] == 0.0
    pos = raw["RAIZ55"]
    assert pos["qty"] == pytest.approx(10_000.0)     # 1.000.000 × 0,01
    assert pos["pm"] == pytest.approx(30.0)          # 0,30 ÷ 0,01
    assert pos["qty"] * pos["pm"] == pytest.approx(300_000.0)  # custo intacto
    assert pos["realized"] == pytest.approx(0.0)     # nothing realized


def test_inplit_rename_factor_one(svc):
    """Fator 1 = pure ticker rename (B3 suffix revert): qty and PM
    unchanged, the position just moves to the new code."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ55", quantity=500, price=28.0,
        date="2026-01-05")
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ55", "type": "corp",
                       "action": "inplit", "factor": 1.0,
                       "new_ticker": "RAIZ4", "date": "2026-02-01"})
    assert r["ok"], r
    pos = _raw(svc, aid)["RAIZ4"]
    assert pos["qty"] == pytest.approx(500.0)
    assert pos["pm"] == pytest.approx(28.0)
    assert pos["qty"] * pos["pm"] == pytest.approx(14_000.0)


def test_inplit_blends_with_existing_target(svc):
    """A pre-existing RAIZ55 position blends with the migrated cost
    (weighted custo médio across the two origins)."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")                                   # custo 300.000
    _tx(svc, aid, ticker="RAIZ55", quantity=100, price=36.0,
        date="2026-01-06")                                   # custo 3.600
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    pos = _raw(svc, aid)["RAIZ55"]
    # migrated 10.000 @30 + owned 100 @36 → 10.100 @ (303.600/10.100)
    assert pos["qty"] == pytest.approx(10_100.0)
    assert pos["pm"] == pytest.approx(303_600.0 / 10_100.0)
    assert pos["qty"] * pos["pm"] == pytest.approx(303_600.0)


def test_inplit_on_flat_is_ledger_noop(svc):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                       "action": "inplit", "factor": 0.01,
                       "new_ticker": "RAIZ55", "date": "2026-01-05"})
    assert r["ok"], r
    raw = _raw(svc, aid)
    assert "RAIZ55" not in raw          # nothing arrived (origin flat)


def test_inplit_realized_stays_on_origin(svc):
    """Sells of RAIZ4 BEFORE the inplit realized under the old code —
    the realized P&L stays with that history (account totals keep it;
    the new ticker starts at realized 0)."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000, price=1.00,
        date="2026-01-05")
    _tx(svc, aid, ticker="RAIZ4", type="sell", quantity=500, price=1.40,
        date="2026-01-06")               # realized +200
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    raw = _raw(svc, aid)
    assert raw["RAIZ4"]["realized"] == pytest.approx(200.0)
    assert raw["RAIZ55"]["realized"] == pytest.approx(0.0)
    # the migrated remainder: 500 @ PM 1,00 → 5 @ PM 100,00
    assert raw["RAIZ55"]["qty"] == pytest.approx(5.0)
    assert raw["RAIZ55"]["pm"] == pytest.approx(100.0)


def test_inplit_same_day_target_trade(svc):
    """Corp-first across tickers: a RAIZ55 sell ON the inplit date
    already trades the migrated position."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    _tx(svc, aid, ticker="RAIZ55", type="sell", quantity=10, price=30.0,
        date="2026-02-01")
    raw = _raw(svc, aid)
    assert raw["RAIZ55"]["qty"] == pytest.approx(9_990.0)
    assert raw["RAIZ55"]["pm"] == pytest.approx(30.0)
    # 10 × (30 − 30) = 0 realized — price equals the migrated PM
    assert raw["RAIZ55"]["realized"] == pytest.approx(0.0)


@pytest.mark.parametrize("body,field", [
    ({"action": "inplit", "factor": 0.01, "new_ticker": "RAIZ4"},
     "new_ticker"),                       # same ticker
    ({"action": "inplit", "factor": 0.01, "new_ticker": "RAIZ"},
     "new_ticker"),                       # invalid B3 ticker
    ({"action": "inplit", "factor": 0.01}, "new_ticker"),   # missing
    ({"action": "inplit", "new_ticker": "RAIZ55"}, "factor"),  # missing
    ({"action": "inplit", "factor": 0.0001, "new_ticker": "RAIZ55"},
     "factor"),                           # below 0,001
    ({"action": "inplit", "factor": 2000.0, "new_ticker": "RAIZ55"},
     "factor"),                           # above 1.000
])
def test_inplit_validation(svc, body, field):
    _, aid = _seed(svc)
    payload = {"account_id": aid, "ticker": "RAIZ4", "type": "corp",
               "date": "2026-01-05"}
    payload.update(body)
    r = svc.create_tx(payload)
    assert not r["ok"] and field in r["errors"], (body, r)


def test_inplit_edit_sanitation(svc):
    """Editing one corp action into another drops the stale keys (an
    inplit turned into rights must not carry new_ticker/factor)."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1000, price=0.30,
        date="2026-01-05")
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                       "action": "inplit", "factor": 0.01,
                       "new_ticker": "RAIZ55", "date": "2026-02-01"})
    tx_id = r["tx"]["id"]
    r2 = svc.update_tx(tx_id, {"ticker": "RAIZ1", "type": "corp",
                               "action": "rights", "quantity": 300,
                               "factor": "", "new_ticker": "",
                               "date": "2026-02-01"})
    assert r2["ok"], r2
    tx = r2["tx"]
    assert tx["action"] == "rights"
    assert "new_ticker" not in tx and "factor" not in tx
    assert tx["quantity"] == pytest.approx(300.0)
    # the store round-trips (reconcile accepts the sanitized shape)
    svc._maybe_reload()
    raw = _raw(svc, aid)
    assert raw["RAIZ1"]["qty"] == pytest.approx(300.0)
    assert raw["RAIZ1"]["pm"] == pytest.approx(0.0)


def test_inplit_reconcile_roundtrip(svc, tmp_path):
    """A store file with inplit/rights rows parses back (the boundary
    validation accepts the v1.28.5 shapes)."""
    import json
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1000, price=0.30,
        date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                   "action": "rights", "quantity": 50,
                   "date": "2026-02-02"})
    snap = svc._snapshot()
    store = {"version": 1, "users": snap["users"], "accounts":
             snap["accounts"], "txs": snap["txs"],
             "tickers": snap.get("tickers", {}), "watchlist":
             snap.get("watchlist", []), "alerts": snap.get("alerts", []),
             "notas": snap.get("notas", []), "undo": []}
    parsed = pfmod._parse_store(json.loads(json.dumps(store)))
    kinds = {(t.get("action")) for t in parsed["txs"]
             if t.get("type") == "corp"}
    assert kinds == {"inplit", "rights"}
    assert parsed["txs"][1]["new_ticker"] == "RAIZ55"


# ════════════════════════════════════════════════════════════════════════════
# B2. THE LADDER — no forked numerics across the new actions
# ════════════════════════════════════════════════════════════════════════════

def test_ladder_origin_and_target_pin_engine(svc):
    """The origin's ladder ends FLAT after the move; the target's
    ladder shows the ARRIVAL row and its final state equals the
    engine's (the pin, extended to inplit)."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    _tx(svc, aid, ticker="RAIZ4", type="sell", quantity=100_000,
        price=0.36, date="2026-01-06")     # realized +6.000
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    _tx(svc, aid, ticker="RAIZ55", type="sell", quantity=100,
        price=33.0, date="2026-03-01")     # realized +300 vs PM 30

    raw = _raw(svc, aid)
    # engine: 900.000 RAIZ4 @0,30 → 9.000 RAIZ55 @30,00
    assert raw["RAIZ55"]["qty"] == pytest.approx(8_900.0)
    assert raw["RAIZ55"]["pm"] == pytest.approx(30.0)
    assert raw["RAIZ55"]["realized"] == pytest.approx(300.0)
    assert raw["RAIZ4"]["realized"] == pytest.approx(6_000.0)

    # the ORIGIN ladder: buy, sell, inplit → flat (realized kept)
    rows4 = _ladder(svc, aid, "RAIZ4")
    assert rows4[-1]["run_qty"] == pytest.approx(0.0)
    assert rows4[-1]["run_pm"] == pytest.approx(0.0)
    assert len([r for r in rows4 if r["type"] == "corp"]) == 1

    # the TARGET ladder: the arrival row + the sell; final == engine
    rows55 = _ladder(svc, aid, "RAIZ55")
    arrivals = [r for r in rows55
                if r["type"] == "corp" and r["action"] == "inplit"]
    assert len(arrivals) == 1
    assert arrivals[0]["run_qty"] == pytest.approx(9_000.0)
    assert arrivals[0]["run_pm"] == pytest.approx(30.0)
    assert rows55[-1]["run_qty"] == pytest.approx(raw["RAIZ55"]["qty"])
    assert rows55[-1]["run_pm"] == pytest.approx(raw["RAIZ55"]["pm"])


def test_ladder_target_blend_pin(svc):
    """The target ladder's arrival blends with a pre-existing target
    position exactly like the engine does (prefix-replay arrival)."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    _tx(svc, aid, ticker="RAIZ55", quantity=100, price=36.0,
        date="2026-01-06")
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    raw = _raw(svc, aid)["RAIZ55"]
    rows = _ladder(svc, aid, "RAIZ55")
    assert rows[-1]["run_qty"] == pytest.approx(raw["qty"])
    assert rows[-1]["run_pm"] == pytest.approx(raw["pm"])
    assert rows[-1]["run_qty"] == pytest.approx(10_100.0)
    assert rows[-1]["run_pm"] == pytest.approx(303_600.0 / 10_100.0)


def test_ladder_rights_rows(svc):
    """A rights grant shows as a corp row with the qty (no factor
    cell) and the zero-PM running state."""
    _, aid = _seed(svc)
    svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                   "action": "rights", "quantity": 300,
                   "date": "2026-02-01"})
    rows = _ladder(svc, aid, "RAIZ1")
    assert len(rows) == 1
    assert rows[0]["action"] == "rights"
    assert rows[0]["factor_br"] is None
    assert rows[0]["qty"] == pytest.approx(300.0)
    assert rows[0]["run_qty"] == pytest.approx(300.0)
    assert rows[0]["run_pm"] == pytest.approx(0.0)


# ════════════════════════════════════════════════════════════════════════════
# B3. RIGHTS — the grant, the market sell, the expiry (venda a R$ 0,00)
# ════════════════════════════════════════════════════════════════════════════

def test_rights_grant_zero_cost(svc):
    """RAIZ1/RAIZ14/RAIZ16 received de graça alongside the RAIZ4 event:
    each lands on its own ticker at PM R$0,00 — the parent position
    untouched."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=10_000, price=0.30,
        date="2026-01-05")
    for tk, q in (("RAIZ1", 100), ("RAIZ14", 50), ("RAIZ16", 25)):
        r = svc.create_tx({"account_id": aid, "ticker": tk, "type": "corp",
                           "action": "rights", "quantity": q,
                           "date": "2026-02-01"})
        assert r["ok"], r
    raw = _raw(svc, aid)
    assert raw["RAIZ4"]["qty"] == pytest.approx(10_000.0)   # untouched
    assert raw["RAIZ4"]["pm"] == pytest.approx(0.30)
    for tk, q in (("RAIZ1", 100), ("RAIZ14", 50), ("RAIZ16", 25)):
        assert raw[tk]["qty"] == pytest.approx(q)
        assert raw[tk]["pm"] == pytest.approx(0.0)
        assert raw[tk]["qty"] * raw[tk]["pm"] == pytest.approx(0.0)


def test_rights_market_sell_and_expiry(svc):
    """The full lifecycle: receive 300 → sell 100 at R$1,50 (realized
    +150, the whole value — cost is zero) → the remaining 200 expire:
    venda a R$ 0,00 (accepted on the zero-cost position, books
    exactly zero, the position leaves)."""
    _, aid = _seed(svc)
    svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                   "action": "rights", "quantity": 300,
                   "date": "2026-02-01"})
    _tx(svc, aid, ticker="RAIZ1", type="sell", quantity=100, price=1.50,
        date="2026-02-10")
    _tx(svc, aid, ticker="RAIZ1", type="sell", quantity=200, price=0.0,
        date="2026-03-01")               # the expiry
    raw = _raw(svc, aid)
    assert raw["RAIZ1"]["qty"] == pytest.approx(0.0)
    assert raw["RAIZ1"]["realized"] == pytest.approx(150.0)


def test_zero_sell_still_refused_on_costful_position(svc):
    """The v1.22 phantom-loss guard lives on: R$ 0,00 sells are ONLY
    for zero-cost positions — a costful position must use a real price."""
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "sell",
                       "quantity": 100, "price": 0.0, "fees": 0.0,
                       "date": "2026-02-01"})
    assert not r["ok"] and "price" in r["errors"]
    assert "fantasma" in r["errors"]["price"].lower()


def test_zero_sell_refused_beyond_position(svc):
    """A zero sell beyond the qty would open a short at R$0,00 — refused."""
    _, aid = _seed(svc)
    svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                   "action": "rights", "quantity": 100,
                   "date": "2026-02-01"})
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "sell",
                       "quantity": 200, "price": 0.0, "fees": 0.0,
                       "date": "2026-02-10"})
    assert not r["ok"] and "price" in r["errors"]
    assert "posição" in r["errors"]["price"].lower()


def test_zero_sell_date_aware_probe(svc):
    """The probe reads the position AT the tx's date: selling at R$0,00
    BEFORE the rights grant (nothing held yet) is refused; the same
    sell after the grant is the valid expiry."""
    _, aid = _seed(svc)
    svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                   "action": "rights", "quantity": 100,
                   "date": "2026-03-01"})
    r_bad = svc.create_tx({"account_id": aid, "ticker": "RAIZ1",
                           "type": "sell", "quantity": 100, "price": 0.0,
                           "fees": 0.0, "date": "2026-02-01"})
    assert not r_bad["ok"] and "price" in r_bad["errors"]
    r_ok = svc.create_tx({"account_id": aid, "ticker": "RAIZ1",
                          "type": "sell", "quantity": 100, "price": 0.0,
                          "fees": 0.0, "date": "2026-03-02"})
    assert r_ok["ok"], r_ok
    assert _raw(svc, aid)["RAIZ1"]["qty"] == pytest.approx(0.0)


@pytest.mark.parametrize("qty", [0, -5])
def test_rights_validation_qty(svc, qty):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                       "action": "rights", "quantity": qty,
                       "date": "2026-02-01"})
    assert not r["ok"] and "quantity" in r["errors"], r


def test_rights_bad_action_still_refused(svc):
    _, aid = _seed(svc)
    r = svc.create_tx({"account_id": aid, "ticker": "PETR4", "type": "corp",
                       "action": "spinoff", "factor": 2.0,
                       "date": "2026-01-05"})
    assert not r["ok"] and "action" in r["errors"]


# ════════════════════════════════════════════════════════════════════════════
# B4. THE IR WALK — the two walks never disagree (now across tickers)
# ════════════════════════════════════════════════════════════════════════════

def test_ir_walk_inplit_then_sell(svc):
    """A RAIZ55 sell after the inplit realizes against the MIGRATED PM
    in the IR walk — same number as the engine (30 → sell 33 = +3/ação)."""
    from webui.services.ir_helper import _walk_account
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    _tx(svc, aid, ticker="RAIZ55", type="sell", quantity=100, price=33.0,
        date="2026-03-01")
    snap = svc._snapshot()
    acc_txs = [t for t in snap["txs"] if t["account_id"] == aid]
    buckets = _walk_account(acc_txs)
    # swing: 100 × (33 − 30) = +300 in 2026-03; buy volume 300.000 in 01
    assert buckets["2026-01"]["buy_vol"] == pytest.approx(300_000.0)
    assert buckets["2026-03"]["swing_res"] == pytest.approx(300.0)
    assert buckets["2026-03"]["swing_vol"] == pytest.approx(3_300.0)


def test_ir_walk_rights_full_profit(svc):
    """Free rights sold at market: 100% of the proceeds is swing profit
    (the cost basis is zero — the walk mirrors the engine)."""
    from webui.services.ir_helper import _walk_account
    _, aid = _seed(svc)
    svc.create_tx({"account_id": aid, "ticker": "RAIZ1", "type": "corp",
                   "action": "rights", "quantity": 300,
                   "date": "2026-02-01"})
    _tx(svc, aid, ticker="RAIZ1", type="sell", quantity=100, price=1.50,
        date="2026-02-10")
    snap = svc._snapshot()
    acc_txs = [t for t in snap["txs"] if t["account_id"] == aid]
    buckets = _walk_account(acc_txs)
    assert buckets["2026-02"]["swing_res"] == pytest.approx(150.0)
    assert buckets["2026-02"]["swing_vol"] == pytest.approx(150.0)


def test_ir_walk_classic_path_unchanged(svc):
    """The restructure must not move the classic numbers: a plain buy
    and sell pin the same buckets the old per-ticker walk produced."""
    from webui.services.ir_helper import _walk_account
    _, aid = _seed(svc)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _tx(svc, aid, type="sell", quantity=60, price=12.0, date="2026-02-01")
    _tx(svc, aid, type="sell", quantity=40, price=9.0, date="2026-02-05")
    snap = svc._snapshot()
    acc_txs = [t for t in snap["txs"] if t["account_id"] == aid]
    buckets = _walk_account(acc_txs)
    # buy 1.000 in jan; feb swing: 60×(12−10)=+120, 40×(9−10)=−40
    assert buckets["2026-01"]["buy_vol"] == pytest.approx(1_000.0)
    assert buckets["2026-02"]["swing_res"] == pytest.approx(80.0)
    assert buckets["2026-02"]["swing_vol"] == pytest.approx(
        60 * 12.0 + 40 * 9.0)


# ════════════════════════════════════════════════════════════════════════════
# B5. LEDGER / UNDO / LABELS
# ════════════════════════════════════════════════════════════════════════════

def test_ledger_corp_cells(svc):
    """The corp ledger cells: rights shows the QTY; inplit reads
    OLD → NEW ×fator; the undo labels name the new events."""
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1000, price=0.30,
        date="2026-01-05")
    r_in = svc.create_tx({"account_id": aid, "ticker": "RAIZ4",
                          "type": "corp", "action": "inplit",
                          "factor": 0.01, "new_ticker": "RAIZ55",
                          "date": "2026-02-01"})
    r_ri = svc.create_tx({"account_id": aid, "ticker": "RAIZ1",
                          "type": "corp", "action": "rights",
                          "quantity": 300, "date": "2026-02-02"})
    assert "inplit" in r_in["undo_label"] and "RAIZ55" in r_in["undo_label"]
    assert "direitos" in r_ri["undo_label"] and "300" in r_ri["undo_label"]

    rows = svc._tx_rows(svc._snapshot(), {aid}, limit=50)[0]
    by_action = {r["action"]: r for r in rows if r["type"] == "corp"}
    assert by_action["inplit"]["factor_br"] == "RAIZ4 → RAIZ55 ×0,01"
    assert by_action["inplit"]["new_ticker"] == "RAIZ55"
    assert by_action["rights"]["qty"] == "300"
    assert by_action["rights"]["factor_br"] == "300"
    assert by_action["rights"]["new_ticker"] is None


def test_undo_restores_inplit(svc):
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1000, price=0.30,
        date="2026-01-05")
    r = svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                       "action": "inplit", "factor": 0.01,
                       "new_ticker": "RAIZ55", "date": "2026-02-01"})
    token = r["undo_token"]
    out = svc.undo_mutation(token)
    assert out["ok"], out
    raw = _raw(svc, aid)
    assert raw["RAIZ4"]["qty"] == pytest.approx(1000.0)   # the move undone
    assert "RAIZ55" not in raw


# ════════════════════════════════════════════════════════════════════════════
# B6. PROVENTOS — the entitlement rides the ladder across the move
# ════════════════════════════════════════════════════════════════════════════

def test_proventos_entitlement_after_inplit(svc, monkeypatch):
    """An ex-date AFTER the inplit sees the MIGRATED quantity on the
    new code (10.000 RAIZ55, not the old 1.000.000 RAIZ4)."""
    import webui.services.portfolio_provents as pp
    _, aid = _seed(svc)
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    monkeypatch.setattr(pp, "_events", lambda tk: (
        [{"ex_date": "2026-04-10", "pay_date": "2026-05-01", "rate": 1.0,
          "type": "Dividendo"}] if tk == "RAIZ55" else []))
    rep = pp.proventos_report("all")
    ev = [e for e in rep["events"] if e["qty"]]
    assert ev and ev[0]["qty"] == pytest.approx(10_000.0)


def test_positions_payload_after_inplit(svc):
    """The positions() row for the new ticker: qty/PM/custo formatted,
    the origin gone (flat tickers don't ship)."""
    _, aid = _seed(svc)
    svc._test_quotes["RAIZ55"] = 30.0
    svc._test_refdates["RAIZ55"] = "2026-11-21"
    _tx(svc, aid, ticker="RAIZ4", quantity=1_000_000, price=0.30,
        date="2026-01-05")
    svc.create_tx({"account_id": aid, "ticker": "RAIZ4", "type": "corp",
                   "action": "inplit", "factor": 0.01,
                   "new_ticker": "RAIZ55", "date": "2026-02-01"})
    rep = svc.positions("all")
    tickers = {r["ticker"] for r in rep["positions"]}
    assert tickers == {"RAIZ55"}
    row = rep["positions"][0]
    assert row["raw_qty"] == pytest.approx(10_000.0)
    assert row["pm"] == "30,00"
    assert row["cost"] == "R$ 300.000,00"
