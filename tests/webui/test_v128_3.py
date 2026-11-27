"""tests/webui/test_v128_3.py — the v1.28.3 suite (the Painel settings round).

The user's list, item by item:

  1. TICKER KPI CARDS — home.ticker_kpis drives the cards (arrange/add/
     remove via the ⚙️ box); ANY share-like instrument now ("make it
     support BDR and normal tickers as well" — Ação/FII/ETF/BDR badges);
     the quotes_for() fallback fills symbols the snapshot window missed;
     the 52-week range rides every card; per-card degradation.
  2. RANKING CARDS — "Maiores Quedas BDR" (the losers twin of v1.28.1's
     gainers card, same liquidity gate, right after Maiores Altas BDR);
     home.cards selects WHICH boxes show and in what ORDER (unknown keys
     dropped); card_catalog rides the payload (the manage box's list).
  3. TICKERS OBSERVADOS — overview() watchlist rows carry high_52/low_52
     (PT-BR BRL), degrading per-ticker ("add more info like max and min
     52 weeks").
  4. SETTINGS — the two new list settings coerce (comma string → list,
     dedup, 40-item cap) with the schema defaults the Painel expects;
     the HomeService memo key busts when they change.

The same round's review pass — the THREE separate sets + the price
color scheme:
  5. KPIs MACRO — home.kpis drives the FIRST set (order preserved,
     unknown keys dropped, the 13-key catalog with the Mercado families'
     options rides the payload); per-KPI degradation (a down SGS renders
     '-' but never hides the INPC/Poupança cards); the family engines
     are read ONLY when one of their KPIs is enabled.
  6. THE PRICE PILL — every price on the Painel (ticker cards + ranking
     rows) carries the Ações 22-range palette {pill, text, range}; the
     volumes card's main value is a financial volume (no pill) — its
     cotação extra carries it; the ticker cards' pos_52 math + volume.

Run:  python -m pytest tests/webui/test_v128_3.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── fixtures ─────────────────────────────────────────────────────────────────

def _snap_fixture() -> dict:
    """The market snapshot: 3 ETFs, 2 BDRs (one up, one down), a native
    and a FII — every instrument kind a ticker KPI card can badge."""
    def sym(tk, name, close, prev, trades, bdi=2):
        return {"ticker": tk, "name": name, "bdi_code": bdi,
                "close": close, "prev_close": prev,
                "variation_pct": (close / prev - 1) * 100 if prev else None,
                "volume": 1e6, "trade_count": trades}
    return {"status": "ok", "session_date": "2026-11-24", "count": 7,
            "symbols": [
                sym("BOVA11", "ISHARES BOVA", 129.35, 127.80, 9000, bdi=14),
                sym("SMAL11", "ISHARES SMAL", 122.10, 124.00, 4500, bdi=14),
                sym("IVVB11", "ISHARES S&P 500", 345.60, 343.10, 3200, bdi=14),
                sym("AAPL34", "APPLE BDR", 25.40, 23.90, 400, bdi=34),   # +6,27%
                sym("MSBR34", "MSFT-WTF BDR", 8.10, 8.40, 400, bdi=34),  # -3,57%
                sym("PETR4", "PETROBRAS", 40.87, 40.38, 88000),          # a native
                sym("HGBS11", "CSHG BOX FII", 102.30, 101.80, 700, bdi=12),
            ]}


def _isolated_settings(tmp_path, monkeypatch):
    """A fresh settings store (no file → schema defaults) + cotahist
    engine calls stubbed so no real DB is ever touched."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.home as homemod
    monkeypatch.setattr(homemod, "_quotes_for",
                        lambda s: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_range_52w",
                        lambda s: {"status": "not_synced"})
    return homemod


def _fake_quotes_for(syms):
    """The per-symbol fallback — POMO4 is the paper the snapshot window
    missed (illiquid, silent 10+ sessions)."""
    rows = {"POMO4": {"ticker": "POMO4", "name": "MARCOPOLO", "bdi_code": 2,
                      "close": 2.44, "prev_close": 2.40,
                      "variation_pct": 1.67, "volume": 1e5,
                      "trade_count": 340}}
    return {"status": "ok", "session_date": "2026-11-24",
            "symbols": [rows[s] for s in syms if s in rows]}


