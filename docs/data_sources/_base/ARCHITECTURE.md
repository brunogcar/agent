# data_sources/_base/ — Cross-Domain Shared Infrastructure

> [Phase 4 Commit 1] Centralizes the SQLite catalog pattern (`connect` / `db_path` /
> `data_dir`) that was duplicated across all 4 data_source domains (bcb, b3, cvm, ddm).

## Why this package exists

Before Phase 4 C1, every data_source domain had its own ~18-line `connect()`
function with the same `mode=ro` URI pattern + `FileNotFoundError` plumbing.
The DDM `_base/catalog_base.py` already factored the DDM-internal version
(7 copies → 1), but the same pattern was still triplicated across CVM / B3 /
BCB. This package is the single canonical home for the cross-domain helpers.

**Scope rule:** only the genuinely cross-domain plumbing (SQLite connection
management) lives here. Domain-specific patterns (sync engines, fetchers,
parsers, schema SQL) stay in their respective domain folders — DDM scrapes
HTML, CVM downloads ZIPs, B3 calls brapi.dev, BCB queries the SGS API.

## Files (2)

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `data_dir`, `db_path`, `connect` for `from data_sources._base import connect` |
| `catalog.py` | The 3 functions themselves |

## Public API

### `data_dir(domain: str) -> Path`

Returns `memory_db/<domain>/` (via `cfg.memory_root`, which reads the
`MEMORY_ROOT` env var — defaults to `<agent_root>/memory_db`). Creates the
directory if missing (idempotent — safe to call on every read or write path).

Resolution chain (unified across all 4 domains as of Phase 4 C4):

1. `core.config.cfg.memory_root / <domain>` — canonical, always set in
   production (the `MEMORY_ROOT` env var defaults to
   `<agent_root>/memory_db` via `core/config_backend/paths.py:38`).
2. `cwd / "memory_db" / <domain>` — fallback for standalone scripts that
   can't import `core.config` (rare; mostly hypothetical).

```python
from data_sources._base import data_dir
p = data_dir("cvm")    # → memory_db/cvm/
```

> **[Phase 4 C4 bugfix]** Previously `data_dir()` consulted a
> `MEMORY_DB_ROOT` env var that was never set anywhere in the repo —
> meaning tests that patched `cfg.memory_root = tmp_path` (the standard
> test pattern) were silently ignored by `_base.data_dir()`. Now it
> consults `cfg.memory_root` (the same source every domain already uses),
> so the resolution chain is unified across DDM / BCB / B3 / CVM / cache.

### `db_path(domain: str, filename: str) -> Path`

Returns `data_dir(domain) / filename`. Convenience wrapper.

```python
from data_sources._base import db_path
p = db_path("sgs", "sgs.db")    # → memory_db/bcb/sgs.db
```

### `connect(path: Path, source_name: str, read_only: bool = True) -> sqlite3.Connection`

Opens a SQLite connection with `row_factory = sqlite3.Row`.

- `read_only=True` (default): uses URI `file:<path>?mode=ro` — fails with
  `FileNotFoundError` if the DB doesn't exist (prevents accidental empty-DB
  creation on the read path).
- `read_only=False`: opens (or creates) the DB for writes. Creates the parent
  directory if needed.

```python
from data_sources._base import db_path, connect
p = db_path("bcb", "sgs.db")
conn = connect(p, "sgs", read_only=True)   # → mode=ro
conn = connect(p, "sgs", read_only=False)  # → write mode (creates if missing)
```

## Migration status

**[Phase 4 C4]** Adopted by all 4 data_source domains (DDM, BCB, B3, CVM) +
the cross-domain engine cache (`data_sources/_cache.py`). Each domain's
`*_data_dir()` / `*_db_path()` / `connect_*()` helpers are now thin
1-line wrappers that delegate to `_base.data_dir(<domain>)` /
`_base.connect(<path>, <source_name>, read_only)`.

| Domain | Files migrated | Wrapper functions |
|--------|----------------|--------------------|
| DDM    | `ddm/_base/catalog_base.py`                          | `ddm_data_dir`, `connect` (the `BaseDDMCatalog` classmethods delegate transitively) |
| BCB    | `bcb/sgs/catalog.py`, `bcb/focus/catalog.py`         | `bcb_data_dir`, `db_path`, `connect` (each file) |
| B3     | `b3/{cotahist,brapi,api,index,dividends}/catalog.py` | `b3_data_dir` / `_db_dir`, `db_path`, `connect` (each file; `dividends` inlines path resolution, `index` keeps private `_db_dir`) |
| CVM    | `cvm/_db.py`                                          | `cvm_db_path`, 8 `<src>_db_path`, 9 `connect_<src>` |
| cache  | `data_sources/_cache.py`                              | `cache_data_dir` |

**Wrapper invariants preserved:**
- Every public name (`connect_dfp`, `bcb_data_dir`, etc.) stays as a
  module-level callable — 93+ mock sites across 30+ test files use
  `monkeypatch.setattr("data_sources.cvm._db.connect_dfp", ...)` (dotted
  string path). All still work.
- Error messages are byte-for-byte identical to pre-refactor (each wrapper
  passes the right `source_name` to `_base.connect`, e.g. `"SGS"` /
  `"Focus"` / `"COTAHIST"` / `"DFP"` / `"B3 dividends"`).
- `connect_dfp` + `connect_itr` preserve the `_ensure_schema(conn)` call
  on first-time DB creation (via an explicit `is_new` check) — the
  empresas + contas + sync_state tables are created exactly when the DB
  file is missing AND we're opening in write mode.
- `connect_bridge` keeps its custom error message
  (`"Run data_source(domain='cvm', sub_domain='bridge', mode='sync') first."`)
  — the standard _base `"Run sync first."` suffix would be misleading for
  the bridge, which has its own dedicated sync entry point. The SQLite
  open part still delegates to `_base.connect`.
- The `b3/dividends/catalog.py:db_path()` had a latent bug (fell back to
  `Path.cwd() / "b3"` instead of `Path.cwd() / "memory_db" / "b3"` when
  `cfg.memory_root` was missing). Migration to `_base.data_dir("b3")`
  fixes this — consistent fallback matching cotahist/brapi/api/index. No
  test caught it because tests always set `cfg.memory_root`.
- The `cvm_db_path()` 5-level walk-up fallback (dead code —
  `cfg.memory_root` is always set in production) is dropped.

**Loc delta:** ~-110 LOC across the 10 source files (smaller than the
investigation's -276 estimate because each wrapper retains an expanded
docstring annotating the migration + the bugfixes).

## See also

- [`data_sources/ddm/_base/ARCHITECTURE.md`](../ddm/_base/ARCHITECTURE.md) — the
  DDM-specific shared infrastructure (catalog/fetcher/sync_engine/status_reporter
  base classes). Phase 3 C1 extraction.
- [`DATA_SOURCES.md`](../../DATA_SOURCES.md) — the data sources layer overview.
- [`STRUCTURE.md`](../../STRUCTURE.md) — full repo layout.

---

*Last updated: 2026-09-15 (Phase 4 C1 — initial creation; Phase 4 C4 — adopted by all 4 domains + cache; `MEMORY_DB_ROOT` env var dropped in favor of `cfg.memory_root`).*
