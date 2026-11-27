"""tests/webui/test_v128_1.py — the v1.28.1 suite.

The Ferramentas polish round (the user's list, item by item):

  1. COMPARAÇÃO — every grid row ranks now (the user's ask: "Dividendos
     inside table not highlighting the best option for all the items" /
     "Mercado inside table not…"): _ROWS carries best on 100% of the
     specs, _build_groups marks a winner wherever 2+ companies have
     data, and the namespace moved to v3 (old cached payloads carried
     the half-ranked grid).
  2. SCREENER — the sector table ships RAW companions (price_raw,
     mktcap_raw, … — the client's sortable headers + best-of-column ✓
     read them), namespace v2.
  3. PAINEL — the ETF row (BOVA11/SMAL11/IVVB11 close + signed day %
     from the same snapshot the cards read; "add kpi to BOVA11 SMAL11
     IVVB11 with the % it rose or fell") and the Maiores Altas BDR card
     (the *34 universe, same liquidity gate; "add maiores altas BDR").
  4. SYSLOG — the terminal tail made visible: the print tee parses
     [ratios]/[webui]/plain lines into sources, the request lines carry
     the QUERY STRING (minus the _t= cache-buster — "i want that log to
     display more info"), and uvicorn's INFO banners hook in.
  5. HTTP SURFACE — /webui/tools renders the third pill (Backtest,
     picker + panel), the company page no longer links the tab, the tab
     fragment 404s, and the Mercado page copy no longer names the
     upstream source.

Run:  python -m pytest tests/webui/test_v128_1.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


PETR = "33000167000101"      # PETR3 + PETR4 (one company, two classes)
PRIO = "02187300000111"
UGPA = "33252800000100"
SECTOR = "Petróleo e Gás"


@pytest.fixture()
def memory_root(tmp_path, monkeypatch):
    """Isolated root + bridge.db carrying the concept trio's sector."""
    from core.config import cfg
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True)
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b = sqlite3.connect(str(cvm / "bridge.db"))
    b.execute("""CREATE TABLE IF NOT EXISTS ticker_map (
        ticker TEXT PRIMARY KEY, issuing TEXT, cd_cvm TEXT, trading_name TEXT,
        cnpj TEXT, denom_social TEXT, denom_comerc TEXT, sit TEXT,
        setor_ativ TEXT, tp_merc TEXT, synced_at TEXT)""")
    for tk, iss, cd, name, cnpj, setor in [
        ("PETR4", "PETR", "9512", "PETROBRAS", PETR, SECTOR),
        ("PETR3", "PETR", "9512", "PETROBRAS", PETR, SECTOR),
        ("PRIO3", "PRIO", "22148", "PRIO", PRIO, SECTOR),
        ("UGPA3", "UGPA", "20646", "ULTRAPAR", UGPA, SECTOR),
    ]:
        b.execute(
            "INSERT INTO ticker_map (ticker, issuing, cd_cvm, trading_name, "
            "cnpj, setor_ativ) VALUES (?, ?, ?, ?, ?, ?)",
            (tk, iss, cd, name, cnpj, setor))
    b.commit()
    b.close()
    return tmp_path


def _entry(ticker: str, *, val=None, fin=None, grw=None, mkt=None,
           error: str = "") -> dict:
    return {"ticker": ticker, "val": val or {}, "fin": fin or {},
            "grw": grw or {}, "mkt": mkt or {},
            "hist_monthly": [], "hist_daily": [], "error": error}