def _fake_range_52w(syms):
    rows = {"BOVA11": {"ticker": "BOVA11", "high_52": 140.10, "low_52": 118.30},
            "POMO4": {"ticker": "POMO4", "high_52": 3.10, "low_52": 2.20}}
    return {"status": "ok", "symbols": [rows[s] for s in syms if s in rows]}


# ── 1. The ticker KPI cards ──────────────────────────────────────────────────

def test_ticker_kpis_setting_drives_the_cards(tmp_path, monkeypatch):
    """home.ticker_kpis owns the row: ANY share-like instrument, order
    preserved, typos/lowercase/dupes cleaned at read."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    from webui.services.settings import settings_service
    res = settings_service().update({"home.ticker_kpis":
                                     ["petr4", "AAPL34", "HGBS11", "BOVA11",
                                      "PETR4", "bad!!"]})
    assert res["ok"], res.get("errors")

    from webui.services.home import HomeService
    cards = HomeService()._ticker_cards(HomeService._quotes(_snap_fixture()))
    # lowercase normalized, dupe dropped, the invalid shape dropped
    assert [c["ticker"] for c in cards] == ["PETR4", "AAPL34", "HGBS11", "BOVA11"]
    # the instrument badge — a normal stock, a BDR, a FII, an ETF
    assert [c["kind"] for c in cards] == ["Ação", "BDR", "FII", "ETF"]
    assert cards[0]["value"] == "R$ 40,87"
    assert cards[1]["variation"].startswith("+")     # AAPL34 rose
    assert cards[3]["variation"].startswith("+")     # BOVA11 rose


def test_quotes_for_fallback_fills_the_snapshot_gaps(tmp_path, monkeypatch):
    """A symbol the snapshot window missed (10+ sessions silent) still
    gets its LAST TRADED price via quotes_for()."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_quotes_for", _fake_quotes_for)
    from webui.services.settings import settings_service
    assert settings_service().update({"home.ticker_kpis": ["POMO4", "BOVA11"]})["ok"]

    from webui.services.home import HomeService
    cards = HomeService()._ticker_cards(HomeService._quotes(_snap_fixture()))
    by_tk = {c["ticker"]: c for c in cards}
    # POMO4 came from the fallback (not in the snapshot)
    assert by_tk["POMO4"]["value"] == "R$ 2,44"
    assert by_tk["POMO4"]["name"] == "MARCOPOLO"
    assert by_tk["POMO4"]["kind"] == "Ação"
    # BOVA11 from the snapshot, unchanged
    assert by_tk["BOVA11"]["value"] == "R$ 129,35"


def test_ticker_cards_carry_the_52_week_range(tmp_path, monkeypatch):
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_range_52w", _fake_range_52w)
    from webui.services.settings import settings_service
    assert settings_service().update({"home.ticker_kpis": ["BOVA11", "SMAL11"]})["ok"]

    from webui.services.home import HomeService
    cards = HomeService()._ticker_cards(HomeService._quotes(_snap_fixture()))
    by_tk = {c["ticker"]: c for c in cards}
    assert by_tk["BOVA11"]["high_52"] == "R$ 140,10"
    assert by_tk["BOVA11"]["low_52"] == "R$ 118,30"
    # a symbol absent from the 52w window degrades to None ("—")
    assert by_tk["SMAL11"]["high_52"] is None
    assert by_tk["SMAL11"]["low_52"] is None


# ── 2. The ranking cards ─────────────────────────────────────────────────────

def test_baixas_bdr_is_the_losers_twin():
    from webui.services.home import HomeService
    cards = HomeService()._ranking_cards(_snap_fixture())
    losers = next(c for c in cards if c["key"] == "baixas_bdr")
    assert losers["title"] == "Maiores Quedas BDR"
    # ascending variation — the falling BDR leads; the tail is the same
    # top-N-of-the-universe semantics the v1.28.1 gainers card uses
    assert [i["ticker"] for i in losers["items"]] == ["MSBR34", "AAPL34"]
    assert losers["items"][0]["variation"].startswith("-")
    # the liquidity gate applies to the losers card too
    snap = _snap_fixture()
    for s in snap["symbols"]:
        if s["bdi_code"] in (34, 35, 36):
            s["trade_count"] = 3
    dead = HomeService()._ranking_cards(snap)
    assert next(c for c in dead if c["key"] == "baixas_bdr")["items"] == []


