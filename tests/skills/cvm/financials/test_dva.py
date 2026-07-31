"""Tests for the `dva` mode of skills/cvm/financials.

Covers TestDVAMode (5 tests):
  - test_dva_basic_shape        : default annual call → ok + accounts dict shape
  - test_dva_no_company         : no company arg → status=error
  - test_dva_no_dva_data        : unknown company → not_found OR empty periods
  - test_dva_quarterly          : period="quarterly" → quarterly shape
  - test_dva_manifest_has_period_param : MANIFEST advertises `period` (not `quarterly=1`)

[v1.12 — dashboard reorg] New API: `period="annual"|"quarterly"` + codes in
`modes/_statement_sections.py` (no `_DVA_CODES` export). Uses the shared
`financials_env` fixture from conftest.py.
"""
from __future__ import annotations


class TestDVAMode:
    """Tests for `financials.dva()` — Demonstração do Valor Adicionado (value added statement)."""

    def test_dva_basic_shape(self, financials_env):
        """Default annual call returns the standalone-statement-mode shape.

        Each period carries a dict-keyed `accounts` map
        (``{codigo: {label, section, valor_brl}}``). DVA rows are split into
        two sections: "Geração" (codes 1-7) vs "Distribuição" (codes 8.*).
        """
        from skills.cvm.financials.modes.dva import dva
        result = dva(company="33000167000101")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["statement"] == "DVA"
        assert result["grupo_filter"] == "DVA"
        assert isinstance(result["periods"], list)
        assert len(result["periods"]) >= 1
        first = result["periods"][0]
        assert isinstance(first["data_fim_exerc"], str)
        assert first["data_fim_exerc"].endswith("-12-31")  # annual period
        assert isinstance(first["accounts"], dict)
        # The synthetic DFP fixture inserts "7.08.04" — which the DVA section
        # classifier maps to "Distribuição" (own-capital remuneration).
        if "7.08.04" in first["accounts"]:
            acct = first["accounts"]["7.08.04"]
            assert "label" in acct
            assert "section" in acct
            assert acct["section"] == "Distribuição"
            assert "valor_brl" in acct
        # Any accounts that ARE present must carry label + section + valor_brl.
        for code, acct in first["accounts"].items():
            assert "label" in acct
            assert "section" in acct
            assert acct["section"] in ("Geração", "Distribuição")
            assert "valor_brl" in acct

    def test_dva_no_company(self, financials_env):
        """No company arg → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.dva import dva
        result = dva()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dva_no_dva_data(self, financials_env):
        """Unknown company → either status=not_found OR ok with empty periods.

        The new dva mode delegates to `complete(grupo="DVA")`, which may
        return either:
          - ``{"status": "not_found", ...}`` when the company doesn't resolve
          - ``{"status": "ok", "periods": []}`` if the company resolves but
            has no DVA rows for the requested period
        Both are acceptable here — the contract is "no DVA data to render".
        """
        from skills.cvm.financials.modes.dva import dva
        result = dva(company="NONEXISTENT")
        if result["status"] == "ok":
            assert result.get("periods") == [] or len(result.get("periods", [])) == 0
        else:
            assert result["status"] in ("not_found", "error", "not_synced")

    def test_dva_quarterly(self, financials_env):
        """period="quarterly" switches to the quarterly shape."""
        from skills.cvm.financials.modes.dva import dva
        result = dva(company="33000167000101", period="quarterly")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"
        assert isinstance(result["periods"], list)
        for p in result["periods"]:
            assert "quarter" in p
            assert p["quarter"] in (1, 2, 3, 4)
            assert isinstance(p["accounts"], dict)

    def test_dva_manifest_has_period_param(self):
        """[v1.12] MANIFEST advertises `period` (string) — NOT the old
        `quarterly=1` int param."""
        from skills.cvm.financials import MANIFEST
        assert "dva" in MANIFEST["modes"]
        params = MANIFEST["modes"]["dva"]["params"]
        assert "period" in params
        assert "quarterly" not in params
        assert "periods" in params
        assert "consolidado" in params
