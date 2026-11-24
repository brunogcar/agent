"""tests/webui/test_ir_helper.py — the IR/DARF helper regression suite.

[v1.22.2] Roadmap item 3: swing × day-trade split, the R$ 20k
exemption, loss carry-forward, IRRF estimates and DARF due dates —
every value HAND-COMPUTED. The replay is a separate walk from the PM
engine (day-trade matched pairs never touch the custo médio), and the
carry pools are computed chronologically, never stored.

Scenarios:
  1.  Swing sell ≤ R$ 20k → exempt (positive result, no tax, IRRF
      under R$ 1,00 → nothing withheld)
  2.  Swing sell > R$ 20k → 15% − IRRF 0,005% (the BTG nota math)
  3.  Pure day trade → 20% − IRRF 1% (per account)
  4.  Partial day: buy 100/sell 30 same day → day +30, 70 stay in
      position at the buy price
  5.  Day carve-out NEVER touches the PM: hold 100@10, same-day buy
      100@12 + sell 100@13 → day +100, PM still 10; a later sell
      realizes against 10
  6.  Swing loss carry: −R$ 2.000 in an exempt-volume month still
      builds the pool (losses in exempt months ARE compensable)
  7.  Exempt positive month does NOT consume the carry
  8.  Day loss pool is SEPARATE from the swing pool
  9.  CPF-level aggregation: two accounts' swing volumes SUM for the
      exemption test (each under 20k, together over)
  10. Residual sell beyond the day's buys: matched part is day trade,
      the excess sells against the PM (swing)
  11. Short: the open short registers the sell VOLUME, no realized
      result until the cover; the cover realizes against the short PM
  12. DARF due dates: last business day of the following month
      (weekend → back to Friday)

Run:  python -m pytest tests/webui/test_ir_helper.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.portfolio as pfmod            # noqa: E402
from webui.services.portfolio import PortfolioService  # noqa: E402
from webui.services.ir_helper import _due_date, ir_report  # noqa: E402


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    monkeypatch.setattr(pfmod, "_quotes_for",
                        lambda tickers: {"status": "ok", "session_date":
                                         "2026-11-21", "symbols": []})
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    # ir_report reads the module singleton — point it at OUR store.
    monkeypatch.setattr(pfmod, "_portfolio_service", s)
    return s


def _seed(svc, user="Ana"):
    u = svc.create_user({"name": user})
    assert u["ok"]
    uid = u["user"]["id"]
    def acc(name="Principal"):
        a = svc.create_account({"user_id": uid, "name": name, "broker": "XP"})
        assert a["ok"]
        return a["account"]["id"]
    return uid, acc


def _tx(svc, aid, **kw):
    body = {"account_id": aid, "ticker": "PETR4", "type": "buy",
            "quantity": 100, "price": 10.0, "fees": 0.0,
            "date": "2026-01-05"}
    body.update(kw)
    r = svc.create_tx(body)
    assert r["ok"], r
    return r


def _rows(svc, uid):
    out = ir_report(f"user:{uid}")
    assert out["ok"], out
    users = out["users"]
    assert len(users) == 1
    return {m["month"]: m for m in users[0]["months"]}


# ── 1. exempt swing (≤ R$ 20k, IRRF under the R$ 1,00 floor) ─────────────────

def test_swing_exempt_and_irrf_floor(svc):
    uid, acc = _seed(svc)
    aid = acc()
    # buy 1000@10 + fees 5 → PM 10,005; sell 1000@12 − fees 5:
    # result = 1000×(12 − 10,005) − 5 = 1.990,00; volume 12.000 ≤ 20k
    _tx(svc, aid, quantity=1000, price=10.0, fees=5.0, date="2026-01-05")
    _tx(svc, aid, type="sell", quantity=1000, price=12.0, fees=5.0,
        date="2026-02-10")
    rows = _rows(svc, uid)
    m = rows["2026-02"]
    assert m["swing_vol"] == 12000.0
    assert m["swing_res"] == 1990.0
    assert m["exempt"] is True
    assert m["swing_tax"] == 0.0
    # 0,005% × 12.000 = R$ 0,60 → under the R$ 1,00 floor: not withheld
    assert m["irrf_s"] == 0.0
    assert m["due_total"] == 0.0 and m["darfs"] == []


# ── 2. swing above the exemption (the BTG nota math) ─────────────────────────

def test_swing_above_20k(svc):
    uid, acc = _seed(svc)
    aid = acc()
    _tx(svc, aid, quantity=1000, price=20.0, date="2026-01-05")
    _tx(svc, aid, type="sell", quantity=1000, price=25.0,
        date="2026-02-10")
    rows = _rows(svc, uid)
    m = rows["2026-02"]
    assert m["swing_vol"] == 25000.0 and m["exempt"] is False
    assert m["swing_res"] == 5000.0
    assert m["swing_tax"] == 750.0                     # 15%
    assert m["irrf_s"] == 1.25                         # 0,005% × 25.000
    assert m["due_s"] == 748.75
    assert m["darfs"] == [{"code": "6015", "value": 748.75,
                           "value_br": "748,75"}]


# ── 3. pure day trade ────────────────────────────────────────────────────────

def test_day_trade(svc):
    uid, acc = _seed(svc)
    aid = acc()
    _tx(svc, aid, quantity=100, price=10.0, date="2026-02-10")
    _tx(svc, aid, type="sell", quantity=100, price=11.0, date="2026-02-10")
    rows = _rows(svc, uid)
    m = rows["2026-02"]
    assert m["day_res"] == 100.0
    assert m["day_vol"] == 1100.0 and m["swing_vol"] == 0.0
    assert m["day_tax"] == 20.0                        # 20%
    assert m["irrf_d"] == 1.0                          # 1% × 100
    assert m["due_d"] == 19.0
    assert m["darfs"] == [{"code": "6120", "value": 19.0,
                           "value_br": "19,00"}]


# ── 4. partial day ───────────────────────────────────────────────────────────

def test_partial_day_trade(svc):
    uid, acc = _seed(svc)
    aid = acc()
    # buy 100@10, sell 30@11 same day → day 30×(11−10) = +30;
    # 70 shares stay in position at 10 (nothing realized, no volume)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-02-10")
    _tx(svc, aid, type="sell", quantity=30, price=11.0, date="2026-02-10")
    rows = _rows(svc, uid)
    m = rows["2026-02"]
    assert m["day_res"] == 30.0
    assert m["day_vol"] == 330.0
    assert m["swing_vol"] == 0.0 and m["swing_res"] == 0.0
    assert m["buy_vol"] == 1000.0


# ── 5. the day carve-out never touches the PM ────────────────────────────────

def test_day_carveout_keeps_pm(svc):
    uid, acc = _seed(svc)
    aid = acc()
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _tx(svc, aid, quantity=100, price=12.0, date="2026-02-10")
    _tx(svc, aid, type="sell", quantity=100, price=13.0, date="2026-02-10")
    # Feb: day +100; position STILL 100@10 (the round-trip changed nothing)
    _tx(svc, aid, type="sell", quantity=100, price=11.0, date="2026-03-05")
    rows = _rows(svc, uid)
    assert rows["2026-02"]["day_res"] == 100.0
    assert rows["2026-02"]["swing_vol"] == 0.0
    # March: sells against PM 10 → +100 (if the day buys had blended,
    # the PM would be 11 and the result 0)
    m = rows["2026-03"]
    assert m["swing_res"] == 100.0 and m["swing_vol"] == 1100.0


# ── 6 + 7. carry: exempt-month losses count, exempt gains don't consume ──────

def test_loss_carry_rules(svc):
    uid, acc = _seed(svc)
    aid = acc()
    # Jan: −2.000 with volume 18.000 (exempt month, loss → pool grows)
    _tx(svc, aid, quantity=1000, price=20.0, date="2026-01-05")
    _tx(svc, aid, type="sell", quantity=1000, price=18.0, date="2026-01-20")
    # Feb: +1.000 with volume 11.000 (exempt month, gain → NO consumption)
    _tx(svc, aid, quantity=1000, price=10.0, date="2026-02-02")
    _tx(svc, aid, type="sell", quantity=1000, price=11.0, date="2026-02-20")
    # Mar: +11.000 with volume 21.000 → taxable = 11.000 − 2.000 carry
    _tx(svc, aid, quantity=1000, price=10.0, date="2026-03-02")
    _tx(svc, aid, type="sell", quantity=1000, price=21.0, date="2026-03-20")
    rows = _rows(svc, uid)
    assert rows["2026-01"]["swing_res"] == -2000.0
    assert rows["2026-01"]["carry_s_after"] == 2000.0
    assert rows["2026-02"]["exempt"] is True
    assert rows["2026-02"]["swing_tax"] == 0.0
    assert rows["2026-02"]["carry_s_after"] == 2000.0     # NOT consumed
    m = rows["2026-03"]
    assert m["carry_used_s"] == 2000.0
    assert m["swing_taxable"] == 9000.0
    assert m["swing_tax"] == 1350.0
    assert m["irrf_s"] == 1.05                            # 0,005% × 21.000
    assert m["due_s"] == 1348.95


# ── 8. day pool separate from swing pool ─────────────────────────────────────

def test_day_pool_separate_from_swing(svc):
    uid, acc = _seed(svc)
    aid = acc()
    # Jan: day −100 (pool), swing +100 (exempt volume — positive, no tax)
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-10")
    _tx(svc, aid, type="sell", quantity=100, price=9.0, date="2026-01-10")
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-11")
    _tx(svc, aid, type="sell", quantity=100, price=11.0, date="2026-01-12")
    # Feb: day +200 → taxable 200 − 100 carry = 100 → 20% = 20 − IRRF 2
    _tx(svc, aid, quantity=100, price=10.0, date="2026-02-10")
    _tx(svc, aid, type="sell", quantity=100, price=12.0, date="2026-02-10")
    rows = _rows(svc, uid)
    assert rows["2026-01"]["day_res"] == -100.0
    assert rows["2026-01"]["swing_res"] == 100.0
    assert rows["2026-01"]["carry_d_after"] == 100.0
    m = rows["2026-02"]
    assert m["carry_used_d"] == 100.0
    assert m["day_tax"] == 20.0
    assert m["irrf_d"] == 2.0                             # 1% × 200
    assert m["due_d"] == 18.0


# ── 9. CPF-level aggregation across accounts ─────────────────────────────────

def test_two_accounts_aggregate_for_exemption(svc):
    uid, acc = _seed(svc)
    a1, a2 = acc("XP"), acc("BTG")
    # XP: sells 12.000 (result +7.000); BTG: sells 9.000 (result +4.000)
    # — each under 20k, but the CPF total 21.000 is NOT exempt
    _tx(svc, a1, quantity=1000, price=5.0, date="2026-01-05")
    _tx(svc, a1, type="sell", quantity=1000, price=12.0, date="2026-02-10")
    _tx(svc, a2, quantity=1000, price=5.0, date="2026-01-05")
    _tx(svc, a2, type="sell", quantity=1000, price=9.0, date="2026-02-10")
    rows = _rows(svc, uid)
    m = rows["2026-02"]
    assert m["swing_vol"] == 21000.0
    assert m["exempt"] is False
    assert m["swing_res"] == 11000.0
    assert m["swing_tax"] == 1650.0                       # 15% × 11.000


# ── 10. residual sell beyond the day's buys ──────────────────────────────────

def test_residual_sell_beyond_day_buys(svc):
    uid, acc = _seed(svc)
    aid = acc()
    # hold 100@10; Feb 10: buy 50@11 + sell 120@12 →
    #   matched 50 → day 50×(12−11) = +50
    #   residual sell 70 @ 12 → swing vol 840, realized 70×(12−10) = +140
    _tx(svc, aid, quantity=100, price=10.0, date="2026-01-05")
    _tx(svc, aid, quantity=50, price=11.0, date="2026-02-10")
    _tx(svc, aid, type="sell", quantity=120, price=12.0, date="2026-02-10")
    rows = _rows(svc, uid)
    m = rows["2026-02"]
    assert m["day_res"] == 50.0
    assert m["day_vol"] == 600.0                          # 50 × 12
    assert m["swing_vol"] == 840.0                        # 70 × 12
    assert m["swing_res"] == 140.0


# ── 11. short: volume now, result at the cover ───────────────────────────────

def test_short_sell_and_cover(svc):
    uid, acc = _seed(svc)
    aid = acc()
    _tx(svc, aid, type="sell", quantity=100, price=10.0, date="2026-01-10")
    _tx(svc, aid, quantity=100, price=8.0, date="2026-02-10")
    rows = _rows(svc, uid)
    jan, feb = rows["2026-01"], rows["2026-02"]
    assert jan["swing_vol"] == 1000.0 and jan["swing_res"] == 0.0
    assert feb["swing_res"] == 200.0                      # 100×(10−8)
    assert feb["buy_vol"] == 800.0


# ── 12. DARF due dates ───────────────────────────────────────────────────────

def test_due_dates():
    assert _due_date("2026-01") == "2026-02-27"   # 28/02 Sat → Fri 27/02
    assert _due_date("2026-02") == "2026-03-31"   # Tue
    assert _due_date("2026-12") == "2027-01-29"   # 31/01 Sun → Fri 29/01
    assert _due_date("2026-11") == "2026-12-31"   # Thu
