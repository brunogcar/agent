"""tests/webui/test_portfolio_engine.py — the Carteira money-engine regression suite.

[v1.22.1, wave 5] "The money engine never gets touched again without
these." One test per confirmed finding of the v1.22 adversarial-review
wave (4 reviews), each with HAND-COMPUTED values — if a refactor changes
any of these numbers, the test fails before the user's portfolio does.

Scenarios (mirrors the v1.22 commit message):
  1.  SHORTS COUNT in the totals (B109 — positions() dropped negative
      market values while keeping negative cost: a short book read
      Patrimônio R$ 0,00 / +100%; positions totals must equal directory)
  2.  Flip fee split, buy side (short 50@20 + buy 100@10 fees 10 →
      realizado 495, PM 10,10 — the covered share of the fee realizes,
      the excess share enters the new long's PM)
  3.  Flip fees, sell side (long 50@10 + sell 100@20 fees 10 → realizado
      490 — ALL sell fees stay realized, the short-open convention)
  4.  Same-second replay order (seq, not uuid — buy/sell/buy inside one
      second must replay in insertion order)
  5.  NaN/±inf rejected at the numeric boundary (they used to pass every
      range check and poison whole accounts)
  6.  Corrupt store: quarantine + last-good reads + 503 writes + self-heal
  7.  ONE ticker definition (B3SA3 passes; BDRs pass; option series and
      lowercase are rejected)
  8.  Sell at R$ 0,00 refused (bonificação is a BUY at 0)
  9.  update_tx refuses moving a tx to ANOTHER USER's account (B125)
  10. Mixed long+short of one ticker → PM/Lucro % "—" (mixed flag)
  11. parseBr: "3.65" is 3,65 not 365 (100× bug); "1.234" stays thousands
  12. Edit/delete that leaves shorts open returns warnings
  13. A never-traded ticker no longer defeats the 30s quote cache
  14. HTTP surface: delete-not-found → 404 (was a TypeError → 500), the
      CSRF guard (cross-site 403 / text-plain 400), and the logs
      endpoints no longer capture themselves (B127)

Run:  python -m pytest tests/webui/test_portfolio_engine.py -v
(from the repo root — imports resolve like every other tests/ module).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Repo root on sys.path (running `pytest tests/...` from the root already
# does this; the explicit insert keeps `pytest tests/webui/` working too).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.portfolio as pfmod          # noqa: E402
from webui.services.portfolio import PortfolioService  # noqa: E402


# ── the fixture: a fresh service over a temp store with fake quotes ──────────

def _fake_quotes_factory(quotes: dict[str, float], calls: list):
    """A quotes_for() stand-in: hand-set closes + a call counter."""
    def _fake(tickers):
        calls.append(list(tickers))
        return {
            "status": "ok",
            "session_date": "2026-11-21",
            "symbols": [{"ticker": t, "close": quotes[t]}
                        for t in tickers if t in quotes],
        }
    return _fake


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    """Fresh PortfolioService; store under tmp_path; quotes faked."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    quotes: dict[str, float] = {}
    calls: list = []
    monkeypatch.setattr(pfmod, "_quotes_for", _fake_quotes_factory(quotes, calls))
    s = PortfolioService()
    # No background CVM metadata threads in tests (network + daemon
    # threads have no place in a deterministic money suite).
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    s._test_quotes = quotes          # type: ignore[attr-defined]
    s._test_calls = calls            # type: ignore[attr-defined]
    return s


def _seed(svc, user="Ana", account="Principal", broker="XP"):
    u = svc.create_user({"name": user})
    assert u["ok"], u
    a = svc.create_account({"user_id": u["user"]["id"], "name": account,
                            "broker": broker})
    assert a["ok"], a
    return u["user"]["id"], a["account"]["id"]


def _tx(svc, aid, **kw):
    body = {"account_id": aid, "ticker": "PETR4", "type": "buy",
            "quantity": 100, "price": 10.0, "fees": 0.0,
            "date": "2026-01-05"}
    body.update(kw)
    return svc.create_tx(body)


# ── 1. shorts count in the totals (B109) ─────────────────────────────────────

