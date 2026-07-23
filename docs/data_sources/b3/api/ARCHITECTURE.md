<- Back to [B3 Overview](../B3.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/api/__init__.py` | MANIFEST + route — sub-domain hub, 5 modes |
| `data_sources/b3/api/catalog.py` | Schema constants: API base, B3_TABLES registry, DB path/connect helpers, dynamic schema creation |
| `data_sources/b3/api/sync_engine.py` | Download via paginated JSON API → store to SQLite. Dynamic columns from API response. |
| `data_sources/b3/api/query_engine.py` | Query: query(), lookup_ticker(), search_company(), status() |

## API Flow

```
GET /tabelas/table/{tableName}/{date}/{page}
  ↓
JSON: {columns: [...], values: [[...], ...], pageCount: N}
  ↓
Page 1 → get columns + pageCount
Pages 2..N → collect all values
  ↓
CREATE TABLE IF NOT EXISTS (dynamic columns from API)
DELETE old rows for this date
INSERT all values
  ↓
Record sync_state
```

## Design Decisions

- **Paginated JSON API**: The old 3-step CSV flow (publications → token → CSV) is broken. The new API returns JSON with column metadata + values, 20 rows per page. No authentication needed.
- **Dynamic schema**: Table columns are created from the API's column response on first sync. This makes it resilient to B3 schema changes — no hardcoded column lists.
- **One DB per table**: instruments.db, trades.db, etc. Keeps each table self-contained, allows independent sync/query.
- **Date-based replace**: Each sync deletes old rows for the same date before inserting. Idempotent re-syncs.
- **No encoding issues**: The old CSV flow used ISO-8859-1 encoding. The new JSON API returns UTF-8 — no encoding issues.

---

*Last updated: 2026-07-23 (v1.0).*
