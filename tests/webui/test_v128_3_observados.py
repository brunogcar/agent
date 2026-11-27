"""tests/webui/test_v128_3_observados.py — the v1.28.3 suite, part 3
(the observados table + the ticker KPI card's banded layout).

The user's list, item by item:

  1. ⭐ TICKERS OBSERVADOS — the completed row: Ticker · Nome · Setor
     (the cadastro's CVM/FCA sector) · Preço · Mín (dia) · Máx (dia) ·
     Var. (dia) · Mín (52) · Máx (52) · Var. (52). The day's Mín/Máx
     ride the quote's OWN session high/low (quotes_for() ships
     day_high/day_low); the 52-week pair reads min-first in
     parentheses; Var. (52) is the 52-week CLOSE series' first-vs-last
     variation (series_52w() — the same window the range reads).
  2. 📊 KPIs DE TICKERS — the card reads in THREE HORIZONTAL BANDS
     (the user's mockup): the header (identity left, price pill + day
     % right), the FULL-WIDTH 52-week chart with the value's dashed
     reference line + the 52-week position bar under it, then the
     stats rows (Mín 52 sem, Máx 52 sem, Volume (dia)) label-left /
     value-right. No price TEXT on the chart — the line marks it.
  3. 🃏 CARDS DE RANKING — the standardized row keeps its BALANCED
     grid (a widened info slot read as an awkward gap between the info
     and the price) and the extra tooltip reads EXACTLY
     "label — value" ("the tooltip should be Volume - Value" — no
     company name).

Run:  python -m pytest tests/webui/test_v128_3_observados.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Import query_engine AT COLLECTION TIME, before any fixture patches
# catalog.connect: query_engine binds `connect` at ITS import, so a
# first import inside a fixture-patched test would freeze that test's
# mock_connect (a closure over ONE tmp db) into the module forever —
# every later test would silently read the first test's database.
# (test_v128_3_scheme.py dodges this by accident: home.py imports query_engine
# long before TestSeries52w runs.)
from data_sources.b3.cotahist.query_engine import quotes_for  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]


# ── fixtures (the v1.28.3 suite's shapes) ────────────────────────────────────

@pytest.fixture
def cotahist_db(tmp_path, monkeypatch):
    """A synthetic cotahist.db (the v1.28.3 suite's fixture pattern)."""
    import sqlite3
    from data_sources.b3.cotahist.catalog import SCHEMA_SQL
    db_path = tmp_path / "cotahist.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL.replace(
        "DROP TABLE IF EXISTS cotahist;\n", ""))
    conn.commit()
    conn.close()

    def mock_db_path():
        return db_path

    def mock_connect(read_only=True):
        c = sqlite3.connect(
            f"file:{db_path}?mode=ro" if read_only else str(db_path),
            uri=read_only)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(
        "data_sources.b3.cotahist.catalog.db_path", mock_db_path)
    monkeypatch.setattr(
        "data_sources.b3.cotahist.catalog.connect", mock_connect)
    return db_path


def _seed(db, rows):
    """rows: (refdate, symbol, bdi, close, high, low[, market_type])."""
    import sqlite3 as s3
    conn = s3.connect(str(db))
    for r in rows:
        mt = r[6] if len(r) > 6 else 10
        conn.execute(
            "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
            " market_type, close, high, low, volume, trade_count,"
            " _ingested_at) VALUES (?, ?, 'X', ?, ?, ?, ?, ?, 1000, 100,"
            " 'x')", (r[0], r[1], r[2], mt, r[3], r[4], r[5]))
    conn.commit()
    conn.close()


# ── 1. quotes_for() ships the session high/low ───────────────────────────────