def test_short_counts_in_totals(svc):
    """Short 100 PETR4 @ 38,00; quote 34,20 → cost −R$ 3.800,00,
    value −R$ 3.420,00, lucro +R$ 380,00 (+10,00%) — and the totals in
    positions() must equal directory()'s (the old >=0 filter dropped the
    negative value while keeping the cost: Patrimônio R$ 0,00 / +100%)."""
    _, aid = _seed(svc)
    svc._test_quotes["PETR4"] = 34.20
    r = _tx(svc, aid, type="sell", quantity=100, price=38.0)
    assert r["ok"], r

    p = svc.positions(f"account:{aid}")
    assert p["status"] == "ok"
    row = next(x for x in p["positions"] if x["ticker"] == "PETR4")
    assert row["short"] is True
    assert row["qty"] == "-100"
    assert row["cost"] == "-R$ 3.800,00"
    assert row["value"] == "-R$ 3.420,00"
    assert row["profit"] == "+R$ 380,00"
    assert row["profit_pct"] == "+10,00%"

    # The totals signed-sum: shorts ENTER the Patrimônio (hand: −3.420).
    assert p["totals"]["cost"] == "-R$ 3.800,00"
    assert p["totals"]["value"] == "-R$ 3.420,00"
    assert p["totals"]["profit"] == "+R$ 380,00"
    assert p["kpis"][0]["label"] == "Patrimônio"
    assert p["kpis"][0]["value"] == "-R$ 3.420,00"   # NOT "R$ 0,00"

    # Parity with directory() — the B109 repro was two Lucros on one page.
    d = svc.directory()
    du = next(u for u in d["users"])
    assert du["value"] == "-R$ 3.420,00"
    assert du["profit"] == "+R$ 380,00"


# ── 2 + 3. flip fees ─────────────────────────────────────────────────────────

def test_flip_buy_fees_split(svc):
    """short 50@20 + buy 100@10 fees 10 → realizado 495 (cover realizes
    50·(20−10) − 5 fee share), PM 10,10 (the excess fee share enters the
    new long: (50·10 + 5)/50)."""
    _, aid = _seed(svc)
    assert _tx(svc, aid, type="sell", quantity=50, price=20.0)["ok"]
    assert _tx(svc, aid, quantity=100, price=10.0, fees=10.0)["ok"]

    p = svc.positions(f"account:{aid}")
    row = next(x for x in p["positions"] if x["ticker"] == "PETR4")
    assert row["short"] is False
    assert row["qty"] == "50"
    assert row["pm"] == "10,10"
    kpi_realizado = next(k for k in p["kpis"] if k["label"] == "Lucro realizado")
    assert kpi_realizado["value"] == "+R$ 495,00"


def test_flip_sell_fees_all_realized(svc):
    """long 50@10 + sell 100@20 fees 10 → realizado 490 (covered 50·(20−10)
    minus the WHOLE fee — sell fees never enter the short's entry price)
    and the short 50 opens at 20,00 (cost −R$ 1.000,00)."""
    _, aid = _seed(svc)
    assert _tx(svc, aid, quantity=50, price=10.0)["ok"]
    assert _tx(svc, aid, type="sell", quantity=100, price=20.0, fees=10.0)["ok"]

    p = svc.positions(f"account:{aid}")
    row = next(x for x in p["positions"] if x["ticker"] == "PETR4")
    assert row["short"] is True
    assert row["qty"] == "-50"
    assert row["pm"] == "20,00"
    assert row["cost"] == "-R$ 1.000,00"
    kpi_realizado = next(k for k in p["kpis"] if k["label"] == "Lucro realizado")
    assert kpi_realizado["value"] == "+R$ 490,00"


# ── 4. deterministic same-second replay (seq) ────────────────────────────────

def test_same_second_seq_order(svc):
    """buy 100@10 · sell 50@15 · buy 50@20, all the same date AND the same
    created_at second: the replay must follow INSERTION order (seq) — the
    sell realizes against PM 10 (50·5 = 250), then the PM blends to 15.
    The pre-v1.22 uuid tiebreak made this coin-flip."""
    _, aid = _seed(svc)
    assert _tx(svc, aid, quantity=100, price=10.0)["ok"]
    assert _tx(svc, aid, type="sell", quantity=50, price=15.0)["ok"]
    assert _tx(svc, aid, quantity=50, price=20.0)["ok"]

    # Force the same second on every tx (created_at has 1s resolution).
    with svc._lock:
        for t in svc._store["txs"]:
            t["created_at"] = "2026-01-05T10:00:00"

    p = svc.positions(f"account:{aid}")
    row = next(x for x in p["positions"] if x["ticker"] == "PETR4")
    assert row["qty"] == "100"
    assert row["pm"] == "15,00"
    kpi_realizado = next(k for k in p["kpis"] if k["label"] == "Lucro realizado")
    assert kpi_realizado["value"] == "+R$ 250,00"   # 50 · (15 − 10)


