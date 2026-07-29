"""Tests for skills/cvm/_freshness.py (v1.5).

Covers TestFreshness (4 tests):
  - test_get_freshness_returns_dict   : get_freshness() returns dict with expected DB keys
  - test_get_last_synced_period_basic : [v1.5] get_last_synced_period() returns dict + reads
                                         MAX(data_fim_exerc) from each DB's `contas` table
  - test_get_last_synced_period_missing_db : missing DBs return "" (no exception)
  - test_add_freshness_includes_both   : [v1.5] add_freshness() now includes both
                                         data_freshness AND last_synced_period keys

Uses the shared `financials_env` fixture from financials/conftest.py so we get
synthetic dfp.db + itr.db with known data_fim_exerc values (2023-12-31 for
DFP, 2023-09-30 for ITR).
"""
from __future__ import annotations


class TestFreshness:
    """Tests for the CVM skill freshness helpers."""

    def test_get_freshness_returns_dict(self, financials_env):
        """get_freshness() returns a dict with at least the dfp + itr keys.

        In the test env, the sync_state table is empty (the conftest only
        inserts contas rows), so freshness values may be "". We only
        verify the keys are present.
        """
        from skills.cvm._freshness import get_freshness
        result = get_freshness()
        assert isinstance(result, dict)
        for key in ("dfp", "itr", "fre", "ipe", "cad", "vlmo", "cgvn", "fca"):
            assert key in result, f"get_freshness missing key '{key}'"
            assert isinstance(result[key], str)

    def test_get_last_synced_period_basic(self, financials_env):
        """[v1.5] get_last_synced_period() returns MAX(data_fim_exerc) per DB.

        The synthetic DFP fixture inserts contas with data_fim_exerc =
        '2023-12-31' (annual) and '2022-12-31' (annual, partial). MAX should
        be '2023-12-31'. The ITR fixture inserts '2023-03-31', '2023-06-30',
        '2023-09-30' — MAX should be '2023-09-30'.
        """
        from skills.cvm._freshness import get_last_synced_period
        result = get_last_synced_period()
        assert isinstance(result, dict)
        # All 8 CVM DB keys must be present (those without a `contas` table
        # return "").
        for key in ("dfp", "itr", "fre", "ipe", "cad", "vlmo", "cgvn", "fca"):
            assert key in result, f"get_last_synced_period missing key '{key}'"
            assert isinstance(result[key], str)
        # DFP should report 2023-12-31 (latest annual period in the fixture).
        assert result["dfp"] == "2023-12-31", \
            f"expected DFP last_synced_period='2023-12-31', got {result['dfp']!r}"
        # ITR should report 2023-09-30 (latest quarterly period in the fixture).
        assert result["itr"] == "2023-09-30", \
            f"expected ITR last_synced_period='2023-09-30', got {result['itr']!r}"

    def test_get_last_synced_period_missing_db(self, tmp_path, monkeypatch):
        """Missing DB files return "" without raising.

        We monkeypatch dfp_db_path to point to a nonexistent path and verify
        the function returns "" instead of raising FileNotFoundError.
        """
        from skills.cvm import _freshness
        nonexistent = tmp_path / "nonexistent.db"
        # Patch the dfp_db_path symbol that _freshness imports at call time.
        import data_sources.cvm._db as cvm_db
        monkeypatch.setattr(cvm_db, "dfp_db_path", lambda: nonexistent)
        result = _freshness.get_last_synced_period()
        assert result["dfp"] == "", \
            f"missing DB should return '', got {result['dfp']!r}"

    def test_add_freshness_includes_both(self, financials_env):
        """[v1.5] add_freshness() now adds BOTH data_freshness AND
        last_synced_period keys to the result dict (in-place + return)."""
        from skills.cvm._freshness import add_freshness
        result = add_freshness({"status": "ok"})
        assert "data_freshness" in result, "missing data_freshness key"
        assert "last_synced_period" in result, "missing last_synced_period key"
        assert isinstance(result["data_freshness"], dict)
        assert isinstance(result["last_synced_period"], dict)
        # The input keys should still be present (add_freshness doesn't strip).
        assert result["status"] == "ok"