PETR_ENTRY = _entry(
    "PETR4",
    val={"price": 40.87, "market_cap": 338.85e9, "p_l": 2.60,
         "p_vpa": 0.81, "ev_ebitda": 2.56, "roe": 0.3119,
         "dividend_yield": 0.1061, "dpa": 4.20, "total_shares": 8.29e9,
         "ev": 500.0e9},
    fin={"receita_liquida": 497.55e9, "ebitda": 155.37e9, "payout": 0.55,
         "event_count_stub": None},
    grw={"receita_yoy": 0.0042},
    mkt={"price": 40.87, "price_date": "2026-11-24", "var_day": 0.012},
)
PRIO_ENTRY = _entry(
    "PRIO3",
    val={"price": 60.54, "market_cap": 45.84e9, "p_l": 11.87,
         "p_vpa": 1.78, "ev_ebitda": 6.47, "roe": 0.1498,
         "dividend_yield": 0.0, "dpa": 0.0, "total_shares": 0.76e9,
         "ev": 90.0e9},
    fin={"receita_liquida": 15.58e9, "ebitda": 7.67e9, "payout": 0.10},
    grw={"receita_yoy": 0.0852},
    mkt={"price": 60.54, "price_date": "2026-11-24", "var_day": -0.004},
)
UGPA_ENTRY = _entry(
    "UGPA3",
    val={"price": 33.39, "market_cap": 35.66e9, "p_l": 13.29,
         "p_vpa": 2.01, "ev_ebitda": 6.84, "roe": 0.1514,
         "dividend_yield": 0.0389, "dpa": 1.30, "total_shares": 1.07e9,
         "ev": 60.0e9},
    fin={"receita_liquida": 142.37e9, "ebitda": 5.14e9, "payout": 0.99},
    grw={"receita_yoy": 0.0664},
    mkt={"price": 33.39, "price_date": "2026-11-24", "var_day": 0.003},
)
SECTOR_ENTRIES = [PETR_ENTRY, PRIO_ENTRY, UGPA_ENTRY]


# ── 1. Comparação — every row ranks ──────────────────────────────────────────

def test_every_row_spec_carries_a_ranking_direction():
    from webui.services.comparison import _ROWS
    unranked = [label for _gk, label, _c, _f, best, _p, _t in _ROWS
                if best not in ("min", "max")]
    assert not unranked, f"rows without a best direction: {unranked}"
    # the v1.28.1 conversions specifically: cotação min, size max,
    # every dividend row max
    by_label = {label: best for _gk, label, _c, _f, best, _p, _t in _ROWS}
    assert by_label["Última Cotação"] == "min"
    assert by_label["Market Cap"] == "max"
    assert by_label["Enterprise Value (EV)"] == "max"
    assert by_label["Total de Ações"] == "max"
    for lbl in ("DPA", "Payout", "Eventos (B3)", "Remun. Total (últ. ano)"):
        assert by_label[lbl] == "max", lbl


def test_build_groups_ranks_mercado_and_dividendos_rows():
    from webui.services.comparison import _build_groups
    groups = {g["key"]: g for g in _build_groups(SECTOR_ENTRIES)}
    rows = {r["label"]: r for g in groups.values() for r in g["rows"]}
    # Mercado: cheapest share price (UGPA3 33,39) + biggest market cap
    # (PETR4) both carry the ✓ now
    assert rows["Última Cotação"]["best"] == [2]          # UGPA3
    assert rows["Market Cap"]["best"] == [0]              # PETR4
    assert rows["Enterprise Value (EV)"]["best"] == [0]   # PETR4
    # Dividendos: DPA max = PETR4 (4,20); DY max = PETR4 too
    assert rows["DPA"]["best"] == [0]
    assert rows["Div Yield"]["best"] == [0]
    # a row with values on ONE company only never ranks (2+ rule)
    solo = _entry("PETR4", val={"quick_ratio": 1.5})
    empty = _entry("PRIO3")
    g2 = [r for g in _build_groups([solo, empty]) for r in g["rows"]]
    qr = next(r for r in g2 if r["label"] == "Liquidez Seca")
    assert qr["best"] == []


def test_comparison_namespace_bumped_to_v3():
    from webui.services.comparison import ComparisonService
    assert ComparisonService._NS == "tools_comparison_v3"


# ── 2. Screener — raw companions on the table rows ───────────────────────────