# ── 5. NaN / ±inf rejected at the boundary ───────────────────────────────────

@pytest.mark.parametrize("field,bad", [
    ("quantity", "nan"), ("quantity", "NaN"), ("quantity", float("nan")),
    ("quantity", "inf"), ("quantity", float("inf")),
    ("price", float("nan")), ("price", "-Infinity"),
    ("fees", float("nan")),
])
def test_nan_infinity_rejected(svc, field, bad):
    """NaN passed every range check (nan <= 0 is False), persisted as a
    bare NaN token and poisoned the whole account. Rejected at _num()."""
    _, aid = _seed(svc)
    body = {"account_id": aid, "ticker": "PETR4", "type": "buy",
            "quantity": 100, "price": 10.0, "fees": 0.0,
            "date": "2026-01-05"}
    body[field] = bad
    r = svc.create_tx(body)
    assert r["ok"] is False
    assert field in r["errors"]
    # All-or-nothing: nothing was persisted.
    assert svc._snapshot()["txs"] == []


# ── 6. corrupt store: quarantine + last-good + 503 + self-heal ───────────────

def test_corrupt_store_quarantine_and_selfheal(svc, tmp_path):
    _, aid = _seed(svc)
    assert _tx(svc, aid, quantity=100, price=10.0)["ok"]
    assert _tx(svc, aid, type="sell", quantity=10, price=11.0)["ok"]  # .bak exists
    path = tmp_path / "webui_portfolio.json"
    assert path.exists()
    assert (tmp_path / "webui_portfolio.json.bak").exists()

    # Corrupt the file on disk. (The explicit utime bumps matter: this
    # suite can write + read inside one filesystem-timestamp tick — the
    # reload is mtime-driven and on coarse-granularity filesystems the
    # ns can collide, including between the two bumps below. NTFS/real
    # disks are fine; tests must not be. Each bump is strictly bigger.)
    bumps = iter(range(1, 10))

    def _bump(p):
        os.utime(p, ns=(p.stat().st_atime_ns,
                        p.stat().st_mtime_ns + next(bumps) * 1_000_000))

    path.write_text("{ this is not json", encoding="utf-8")
    _bump(path)

    # Reads keep serving the LAST GOOD store + the degraded banner.
    st = svc.state()
    assert len(st["users"]) == 1
    assert len(svc._snapshot()["txs"]) == 2
    assert st["store_error"] and "corrompido" in st["store_error"]

    # Writes are refused with a PT-BR 503 — never a silent wipe.
    r = _tx(svc, aid, quantity=5, price=12.0)
    assert r["ok"] is False and r.get("status") == 503

    # The damaged file was quarantined, not overwritten.
    q = list(tmp_path.glob("webui_portfolio.json.corrupt-*"))
    assert len(q) == 1 and "{ this is not json" in q[0].read_text()

    # Self-heal: replace the file with valid JSON (the .bak serves) —
    # the next touch re-parses, clears the error and accepts writes.
    bak = json.loads((tmp_path / "webui_portfolio.json.bak").read_text())
    path.write_text(json.dumps(bak), encoding="utf-8")
    _bump(path)
    st = svc.state()
    assert st["store_error"] is None
    assert _tx(svc, aid, quantity=5, price=12.0)["ok"]


# ── 7. ONE ticker definition (B3SA3, BDRs, option series) ───────────────────

def test_ticker_regex(svc):
    """B3's own paper (B3SA3) and BDRs (A1MD34) pass — a digit in the
    stem is legal B3 symbology. The pattern is a STRICT SUPERSET of the
    old letters-only one (the price of B3SA3/A1MD34): option-shaped
    strings like PETRF274 also match — they never get a quote, so they
    degrade to "—" rows; no data path cares. Junk is still rejected,
    and the SERVICE normalizes case before matching."""
    from webui.validators import TICKER_RE
    for good in ("PETR4", "B3SA3", "VALE3", "BOVA11", "A1MD34", "POMO4"):
        assert TICKER_RE.match(good), good
    for bad in ("PETR", "PETR41A ", "A-BCD1", "", "PETRF27442"):
        assert not TICKER_RE.match(bad), bad

    _, aid = _seed(svc)
    assert _tx(svc, aid, ticker="B3SA3", quantity=10, price=10.0)["ok"]
    # Lowercase normalizes to the canonical form (never a distinct book).
    assert _tx(svc, aid, ticker="petr4", quantity=10, price=10.0)["ok"]
    assert svc._snapshot()["txs"][1]["ticker"] == "PETR4"
    # Option-shaped strings pass the boundary (strict superset) and
    # simply carry no quote — documented behavior, not a rejection.
    assert _tx(svc, aid, ticker="PETRF274", quantity=1, price=1.0)["ok"]
    p = svc.positions(f"account:{aid}")
    row = next(x for x in p["positions"] if x["ticker"] == "PETRF274")
    assert row["price"] is None            # no quote → "—" degradation


