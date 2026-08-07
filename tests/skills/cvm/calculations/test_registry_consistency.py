"""Cross-registry consistency tests.

[v1.18 hardening] Regression guards for the engine/metric registry.
Catches:
  - Duplicate registered names (would raise ValueError at import time)
  - Failed auto-discovery imports (broken engine/metric files)
  - Engine/metric count regressions (unexpected drops)
  - Missing required engines/metrics

Suggested by external LLM review (Claude 1, Claude 2, Qwen).
"""
from __future__ import annotations

import pytest


class TestRegistryConsistency:
    """Verify the registry is in a consistent state."""

    def test_all_engines_load_without_error(self):
        """Every engine file should import + register without raising.
        If _auto_discover() skipped any file due to ImportError, it will
        appear in _auto_discover._failed."""
        from skills.cvm.calculations._registry import _auto_discover
        failed = getattr(_auto_discover, "_failed", [])
        assert failed == [], f"Failed imports: {failed}"

    def test_no_duplicate_engine_names(self):
        """register_engine() raises on duplicates, but this test documents
        the invariant explicitly. If a file-move refactor leaves an old
        file behind, this test catches it before the ValueError does."""
        from skills.cvm.calculations._registry import list_engines, ENGINES
        names = list_engines()
        # ENGINES is a dict, so names are already unique — but verify the
        # count matches (catches any future change to the data structure)
        assert len(names) == len(ENGINES), "Engine name count mismatch"
        # Verify no None or empty-string names
        assert all(n for n in names), "Empty engine name found"

    def test_no_duplicate_metric_names(self):
        """Same check for metrics."""
        from skills.cvm.calculations._registry import list_metrics, METRICS
        names = list_metrics()
        assert len(names) == len(METRICS), "Metric name count mismatch"
        assert all(n for n in names), "Empty metric name found"

    def test_engine_count_above_threshold(self):
        """Engine count should never drop below 39 (current count after
        v1.16/v1.17 reorganization). If a file is accidentally deleted,
        this test catches it."""
        from skills.cvm.calculations._registry import list_engines
        names = list_engines()
        assert len(names) >= 39, (
            f"Engine count dropped to {len(names)} — expected >= 39. "
            f"Missing: check _auto_discover._failed for import errors."
        )

    def test_metric_count_above_threshold(self):
        """Metric count should never drop below 54 (current count)."""
        from skills.cvm.calculations._registry import list_metrics
        names = list_metrics()
        assert len(names) >= 54, (
            f"Metric count dropped to {len(names)} — expected >= 54. "
            f"Missing: check _auto_discover._failed for import errors."
        )

    def test_all_engine_subfolders_have_init(self):
        """Every engine subfolder must have __init__.py for Python to
        treat it as a package."""
        from pathlib import Path
        engines_dir = Path(__file__).parent.parent.parent.parent.parent / \
            "skills" / "cvm" / "calculations" / "engines"
        for sub_dir in sorted(engines_dir.iterdir()):
            if sub_dir.is_dir() and not sub_dir.name.startswith("__"):
                init_file = sub_dir / "__init__.py"
                assert init_file.exists(), (
                    f"Missing __init__.py in engines/{sub_dir.name}/"
                )

    def test_required_engines_present(self):
        """Spot-check that key engines are registered after the
        bpa/bpp/dre/dfc/dva reorganization."""
        from skills.cvm.calculations._registry import list_engines
        engines = set(list_engines())
        # Top-level
        assert "beta" in engines
        assert "price" in engines
        assert "shares" in engines
        assert "selic" in engines
        assert "dividends" in engines
        # BPA
        assert "cash" in engines
        assert "total_assets" in engines
        assert "receivables" in engines
        # BPP
        assert "pl" in engines
        assert "debt" in engines
        # DRE
        assert "revenue" in engines
        assert "earnings" in engines
        assert "ebit" in engines
        # DFC
        assert "operating_cf" in engines
        assert "capex" in engines
        assert "da" in engines
        # DVA (generation-side with va_ prefix)
        assert "va_revenue" in engines
        assert "va_inputs" in engines
        # DVA (distribution-side)
        assert "value_added" in engines
        assert "dividends_paid" in engines

    def test_required_metrics_present(self):
        """Spot-check that key metrics are registered."""
        from skills.cvm.calculations._registry import list_metrics
        metrics = set(list_metrics())
        required = [
            "roe", "roa", "roic", "gross_margin", "net_margin",
            "ev_ebitda", "ev_ebit", "p_ebit", "p_ebitda",
            "lpa", "vpa", "dpa", "rps",
            "debt_equity", "net_debt_ebitda", "interest_coverage",
            "current_ratio", "quick_ratio",
            "revenue_growth_3m", "revenue_growth_1y", "revenue_growth_5y",
            "net_income_growth_3m", "net_income_growth_1y", "net_income_growth_5y",
            "coe", "beta",
            "graham_number", "magic_number",
            "effective_tax_rate",
        ]
        missing = [m for m in required if m not in metrics]
        assert missing == [], f"Missing required metrics: {missing}"

    def test_all_engine_categories_represented(self):
        """Verify all expected engine categories are present."""
        from skills.cvm.calculations._registry import list_engine_categories
        cats = set(list_engine_categories())
        expected = {"market", "shares", "dre", "bpa", "bpp", "dfc", "dva"}
        missing = expected - cats
        assert not missing, f"Missing engine categories: {missing}"

    def test_all_metric_categories_represented(self):
        """Verify all expected metric categories are present."""
        from skills.cvm.calculations._registry import list_metric_categories
        cats = set(list_metric_categories())
        expected = {
            "profitability", "valuation", "per_share", "leverage",
            "efficiency", "growth", "liquidity", "market", "tax",
        }
        missing = expected - cats
        assert not missing, f"Missing metric categories: {missing}"
