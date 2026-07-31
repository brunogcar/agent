"""Tests for the `bpp` mode of skills/cvm/financials.

Covers TestBPPMode (5 tests):
  - test_bpp_basic_shape        : default annual call → ok + accounts dict shape
  - test_bpp_no_company         : no company arg → status=error
  - test_bpp_no_bpp_data        : unknown company → not_found OR empty periods
  - test_bpp_quarterly          : period="quarterly" → quarterly shape
  - test_bpp_manifest_has_period_param : MANIFEST advertises `period` (not `quarterly=1`)

[v1.12 — dashboard reorg] New API: `period="annual"|"quarterly"` + codes in
`modes/_statement_sections.py` (no `_BPP_CODES` export). Uses the shared
`financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestBPPMode:
    """Tests for `financials.bpp()` — Balance Patrimonial Passivo (liabilities + equity)."""

    def test_bpp_basic_shape(self, financials_env):
        """Default annual call returns the standalone-statement-mode shape.

        Each period carries a dict-keyed `accounts` map
        (``{codigo: {label, section, valor_brl}}``).
        """
        from skills.cvm.financials.modes.bpp import bpp
        result = bpp(company="33000167000101")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["statement"] == "BPP"
        assert result["grupo_filter"] == "BPP"
        assert isinstance(result["periods"], list)
        assert len(result["periods"]) >= 1
        first = result["periods"][0]
        assert isinstance(first["data_fim_exerc"], str)
        assert first["data_fim_exerc"].endswith("-12-31")  # annual period
        assert isinstance(first["accounts"], dict)
        # The synthetic DFP fixture inserts "2" = Passivo Total + "2.03" = PL.
        assert "2" in first["accounts"] or "2.03" in first["accounts"], \
            f"expected BPP codes '2' or '2.03' in accounts, got {sorted(first['accounts'])}"
        # Verify the section classifier for at least one code.
        for code, acct in first["accounts"].items():
            assert "label" in acct
            assert "section" in acct
            assert "valor_brl" in acct
            # BPP sections: Passivo Total / Passivo Circulante / Passivo Não
            # Circulante / Patrimônio Líquido. "2" maps to "Passivo Total".
            if code == "2":
                assert acct["section"] == "Passivo Total"
            if code.startswith("2.03"):
                assert acct["section"] == "Patrimônio Líquido"

    def test_bpp_no_company(self, financials_env):
        """No company arg → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.bpp import bpp
        result = bpp()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_bpp_no_bpp_data(self, financials_env):
        """Unknown company → either status=not_found OR ok with empty periods.

        The new bpp mode delegates to `complete(grupo="BPP")`, which may
        return either:
          - ``{"status": "not_found", ...}`` when the company doesn't resolve
          - ``{"status": "ok", "periods": []}`` if the company resolves but
            has no BPP rows for the requested period
        Both are acceptable here — the contract is "no BPP data to render".
        """
        from skills.cvm.financials.modes.bpp import bpp
        result = bpp(company="NONEXISTENT")
        if result["status"] == "ok":
            assert result.get("periods") == [] or len(result.get("periods", [])) == 0
        else:
            assert result["status"] in ("not_found", "error", "not_synced")

    def test_bpp_quarterly(self, financials_env):
        """period="quarterly" switches to the quarterly shape."""
        from skills.cvm.financials.modes.bpp import bpp
        result = bpp(company="33000167000101", period="quarterly")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"
        assert isinstance(result["periods"], list)
        for p in result["periods"]:
            assert "quarter" in p
            assert p["quarter"] in (1, 2, 3, 4)
            assert isinstance(p["accounts"], dict)

    def test_bpp_manifest_has_period_param(self):
        """[v1.12] MANIFEST advertises `period` (string) — NOT the old
        `quarterly=1` int param."""
        from skills.cvm.financials import MANIFEST
        assert "bpp" in MANIFEST["modes"]
        params = MANIFEST["modes"]["bpp"]["params"]
        assert "period" in params
        assert "quarterly" not in params
        assert "periods" in params
        assert "consolidado" in params