class TestQuotesDayRange:
    """The ⭐ observados' Mín/Máx (dia) columns — the quote's OWN
    last-session high/low, riding the same quotes_for() row the
    valuation has always read."""

    def test_day_high_low_ride_the_quote(self, cotahist_db):
        _seed(cotahist_db, [
            ("2026-11-19", "PETR4", 2, 40.38, 40.50, 40.10),
            ("2026-11-20", "PETR4", 2, 39.00, 40.20, 38.10),
        ])
        res = quotes_for(["PETR4"])
        assert res["status"] == "ok"
        row = res["symbols"][0]
        assert row["close"] == 39.00
        assert row["day_high"] == 40.20          # the OWN session's high
        assert row["day_low"] == 38.10           # the OWN session's low
        # the prev-close join still anchors the variation (regression:
        # the SELECT grew two columns, the join must not have moved)
        assert row["prev_close"] == 40.38
        assert round(row["variation_pct"], 2) == round(
            (39.00 / 40.38 - 1) * 100, 2)

    def test_null_high_low_degrades_to_none(self, cotahist_db):
        """The fixture shape (no high/low columns filled) — None, and
        the client renders "—" (never a fake 0.0)."""
        _seed(cotahist_db, [
            ("2026-11-19", "PETR4", 2, 40.38, None, None),
            ("2026-11-20", "PETR4", 2, 39.00, None, None),
        ])
        row = quotes_for(["PETR4"])["symbols"][0]
        assert row["day_high"] is None
        assert row["day_low"] is None

    def test_share_like_universe_unchanged(self, cotahist_db):
        """The day range rides every share-like quote (ETF/FII/BDR
        included) and the fractional market stays out — the day-range
        columns must not have rescoped the universe."""
        _seed(cotahist_db, [
            ("2026-11-20", "PETR4", 2, 39.00, 40.20, 38.10),
            ("2026-11-20", "BOVA11", 14, 129.00, 130.00, 128.00),
            ("2026-11-20", "AAPL34", 34, 25.40, 25.60, 25.30),
            ("2026-11-20", "PETR4", 96, 90.00, 91.00, 89.00, 70),
        ])
        by_tk = {s["ticker"]: s for s in
                 quotes_for(["PETR4", "BOVA11", "AAPL34"])["symbols"]}
        assert by_tk["PETR4"]["day_high"] == 40.20     # not the 91.00 print
        assert by_tk["BOVA11"]["day_high"] == 130.00
        assert by_tk["AAPL34"]["day_low"] == 25.30


# ── 2. The ⭐ observados row: setor + Mín/Máx (dia) + Mín-first 52s ───────────

