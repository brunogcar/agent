"""Import smoke test — verifies all skill mode files + adapter files import cleanly.

Catches stale import paths (e.g., `from skills.cvm.dividends.dividends import ...`
after a file split) without needing fixture-heavy test suites to run.

This test does NOT call any function — it only imports modules and checks
for ImportError. It runs in <1 second.
"""
import importlib
import pkgutil
from pathlib import Path

import pytest


def _import_all_modules(package_name: str) -> list[str]:
    """Import all submodules of a package recursively. Returns list of errors."""
    errors = []
    try:
        pkg = importlib.import_module(package_name)
    except Exception as e:
        return [f"{package_name}: {e}"]

    for finder, name, ispkg in pkgutil.walk_packages(pkg.__path__, prefix=f"{package_name}."):
        try:
            importlib.import_module(name)
        except Exception as e:
            errors.append(f"{name}: {e}")
    return errors


class TestImportSmoke:
    """Verify all CVM skill modules + report adapters import without errors."""

    @pytest.mark.parametrize("skill", [
        "skills.cvm.financials",
        "skills.cvm.valuation",
        "skills.cvm.backtest",
        "skills.cvm.comparison",
        "skills.cvm.dividends",
        "skills.cvm.governance",
        "skills.cvm.historical",
        "skills.cvm.calculations",
        # [v1.8] Added the 4 skills that were split in the modular refactor.
        # Without these, a stale import path in screener/shareholders/insider/investsite
        # would go undetected until a user calls the skill.
        "skills.cvm.screener",
        "skills.cvm.shareholders",
        "skills.cvm.insider",
        "skills.investsite",
    ])
    def test_skill_imports(self, skill):
        errors = _import_all_modules(skill)
        assert not errors, f"Import failures in {skill}:\n" + "\n".join(errors)

    def test_adapters_import(self):
        errors = _import_all_modules("tools.report_ops.adapters")
        assert not errors, f"Import failures in adapters:\n" + "\n".join(errors)