# ── 8. sell at R$ 0,00 refused; buy at 0 is a bonificação ────────────────────

def test_sell_zero_rejected_buy_zero_ok(svc):
    _, aid = _seed(svc)
    r = _tx(svc, aid, quantity=500, price=0.0)
    assert r["ok"], r                                  # bonificação: a BUY at 0
    # [v1.28.5] A SELL at R$ 0,00 is now legal on a zero-cost position
    # (the worthless-rights expiry — PM 0, covered qty → zero realized,
    # the position just leaves). The pre-v1.28.5 hard refusal is gone
    # for THIS case only.
    r = _tx(svc, aid, type="sell", quantity=1, price=0.0)
    assert r["ok"], r
    # …but the guard lives on where it always mattered: a zero sell
    # beyond the position (would open a short at R$ 0,00)…
    r = _tx(svc, aid, type="sell", quantity=99999, price=0.0)
    assert r["ok"] is False and "price" in r["errors"]
    assert "posição" in r["errors"]["price"].lower()
    # …and a zero sell on a COSTFUL position (the whole cost would
    # book as a phantom realized loss — [v1.22] rule, unchanged).
    r = _tx(svc, aid, quantity=100, price=10.0, date="2026-02-01")
    assert r["ok"], r
    r = _tx(svc, aid, type="sell", quantity=1, price=0.0, date="2026-02-02")
    assert r["ok"] is False and "price" in r["errors"]
    # [v1.22.3] The explanation still points to the price rule.
    assert "r$ 0,00" in r["errors"]["price"].lower()


# ── 9. cross-user move blocked (B125) ────────────────────────────────────────

def test_cross_user_move_blocked(svc):
    u1, a1 = _seed(svc)
    u2 = svc.create_user({"name": "Bruno"})
    a2 = svc.create_account({"user_id": u2["user"]["id"], "name": "Outra"})
    assert _tx(svc, a1, quantity=100, price=10.0)["ok"]
    tx_id = svc._snapshot()["txs"][0]["id"]

    r = svc.update_tx(tx_id, {"account_id": a2["account"]["id"]})
    assert r["ok"] is False
    assert "outro usuário" in r["errors"]["account_id"]

    # Same-user move is allowed.
    a3 = svc.create_account({"user_id": u1, "name": "Mesma pessoa"})
    r = svc.update_tx(tx_id, {"account_id": a3["account"]["id"]})
    assert r["ok"], r


# ── 10. mixed long+short → PM "—" ────────────────────────────────────────────

def test_mixed_long_short_pm_null(svc):
    """100 long @10 in one account + 60 short @20 in another (same user):
    the blended Σ(qty·pm)/Σqty exists in no broker — PM and Lucro % go
    null (mixed flag); value − cost still sums the per-leg profit."""
    u, _ = _seed(svc)
    a1 = svc.create_account({"user_id": u, "name": "Long"})["account"]["id"]
    a2 = svc.create_account({"user_id": u, "name": "Short"})["account"]["id"]
    assert _tx(svc, a1, quantity=100, price=10.0)["ok"]
    assert _tx(svc, a2, type="sell", quantity=60, price=20.0)["ok"]
    svc._test_quotes["PETR4"] = 34.20

    p = svc.positions("all")
    row = next(x for x in p["positions"] if x["ticker"] == "PETR4")
    assert row["mixed"] is True
    assert row["pm"] is None
    assert row["profit_pct"] is None
    assert row["qty"] == "40"
    assert row["cost"] == "-R$ 200,00"          # 100·10 − 60·20
    assert row["value"] == "R$ 1.368,00"        # 40 · 34,20
    assert row["profit"] == "+R$ 1.568,00"      # 1368 − (−200)