def test_cards_setting_selects_and_orders(tmp_path, monkeypatch):
    """home.cards picks WHICH boxes render and in WHAT order — unknown
    keys drop at read; the catalog (all 8) always rides the payload."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_market_snapshot", _snap_fixture)
    monkeypatch.setattr(homemod, "_query_index",
                        lambda code: {"status": "error"})   # ibov degrades
    from webui.services.settings import settings_service
    res = settings_service().update({"home.cards": ["baixas_bdr", "ibov", "nope"]})
    assert res["ok"], res.get("errors")

    from webui.services.home import HomeService
    svc = HomeService()
    svc._kpis = lambda: ([], None)          # no SGS reads in this test
    payload = svc._compute()
    assert [c["key"] for c in payload["cards"]] == ["baixas_bdr", "ibov"]
    assert payload["cards"][0]["title"] == "Maiores Quedas BDR"
    # the degraded ibov card still renders (its own error message)
    assert payload["cards"][1]["error"]
    # the catalog — all 8, canonical order, for the ⚙️ box
    assert [c["key"] for c in payload["card_catalog"]] == [
        "ibov", "smll", "negocios", "volumes", "altas", "baixas",
        "altas_bdr", "baixas_bdr"]
    assert "etfs" not in payload          # the v1.28.1 row key is gone


def test_empty_cards_setting_renders_no_boxes(tmp_path, monkeypatch):
    """An explicitly empty home.cards is the user's choice — only the
    ticker KPI cards remain on the grid."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_market_snapshot", _snap_fixture)
    from webui.services.settings import settings_service
    assert settings_service().update({"home.cards": []})["ok"]

    from webui.services.home import HomeService
    svc = HomeService()
    svc._kpis = lambda: ([], None)
    payload = svc._compute()
    assert payload["cards"] == []
    assert len(payload["ticker_cards"]) == 3        # the default trio


def test_overview_memo_busts_on_a_settings_change(tmp_path, monkeypatch):
    """The 60s payload memo keys on kpis + ticker_kpis + cards — a save in
    the ⚙️ box is visible on the NEXT overview() call, not after the TTL."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_market_snapshot", _snap_fixture)
    monkeypatch.setattr(homemod, "_query_index",
                        lambda code: {"status": "error"})
    from webui.services.settings import settings_service

    from webui.services.home import HomeService
    svc = HomeService()
    svc._kpis = lambda: ([], None)
    first = svc.overview()
    assert len(first["cards"]) == 8                 # the schema default

    assert settings_service().update({"home.cards": ["baixas"],
                                      "home.ticker_kpis": ["PETR4"]})["ok"]
    second = svc.overview()
    assert [c["key"] for c in second["cards"]] == ["baixas"]
    assert [c["ticker"] for c in second["ticker_cards"]] == ["PETR4"]

    # a home.kpis save busts the memo too (the ⚙️ 📈 list)
    assert settings_service().update({"home.kpis": ["usd_brl"]})["ok"]
    third = svc.overview()
    assert third is not second      # recomputed, not the cached object


# ── 3. Tickers Observados — the 52-week columns ─────────────────────────────

def test_overview_watchlist_carries_the_52_week_range(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.portfolio as pfmod

    def fake_quotes(tickers):
        return {"status": "ok", "session_date": "2026-11-24",
                "symbols": [{"ticker": t, "name": t + " SA", "bdi_code": 2,
                             "close": 40.87, "prev_close": 40.38,
                             "variation_pct": 1.21, "volume": 1e6,
                             "trade_count": 800}
                            for t in tickers if t == "PETR4"]}

    def fake_range(tickers):
        return {"status": "ok",
                "symbols": [{"ticker": "PETR4", "high_52": 45.00,
                             "low_52": 30.50}]}

    monkeypatch.setattr(pfmod, "_quotes_for", fake_quotes)
    monkeypatch.setattr(pfmod, "_range_52w", fake_range)

    from webui.services.portfolio import PortfolioService
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    assert s.add_watch({"ticker": "PETR4"})["ok"]
    assert s.add_watch({"ticker": "VALE3"})["ok"]     # absent from the range

    ov = s.overview()
    assert ov["has_data"] and ov["tickers"]
    by_tk = {t["ticker"]: t for t in ov["tickers"]}
    assert by_tk["PETR4"]["high_52"] == "R$ 45,00"
    assert by_tk["PETR4"]["low_52"] == "R$ 30,50"
    # _px: adaptive decimals, no "R$" (the carteira table convention)
    assert by_tk["PETR4"]["price"] == "40,87"
    # a symbol the 52w window never saw degrades per-ticker
    assert by_tk["VALE3"]["high_52"] is None
    assert by_tk["VALE3"]["low_52"] is None


# ── 4. The settings layer ────────────────────────────────────────────────────

@pytest.fixture()
def memory_root(tmp_path, monkeypatch):
    """Isolated root (no synced DBs — every section degrades alone)."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    return tmp_path


