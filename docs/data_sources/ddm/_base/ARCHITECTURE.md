# DDM `_base/` — Architecture

Package: **`data_sources/ddm/_base/`**
Domain: `ddm`
Excluded from sub-domain auto-discovery (the hub skips directories starting
with `_`).

## Purpose

The `_base/` package holds the **shared scaffolding** extracted from the 7
DDM sub-domain source packages (`inflation`, `juros`, `poupanca`, `acoes`,
`dividends`, `fluxo`, `focus`). Each sub-domain's `catalog.py`,
`fetcher.py`, `sync_engine.py`, `status_reporter.py`, and `__init__.py`
imports from `_base/` and keeps only the source-specific code (schema, URL
helpers, parser functions, business logic).

This package was created in **Phase 3, Commit 1** of the code-review-driven
extraction (see `phase3-investigate-ddm-base` + `phase3-commit1-ddm-base`
in `worklog.md`).

## File map (6 files)

```
data_sources/ddm/_base/
├── __init__.py          # re-exports the public API (10 names)
├── catalog_base.py      # API_BASE, ddm_data_dir(), connect(), ensure_schema(),
│                        #   BaseDDMCatalog (config-driven subclass)
├── fetcher_base.py      # CLOUDFRONT_HEADERS, BROWSER_HEADERS, BOT_HEADERS,
│                        #   BaseDDMFetcher (cache + concurrency + httpx.get)
├── sync_base.py         # BaseDDMSyncEngine.sync_single_page + sync_multi_page
│                        #   + _record_sync_state + _progress/_now/_today_date
├── status_base.py       # BaseDDMStatusReporter (path-check + connect +
│                        #   try/except + finally scaffold)
└── route_base.py        # make_ddm_route(sub_domain, mode_map, manifest) factory
```

Total: ~1020 lines of shared infrastructure (replacing ~970 lines of
duplicated code across the 7 sources).

## Public API

```python
from data_sources.ddm._base import (
    # catalog_base
    API_BASE,                # "https://www.dadosdemercado.com.br"
    ddm_data_dir,            # () -> Path (memory_db/ddm/)
    BaseDDMCatalog,          # subclass with DB_FILENAME/SOURCE_NAME/SCHEMA_SQL/INDEX_CATALOG/CATALOG_TABLE

    # fetcher_base
    CLOUDFRONT_HEADERS,      # Chrome 127 + Accept-Encoding (focus variant)
    BROWSER_HEADERS,         # Chrome 127, NO Accept-Encoding (fluxo variant)
    BOT_HEADERS,             # bare 2-header (acoes/dividends/inflation/juros/poupanca)
    BaseDDMFetcher,          # subclass with SOURCE_NAME; provides fetch_page() + clear_cache()

    # sync_base
    BaseDDMSyncEngine,       # subclass with SOURCE_NAME; provides sync_single_page + sync_multi_page

    # status_base
    BaseDDMStatusReporter,   # subclass with SOURCE_NAME + _build_status_dict()

    # route_base
    make_ddm_route,          # factory: (sub_domain, mode_map, manifest) -> route() function
)
```

## How each sub-domain uses `_base/`

### catalog.py

```python
from data_sources.ddm._base.catalog_base import API_BASE, BaseDDMCatalog

INDEX_CATALOG = {...}    # multi-page only
SCHEMA_SQL = """..."""

class _Catalog(BaseDDMCatalog):
    DB_FILENAME = "inflation.db"
    SOURCE_NAME = "inflation"
    SCHEMA_SQL = SCHEMA_SQL
    INDEX_CATALOG = INDEX_CATALOG       # {} for single-page sources
    CATALOG_TABLE = "index_catalog"     # "" for single-page sources

# Re-export as module-level callables for backward compat:
db_path = _Catalog.db_path
connect = _Catalog.connect
ensure_schema = _Catalog.ensure_schema
```

### fetcher.py

```python
from data_sources.ddm._base.fetcher_base import BOT_HEADERS, BaseDDMFetcher

class _Fetcher(BaseDDMFetcher):
    SOURCE_NAME = "inflation"     # for "[ddm.inflation]" log prefix

def fetch_index_page(slug, force=False):
    return _Fetcher.fetch_page(
        url=index_url(slug),
        cache_key=f"page:{slug}",
        headers=BOT_HEADERS,       # or BROWSER_HEADERS / CLOUDFRONT_HEADERS
        slug=slug,                 # None for single-page sources
        force=force,
    )
```

### sync_engine.py

