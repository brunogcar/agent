"""Shared fixtures for ALL B3 skill tests.

Sets environment variables + mocks slow cross-skill calls (brapi, sgs,
investsite) so dashboard tests don't hit real DBs/HTTP.

Individual skill conftests (price, options, term) add their own
skill-specific fixtures on top of this.
"""
from __future__ import annotations
import os

import pytest
from unittest.mock import patch

# Set env vars at module level (before any test or core.config import).
os.environ.setdefault("PLANNER_MODEL", "test")
os.environ.setdefault("PLANNER_PROVIDER", "test")
os.environ.setdefault("EXECUTOR_MODEL", "test")
os.environ.setdefault("EXECUTOR_PROVIDER", "test")
os.environ.setdefault("CVM_SKIP_SYNC", "1")
os.environ.setdefault("CVM_SKIP_HTML", "1")


@pytest.fixture(autouse=True)
def mock_b3_slow_calls(monkeypatch):
    """[fast-tests] Mock slow calls that B3 dashboard tests don't need.

    - brapi quote/history → returns dummy data (avoids real HTTP to brapi.dev)
    - investsite fetch_page → returns empty HTML (avoids real HTTP + login)
    - build_company_header → returns dummy company (avoids bridge DB)
    - build_price_chart → returns None (avoids brapi HTTP for price history)
    """
    # Mock brapi — b3/price dashboard calls latest_quote from cotahist
    # (already mocked by price conftest), but some paths also call brapi.
    try:
        monkeypatch.setattr(
            "data_sources.b3.brapi.query_engine.quote",
            lambda ticker="", force=False: {"status": "error", "error": "mocked"},
        )
    except (ImportError, AttributeError):
        pass

    # Mock investsite — valuation fetchers import it as fallback.
    try:
        monkeypatch.setattr(
            "skills.investsite.fetcher.fetch_page",
            lambda *a, **kw: "<html>mocked</html>",
        )
    except (ImportError, AttributeError):
        pass

    # Mock build_company_header + build_price_chart (shared CVM report helpers
    # imported by some B3 dashboards via cross-skill integration).
    try:
        monkeypatch.setattr(
            "skills.cvm._shared_report.company_header.build_company_header",
            lambda c: {"name": "TEST", "cnpj": c, "ticker": "TEST4"},
        )
    except (ImportError, AttributeError):
        pass

    try:
        monkeypatch.setattr(
            "skills.cvm._shared_report.price_chart.build_price_chart",
            lambda c: None,
        )
    except (ImportError, AttributeError):
        pass
