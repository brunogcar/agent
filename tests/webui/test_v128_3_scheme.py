"""tests/webui/test_v128_3_scheme.py — the v1.28.3 suite, part 2 (the
price-scheme half of the Painel settings round).

The user's list, item by item:

  1. KPIs MACRO — the Mercado families COMPLETE: the Juros "mercado"
     twins ("you didnt include some kpics with selic from mercado, they
     are slightly different" — Selic/CDI/Meta Selic mercado mês/12m read
     ddm-juros, next to the SGS annualizations) + the ANO acumulados
     ("IPCA — ano, IGP-M — ano, INPC — ano" + "Poupança — ano" — the
     year-to-date reads of ddm-inflation/ddm-poupanca). Per-KPI
     degradation names each family's sync source; the family engines
     stay LAZY (the default seven never touch them — and IPCA/IGP-M
     (mês)/(12m) still ride SGS, only the — ano cards read inflation).
  2. THE PRICE COLOR SCHEME EVERYWHERE — one shared payload
     (contract.price_pill, the Ações 22-range palette, no forked colors)
     on every surface's MAIN price: the Ações table's Última (R$) cell,
     the ⭐ observados' Preço, the carteira positions' Valor Hoje, the
     comparison's Última Cotação row and the screener's peers table.
     Min/max/PM/multiples stay plain ("just apply to main price").
  3. KPIs DE TICKERS — the card's CHART: series_52w() (the trailing
     52-week closes, window anchored on the DB's own latest refdate,
     resampled to ≤40 points with the LAST close always kept — the
     dashed reference line's anchor).
  4. CARDS DE RANKING — the STANDARDIZED row "ticker - that extra info
     - price - %": the volumes card's cotação is the row's MAIN value
     (pill and all) and the volume rides the info slot; the altas/
     baixas/BDR rows carry no extra (the NAME fills the slot
     client-side).

Run:  python -m pytest tests/webui/test_v128_3_scheme.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── fixtures (the v1.28.3 suite's shapes) ────────────────────────────────────

def _snap_fixture() -> dict:
    def sym(tk, name, close, prev, trades, bdi=2):
        return {"ticker": tk, "name": name, "bdi_code": bdi,
                "close": close, "prev_close": prev,
                "variation_pct": (close / prev - 1) * 100 if prev else None,
                "volume": 1e6, "trade_count": trades}
    return {"status": "ok", "session_date": "2026-11-24", "count": 4,
            "symbols": [
                sym("PETR4", "PETROBRAS", 40.87, 40.38, 88000),
                sym("VALE3", "VALE", 68.20, 69.10, 61000),
                sym("BOVA11", "ISHARES BOVA", 129.35, 127.80, 9000, bdi=14),
                sym("AAPL34", "APPLE BDR", 25.40, 23.90, 400, bdi=34),
            ]}


def _isolated_settings(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.home as homemod
    monkeypatch.setattr(homemod, "_quotes_for",
                        lambda s: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_range_52w",
                        lambda s: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_series_52w",
                        lambda s, max_points=40: {"status": "not_synced"})
    return homemod


# ── 1. The KPI catalog completes the Mercado families ────────────────────────

def test_mercado_juros_and_ano_kpis(tmp_path, monkeypatch):
    """The new catalog options read their OWN family engines — the Juros
    mercado twins (slightly different from the SGS reads, exactly the
    user's point) and the ano acumulados — with the families' sync
    sources named in the degraded tooltips."""
    _isolated_settings(tmp_path, monkeypatch)
    import webui.services.home as homemod
    monkeypatch.setattr(homemod, "_last",
                        lambda code: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_observations", lambda code, rows: [])
    monkeypatch.setattr(homemod, "_juros_last", lambda slug: {
        "status": "ok", "ref_date": "2026-10", "month_value": 13.65,
        "media_no_ano": 14.02, "media_12m": 13.88}[":"] if False else {
        "status": "ok", "ref_date": "2026-10",
        "month_value": {"selic": 13.65, "cdi": 13.59,
                        "meta-selic": 14.25}[slug],
        "media_no_ano": 14.02, "media_12m": 13.88})
    monkeypatch.setattr(homemod, "_infl_last", lambda slug: {
        "status": "ok", "ref_date": "2026-10", "month_value": 0.5,
        "year_acumulado": {"ipca": 3.98, "igp-m": 5.71,
                           "inpc": 4.25}[slug], "acumulado_12m": 4.4})
    monkeypatch.setattr(homemod, "_poup_last", lambda slug: {
        "status": "ok", "ref_date": "2026-10", "month_value": 0.62,
        "acumulado_no_ano": 5.5, "acumulado_12m": 7.94})

    from webui.services.settings import settings_service
    assert settings_service().update({"home.kpis": [
        "selic_mercado_mes", "selic_mercado_12m", "cdi_mercado_mes",
        "cdi_mercado_12m", "meta_selic_mercado_mes",
        "meta_selic_mercado_12m", "ipca_ano", "igpm_ano", "inpc_ano",
        "poupanca_ano"]})["ok"]

    from webui.services.home import HomeService
    kpis, _ = HomeService()._kpis()
    by_label = {k["label"]: k for k in kpis}
    # the Juros mercado twins — the DDM monthly reads
    assert by_label["Selic mercado — mês"]["value"] == "13,65%"
    assert "Mercado → Juros" in by_label["Selic mercado — mês"]["tooltip"]
    assert by_label["Selic mercado — 12m"]["value"] == "13,88%"
    assert by_label["CDI mercado — mês"]["value"] == "13,59%"
    assert by_label["Meta Selic mercado — mês"]["value"] == "14,25%"
    # the ano acumulados
    assert by_label["IPCA — ano"]["value"] == "3,98%"
    assert by_label["IGP-M — ano"]["value"] == "5,71%"
    assert by_label["INPC — ano"]["value"] == "4,25%"
    assert by_label["Poupança — ano"]["value"] == "5,50%"


def test_mercado_kpis_degrade_naming_their_source(tmp_path, monkeypatch):
    _isolated_settings(tmp_path, monkeypatch)
    import webui.services.home as homemod
    monkeypatch.setattr(homemod, "_juros_last",
                        lambda slug: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_infl_last",
                        lambda slug: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_poup_last",
                        lambda slug: {"status": "not_synced"})
    from webui.services.settings import settings_service
    assert settings_service().update({"home.kpis": [
        "selic_mercado_mes", "ipca_ano", "poupanca_ano"]})["ok"]

    from webui.services.home import HomeService
    kpis, _ = HomeService()._kpis()
    assert all(k["value"] == "-" for k in kpis)
    assert "ddm-juros" in kpis[0]["tooltip"]
    assert "ddm-inflation" in kpis[1]["tooltip"]
    assert "ddm-poupanca" in kpis[2]["tooltip"]


def test_family_reads_stay_lazy(tmp_path, monkeypatch):
    """The default seven never touch a family DB — and the (mês)/(12m)
    IPCA/IGP-M cards still ride SGS: only their — ano cards (and the
    INPC windows + the juros mercado twins) read the family engines."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_last",
                        lambda code: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_observations", lambda code, rows: [])
    calls = {"infl": 0, "poup": 0, "juros": 0}
    monkeypatch.setattr(homemod, "_infl_last",
                        lambda slug: calls.__setitem__(
                            "infl", calls["infl"] + 1) or {"status": "error"})
    monkeypatch.setattr(homemod, "_poup_last",
                        lambda slug: calls.__setitem__(
                            "poup", calls["poup"] + 1) or {"status": "error"})
    monkeypatch.setattr(homemod, "_juros_last",
                        lambda slug: calls.__setitem__(
                            "juros", calls["juros"] + 1) or {"status": "error"})

    from webui.services.settings import settings_service
    from webui.services.home import HomeService

    def _set(keys):
        assert settings_service().update({"home.kpis": keys})["ok"]
        HomeService()._kpis()

    # the default seven: nothing is read
    _set(["selic_aa", "tr", "ipca_mes", "ipca_12m", "igpm_mes",
          "igpm_12m", "usd_brl"])
    assert calls == {"infl": 0, "poup": 0, "juros": 0}
    # the SGS (mês)/(12m) cards still never read a family
    _set(["selic_aa", "cdi_aa", "meta_selic", "ipca_mes", "igpm_12m"])
    assert calls == {"infl": 0, "poup": 0, "juros": 0}
    # the — ano / mercado / INPC / Poupança cards DO
    _set(["ipca_ano"])
    assert calls["infl"] == 1 and calls["juros"] == 0
    _set(["selic_mercado_mes"])
    assert calls["juros"] == 1 and calls["infl"] == 1
    _set(["inpc_12m", "poupanca_mes"])
    assert calls["infl"] == 2 and calls["poup"] == 1


# ── 2. The price color scheme everywhere — the shared builder ───────────────

def test_price_pill_is_the_shared_palette():
    """contract.price_pill is ONE definition — the palette's own colors
    (the acoes.py import precedent, no forks), None-safe, and the SAME
    payload every surface ships (home/ações/portfolio/comparison/
    screener)."""
    from webui.adapters.contract import price_pill
    from skills._colors.price import price_range_color
    assert price_pill(129.35) == {
        "pill": "#2563eb", "text": "#fff", "range": "125 \u2264 X < 150"}
    assert price_pill(40.87)["pill"] == price_range_color(40.87)["bg"]
    assert price_pill(None) is None
    # home.py's helper is the same builder
    from webui.services.home import _price_pill
    assert _price_pill(2.44) == price_pill(2.44)


def test_acoes_table_ultima_cell_wears_the_pill(tmp_path, monkeypatch):
    """The Ações B3 table's Última (R$) cells carry the {text, price}
    shape — the generic renderer's pill branch (the faixa tooltip rides
    the cell; Negócios/Variação stay plain)."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.acoes as acoesmod
    monkeypatch.setattr(acoesmod, "_stocks", lambda: [
        {"ticker": "PETR4", "name": "PETROBRAS", "negocios": 88000,
         "last_price": 40.87, "variation": 1.21, "ref_date": "2026-11-24"},
        {"ticker": "BOVA11", "name": "ISHARES BOVA", "negocios": 9000,
         "last_price": 129.35, "variation": 1.21, "ref_date": "2026-11-24"},
    ])
    from webui.services.acoes import AcoesService
    secs = AcoesService().overview()["sections"]
    tbl = next(s for s in secs if s.get("title") == "Ações B3")
    row = tbl["rows"][0]
    cell = row[3]                                  # the Última (R$) column
    assert cell["text"] == "R$ 40,87"
    assert cell["price"]["pill"] == "#a5d6a7"      # 40 ≤ X < 50 band
    assert "Faixa de preço" in cell["tooltip"]
    # the other columns stay plain strings
    assert row[2] == "88.000" and isinstance(row[4], str)


def test_comparison_ultima_cotacao_row_pills(tmp_path, monkeypatch):
    """The comparison's Última Cotação row carries one pill per cell
    (the row IS the price row — every other metric stays plain)."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.comparison import _build_groups

    def _entry(tk, price):
        return {"ticker": tk, "val": {"price": price, "p_l": 2.6},
                "fin": {}, "div": {}, "grw": {},
                "mkt": {"price": price}, "hist_monthly": [],
                "hist_daily": [], "error": ""}
    groups = _build_groups([_entry("PETR4", 40.87), _entry("VALE3", 68.20)])
    mkt = next(g for g in groups if g["key"] == "mercado")
    cot = next(r for r in mkt["rows"] if r["label"] == "Última Cotação")
    assert cot["pills"][0]["pill"] == "#a5d6a7"     # 40 ≤ X < 50
    assert cot["pills"][1]["pill"] == "#43a047"     # 60 ≤ X < 70
    # every other row carries no pills key
    pl = next(g for g in groups if g["key"] == "valuation")
    assert all("pills" not in r for r in pl["rows"])


def test_observados_and_positions_carry_the_pill(tmp_path, monkeypatch):
    """portfolio.py ships the pill on the observados' Preço and the
    positions' Valor Hoje — the main prices only (Máx/Mín 52s and PM
    have no pill key at all)."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.portfolio as pfmod

    def fake_quotes(tickers):
        return {"status": "ok", "session_date": "2026-11-24",
                "symbols": [{"ticker": t, "name": t + " SA", "bdi_code": 2,
                             "close": 40.87, "prev_close": 40.38,
                             "variation_pct": 1.21, "volume": 1e6,
                             "trade_count": 800, "refdate": "2026-11-24"}
                            for t in tickers if t == "PETR4"]}

    monkeypatch.setattr(pfmod, "_quotes_for", fake_quotes)
    monkeypatch.setattr(pfmod, "_range_52w",
                        lambda tk: {"status": "ok",
                                    "symbols": [{"ticker": "PETR4",
                                                 "high_52": 45.0,
                                                 "low_52": 30.5}]})
    from webui.services.portfolio import PortfolioService
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    assert s.add_watch({"ticker": "PETR4"})["ok"]

    ov = s.overview()
    obs = ov["tickers"][0]
    assert obs["price_pill"]["range"] == "40 \u2264 X < 50"
    assert "price_pill" not in obs["high_52"]      # min/max stay plain

    # a position: Valor Hoje carries the pill, PM does not
    assert s.create_user({"name": "U"})["ok"]
    users = s.state()["users"]
    acc = s.create_account({"user_id": users[0]["id"],
                            "name": "A"})["account"]
    assert s.create_tx({"account_id": acc["id"], "ticker": "PETR4",
                        "type": "buy", "quantity": 100,
                        "price": 38.0, "date": "2026-01-05"})["ok"]
    pos = s.positions("account:" + acc["id"])["positions"][0]
    assert pos["price_pill"]["pill"] == "#a5d6a7"
    assert "price_pill" not in pos["pm"]


def test_screener_peers_price_pill(tmp_path, monkeypatch):
    """The screener's peers table rows carry price_pill (the Preço
    column's chip); the multiples ride as plain strings as before."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.screener import ScreenerService

    svc = ScreenerService()
    monkeypatch.setattr(svc, "_sector_companies",
                        lambda subject: ("Petróleo", [
                            {"ticker": "PETR4", "name": "PETROBRAS",
                             "is_subject": True},
                            {"ticker": "PRIO3", "name": "PRIO",
                             "is_subject": False}]))

    def fake_fetch(peers):
        return [
            {"ticker": p["ticker"],
             "val": {"price": 40.87 if p["ticker"] == "PETR4" else 44.0,
                     "p_l": 2.6},
             "fin": {}, "grw": {}, "mkt": {}, "error": ""}
            for p in peers]

    monkeypatch.setattr(svc, "_fetch_all", fake_fetch)
    payload = svc.screen("PETR4")
    assert payload["status"] == "ok", payload.get("error")
    tbl_row = next(r for r in payload["table"] if r["ticker"] == "PETR4")
    assert tbl_row["price_pill"]["range"] == "40 \u2264 X < 50"
    assert tbl_row["price"] == "R$ 40,87"


# ── 3. The ticker cards' spark (series_52w) ──────────────────────────────────

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


class TestSeries52w:
    """series_52w() — the ticker cards' chart series (and Var. (52)'s
    source in the observados table)."""

    def _seed(self, db, rows):
        """rows: (refdate, symbol, bdi, close[, market_type])"""
        import sqlite3 as s3
        conn = s3.connect(str(db))
        for r in rows:
            mt = r[4] if len(r) > 4 else 10
            conn.execute(
                "INSERT INTO cotahist (refdate, symbol, corp_name, bdi_code,"
                " market_type, close, volume, trade_count,"
                " _ingested_at) VALUES (?, ?, 'X', ?, ?, ?, 1000, 100,"
                " 'x')", (r[0], r[1], r[2], mt, r[3]))
        conn.commit()
        conn.close()

    def test_window_anchor_and_order(self, cotahist_db):
        """The window anchors on the DB's OWN latest refdate; the series
        is date-ASC and ends on the last in-window close."""
        self._seed(cotahist_db, [
            ("2025-06-10", "PETR4", 2, 99.0),     # ~17 months old — OUT
            ("2025-11-19", "PETR4", 2, 98.0),     # 1d before cutoff — OUT
            ("2026-10-15", "PETR4", 2, 31.0),
            ("2026-11-20", "PETR4", 2, 39.0),
            ("2026-11-18", "PETR4", 2, 35.0),
        ])
        from data_sources.b3.cotahist.query_engine import series_52w
        res = series_52w(["PETR4"])
        assert res["status"] == "ok"
        assert res["ref_date"] == "2026-11-20"
        assert res["window_from"] == "2025-11-20"
        row = res["symbols"][0]
        assert row["points"] == [31.0, 35.0, 39.0]   # ASC, last = latest
        assert row["last"] == 39.0

    def test_resample_caps_at_40_and_keeps_the_last(self, cotahist_db):
        """A full year of dailies (~250) resamples to ≤40 points and the
        LAST close is always kept — it is the price tag's anchor."""
        import datetime as dt
        base = dt.date(2026, 11, 20)
        rows = [((base - dt.timedelta(days=7 * i)).isoformat(),
                 "PETR4", 2, 30.0 + i) for i in range(0, 53)]  # ~1y weekly
        self._seed(cotahist_db, rows)
        from data_sources.b3.cotahist.query_engine import series_52w
        res = series_52w(["PETR4"])
        pts = res["symbols"][0]["points"]
        assert len(pts) <= 40
        assert pts[0] == 82.0            # the oldest in-window close
        assert pts[-1] == 30.0           # the latest close — always kept

    def test_universe_and_absent_symbols(self, cotahist_db):
        """Fractional duplicates stay out; share-like BDIs ride; absent
        symbols are simply missing (the caller degrades per-ticker)."""
        self._seed(cotahist_db, [
            ("2026-11-20", "PETR4", 2, 39.0),
            ("2026-11-20", "PETR4", 96, 90.0, 70),     # fractional — OUT
            ("2026-11-20", "BOVA11", 14, 129.0),       # ETF — IN
        ])
        from data_sources.b3.cotahist.query_engine import series_52w
        res = series_52w(["PETR4", "BOVA11", "ZZZZ99"])
        by_tk = {s["ticker"]: s for s in res["symbols"]}
        assert by_tk["PETR4"]["points"] == [39.0]      # not the 90.0 print
        assert by_tk["BOVA11"]["points"] == [129.0]
        assert "ZZZZ99" not in by_tk


def test_ticker_cards_carry_the_spark(tmp_path, monkeypatch):
    """_ticker_cards ships the 52-week series per card; a symbol the
    window missed renders spark-less (the middle third's empty state)."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_series_52w", lambda s, max_points=40: {
        "status": "ok",
        "symbols": [{"ticker": "BOVA11",
                     "points": [118.3, 125.0, 129.35], "last": 129.35}]})
    from webui.services.settings import settings_service
    assert settings_service().update(
        {"home.ticker_kpis": ["BOVA11", "PETR4"]})["ok"]
    from webui.services.home import HomeService
    cards = HomeService()._ticker_cards(HomeService._quotes(_snap_fixture()))
    by_tk = {c["ticker"]: c for c in cards}
    assert by_tk["BOVA11"]["spark"] == [118.3, 125.0, 129.35]
    assert by_tk["PETR4"]["spark"] is None          # not in the window


# ── 4. The standardized ranking row ─────────────────────────────────────────

def test_ranking_rows_are_standardized(tmp_path, monkeypatch):
    """\"ticker - that extra info - price - %\": the volumes card's
    COTAÇÃO is the main value (pill and all) with the volume riding the
    info slot; the altas/baixas rows carry no extra (the NAME fills the
    slot client-side); the negócios card keeps its negócios extra."""
    _isolated_settings(tmp_path, monkeypatch)
    from webui.services.home import HomeService
    rank = {c["key"]: c for c in
            HomeService()._ranking_cards(_snap_fixture())}

    # volumes: price is the MAIN value now, volume rides the extra
    vol = rank["volumes"]["items"][0]
    assert vol["value"].startswith("R$ ") and "mi" not in vol["value"] \
        or vol["value"] == "R$ 40,87"
    assert vol["price"]["range"]
    assert vol["extra"]["label"] == "volume"
    assert vol["extra"]["text"].startswith("R$")
    assert "price" not in vol["extra"]

    # negócios keeps its extra; the price is the main value with the pill
    neg = rank["negocios"]["items"][0]
    assert neg["extra"]["label"] == "negócios"
    assert neg["value"] == "R$ 40,87"
    assert neg["price"]["range"] == "40 \u2264 X < 50"

    # altas/baixas (+BDR twins): no extra — the client fills the info
    # slot with the NAME
    for key in ("altas", "baixas", "altas_bdr", "baixas_bdr"):
        for item in rank[key]["items"]:
            assert item["extra"] is None
            assert item["name"]
            assert item["price"]["range"]
