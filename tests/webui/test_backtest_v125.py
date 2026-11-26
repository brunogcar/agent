"""tests/webui/test_backtest_v125.py — the v1.25 Backtest suite.

Focused (the user's standing rule: "no need to worry too much about the
tests, just add important ones if really needed"). What actually matters
in a simulator — the NUMBERS and the GUARDS:

  1.  ENGINE MATH, hand-computed on a 25-bar synthetic series:
      buy & hold +60% (100 shares @ 10 → 16), the fee guard (99 shares
      when R$ 10 corretagem must fit inside R$ 1.000 → +57,4%), 50%
      position sizing (+30%), the ma_cross stop-loss path (enter 29,
      stop at 10 = −65,52%, re-enter 10, signal-exit 10 = 0% → −64,6%
      total — exactly the REPL verification), max drawdown measured
      from the PEAK (1.034 → 354 = 65,76%), profit factor 0 when every
      trade loses, entry/exit markers, and the underwater curve.
  2.  SIGNAL EVALUATION — the step-function lookup honours "most recent
      ≤ date", the scale conversion (ROE 20% in the form → 0,20 fraction
      the engines emit), composite entry is AND ('all') and its exit is
      OR ('any').
  3.  THE FUNDAMENTAL PATH — a patched _precompute_signals drives a
      value_pe run: entry only under the threshold, exit_on_signal at
      the reversal, max_holding when left on, and the honest warning
      when a metric series is MISSING (the "sync CVM" note).
  4.  VALIDATION — bad strategy, out-of-bounds engine params, malformed
      / inverted dates, sma fast ≥ slow, and the date clamping to the
      ticker's own price range.
  5.  CLEAN PRICE FETCH — bdi_code=2 preferred (DIR/REC rights rows at
      R$ 0,50 dropped), per-date dedupe (highest volume wins), fallback
      to the plain market filter when a ticker has no lote-padrão rows.
  6.  PURE HELPERS — _sma_series (None until the window fills),
      _drawdown_series, _downsample_indices (first/last always kept).
  7.  HTTP — meta (8 strategies, presets, range), run (buy_hold ok,
      validation error → 400 JSON, text/plain body → 400 — the v1.22
      CSRF rule), the tab fragment and the page route.

Run:  python -m pytest tests/webui/test_backtest_v125.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.backtest as bt                          # noqa: E402
from webui.services.backtest import (                         # noqa: E402
    BacktestService, STRATEGY_SPECS, _drawdown_series,
    _downsample_indices, _sma_series,
)


# ── the synthetic world ─────────────────────────────────────────────────────
# TWO series, each hand-computed:
#   PRICES (25 bars) — the ma_cross/stop study: prices rise 10→30 so
#   SMA(5) crosses above SMA(20) first at idx 19 (close 29); the crash
#   to 10 trips the 20% stop; recovery re-crosses; ends flat at 10.
#   BH_PRICES (10 bars) — the money math: buy 100 @10, end at 16 (+60%).
CLOSING = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
           25, 26, 27, 28, 29, 30, 10, 10, 10, 10]
PRICES = [("2026-01-%02d" % (i + 1), p) for i, p in enumerate(CLOSING)]
RANGE = ("2026-01-01", "2026-01-25")
DATES = {"start_date": "2026-01-01", "end_date": "2026-01-25"}

BH_CLOSING = [10, 10, 11, 12, 13, 14, 15, 5, 15, 16]
BH_PRICES = [("2026-01-%02d" % (i + 1), p) for i, p in enumerate(BH_CLOSING)]
BH_RANGE = ("2026-01-01", "2026-01-10")
BH_DATES = {"start_date": "2026-01-01", "end_date": "2026-01-10"}

_REPO_DB = Path(__file__).resolve().parents[2] / "memory_db" / "b3" / "cotahist.db"


def _mk(monkeypatch, prices, rng):
    s = BacktestService()
    monkeypatch.setattr(s, "_clean_prices", lambda t, f, e: list(prices))
    monkeypatch.setattr(s, "_price_range", lambda t: rng)
    return s


@pytest.fixture()
def svc(monkeypatch):
    """A service pinned to the 25-bar synthetic price world."""
    return _mk(monkeypatch, PRICES, RANGE)


@pytest.fixture()
def svc10(monkeypatch):
    """The 10-bar world (buy & hold gains — the money-math checks)."""
    return _mk(monkeypatch, BH_PRICES, BH_RANGE)


# ── 1. engine math (hand-computed) ──────────────────────────────────────────

def test_buy_hold_math(svc10):
    r = svc10.run("T", dict(BH_DATES, strategy="buy_hold", initial_capital=1000))
    assert r["status"] == "ok"
    t = r["trades"][0]
    assert (t["shares"], t["entry_price"], t["exit_price"]) == (100, 10, 16)
    assert t["exit_reason"] == "end_of_period"
    assert r["performance"]["total_return_pct"] == 60.0
    assert r["performance"]["buy_hold_return_pct"] == 60.0
    assert r["performance"]["alpha_vs_buy_hold"] == 0.0


def test_fee_fits_inside_cash(svc10):
    r = svc10.run("T", dict(BH_DATES, strategy="buy_hold",
                             initial_capital=1000, fee_brl=10))
    # int(1000/10)=100 shares would cost 1010 — the guard walks to 99
    assert r["trades"][0]["shares"] == 99
    # 99×16 − 10 = 1574 → +57,4%
    assert r["performance"]["total_return_pct"] == 57.4


def test_position_sizing_half(svc10):
    r = svc10.run("T", dict(BH_DATES, strategy="buy_hold",
                             initial_capital=1000, position_pct=50))
    # 50 shares @10 (cash 500) → 500 + 50×16 = 1300 → +30%
    assert r["performance"]["total_return_pct"] == 30.0


def test_ma_cross_stop_loss_path(svc):
    r = svc.run("T", dict(DATES, strategy="ma_cross", sma_fast=5, sma_slow=20,
                          initial_capital=1000, stop_loss_pct=20))
    trades = r["trades"]
    assert [(t["entry_price"], t["exit_price"], t["exit_reason"])
            for t in trades] == [(29, 10, "stop_loss"), (10, 10, "signal")]
    assert [t["return_pct"] for t in trades] == [-65.52, 0.0]
    assert r["performance"]["total_return_pct"] == -64.6
    # equity peaked at 1.034 (34 shares × 30) then fell to 354 → 65,76%
    assert r["performance"]["max_drawdown_pct"] == 65.76
    # every trade lost-or-zero → PF 0, win rate 0
    assert r["performance"]["profit_factor"] == 0.0
    assert r["performance"]["win_rate_pct"] == 0.0
    assert r["performance"]["avg_holding_days"] == 2.0
    # the trade markers ride the payload (the price chart reads them)
    assert r["curves"]["entries"] == [{"date": "2026-01-20", "price": 29},
                                      {"date": "2026-01-22", "price": 10}]
    assert [e["reason"] for e in r["curves"]["exits"]] == ["stop_loss", "signal"]
    # the underwater curve hangs BELOW zero (the static's convention)
    assert min(r["curves"]["drawdown"]) == -65.76


def test_max_holding_exit(svc):
    r = svc.run("T", dict(DATES, strategy="ma_cross", sma_fast=5, sma_slow=20,
                          initial_capital=1000, max_holding_days=1))
    assert all(t["exit_reason"] in ("max_holding", "signal",
                                    "end_of_period") for t in r["trades"])
    assert any(t["exit_reason"] == "max_holding" for t in r["trades"])


def test_buy_hold_ignores_stops_and_never_reenters(svc):
    r = svc.run("T", dict(DATES, strategy="buy_hold", initial_capital=1000,
                          stop_loss_pct=50, take_profit_pct=5,
                          max_holding_days=1))
    assert len(r["trades"]) == 1
    assert r["trades"][0]["exit_reason"] == "end_of_period"


# ── 2. signal evaluation ────────────────────────────────────────────────────

def test_signal_ok_step_scale_and_modes():
    from webui.services.backtest import BacktestService as S
    signal = {"pe": {"2026-01-05": 4.0, "2026-01-15": 9.0},
              "roe": {"2026-01-05": 0.25, "2026-01-15": 0.08}}
    conds = [
        {"key": "pe_max", "metric": "pe", "op": "<", "scale": 1.0},
        {"key": "roe_min", "metric": "roe", "op": ">", "scale": 0.01},
    ]
    th = {"pe_max": 5.0, "roe_min": 20.0}  # 20% form → 0.20 fraction
    # 2026-01-10: pe step = 4.0 (< 5 ✓), roe step = 0.25 (> 0.20 ✓) → AND ok
    assert S._signal_ok(conds, "2026-01-10", signal, th, "all") is True
    # 2026-01-20: pe = 9.0 (✗), roe = 0.08 (✗) → AND fails, OR fails
    assert S._signal_ok(conds, "2026-01-20", signal, th, "all") is False
    # OR mode: one leg holding is enough (composite exit semantics)
    th2 = {"pe_max": 1.0, "roe_min": 20.0}
    assert S._signal_ok(conds, "2026-01-20", signal, th2, "any") is False
    th3 = {"pe_max": 10.0, "roe_min": 50.0}   # pe 9 < 10 ✓, roe 8% < 50% ✗
    assert S._signal_ok(conds, "2026-01-20", signal, th3, "any") is True
    # before the first observation → no signal
    assert S._signal_ok(conds, "2026-01-01", signal, th, "all") is False


# ── 3. the fundamental path (patched signal precompute) ─────────────────────

_PE_SERIES = {"pe": {"2026-01-0%d" % d: (4.0 if d <= 6 else 9.0)
                     for d in range(1, 10)}}


def test_value_pe_entry_exit_and_max_holding(svc, monkeypatch):
    import skills.cvm.backtest.helpers as helpers
    monkeypatch.setattr(helpers, "_precompute_signals",
                        lambda t, f, e, m: dict(_PE_SERIES))
    # pe < 5 from day 1; exit_on_signal pe > 8 fires on day 7
    r = svc.run("T", dict(DATES, strategy="value_pe", initial_capital=1000,
                          exit_on_signal=True, pe_exit=8))
    trades = r["trades"]
    assert trades and trades[0]["entry_date"] == "2026-01-01"
    assert trades[0]["exit_date"] == "2026-01-07"
    assert trades[0]["exit_reason"] == "signal"
    # without exit_on_signal: max_holding (defaults 252 — capped by the
    # period end) → end_of_period with exit reason fallback
    r2 = svc.run("T", dict(DATES, strategy="value_pe", initial_capital=1000,
                           max_holding_days=3))
    assert r2["trades"][0]["exit_reason"] == "max_holding"
    assert r2["trades"][0]["holding_days"] == 3


def test_value_pe_missing_metric_warns(svc, monkeypatch):
    import skills.cvm.backtest.helpers as helpers
    monkeypatch.setattr(helpers, "_precompute_signals",
                        lambda t, f, e, m: {"pe": {}})
    r = svc.run("T", dict(DATES, strategy="value_pe", initial_capital=1000))
    assert r["status"] == "ok"
    assert r["performance"]["num_trades"] == 0
    assert any("P/L" in w and "sincronize" in w for w in r["warnings"])
    # the generic no-entry warning must NOT double up on the missing one
    assert len(r["warnings"]) == 1


# ── 4. validation ───────────────────────────────────────────────────────────

def test_validation_errors(svc):
    cases = [
        ({"strategy": "nope"}, "Estratégia inválida"),
        ({"strategy": "value_pe", "initial_capital": 10}, "initial_capital"),
        ({"strategy": "value_pe", "position_pct": 200}, "position_pct"),
        ({"strategy": "value_pe", "start_date": "13/01/2026"}, "Período inválido"),
        ({"strategy": "value_pe", "start_date": "2026-01-25",
          "end_date": "2026-01-01"}, "anterior à final"),
        ({"strategy": "ma_cross", "sma_fast": 300}, "Média rápida"),
        ({"strategy": "ma_cross", "sma_fast": 100, "sma_slow": 50},
         "menor que a lenta"),
        ({"strategy": "value_pe", "start_date": "2026-02-01",
          "end_date": "2026-03-01"}, "não cruza o histórico"),
    ]
    for body, frag in cases:
        r = svc.run("T", body)
        assert r.get("_error") and frag in r["_error"], (body, r)


def test_dates_clamp_to_range(svc):
    r = svc.run("T", {"strategy": "buy_hold", "initial_capital": 1000,
                      "start_date": "2015-01-01", "end_date": "2030-01-01"})
    assert r["status"] == "ok"
    assert r["period"]["start"] == "2026-01-01"
    assert r["period"]["end"] == "2026-01-25"


def test_no_prices_error(svc):
    svc._clean_prices = lambda t, f, e: [("2026-01-01", 10.0)]
    r = svc.run("T", dict(DATES, strategy="buy_hold"))
    assert "Sem preços suficientes" in r["_error"]


# ── 5. the clean price fetch ────────────────────────────────────────────────

def test_clean_prices_bdi_and_dedupe(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / "cotahist.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE cotahist (refdate TEXT, symbol TEXT, "
                 "bdi_code INT, market_type INT, close REAL, volume REAL)")
    rows = [
        # day 1: the real share + a DIR/REC right + a low-volume dupe
        ("2026-01-01", "T", 2, 10, 10.0, 1_000_000),
        ("2026-01-01", "T", 14, 10, 0.5, 25_000),
        ("2026-01-01", "T", 2, 10, 10.5, 500),     # dupe — loses on volume
        # day 2: only a rights row (the 0.5 trap)
        ("2026-01-02", "T", 2, 10, 11.0, 800_000),
        ("2026-01-02", "T", 96, 10, 0.5, 25_000),
    ]
    conn.executemany("INSERT INTO cotahist VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    s = BacktestService()
    monkeypatch.setattr(s, "_cotahist_path", lambda: db)
    series = s._clean_prices("T", "2026-01-01", "2026-01-31")
    # one row per date, the rights rows dropped, the max-volume dupe won
    assert series == [("2026-01-01", 10.0), ("2026-01-02", 11.0)]


def test_clean_prices_fallback_without_bdi2(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / "cotahist.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE cotahist (refdate TEXT, symbol TEXT, "
                 "bdi_code INT, market_type INT, close REAL, volume REAL)")
    # a paper with ONLY odd bdi codes (BDR-ish) — the fallback keeps it
    conn.execute("INSERT INTO cotahist VALUES ('2026-01-01','T',82,10,3.0,10)")
    conn.commit()
    conn.close()
    s = BacktestService()
    monkeypatch.setattr(s, "_cotahist_path", lambda: db)
    assert s._clean_prices("T", "2026-01-01", "2026-01-31") == [("2026-01-01", 3.0)]


# ── 6. pure helpers ─────────────────────────────────────────────────────────

def test_sma_series():
    out = _sma_series([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2:] == [2.0, 3.0, 4.0]


def test_drawdown_series():
    # negatives — the classic underwater form (0 = at the peak)
    assert _drawdown_series([100, 120, 60, 90]) == [0.0, 0.0, -50.0, -25.0]


def test_downsample_indices():
    assert _downsample_indices(10, 100) == list(range(10))
    idx = _downsample_indices(2500, 1000)
    assert len(idx) <= 1001 and idx[0] == 0 and idx[-1] == 2499
    assert idx == sorted(idx)


# ── 7. HTTP surface ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    # memory_root isolated (the v124 recipe) + the real cotahist.db
    # (READ-ONLY — meta's MIN/MAX and the fixture's clamps need it) +
    # the 10-bar synthetic price world for run().
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(
        Path(__file__).resolve().parents[2] / "memory_db"), raising=False)
    monkeypatch.setattr(BacktestService, "_clean_prices",
                        lambda self, t, f, e: list(BH_PRICES))
    monkeypatch.setattr(BacktestService, "_price_range",
                        lambda self, t: BH_RANGE)
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_meta(client):
    r = client.get("/api/webui/company/PETR4/backtest/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    names = [s["name"] for s in body["strategies"]]
    assert names == list(STRATEGY_SPECS)            # all 8, in order
    pe = body["strategies"][0]
    assert pe["entry"][0]["key"] == "pe_max" and pe["entry"][0]["default"] == 5.0
    assert [p["label"] for p in body["presets"]] == ["1A", "3A", "5A", "10A", "Máximo"]
    assert body["range"]["first"] <= body["defaults"]["start_date"]


def test_http_run_ok_and_errors(client):
    r = client.post("/api/webui/company/PETR4/backtest/run",
                    json=dict(BH_DATES, strategy="buy_hold", initial_capital=1000))
    assert r.status_code == 200
    assert r.json()["performance"]["total_return_pct"] == 60.0
    # validation error → 400 + JSON (never a plain-text 500)
    r2 = client.post("/api/webui/company/PETR4/backtest/run",
                     json={"strategy": "nope"})
    assert r2.status_code == 400
    assert "Estratégia inválida" in r2.json()["_error"]
    # the v1.22 CSRF rule: text/plain must not parse
    r3 = client.post("/api/webui/company/PETR4/backtest/run",
                     content='{"strategy":"buy_hold"}',
                     headers={"Content-Type": "text/plain"})
    assert r3.status_code == 400
    assert "JSON" in r3.json()["_error"]


def test_http_tab_and_page(client):
    # [v1.28.1] the Backtest TAB is GONE (the simulator moved to the
    # Ferramentas page); the per-ticker endpoints stay (the tool calls
    # them for whichever ticker is picked). The tab fragment 404s in
    # PT-BR, the company page no longer links it, and the tools page
    # carries the third family pill instead.
    r = client.get("/api/webui/company/PETR4/tab/backtest")
    assert r.status_code == 404
    r2 = client.get("/webui/company/PETR4/backtest", follow_redirects=False)
    assert r2.status_code == 302  # unknown tab → redirect to the overview
    r3 = client.get("/webui/tools")
    assert r3.status_code == 200
    assert 'id="family-pill-backtest"' in r3.text
    assert 'id="bt-tool-search"' in r3.text