# ── 11. parseBr: one dot is a decimal, not a 100× error ──────────────────────

def test_parse_br_dot_decimal(svc):
    _, aid = _seed(svc)
    assert _tx(svc, aid, quantity=100, price="3.65")["ok"]
    assert svc._snapshot()["txs"][0]["price"] == pytest.approx(3.65)
    assert _tx(svc, aid, type="sell", quantity=10, price="1.234")["ok"]
    assert svc._snapshot()["txs"][1]["price"] == pytest.approx(1234.0)
    assert _tx(svc, aid, type="sell", quantity=10, price="1.234,56")["ok"]
    assert svc._snapshot()["txs"][2]["price"] == pytest.approx(1234.56)


# ── 12. edits/deletes that leave shorts open warn ────────────────────────────

def test_short_warning_on_edit_and_delete(svc):
    """The warning fires when a mutation makes a NEW transaction cross
    zero — an edit that deepens a sell into a short, or a delete that
    removes the buy behind a partial sell."""
    # EDIT: sell 50 → 150 crosses zero → warning.
    _, aid = _seed(svc)
    assert _tx(svc, aid, quantity=100, price=10.0)["ok"]
    sell = _tx(svc, aid, type="sell", quantity=50, price=20.0)
    assert sell["ok"]
    r = svc.update_tx(sell["tx"]["id"], {"quantity": 150})
    assert r["ok"] is True
    assert r.get("warnings"), "deepening the sell into a short must warn"
    assert "descoberto" in r["warnings"][0]

    # DELETE: removing the buy behind a partial sell reopens the short.
    _, aid2 = _seed(svc, account="Outra")
    buy = _tx(svc, aid2, quantity=100, price=10.0)
    assert buy["ok"]
    assert _tx(svc, aid2, type="sell", quantity=50, price=20.0)["ok"]
    r = svc.delete_tx(buy["tx"]["id"])
    assert r["ok"] is True
    assert r.get("warnings"), "deleting the buy must warn about the short"
    assert "descoberto" in r["warnings"][0]


# ── 13. a never-traded ticker no longer defeats the quote cache ──────────────

def test_missing_ticker_does_not_defeat_cache(svc):
    _, aid = _seed(svc)
    svc._test_quotes["PETR4"] = 34.20           # XYZZ4: no quote, ever
    assert _tx(svc, aid, ticker="PETR4", quantity=10, price=10.0)["ok"]
    assert _tx(svc, aid, ticker="XYZZ4", quantity=10, price=1.0)["ok"]

    svc.positions("all")                        # queries once (both tickers)
    svc.positions("all")                        # within TTL: NO re-query
    assert len(svc._test_calls) == 1, svc._test_calls
    assert set(svc._test_calls[0]) == {"PETR4", "XYZZ4"}


# ── 14. HTTP surface: 404s, CSRF, logs self-capture (B127) ───────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "webui_app_for_tests", Path(pfmod.__file__).parents[1] / "app.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_delete_not_found_is_404(client):
    """The _bad(status=) TypeError made every delete-not-found a 500."""
    r = client.delete("/api/webui/portfolio/txs/deadbeef01")
    assert r.status_code == 404
    assert r.json() == {"ok": False, "_error": "Transação não encontrada."}


def test_http_csrf_guard(client):
    B = "/api/webui/portfolio"
    # Cross-site origin → 403, PT-BR, before any handler runs.
    r = client.post(B + "/users", json={"name": "evil"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert "entre sites" in r.json()["_error"]
    # text/plain body (the CORS-simple content type that skips the
    # preflight) → rejected before parsing.
    r = client.post(B + "/users", content='{"name": "x"}',
                    headers={"Content-Type": "text/plain"})
    assert r.status_code == 400
    assert "JSON" in r.json()["_error"]
    # Same-origin JSON reaches the handler and succeeds.
    r = client.post(B + "/users", json={"name": "Legítimo"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_http_logs_do_not_capture_themselves(client):
    """B127: every drawer poll used to append 'GET /api/webui/logs → 200'
    to the log it was reading — watching the log spammed the log."""
    client.get("/api/webui/logs")
    client.get("/api/webui/logs")
    r = client.get("/api/webui/logs")
    assert r.status_code == 200
    for e in r.json()["entries"]:
        assert "GET /api/webui/logs" not in e["message"], e
