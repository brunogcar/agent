"""data_sources/ddm/_base/__init__.py -- Shared infrastructure for DDM sources.

The `_base/` package holds the shared scaffolding extracted from the 7 DDM
sub-domain source packages (inflation, juros, poupanca, acoes, dividends,
fluxo, focus). Each sub-domain's `catalog.py`, `fetcher.py`, `sync_engine.py`,
`status_reporter.py`, and `__init__.py` imports from here and keeps only
the source-specific code (schema, URL helpers, parser functions, business
logic).

This package is excluded from the DDM domain hub's auto-discovery (the
hub skips directories starting with `_`), so it does NOT register a
sub-domain MANIFEST.

Public API (re-exported here for convenience):

  From catalog_base:
    - API_BASE
    - ddm_data_dir
    - BaseDDMCatalog

  From fetcher_base:
    - CLOUDFRONT_HEADERS  (Chrome 127 + Accept-Encoding; focus variant)
    - BROWSER_HEADERS     (Chrome 127, no Accept-Encoding; fluxo variant)
    - BOT_HEADERS         (bare 2-header; acoes/dividends/inflation/juros/poupanca)
    - BaseDDMFetcher

  From sync_base:
    - BaseDDMSyncEngine

  From status_base:
    - BaseDDMStatusReporter

  From route_base:
    - make_ddm_route

[Phase 3, Commit 1] Created as part of the code-review-driven extraction.
See phase3-investigate-ddm-base + phase3-commit1-ddm-base in worklog.md.
"""

from __future__ import annotations

from data_sources.ddm._base.catalog_base import (
    API_BASE,
    BaseDDMCatalog,
    ddm_data_dir,
)
from data_sources.ddm._base.fetcher_base import (
    BOT_HEADERS,
    BROWSER_HEADERS,
    CLOUDFRONT_HEADERS,
    BaseDDMFetcher,
)
from data_sources.ddm._base.route_base import make_ddm_route
from data_sources.ddm._base.status_base import BaseDDMStatusReporter
from data_sources.ddm._base.sync_base import BaseDDMSyncEngine

__all__ = [
    # catalog_base
    "API_BASE",
    "BaseDDMCatalog",
    "ddm_data_dir",
    # fetcher_base
    "BOT_HEADERS",
    "BROWSER_HEADERS",
    "CLOUDFRONT_HEADERS",
    "BaseDDMFetcher",
    # sync_base
    "BaseDDMSyncEngine",
    # status_base
    "BaseDDMStatusReporter",
    # route_base
    "make_ddm_route",
]
