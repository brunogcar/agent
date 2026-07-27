"""Engine registration tests for the calculations package.

Merged from two prior test files (formerly TestNewEngineRegistration in
test_roa_margins.py + TestNewEngineRegistration in test_tier56_metrics.py).

Covers registration + category/quantity metadata for every engine that
was added in tiers 3, 5, and 6:
  - assets (bpa)
  - gross_profit (dre)
  - ebit (dre)
  - capex (dfc)
  - total_assets (bpa)
  - current_liabilities (bpp)

Plus total engine/metric counts (16 engines, 17 metrics as of v2.1).
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Engine registration: bpa / dre (v1.7 batch)
# ════════════════════════════════════════════════════════════════════════════

class TestEngineRegistration:
    """Engines added in v1.7: assets, gross_profit, ebit."""

    def test_assets_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "assets" in ENGINES
        assert ENGINES["assets"].category == "bpa"
        assert ENGINES["assets"].quantity == "assets"

    def test_gross_profit_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "gross_profit" in ENGINES
        assert ENGINES["gross_profit"].category == "dre"
        assert ENGINES["gross_profit"].quantity == "ttm_gp"

    def test_ebit_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "ebit" in ENGINES
        assert ENGINES["ebit"].category == "dre"
        assert ENGINES["ebit"].quantity == "ttm_ebit"

    def test_bpa_category_has_assets(self):
        from skills.cvm.calculations._registry import list_engines
        bpa_engines = list_engines(category="bpa")
        assert "assets" in bpa_engines

    def test_dre_category_has_engines(self):
        from skills.cvm.calculations._registry import list_engines
        dre_engines = list_engines(category="dre")
        assert "earnings" in dre_engines
        assert "revenue" in dre_engines
        assert "gross_profit" in dre_engines
        assert "ebit" in dre_engines
        assert len(dre_engines) >= 4  # v1.7 had 4, v1.8 added tax (5)


# ════════════════════════════════════════════════════════════════════════════
# Engine registration: dfc / bpa / bpp (v1.9-2.1 batch)
# ════════════════════════════════════════════════════════════════════════════

class TestEngineRegistrationExtended:
    """Engines added in v2.1: capex, total_assets, current_liabilities."""

    def test_capex_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "capex" in ENGINES
        assert ENGINES["capex"].category == "dfc"
        assert ENGINES["capex"].quantity == "ttm_capex"

    def test_total_assets_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "total_assets" in ENGINES
        assert ENGINES["total_assets"].category == "bpa"
        assert ENGINES["total_assets"].quantity == "total_assets"

    def test_current_liabilities_registered(self):
        from skills.cvm.calculations._registry import ENGINES
        assert "current_liabilities" in ENGINES
        assert ENGINES["current_liabilities"].category == "bpp"
        assert ENGINES["current_liabilities"].quantity == "current_liabilities"

    def test_total_engines_is_16(self):
        from skills.cvm.calculations._registry import list_engines
        assert len(list_engines()) == 16

    def test_total_metrics_is_17(self):
        from skills.cvm.calculations._registry import list_metrics
        assert len(list_metrics()) == 17