def _screened(memory_root, monkeypatch, entries=None):
    """screen() with the engines faked — the bridge sector stays real."""
    from webui.services.screener import ScreenerService
    if entries is not None:
        monkeypatch.setattr(ScreenerService, "_fetch_all",
                            lambda self, peers: entries)
    monkeypatch.setattr(ScreenerService, "_fingerprint",
                        lambda self, tks: None)   # cache OFF for unit paths
    return ScreenerService().screen("PETR4")


def test_screener_table_rows_carry_raw_companions(memory_root, monkeypatch):
    out = _screened(memory_root, monkeypatch, SECTOR_ENTRIES)
    assert out["status"] == "ok"
    raw_keys = {"price_raw", "mktcap_raw", "p_l_raw", "p_vpa_raw",
                "ev_ebitda_raw", "roe_raw", "dy_raw", "receita_raw",
                "ebitda_raw", "marg_ebitda_raw", "cresc_raw"}
    for row in out["table"]:
        missing = raw_keys - set(row)
        assert not missing, f"{row['ticker']} missing raw keys: {missing}"
    petr = next(r for r in out["table"] if r["ticker"] == "PETR4")
    assert petr["price_raw"] == pytest.approx(40.87)
    assert petr["mktcap_raw"] == pytest.approx(338.85e9)
    assert petr["roe_raw"] == pytest.approx(0.3119)
    # the formatted strings still ship alongside
    assert petr["price"] and petr["p_l"]


def test_screener_namespace_bumped_to_v2():
    from webui.services.screener import ScreenerService
    # [v1.28.2] v3 — cached v2 payloads carry the ratio-formula delta
    # (sign-flipped on negative medians); they must not serve.
    # [v1.28.4] v4 — the vs_rows carry the Posição keys (pos_rank/
    # pos_of/pos_fmt); cached v3 payloads lack them.
    assert ScreenerService._NS == "tools_screener_v4"


# ── 3. Painel — the ETF row + the Maiores Altas BDR card ─────────────────────

def _snap_fixture() -> dict:
    """A market snapshot with the three ETFs + a BDR + a native.

    [v1.28.2] rows carry bdi_code (2=equity, 12=FII, 14=ETF, 34/35/36=
    BDR): the snapshot's universe spans the share-like instruments and
    the ranking cards slice it in the service (natives stay bdi 2).
    """
    def sym(tk, name, close, prev, trades, bdi=2):
        return {"ticker": tk, "name": name, "bdi_code": bdi,
                "close": close, "prev_close": prev,
                "variation_pct": (close / prev - 1) * 100 if prev else None,
                "volume": 1e6, "trade_count": trades}
    return {"status": "ok", "session_date": "2026-11-24", "count": 6,
            "symbols": [
                sym("BOVA11", "ISHARES BOVA", 129.35, 127.80, 9000, bdi=14),
                sym("SMAL11", "ISHARES SMAL", 122.10, 124.00, 4500, bdi=14),
                sym("IVVB11", "ISHARES S&P 500", 345.60, 343.10, 3200, bdi=14),
                sym("AAPL34", "APPLE BDR", 25.40, 23.90, 400, bdi=34),   # +6,27%
                sym("MSBR34", "MSFT-WTF BDR", 8.10, 8.40, 400, bdi=34),  # illiquid-ish
                sym("PETR4", "PETROBRAS", 40.87, 40.38, 88000),          # a native
            ]}


