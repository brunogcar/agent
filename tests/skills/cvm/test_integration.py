"""Integration tests for CVM skills + data sources with REAL databases.

These tests exercise the full stack against real synced data (DFP, ITR, FRE,
IPE, CAD, bridge, B3 dividends, brapi, COTAHIST). They skip gracefully when
a required database is not synced — so they run on the user's machine (full
DBs) but don't fail in CI / sandbox (no DBs).

Run just these tests:
    python -m pytest tests/skills/cvm/test_integration.py -v -W error --tb=short

Markers:
    @pytest.mark.integration — tags for selective running
    DB_AVAILABLE fixture — skips if the needed DB is missing
"""
from __future__ import annotations

import pytest

TICKERS = ["PETR4", "KLBN11", "SUZB3"]


# ── Fixtures: skip gracefully when DBs are missing ───────────────────────────

@pytest.fixture
def dfp_available():
    """Skip test if DFP database is not synced."""
    try:
        from data_sources.cvm._db import connect_dfp
        conn = connect_dfp(read_only=True)
        conn.close()
    except (FileNotFoundError, ImportError):
        pytest.skip("DFP database not synced")
    return True


@pytest.fixture
def itr_available():
    try:
        from data_sources.cvm._db import connect_itr
        conn = connect_itr(read_only=True)
        conn.close()
    except (FileNotFoundError, ImportError):
        pytest.skip("ITR database not synced")
    return True


@pytest.fixture
def fre_available():
    try:
        from data_sources.cvm._db import connect_fre
        conn = connect_fre(read_only=True)
        conn.close()
    except (FileNotFoundError, ImportError):
        pytest.skip("FRE database not synced")
    return True


@pytest.fixture
def ipe_available():
    try:
        from data_sources.cvm._db import connect_ipe
        conn = connect_ipe(read_only=True)
        conn.close()
    except (FileNotFoundError, ImportError):
        pytest.skip("IPE database not synced")
    return True


@pytest.fixture
def cad_available():
    try:
        from data_sources.cvm._db import connect_cad
        conn = connect_cad(read_only=True)
        conn.close()
    except (FileNotFoundError, ImportError):
        pytest.skip("CAD database not synced")
    return True


@pytest.fixture
def bridge_available():
    try:
        from data_sources.cvm.bridge.query_engine import lookup
        r = lookup(ticker="PETR4")
        if r.get("status") != "ok":
            pytest.skip("Bridge database not synced")
    except (FileNotFoundError, ImportError):
        pytest.skip("Bridge database not synced")
    return True


@pytest.fixture
def b3_dividends_available():
    try:
        from data_sources.b3.dividends.query_engine import dividends
        r = dividends(ticker="PETR4", limit=1)
        if r.get("status") == "not_synced":
            pytest.skip("B3 dividends database not synced")
    except (FileNotFoundError, ImportError):
        pytest.skip("B3 dividends database not synced")
    return True


@pytest.fixture
def cotahist_available():
    try:
        from data_sources.b3.cotahist.query_engine import query
        r = query(ticker="PETR4", limit=1, market_type=10)
        if r.get("status") == "not_synced":
            pytest.skip("COTAHIST database not synced")
    except (FileNotFoundError, ImportError):
        pytest.skip("COTAHIST database not synced")
    return True


# ── Data source integration tests ────────────────────────────────────────────

class TestDataSources:
    """Verify each data source can be queried with real data."""

    def test_cad_has_companies(self, cad_available):
        from data_sources.cvm.cad.status_reporter import status
        r = status()
        assert r["status"] == "ok"
        assert r["total_companies"] > 0

    def test_bridge_resolves_petr4(self, bridge_available):
        from data_sources.cvm.bridge.query_engine import lookup
        r = lookup(ticker="PETR4")
        assert r["status"] == "ok"
        assert r["cnpj"]
        assert r["cd_cvm"]

    def test_dfp_query_lucro_liquido(self, dfp_available):
        from data_sources.cvm.dfp.query_engine import query
        r = query(company="PETR4", codigo="3.11", limit_years=1)
        assert r["status"] == "ok"
        assert len(r["periods"]) > 0

    def test_itr_query_receita(self, itr_available):
        from data_sources.cvm.itr.query_engine import query
        r = query(company="PETR4", codigo="3.01", limit_years=1)
        assert r["status"] in ("ok", "not_found")

    def test_fre_shareholders(self, fre_available):
        from data_sources.cvm.fre.query_engine import shareholders
        r = shareholders(company="PETR4", limit=5)
        assert r["status"] in ("ok", "not_found")

    def test_ipe_events(self, ipe_available):
        from data_sources.cvm.ipe.query_engine import query
        r = query(company="PETR4", limit=5)
        assert r["status"] in ("ok", "not_found")

    def test_b3_dividends(self, b3_dividends_available):
        from data_sources.b3.dividends.query_engine import dividends
        r = dividends(ticker="PETR4", limit=5)
        assert r["status"] == "ok"
        assert r["count"] >= 0

    def test_cotahist_query(self, cotahist_available):
        from data_sources.b3.cotahist.query_engine import query
        r = query(ticker="PETR4", limit=5, market_type=10)
        # "ok" = has data; "not_found" = DB synced but ticker not in synced year
        # (both are valid — the DB is accessible, which is what we're testing)
        assert r["status"] in ("ok", "not_found"), f"Unexpected: {r.get('error','')}"
        if r["status"] == "ok":
            assert r["count"] > 0
            assert r["rows"][0]["close"] is not None


# ── CVM skill integration tests ──────────────────────────────────────────────

