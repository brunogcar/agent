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

Returns `memory_db/<domain>/` (or `$MEMORY_DB_ROOT/<domain>/` if the env
var is set). Creates the directory if missing (idempotent — safe to call on
every read or write path).

```python
from data_sources._base import data_dir
p = data_dir("cvm")    # → memory_db/cvm/
```

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

This package is **newly created** in Phase 4 C1. The existing domain-specific
catalog helpers (e.g. `data_sources/ddm/_base/catalog_base.py`) are NOT yet
refactored to use it — that's a separate follow-up commit. The intent is that
future new domains (or major refactors of existing ones) will import from
`data_sources._base` instead of re-defining the same `connect()` body.

## See also

- [`data_sources/ddm/_base/ARCHITECTURE.md`](../ddm/_base/ARCHITECTURE.md) — the
  DDM-specific shared infrastructure (catalog/fetcher/sync_engine/status_reporter
  base classes). Phase 3 C1 extraction.
- [`DATA_SOURCES.md`](../../DATA_SOURCES.md) — the data sources layer overview.
- [`STRUCTURE.md`](../../STRUCTURE.md) — full repo layout.

---

*Last updated: 2026-09-15 (Phase 4 C1 — initial creation).*