```python
from data_sources.ddm._base.sync_base import BaseDDMSyncEngine

class _SyncEngine(BaseDDMSyncEngine):
    SOURCE_NAME = "inflation"

def sync_all(force=False):
    return _SyncEngine.sync_multi_page(    # or sync_single_page for acoes/dividends/fluxo/focus
        catalog=INDEX_CATALOG,
        fetch_fn=fetch_index_page,
        parse_pipeline_fn=parse_historical_table,
        connect_fn=connect,
        ensure_schema_fn=ensure_schema,
        insert_sql=_INSERT_SQL,
        row_mapper=_row_mapper,
        force=force,
    )
```

### status_reporter.py

```python
from data_sources.ddm._base.status_base import BaseDDMStatusReporter

class _StatusReporter(BaseDDMStatusReporter):
    SOURCE_NAME = "inflation"

    @classmethod
    def _build_status_dict(cls, conn, path, db_size_kb):
        # source-specific queries here
        return {...}

def status():
    return _StatusReporter.status(db_path, connect)
```

### __init__.py

```python
from data_sources.ddm._base.route_base import make_ddm_route

MANIFEST = {...}

_MODE_MAP = {
    "sync_all":   ("data_sources.ddm.inflation.sync_engine",     "sync_all"),
    "sync_index": ("data_sources.ddm.inflation.sync_engine",     "sync_index"),
    ...
}

route = make_ddm_route(
    sub_domain="inflation",
    mode_map=_MODE_MAP,
    manifest=MANIFEST,
)
```

## Header constants

| Constant              | Used by                                         | Accept-Encoding? | Bot UA? |
| --------------------- | ----------------------------------------------- | ---------------- | ------- |
| `CLOUDFRONT_HEADERS`  | `focus` (CloudFront WAF, strictest)             | Yes              | No (Chrome 127) |
| `BROWSER_HEADERS`     | `fluxo` (CloudFront WAF, accepts leaner set)    | No               | No (Chrome 127) |
| `BOT_HEADERS`         | `acoes`, `dividends`, `inflation`, `juros`, `poupanca` | N/A        | Yes (`ddm-fetcher/1.0`) |

The `Accept-Encoding` divergence between `CLOUDFRONT_HEADERS` (focus) and
`BROWSER_HEADERS` (fluxo) is intentional and preserved from the
pre-extraction code (verified by reading both files). The focus endpoint
requires the full header set including `Accept-Encoding: gzip, deflate, br`;
the fluxo endpoint accepts the leaner set without it (avoids the br/gzip
decode path).

## Sync patterns

The 7 sources split into two clean groups:

| Group        | Sources                          | sync_all() pattern                       | B4 stale-row cleanup? |
| ------------ | -------------------------------- | ---------------------------------------- | --------------------- |
| Multi-page   | `inflation`, `juros`, `poupanca` | TPE (max_workers=3) over catalog slugs   | NO (history accumulates by `(slug, ref_date)`) |
| Single-page  | `acoes`, `dividends`             | Single HTTP call + DELETE + INSERT       | YES (full-refresh snapshot) |
| Single-page  | `fluxo`                          | Single HTTP call + DELETE + INSERT       | YES (NEW in Phase 3 Commit 1 — daily full-refresh snapshot) |
| Single-page  | `focus`                          | Single HTTP call + INSERT (no DELETE)    | NO (history accumulates by `(year, indicator, ref_date)`) |

The `sync_single_page(...)` method takes a `full_refresh: bool` flag and a
`table_name: str | None` — when `full_refresh=True`, it runs
`DELETE FROM <table_name>` before the INSERT batch. This is the **B4
stale-row cleanup** pattern from Phase 2 (originally added to acoes +
dividends; extended to fluxo in Phase 3 Commit 1).

## Auto-discovery exclusion

`data_sources/ddm/__init__.py` auto-discovers sub-domains by scanning
`data_sources/ddm/` for subdirectories with `__init__.py` + `MANIFEST` +
`route()`. The scan skips directories starting with `_` or `.` (line 45):

```python
if not item.is_dir() or item.name.startswith(("_", ".")):
    continue
```

So `_base/` is automatically excluded — no hub change was needed. The
`_base/` package does NOT define a `MANIFEST` or `route()`, so even if
the scan did pick it up, it would be filtered out by the MANIFEST check.

## See also

- [`docs/data_sources/ddm/<source>/ARCHITECTURE.md`](../) — per-source
  architecture docs (each mentions the `_base/` extraction).
- `worklog.md` → `phase3-investigate-ddm-base` (the duplication analysis
  that motivated this extraction).
- `worklog.md` → `phase3-commit1-ddm-base` (this commit's work record).