def test_observados_row_carries_setor_and_day_range(tmp_path, monkeypatch):
    """portfolio.overview()'s tickers rows ship the FULL read — sector
    (the cadastro's CVM cache), the day's low/high, the 52-week pair
    closed by Var. (52) (the series' first-vs-last) — and the pill
    stays on the Preço only."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.portfolio as pfmod

    def fake_quotes(tickers):
        return {"status": "ok", "session_date": "2026-11-24",
                "symbols": [{"ticker": t, "name": t + " SA", "bdi_code": 2,
                             "close": 40.87, "prev_close": 40.38,
                             "variation_pct": 1.21, "volume": 1e6,
                             "trade_count": 800, "refdate": "2026-11-24",
                             "day_high": 41.20, "day_low": 40.05}
                            for t in tickers if t == "PETR4"]}

    monkeypatch.setattr(pfmod, "_quotes_for", fake_quotes)
    monkeypatch.setattr(pfmod, "_range_52w",
                        lambda tk: {"status": "ok",
                                    "symbols": [{"ticker": "PETR4",
                                                 "high_52": 45.0,
                                                 "low_52": 30.5}]})
    # the 52-week CLOSE series — first point ~52 weeks ago (30.00),
    # last = the quoted price (40.87): Var. (52) = +36,23%.
    monkeypatch.setattr(pfmod, "_series_52w",
                        lambda tk: {"status": "ok",
                                    "symbols": [{"ticker": "PETR4",
                                                 "points": [30.00, 33.20,
                                                            38.45, 40.87]}]})
    from webui.services.portfolio import PortfolioService
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    assert s.add_watch({"ticker": "PETR4"})["ok"]

    # the cadastro's cached meta — the sector the row must now ship
    with s._lock:
        s._store["tickers"]["PETR4"] = {
            "name": "PETROBRAS PN", "sector": "Petróleo, Gás e Biocombustíveis",
            "updated_at": "2026-11-24T10:00:00"}

    obs = s.overview()["tickers"][0]
    assert obs["sector"] == "Petróleo, Gás e Biocombustíveis"
    assert obs["low_day"] == "R$ 40,05"          # the day's Mín
    assert obs["high_day"] == "R$ 41,20"         # the day's Máx
    assert obs["low_52"] == "R$ 30,50"           # 52s: Mín rides too
    assert obs["high_52"] == "R$ 45,00"
    # Var. (52) — the series' first close vs the last
    assert obs["var_52"] == "+36,23%"
    # the pill stays on the MAIN price only
    assert obs["price_pill"]["range"] == "40 \u2264 X < 50"
    for plain in ("low_day", "high_day", "low_52", "high_52"):
        assert isinstance(obs[plain], str)       # plain strings, no pill


def test_observados_sector_degrades_to_none(tmp_path, monkeypatch):
    """No cadastro meta yet (the background FCA fetch hasn't landed) —
    sector is None → the client renders "—", the row never breaks."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.portfolio as pfmod
    monkeypatch.setattr(pfmod, "_quotes_for",
                        lambda tk: {"status": "ok", "session_date": "x",
                                    "symbols": []})
    monkeypatch.setattr(pfmod, "_range_52w",
                        lambda tk: {"status": "ok", "symbols": []})
    monkeypatch.setattr(pfmod, "_series_52w",
                        lambda tk: {"status": "ok", "symbols": []})
    from webui.services.portfolio import PortfolioService
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    assert s.add_watch({"ticker": "VALE3"})["ok"]
    obs = s.overview()["tickers"][0]
    assert obs["sector"] is None
    assert obs["low_day"] is None and obs["high_day"] is None
    assert obs["var_52"] is None                 # no series → "—"


# ── 3. The layout pins (the user's explicit asks, in the stylesheet) ─────────

def test_ticker_card_reads_in_three_bands():
    """The card reads in THREE HORIZONTAL BANDS (top → bottom), per the
    user's mockup: .home-tk-stack is a vertical flex column; the head
    is a space-between row (identity left, quote right); the chart
    spans the FULL width with the value's dashed reference line
    (.home-tk-spark-ref) and the position bar under it; the stats rows
    are label-left/value-right (space-between). The old side-by-side
    thirds and the price TAG on the chart are gone — "the chart has a
    line in the value instead of displaying the value over the
    chart"."""
    css = (_REPO / "webui" / "static" / "css" / "app.css").read_text(
        encoding="utf-8")

    m = re.search(r"\.home-tk-stack\s*\{[^}]*\}", css)
    assert m, ".home-tk-stack rule missing"
    assert "flex-direction: column" in m.group(0)

    head = re.search(r"\.home-tk-head\s*\{[^}]*\}", css)
    assert head, ".home-tk-head rule missing"
    assert "justify-content: space-between" in head.group(0)

    meta_row = re.search(r"\.home-tk-meta-row\s*\{[^}]*\}", css)
    assert meta_row, ".home-tk-meta-row rule missing"
    assert "justify-content: space-between" in meta_row.group(0)

    # the value's dashed reference line + the position bar stay
    assert re.search(r"\.home-tk-spark-ref\s*\{[^}]*\}", css)
    assert "stroke-dasharray" in re.search(
        r"\.home-tk-spark-ref\s*\{[^}]*\}", css).group(0)
    assert re.search(r"\.home-tk-bar\s*\{", css)

    # the side-by-side thirds and the price tag on the chart are GONE
    assert ".home-tk-3col" not in css
    assert ".home-tk-tag" not in css
    assert ".home-tk-col" not in css

    # the renderer builds the same bands, and NO price text rides the
    # chart (the line marks the value)
    js = (_REPO / "webui" / "static" / "js" / "app.js").read_text(
        encoding="utf-8")
    assert "home-tk-stack" in js
    assert "home-tk-head" in js
    assert "home-tk-chart" in js
    assert "home-tk-spark-ref" in js
    assert "home-tk-tag" not in js


def test_ranking_row_grid_keeps_its_balance():
    """The standardized row's grid stays BALANCED — the earlier widened
    info slot (50px·1fr·92px·58px + 12px padding) read as an awkward
    gap between the info and the price column, so the proportions are
    the balanced 56px·1fr·84px·64px with the 16px row padding back."""
    css = (_REPO / "webui" / "static" / "css" / "app.css").read_text(
        encoding="utf-8")
    m = re.search(r"\.ticker-row\s*\{[^}]*\}", css)
    assert m, ".ticker-row rule missing"
    block = m.group(0)
    assert "grid-template-columns: 56px minmax(0, 1fr) 84px 64px" in block
    assert "padding: 7px var(--space-4)" in block
    assert "92px" not in block and "50px" not in block


def test_ranking_tooltip_carries_the_value():
    """"the tooltip should be Volume - Value" — EXACTLY label — value,
    no company name ("i didnt say Volume - value - Company"). Pinned
    against the renderer's source, the same way the layout pins read
    the stylesheet."""
    js = (_REPO / "webui" / "static" / "js" / "app.js").read_text(
        encoding="utf-8")
    m = re.search(
        r"var infoTip = item\.extra\s*\n?\s*\?\s*\(valEsc\(item\.extra\.label"
        r" \|\| ''\) \+ ' — ' \+ valEsc\(item\.extra\.text \|\| ''\)\)\s*\n?\s*"
        r": valEsc\(item\.name\)", js)
    assert m, "the extra tooltip must read exactly: label — value"
    # and the name must NOT ride the extra's tooltip
    tip_block = m.group(0)
    assert "item.name" not in tip_block.replace(": valEsc(item.name)", "")
