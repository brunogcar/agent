"""Tests for the `bpa` mode of skills/cvm/financials.

Covers TestBPAMode (5 tests):
  - test_bpa_basic_shape        : default annual call → ok + accounts dict shape
  - test_bpa_no_company         : no company arg → status=error
  - test_bpa_no_bpa_data        : unknown company → not_found OR empty periods
  - test_bpa_quarterly          : period="quarterly" → quarterly shape
  - test_bpa_manifest_has_period_param : MANIFEST advertises `period` (not `quarterly=1`)

[v1.12 — dashboard reorg] The 5 standalone statement modes (bpa/bpp/dre/dfc/dva)
were rewritten with a new API:
  - Old API: `quarterly=1` param + `_BPA_CODES` exported.
  - New API: `period="annual"|"quarterly"` param + codes in
    `modes/_statement_sections.py` (no `_BPA_CODES` export).

These tests verify the NEW API. Uses the shared `financials_env` fixture from
conftest.py.
"""
from __future__ import annotations


class TestBPAMode:
    """Tests for `financials.bpa()` — Balance Patrimonial Ativo (assets)."""

    def test_bpa_basic_shape(self, financials_env):
        """Default annual call returns the standalone-statement-mode shape.

        Each period carries a dict-keyed `accounts` map
        (``{codigo: {label, section, valor_brl}}``) — NOT the list shape
        that `complete()` returns.
        """
        from skills.cvm.financials.modes.bpa import bpa
        result = bpa(company="33000167000101")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["statement"] == "BPA"
        assert result["grupo_filter"] == "BPA"
        # At least one annual period is present in the synthetic DB (2023).
        assert isinstance(result["periods"], list)
        assert len(result["periods"]) >= 1
        # The synthetic DFP fixture stores 2023-12-31 as the latest data_fim.
        first = result["periods"][0]
        assert isinstance(first["data_fim_exerc"], str)
        assert first["data_fim_exerc"].endswith("-12-31")  # annual period
        # `accounts` is a dict keyed by codigo (NOT a list — that's complete()).
        assert isinstance(first["accounts"], dict)
        # Spot-check at least one known BPA code from the synthetic fixture
        # (conftest inserts "1" = Ativo Total for 2023-12-31).
        assert "1" in first["accounts"], \
            f"expected BPA code '1' in accounts, got {sorted(first['accounts'])}"
        acct = first["accounts"]["1"]
        assert "label" in acct
        assert "section" in acct
        assert "valor_brl" in acct
        # BPA section classifier maps "1" → "Ativo Total".
        assert acct["section"] == "Ativo Total"

    def test_bpa_no_company(self, financials_env):
        """No company arg → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.bpa import bpa
        result = bpa()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_bpa_no_bpa_data(self, financials_env):
        """Unknown company → either status=not_found OR ok with empty periods.

        The new bpa mode delegates to `complete(grupo="BPA")`, which may
        return either:
          - ``{"status": "not_found", ...}`` when the company doesn't resolve
          - ``{"status": "ok", "periods": []}`` if the company resolves but
            has no BPA rows for the requested period
        Both are acceptable here — the contract is "no BPA data to render".
        """
        from skills.cvm.financials.modes.bpa import bpa
        result = bpa(company="NONEXISTENT")
        # Accept either signal — both mean "no BPA data".
        if result["status"] == "ok":
            assert result.get("periods") == [] or len(result.get("periods", [])) == 0
        else:
            assert result["status"] in ("not_found", "error", "not_synced")

    def test_bpa_quarterly(self, financials_env):
        """period="quarterly" switches to the quarterly shape (4 periods by
        default, quarter labels + quarter numbers populated)."""
        from skills.cvm.financials.modes.bpa import bpa
        result = bpa(company="33000167000101", period="quarterly")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"
        assert isinstance(result["periods"], list)
        # Quarterly returns a list of periods (may be fewer than 4 if ITR is
        # missing); each period that IS present must carry the quarter fields.
        for p in result["periods"]:
            assert "quarter" in p
            assert p["quarter"] in (1, 2, 3, 4)
            assert isinstance(p["accounts"], dict)

    def test_bpa_manifest_has_period_param(self):
        """[v1.12] MANIFEST advertises `period` (string) — NOT the old
        `quarterly=1` int param. This locks the new API contract."""
        from skills.cvm.financials import MANIFEST
        assert "bpa" in MANIFEST["modes"]
        params = MANIFEST["modes"]["bpa"]["params"]
        # The new API exposes `period` as a string ("annual" | "quarterly").
        assert "period" in params
        # The old `quarterly` int param is NOT advertised anymore.
        assert "quarterly" not in params
        # `periods` and `consolidado` are still part of the contract.
        assert "periods" in params
        assert "consolidado" in params
