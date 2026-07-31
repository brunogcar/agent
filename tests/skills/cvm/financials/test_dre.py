"""Tests for the `dre` mode of skills/cvm/financials.

Covers TestDREMode (5 tests):
  - test_dre_basic_shape        : default annual call → ok + accounts dict shape
  - test_dre_no_company         : no company arg → status=error
  - test_dre_no_dre_data        : unknown company → not_found OR empty periods
  - test_dre_quarterly          : period="quarterly" → quarterly shape
  - test_dre_manifest_has_period_param : MANIFEST advertises `period` (not `quarterly=1`)

[v1.12 — dashboard reorg] New API: `period="annual"|"quarterly"` + codes in
`modes/_statement_sections.py` (no `_DRE_CODES` export). Uses the shared
`financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestDREMode:
    """Tests for `financials.dre()` — Demonstração do Resultado do Exercício (income statement)."""

    def test_dre_basic_shape(self, financials_env):
        """Default annual call returns the standalone-statement-mode shape.

        Each period carries a dict-keyed `accounts` map
        (``{codigo: {label, section, valor_brl}}``). All DRE rows share the
        same ``section == "DRE"`` (single-section statement).
        """
        from skills.cvm.financials.modes.dre import dre
        result = dre(company="33000167000101")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["statement"] == "DRE"
        assert result["grupo_filter"] == "DRE"
        assert isinstance(result["periods"], list)
        assert len(result["periods"]) >= 1
        first = result["periods"][0]
        assert isinstance(first["data_fim_exerc"], str)
        assert first["data_fim_exerc"].endswith("-12-31")  # annual period
        assert isinstance(first["accounts"], dict)
        # Synthetic fixture inserts DRE codes 3.01, 3.03, 3.05, 3.06, 3.11.
        # Spot-check that "3.01" (Receita Líquida) is present.
        assert "3.01" in first["accounts"], \
            f"expected DRE code '3.01' in accounts, got {sorted(first['accounts'])}"
        # All DRE rows share section "DRE" (single-section classifier).
        for code, acct in first["accounts"].items():
            assert "label" in acct
            assert "section" in acct
            assert acct["section"] == "DRE"
            assert "valor_brl" in acct

    def test_dre_no_company(self, financials_env):
        """No company arg → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.dre import dre
        result = dre()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dre_no_dre_data(self, financials_env):
        """Unknown company → either status=not_found OR ok with empty periods.

        The new dre mode delegates to `complete(grupo="DRE")`, which may
        return either:
          - ``{"status": "not_found", ...}`` when the company doesn't resolve
          - ``{"status": "ok", "periods": []}`` if the company resolves but
            has no DRE rows for the requested period
        Both are acceptable here — the contract is "no DRE data to render".
        """
        from skills.cvm.financials.modes.dre import dre
        result = dre(company="NONEXISTENT")
        if result["status"] == "ok":
            assert result.get("periods") == [] or len(result.get("periods", [])) == 0
        else:
            assert result["status"] in ("not_found", "error", "not_synced")

    def test_dre_quarterly(self, financials_env):
        """period="quarterly" switches to the quarterly shape."""
        from skills.cvm.financials.modes.dre import dre
        result = dre(company="33000167000101", period="quarterly")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"
        assert isinstance(result["periods"], list)
        for p in result["periods"]:
            assert "quarter" in p
            assert p["quarter"] in (1, 2, 3, 4)
            assert isinstance(p["accounts"], dict)

    def test_dre_manifest_has_period_param(self):
        """[v1.12] MANIFEST advertises `period` (string) — NOT the old
        `quarterly=1` int param."""
        from skills.cvm.financials import MANIFEST
        assert "dre" in MANIFEST["modes"]
        params = MANIFEST["modes"]["dre"]["params"]
        assert "period" in params
        assert "quarterly" not in params
        assert "periods" in params
        assert "consolidado" in params