@pytest.fixture()
def client(memory_root):
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_schema_carries_the_painel_settings():
    from webui.services.settings import SCHEMA
    by_key = {s["key"]: s for s in SCHEMA}
    assert by_key["home.ticker_kpis"]["default"] == ["BOVA11", "SMAL11", "IVVB11"]
    assert by_key["home.cards"]["default"] == [
        "ibov", "smll", "negocios", "volumes", "altas", "baixas",
        "altas_bdr", "baixas_bdr"]
    assert by_key["home.ticker_kpis"]["type"] == "list"
    assert by_key["home.cards"]["type"] == "list"
    # [v1.28.3] home.kpis — the macro row, default = the v1.21 seven
    assert by_key["home.kpis"]["type"] == "list"
    assert by_key["home.kpis"]["default"] == [
        "selic_aa", "tr", "ipca_mes", "ipca_12m", "igpm_mes", "igpm_12m",
        "usd_brl"]


def test_list_settings_coerce_strings_lists_and_caps(tmp_path, monkeypatch):
    """The list type accepts the ⚙️ box's real list OR the settings page's
    comma/space string; dedupes, caps at 40, keeps order."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.settings import settings_service
    res = settings_service().update({"home.ticker_kpis": "BOVA11, SMAL11 PETR4"})
    assert res["ok"], res.get("errors")
    assert res["values"]["home.ticker_kpis"] == ["BOVA11", "SMAL11", "PETR4"]
    # dedup on a real list
    res = settings_service().update({"home.cards": ["baixas", "baixas", "altas"]})
    assert res["values"]["home.cards"] == ["baixas", "altas"]
    # the 40-item cap
    res = settings_service().update({"home.ticker_kpis":
                                     [f"T{i:03d}4" for i in range(45)]})
    assert not res["ok"]
    assert "40" in res["errors"]["home.ticker_kpis"]


def test_the_painel_page_renders_the_manage_button(client):
    """dashboard.html carries the ⚙️ top-right button + the modal shell +
    the THREE separate sets' slots (macro KPIs / tickers / rankings)."""
    r = client.get("/webui")
    assert r.status_code == 200
    html = r.text
    assert 'id="home-manage-btn"' in html
    assert 'id="home-manage-modal"' in html
    assert "home-head-row" in html
    # [v1.28.3] the three sets — separate slots, own grids
    assert 'id="home-kpis"' in html
    assert 'id="home-tickers"' in html
    assert 'id="home-cards"' in html
    assert "home-tk-grid" in html


# ── 5. [v1.28.3] KPIs macro — the managed FIRST set ────────────────────

