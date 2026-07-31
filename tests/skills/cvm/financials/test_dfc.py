"""Tests for the `dfc` mode of skills/cvm/financials.

Covers TestDFCMode (7 tests):
  - test_dfc_basic_shape                  : default annual call → ok + accounts dict shape
  - test_dfc_no_company                   : no company arg → status=error
  - test_dfc_no_dfc_data                  : unknown company → not_found OR empty periods
  - test_dfc_quarterly                    : period="quarterly" → quarterly shape
  - test_dfc_manifest_has_period_param    : MANIFEST advertises `period` (not `quarterly=1`)
  - test_dfc_extract_metrics_new_keys     : _extract_metrics exposes `variacao_cambial`
  - test_dfc_extract_metrics_6_01_04_not_da: 6.01.04 is NOT a D&A fallback anymore

[v1.12 — dashboard reorg] New API: `period="annual"|"quarterly"` + codes in
`modes/_statement_sections.py` (no `_DFC_CODES` export).

[v1.5 fix-tests-version] _extract_metrics gains a `variacao_cambial` key
sourced from DFC code 6.01.04, AND 6.01.04 is no longer used as a D&A
fallback (it is "Variações Cambiais", not depreciation & amortization).

Uses the shared `financials_env` fixture from conftest.py for the DB-backed
tests. The two `_extract_metrics` tests are pure-Python (no fixture needed).
"""
from __future__ import annotations