class TestFinancialsSkill:
    """financials skill against real DFP + ITR databases."""

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_quarterly_with_ttm(self, dfp_available, ticker):
        from skills.cvm.financials.financials import quarterly
        r = quarterly(company=ticker, periods=4)
        assert r["status"] == "ok", f"{ticker}: {r.get('error','')}"
        assert len(r["periods"]) > 0
        # TTM (v1.1) — status is "ok" if 4 quarters available, "insufficient_data" otherwise
        ttm = r.get("ttm", {})
        assert ttm["status"] in ("ok", "insufficient_data")
        if ttm["status"] == "ok":
            # TTM metrics may be None if any of the 4 quarters is missing that
            # value (by design — can't sum with None). Just check the key exists.
            assert "receita_liquida" in ttm["metrics"]
            # If receita is not None, it should be a positive number
            rec = ttm["metrics"]["receita_liquida"]
            if rec is not None:
                assert rec > 0, f"{ticker} TTM receita should be positive, got {rec}"

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_annual(self, dfp_available, ticker):
        from skills.cvm.financials.financials import annual
        r = annual(company=ticker, periods=2)
        assert r["status"] == "ok", f"{ticker}: {r.get('error','')}"
        assert len(r["periods"]) > 0


class TestValuationSkill:
    """valuation skill against real DFP + FRE + brapi/investsite."""

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_ratios_returns_price_and_pl(self, dfp_available, fre_available, bridge_available, ticker):
        from skills.cvm.valuation.valuation import ratios
        r = ratios(company=ticker)
        assert r["status"] == "ok", f"{ticker}: {r.get('error','')}"
        ratios_data = r["ratios"]
        assert ratios_data["price"] is not None
        assert ratios_data["p_l"] is not None

    def test_unit_ticker_market_cap_not_computed(self, dfp_available, fre_available, bridge_available):
        """KLBN11 (UNIT) must NOT have market_cap_source='computed' (wrong for units).
        This is the regression test for the v1.0.9-v1.0.13 unit ticker fix."""
        from skills.cvm.valuation.valuation import ratios
        r = ratios(company="KLBN11")
        assert r["status"] == "ok"
        ratios_data = r["ratios"]
        assert ratios_data["unit_ticker"] is True
        mc_src = ratios_data.get("market_cap_source")
        # Must be "brapi", "investsite", or "investsite_derived" — NOT "computed"
        assert mc_src != "computed", (
            f"UNIT ticker KLBN11 has market_cap_source='computed' (wrong for units). "
            f"p_l_source={ratios_data.get('p_l_source')}"
        )
        # P/L should be a sane value (not 65, not 1e-09)
        pl = ratios_data.get("p_l")
        assert pl is not None and 0.1 < pl < 500, f"P/L out of sane range: {pl}"


class TestShareholdersSkill:
    @pytest.mark.parametrize("ticker", TICKERS)
    def test_shareholders(self, fre_available, bridge_available, ticker):
        from skills.cvm.shareholders.shareholders import shareholders
        r = shareholders(company=ticker, limit=5)
        assert r["status"] in ("ok", "not_found")


class TestDividendsSkill:
    @pytest.mark.parametrize("ticker", TICKERS)
    def test_summary(self, dfp_available, b3_dividends_available, bridge_available, ticker):
        from skills.cvm.dividends.dividends import summary
        r = summary(company=ticker)
        assert r["status"] == "ok", f"{ticker}: {r.get('error','')}"


# ── Comparison skill integration tests ───────────────────────────────────────

class TestComparisonSkill:
    """comparison skill against real data for all 3 tickers."""

    def test_side_by_side_has_3_sections_and_sectors(self, dfp_available, fre_available,
                                                      b3_dividends_available, bridge_available, cad_available):
        from skills.cvm.comparison.comparison import side_by_side
        r = side_by_side(tickers=TICKERS)
        assert r["status"] == "ok"
        assert len(r["sections"]) == 3
        assert "sectors" in r
        # Each ticker should have a sector resolved
        for t in TICKERS:
            assert r["sectors"].get(t, "") != "", f"{t} has no sector"

    def test_summary_single_section(self, dfp_available, fre_available,
                                     b3_dividends_available, bridge_available, cad_available):
        from skills.cvm.comparison.comparison import summary
        r = summary(tickers=TICKERS)
        assert r["status"] == "ok"
        assert len(r["sections"]) == 1

    def test_growth_returns_values(self, dfp_available, itr_available, bridge_available):
        """Growth mode: sign-change guard returns None for profit→loss,
        real values for same-sign growth. No crash."""
        from skills.cvm.comparison.comparison import growth
        r = growth(tickers=TICKERS)
        assert r["status"] == "ok"
        assert len(r["sections"]) == 1
        sec = r["sections"][0]
        assert "Receita QoQ" in sec["columns"]
        assert "ROE (TTM)" in sec["columns"]


# ── Investsite skill integration test ────────────────────────────────────────

class TestInvestsiteSkill:
    """investsite skill — verifies we can fetch + parse indicators.
    Also dumps the precos_relativos keys so we can see what's available."""

    def test_investsite_indicators_dumps_keys(self):
        """Fetch KLBN11 indicators and dump all precos_relativos keys.
        This is the diagnostic that shows us if investsite exposes market cap."""
        from skills.investsite.investsite import indicators
        r = indicators(ticker="KLBN11")
        if r.get("status") != "ok":
            pytest.skip(f"investsite unavailable: {r.get('error','')}")
        precos = r.get("sections", {}).get("precos_relativos", {})
        # Assert we got P/L (the key we use for the unit fallback)
        assert "Preco/Lucro" in precos or "Preço/Lucro" in precos, (
            f"investsite precos_relativos missing P/L. Keys: {list(precos.keys())}"
        )
        # Print all keys for diagnostic visibility (shows in -v output)
        print(f"\n       investsite precos_relativos keys: {list(precos.keys())}")