def test_kpis_setting_selects_and_orders(tmp_path, monkeypatch):
    """home.kpis owns the macro KPI row: order preserved, unknown keys
    dropped, the 13-key catalog rides the payload; the schema default
    is the v1.21 seven (the page opens exactly as it did)."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_last",
                        lambda code: {"status": "ok", "value": 0.05,
                                      "ref_date": "2026-11-24"})
    monkeypatch.setattr(homemod, "_observations",
                        lambda code, rows: [{"ref_date": "2026-10-31",
                                             "value": 0.5}])
    monkeypatch.setattr(homemod, "_rolling_12m",
                        lambda obs: [{"acum_12m": 4.5}])
    monkeypatch.setattr(homemod, "_infl_last", lambda slug: {
        "status": "ok", "ref_date": "2026-10", "month_value": 0.4,
        "year_acumulado": 3.2, "acumulado_12m": 3.9})
    from webui.services.settings import settings_service
    res = settings_service().update(
        {"home.kpis": ["usd_brl", "inpc_12m", "nope", "selic_aa"]})
    assert res["ok"], res.get("errors")

    from webui.services.home import HomeService
    kpis, note = HomeService()._kpis()
    # order preserved; the unknown key dropped
    assert [k["label"] for k in kpis] == [
        "USD/BRL (ptax)", "INPC (12m)", "Selic (a.a.)"]
    assert note is None
    # the INPC option reads the ddm-inflation engine (the Mercado family)
    assert kpis[1]["value"] == "3,90%"

    # the schema default = the v1.21 seven (the page opens as it did)
    from webui.services.settings import SCHEMA
    by_key = {s["key"]: s for s in SCHEMA}
    assert by_key["home.kpis"]["default"] == [
        "selic_aa", "tr", "ipca_mes", "ipca_12m", "igpm_mes", "igpm_12m",
        "usd_brl"]
    assert settings_service().update(
        {"home.kpis": by_key["home.kpis"]["default"]})["ok"]
    from webui.services.home import _kpis_setting
    assert _kpis_setting() == ["selic_aa", "tr", "ipca_mes", "ipca_12m",
                               "igpm_mes", "igpm_12m", "usd_brl"]

    # the catalog rides the payload — [v1.28.3] all 23, canonical
    # order (the families complete: the juros mercado twins + the ano
    # acumulados join their SGS/monthly siblings)
    monkeypatch.setattr(homemod, "_market_snapshot", _snap_fixture)
    monkeypatch.setattr(homemod, "_query_index",
                        lambda code: {"status": "error"})
    svc = HomeService()
    svc._kpis = lambda: ([], None)
    payload = svc._compute()
    assert [c["key"] for c in payload["kpi_catalog"]] == [
        "selic_aa", "selic_mercado_mes", "selic_mercado_12m",
        "cdi_aa", "cdi_mercado_mes", "cdi_mercado_12m",
        "meta_selic", "meta_selic_mercado_mes", "meta_selic_mercado_12m",
        "tr", "ipca_mes", "ipca_ano", "ipca_12m",
        "igpm_mes", "igpm_ano", "igpm_12m",
        "inpc_mes", "inpc_ano", "inpc_12m",
        "poupanca_mes", "poupanca_ano", "poupanca_12m",
        "usd_brl"]
    assert payload["kpi_catalog"][1]["title"] == "Selic mercado — mês"
    assert payload["kpi_catalog"][11]["title"] == "IPCA — ano"
    assert payload["kpi_catalog"][20]["title"] == "Poupança — ano"


def test_kpi_degradation_is_per_kpi_and_families_lazy(tmp_path, monkeypatch):
    """A down SGS renders '-' cards + the note but never hides the
    INPC/Poupança cards (per-KPI degradation — a down source can't wipe
    the row); a down family degrades ITS card naming its source; the
    family engines are read ONLY when one of their KPIs is enabled."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_last",
                        lambda code: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_observations", lambda code, rows: [])
    calls = {"infl": 0, "poup": 0}

    def fake_infl(slug):
        calls["infl"] += 1
        return {"status": "not_synced"}

    def fake_poup(slug):
        calls["poup"] += 1
        return {"status": "ok", "ref_date": "2026-10", "month_value": 0.62,
                "acumulado_no_ano": 5.5, "acumulado_12m": 7.94}

    monkeypatch.setattr(homemod, "_infl_last", fake_infl)
    monkeypatch.setattr(homemod, "_poup_last", fake_poup)
    from webui.services.settings import settings_service
    assert settings_service().update(
        {"home.kpis": ["selic_aa", "inpc_mes", "poupanca_12m"]})["ok"]

    from webui.services.home import HomeService
    kpis, note = HomeService()._kpis()
    by_label = {k["label"]: k for k in kpis}
    # SGS down → the card degrades to '-' + the visible note (v1.19 role)
    assert by_label["Selic (a.a.)"]["value"] == "-"
    assert note and "sgs" in note
    # the family KPIs LIVE — their sources aren't SGS
    assert by_label["Poupança (12m)"]["value"] == "7,94%"
    # a down family degrades per-card, naming its sync source
    assert by_label["INPC (mês)"]["value"] == "-"
    assert "ddm-inflation" in by_label["INPC (mês)"]["tooltip"]

    # LAZY: the default seven never read the family engines
    assert settings_service().update(
        {"home.kpis": ["selic_aa", "tr", "ipca_mes", "ipca_12m",
                       "igpm_mes", "igpm_12m", "usd_brl"]})["ok"]
    HomeService()._kpis()
    assert calls["infl"] == 1 and calls["poup"] == 1   # unchanged