class TestDFCMode:
    """Tests for `financials.dfc()` — Demonstração dos Fluxos de Caixa (cash flow)."""

    def test_dfc_basic_shape(self, financials_env):
        """Default annual call returns the standalone-statement-mode shape.

        Each period carries a dict-keyed `accounts` map
        (``{codigo: {label, section, valor_brl}}``). DFC rows are split into
        three sections: "Operações" (6.01.*) / "Investimento" (6.02.*) /
        "Financiamento" (6.03.*).
        """
        from skills.cvm.financials.modes.dfc import dfc
        result = dfc(company="33000167000101")
        assert result["status"] == "ok"
        assert result["period_type"] == "annual"
        assert result["statement"] == "DFC"
        # The dfc() mode fetches grupo="DFC_MI" — the reshape helper copies
        # grupo_filter through from the complete() raw result, so the value
        # here is "DFC_MI" (NOT "DFC"). Statement label is "DFC".
        assert result["grupo_filter"] in ("DFC_MI", "DFC")
        assert isinstance(result["periods"], list)
        assert len(result["periods"]) >= 1
        first = result["periods"][0]
        assert isinstance(first["data_fim_exerc"], str)
        assert first["data_fim_exerc"].endswith("-12-31")  # annual period
        assert isinstance(first["accounts"], dict)
        # Synthetic fixture inserts DFC codes 6.01, 6.02, 6.03, 6.01.01.02.
        # Spot-check at least one of the FCO/FCI/FCF codes is present.
        dfc_codes_present = {c for c in first["accounts"]
                             if c.startswith("6.0")}
        assert dfc_codes_present, \
            f"expected at least one DFC code (6.0*) in accounts, got {sorted(first['accounts'])}"
        # Section classifier maps 6.01.* → Operações, 6.02.* → Investimento,
        # 6.03.* → Financiamento.
        for code, acct in first["accounts"].items():
            assert "label" in acct
            assert "section" in acct
            assert "valor_brl" in acct
            if code.startswith("6.01"):
                assert acct["section"] == "Operações"
            elif code.startswith("6.02"):
                assert acct["section"] == "Investimento"
            elif code.startswith("6.03"):
                assert acct["section"] == "Financiamento"

    def test_dfc_no_company(self, financials_env):
        """No company arg → status=error (does NOT touch DBs)."""
        from skills.cvm.financials.modes.dfc import dfc
        result = dfc()
        assert result["status"] == "error"
        assert "company is required" in result["error"]

    def test_dfc_no_dfc_data(self, financials_env):
        """Unknown company → either status=not_found OR ok with empty periods.

        The new dfc mode delegates to `complete(grupo="DFC_MI")`, which may
        return either:
          - ``{"status": "not_found", ...}`` when the company doesn't resolve
          - ``{"status": "ok", "periods": []}`` if the company resolves but
            has no DFC rows for the requested period
        Both are acceptable here — the contract is "no DFC data to render".
        """
        from skills.cvm.financials.modes.dfc import dfc
        result = dfc(company="NONEXISTENT")
        if result["status"] == "ok":
            assert result.get("periods") == [] or len(result.get("periods", [])) == 0
        else:
            assert result["status"] in ("not_found", "error", "not_synced")

    def test_dfc_quarterly(self, financials_env):
        """period="quarterly" switches to the quarterly shape."""
        from skills.cvm.financials.modes.dfc import dfc
        result = dfc(company="33000167000101", period="quarterly")
        assert result["status"] == "ok"
        assert result["period_type"] == "quarterly"
        assert isinstance(result["periods"], list)
        for p in result["periods"]:
            assert "quarter" in p
            assert p["quarter"] in (1, 2, 3, 4)
            assert isinstance(p["accounts"], dict)

    def test_dfc_manifest_has_period_param(self):
        """[v1.12] MANIFEST advertises `period` (string) — NOT the old
        `quarterly=1` int param."""
        from skills.cvm.financials import MANIFEST
        assert "dfc" in MANIFEST["modes"]
        params = MANIFEST["modes"]["dfc"]["params"]
        assert "period" in params
        assert "quarterly" not in params
        assert "periods" in params
        assert "consolidado" in params

    # ───────────────────────────────────────────────────────────────────────
    # _extract_metrics regressions (v1.5 fix-tests-version)
    # ───────────────────────────────────────────────────────────────────────

    def test_dfc_extract_metrics_new_keys(self):
        """[v1.5 fix-tests-version] _extract_metrics returns a
        `variacao_cambial` key sourced from DFC code 6.01.04.

        Prior to this fix, _extract_metrics did NOT have a `variacao_cambial`
        key — callers that tried to read ``m["variacao_cambial"]`` got a
        KeyError. The new key is always present (None when 6.01.04 is
        missing), so the DFC dashboard can render the FX variation row
        independently from D&A.
        """
        from skills.cvm.financials.fetchers import _extract_metrics
        # Empty input → all keys present, variacao_cambial=None.
        m = _extract_metrics({})
        assert "variacao_cambial" in m
        assert m["variacao_cambial"] is None
        # 6.01.04 present → variacao_cambial carries its value.
        m = _extract_metrics({"6.01.04": 2000.0})
        assert m["variacao_cambial"] == 2000.0
        # Other keys are unchanged.
        assert "da" in m
        assert "fco" in m
        assert "fci" in m
        assert "fcf" in m

    def test_dfc_extract_metrics_6_01_04_not_da(self):
        """[v1.5 fix-tests-version] 6.01.04 is NOT a D&A fallback anymore.

        The 6.01.04 code is "Variações Cambiais" (foreign exchange variations)
        under DFC operating cash flow — NOT depreciation & amortization.
        Previously _extract_metrics fell back to 6.01.04 when both 6.01.01.02
        (DFC_MI indirect) and 6.02.01.02 (DFC_MD direct) were missing,
        incorrectly inflating EBITDA for filers that reported FX variations
        but no D&A in their indirect-method DFC.

        After the fix:
          - When only 6.01.04 is present: `da` is None (NOT 2000.0).
          - The 6.01.04 value surfaces on the dedicated `variacao_cambial`
            key instead (so the dashboard can still display it as an FX row).
        """
        from skills.cvm.financials.fetchers import _extract_metrics
        vals = {"6.01.04": 2000.0}  # no 6.01.01.02, no 6.02.01.02
        m = _extract_metrics(vals)
        # 6.01.04 is FX variation, not D&A → `da` must be None.
        assert m["da"] is None, \
            f"6.01.04 should NOT be used as D&A fallback, got da={m['da']}"
        # The value surfaces on variacao_cambial instead.
        assert m["variacao_cambial"] == 2000.0