def test_ticker_cards_default_trio(tmp_path, monkeypatch):
    """[v1.28.1→v1.28.3] the ETF row became the TICKER CARDS — the
    default home.ticker_kpis (BOVA11/SMAL11/IVVB11) still leads the
    grid, now as ranking-card-sized quote cards with the ETF badge
    ("kpi for the ETF are too large, make them the size of card of
    ranking like IBOV · Top 10")."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import webui.services.home as homemod
    monkeypatch.setattr(homemod, "_quotes_for",
                        lambda s: {"status": "not_synced"})
    monkeypatch.setattr(homemod, "_range_52w",
                        lambda s: {"status": "not_synced"})
    from webui.services.home import HomeService
    snap = _snap_fixture()
    quotes = HomeService._quotes(snap)
    cards = HomeService()._ticker_cards(quotes)
    assert [c["ticker"] for c in cards] == ["BOVA11", "SMAL11", "IVVB11"]
    assert all(c["kind"] == "ETF" for c in cards)
    assert cards[0]["value"] == "R$ 129,35"
    assert cards[0]["variation"].startswith("+")
    assert cards[1]["variation"].startswith("-")   # SMAL11 fell
    assert all("COTAHIST" in c["tooltip"] for c in cards)
    # cotahist fully down (no snapshot quotes, no fallback) → the cards
    # still render, degraded per-card ("—" cells — the house rule)
    degraded = HomeService()._ticker_cards(None)
    assert [c["ticker"] for c in degraded] == ["BOVA11", "SMAL11", "IVVB11"]
    assert all(c["value"] == "—" for c in degraded)


def test_bdr_gainers_card_scopes_to_the_bdr_suffixes():
    from webui.services.home import HomeService
    cards = HomeService()._ranking_cards(_snap_fixture())
    bdr = next(c for c in cards if c["key"] == "altas_bdr")
    assert bdr["title"] == "Maiores Altas BDR"
    assert [i["ticker"] for i in bdr["items"]] == ["AAPL34", "MSBR34"]
    assert bdr["items"][0]["variation"].startswith("+")
    # [v1.28.2] the BDR card sits AFTER Maiores Baixas (the user's ask:
    # native rankings first, the BDR slice last); [v1.28.3] Maiores
    # Quedas BDR closes the row (the losers twin)
    keys = [c["key"] for c in cards]
    assert keys.index("altas_bdr") > keys.index("baixas")
    assert keys == ["negocios", "volumes", "altas", "baixas",
                    "altas_bdr", "baixas_bdr"]
    # [v1.28.2] the four ranking cards stay NATIVES-ONLY (bdi 2): the
    # snapshot universe spans ETFs/FIIs/BDRs now, so the equities slice
    # is explicit — the cards' content is unchanged (a BDR can no longer
    # lead Maiores Altas; an ETF can't top Mais Negócios)
    altas = next(c for c in cards if c["key"] == "altas")
    assert [i["ticker"] for i in altas["items"]] == ["PETR4"]
    negocios = next(c for c in cards if c["key"] == "negocios")
    assert [i["ticker"] for i in negocios["items"]] == ["PETR4"]
    # the degraded branch carries the BDR cards too (last, same as the ok path)
    dead = HomeService()._ranking_cards({"status": "not_synced"})
    assert [c["key"] for c in dead] == [
        "negocios", "volumes", "altas", "baixas", "altas_bdr", "baixas_bdr"]


def test_bdr_gainers_respect_the_liquidity_gate():
    from webui.services.home import HomeService
    snap = _snap_fixture()
    # both BDRs below the 100-trade gate → the card renders empty
    for s in snap["symbols"]:
        if s["bdi_code"] in (34, 35, 36):
            s["trade_count"] = 3
    cards = HomeService()._ranking_cards(snap)
    bdr = next(c for c in cards if c["key"] == "altas_bdr")
    assert bdr["items"] == []


# ── 4. Syslog — the terminal tail + richer request lines ─────────────────────

def test_stdout_tee_parses_sources_and_levels():
    import io
    from webui.services.syslog import _StdoutTee, syslog

    # unique markers — the ring buffer is process-global and other tests
    # (the HTTP clients, engine runs) flood it; anchoring on len() would
    # race. Search for OUR lines instead.
    marker = f"zz{next(iter({id(object()): 1}))}"
    buf = io.StringIO()
    tee = _StdoutTee(buf, is_stderr=False)
    tee.write(f"  [ratios] 12/49 {marker}-r (0.00s, total 0.1s) = 0.5841\n")
    tee.write(f"[webui] screener {marker}-w partial: valuation indisponível\n")
    tee.write(f"plain informational line {marker}-a\n")
    err_tee = _StdoutTee(io.StringIO(), is_stderr=True)
    err_tee.write(f"[webui] backtest run failed: {marker}-f\n")
    err_tee.write(f"Traceback (most recent call last): {marker}-t\n")
    tee.write(f"{marker}-p1")
    tee.write(" coalesced\n")   # partial writes must NOT log twice

    def find(tag):
        for e in reversed(syslog.snapshot(5000)):
            if marker in e["message"] and tag in e["message"]:
                return e
        return None

    r = find(f"{marker}-r");  assert r and r["source"] == "ratios" and r["level"] == "info"
    w = find(f"{marker}-w");  assert w and w["source"] == "webui" and w["level"] == "info"
    a = find(f"{marker}-a");  assert a and a["source"] == "app" and a["level"] == "info"
    f = find(f"{marker}-f");  assert f and f["source"] == "webui" and f["level"] == "warning"
    t = find(f"{marker}-t");  assert t and t["source"] == "stderr" and t["level"] == "error"
    p = find("coalesced");    assert p and p["message"].strip() == f"{marker}-p1 coalesced"
    # the ORIGINAL stream still received every byte (PowerShell unchanged)
    assert marker in buf.getvalue()


def test_request_log_carries_the_query_string_sans_cache_buster():
    from webui.services.syslog import RequestLoggingMiddleware
    scope = {"type": "http", "method": "GET", "path": "/api/webui/tools/comparison/search",
             "query_string": b"q=pomo4&_t=1795648483839"}
    assert RequestLoggingMiddleware._path_with_query(scope) == \
        "/api/webui/tools/comparison/search?q=pomo4"
    # only the cache-buster → bare path; nothing at all → bare path
    assert RequestLoggingMiddleware._path_with_query(
        {"path": "/x", "query_string": b"_t=42"}) == "/x"
    assert RequestLoggingMiddleware._path_with_query(
        {"path": "/x", "query_string": b""}) == "/x"


def test_attach_print_tee_is_idempotent(monkeypatch):
    import sys as _sys
    import webui.services.syslog as sl
    saved_out, saved_err = _sys.stdout, _sys.stderr
    try:
        sl.attach_print_tee()
        wrapped_out, wrapped_err = _sys.stdout, _sys.stderr
        assert isinstance(wrapped_out, sl._StdoutTee)
        sl.attach_print_tee()                     # second call → no-op
        assert _sys.stdout is wrapped_out and _sys.stderr is wrapped_err
        # the tee passes everything through to the original stream
        assert wrapped_out.write("x") >= 1
    finally:
        monkeypatch.setattr(_sys, "stdout", saved_out, raising=False)
        monkeypatch.setattr(_sys, "stderr", saved_err, raising=False)


# ── 5. HTTP surface ──────────────────────────────────────────────────────────

@pytest.fixture()
def client(memory_root):
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_tools_page_renders_the_third_pill(client):
    r = client.get("/webui/tools")
    assert r.status_code == 200
    body = r.text
    assert ">Comparação<" in body and ">Screener<" in body
    assert ">Backtest<" in body                       # the new pill
    assert 'id="family-pill-backtest"' in body
    assert 'id="family-backtest"' in body             # the panel
    assert 'id="bt-tool-search"' in body              # the picker
    assert 'id="bt-tool-result"' in body              # the result box


def test_company_page_lost_the_backtest_tab(client):
    r = client.get("/webui/company/PETR4")
    assert r.status_code == 200
    assert "tab/backtest" not in r.text
    frag = client.get("/api/webui/company/PETR4/tab/backtest")
    assert frag.status_code == 404
    # the per-ticker endpoints the TOOL calls stay alive
    meta = client.get("/api/webui/company/PETR4/backtest/meta")
    assert meta.status_code == 200


def test_mercado_copy_names_no_upstream_source(client):
    r = client.get("/webui/mercado")
    assert r.status_code == 200
    assert "dadosdemercado" not in r.text
    # the source hint still tells the user WHAT to sync, just not WHERE
    # it comes from
    assert "Boletim Focus" in r.text