# ── 6. [v1.28.3] The price color scheme — the Ações palette pill ──────

def test_price_pills_wear_the_acoes_palette(tmp_path, monkeypatch):
    """Every PRICE on the Painel carries the Ações 22-range palette
    fields {pill, text, range} — the ticker cards' main price and every
    ranking row's value; the volumes card's main value is a financial
    VOLUME (no pill) — its cotação extra carries it."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    from webui.services.settings import settings_service
    assert settings_service().update(
        {"home.ticker_kpis": ["BOVA11", "PETR4"]})["ok"]

    from webui.services.home import HomeService
    svc = HomeService()

    cards = svc._ticker_cards(HomeService._quotes(_snap_fixture()))
    by_tk = {c["ticker"]: c for c in cards}
    # BOVA11 129,35 → the 125–150 band (royal blue, white text)
    assert by_tk["BOVA11"]["price"] == {
        "pill": "#2563eb", "text": "#fff", "range": "125 \u2264 X < 150"}
    # PETR4 40,87 → the 40–50 band (pale green, black text)
    assert by_tk["PETR4"]["price"] == {
        "pill": "#a5d6a7", "text": "#000", "range": "40 \u2264 X < 50"}
    # the band matches the palette's own definition (no forked colors)
    from skills._colors.price import price_range_color
    assert by_tk["BOVA11"]["price"]["pill"] == price_range_color(129.35)["bg"]

    rank = {c["key"]: c for c in svc._ranking_cards(_snap_fixture())}
    petr = next(i for i in rank["altas"]["items"]
                if i["ticker"] == "PETR4")
    assert petr["price"]["range"] == "40 \u2264 X < 50"
    # the volumes card: [v1.28.3] the row is STANDARDIZED with
    # every other card — the COTAÇÃO is the main value (pill and all)
    # and the volume rides the info slot
    vol_row = rank["volumes"]["items"][0]
    assert vol_row["price"]["range"] == "40 \u2264 X < 50"
    assert vol_row["extra"]["label"] == "volume"
    assert vol_row["extra"]["text"].startswith("R$")
    assert "price" not in (vol_row["extra"] or {})
    # the ibov/smll cards pill their quote values too
    monkeypatch.setattr(homemod, "_query_index", lambda code: {
        "status": "ok", "ref_date": "2026-08-05",
        "constituents": [{"ticker": "PETR4", "company_name": "PETROBRAS",
                          "participation": 10.886}]})
    ibov = svc._index_card("IBOV", "IBOV · Top 10",
                           HomeService._quotes(_snap_fixture()))
    assert ibov["items"][0]["price"]["range"] == "40 \u2264 X < 50"


def test_ticker_card_position_and_volume(tmp_path, monkeypatch):
    """The ticker card's extra info: pos_52 (where the close sits in the
    52-week range) and the day's financial volume — the MEDIUM size's
    content ("in length a bit bigger to display more info")."""
    homemod = _isolated_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(homemod, "_range_52w", _fake_range_52w)
    from webui.services.settings import settings_service
    assert settings_service().update(
        {"home.ticker_kpis": ["BOVA11", "SMAL11"]})["ok"]

    from webui.services.home import HomeService
    cards = HomeService()._ticker_cards(HomeService._quotes(_snap_fixture()))
    by_tk = {c["ticker"]: c for c in cards}
    # BOVA11: close 129,35 in [118,30 .. 140,10] → (11,05 / 21,80) = 50,7%
    assert by_tk["BOVA11"]["pos_52"] == 51
    assert by_tk["BOVA11"]["volume"] == "R$ 1,00 mi"
    # SMAL11: absent from the 52w window → no bar, volume still shows
    assert by_tk["SMAL11"]["pos_52"] is None
    assert by_tk["SMAL11"]["volume"] == "R$ 1,00 mi"
    # the bounds math — the fixture's POMO4 window
    from webui.services.home import _pos_52
    assert _pos_52(2.44, 3.10, 2.20) == 27       # (0,24 / 0,90) = 26,7 → 27
    assert _pos_52(2.20, 3.10, 2.20) == 0        # at the low
    assert _pos_52(3.10, 3.10, 2.20) == 100      # at the high
    assert _pos_52(2.44, 2.50, 2.50) is None     # degenerate window
    assert _pos_52(None, 3.10, 2.20) is None
