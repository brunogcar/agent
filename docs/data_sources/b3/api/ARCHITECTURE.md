<- Back to [API Overview](../API.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/api/__init__.py` | MANIFEST + route — sub-domain hub, 5 modes |
| `data_sources/b3/api/catalog.py` | Schema constants: API base, B3_TABLES registry, DB path/connect helpers, dynamic schema creation + migration (ALTER TABLE ADD COLUMN) |
| `data_sources/b3/api/sync_engine.py` | Download via CSV bulk API (2-step: token → CSV) → parse → store to SQLite. Dynamic columns from CSV header. |
| `data_sources/b3/api/query_engine.py` | Query: query(), lookup_ticker(), search_company() — dynamically discovers columns via PRAGMA table_info |
| `data_sources/b3/api/status_reporter.py` | Status: sync statistics for all B3 tables |

## API Flow (v2.0 — CSV Bulk Download)

```
Step 1: GET /api/download/requestname?fileName={tableName}&date={date}
  ↓
JSON: {"token": "...", "file": {"name": "...", "extension": ".csv"}}

Step 2: GET /api/download/?token={token}
  ↓
Full CSV file (semicolon-separated, ISO-8859-1, 15-52 columns)
  ↓
Parse CSV (skip "Status do Arquivo: Final" line if present)
  ↓
ensure_schema: CREATE TABLE IF NOT EXISTS (all columns)
  OR  ALTER TABLE ADD COLUMN (migrate old 4-column schema)
  ↓
DELETE old rows for this date
COMMIT (close DELETE transaction)
INSERT all rows via executemany
COMMIT
  ↓
Record sync_state
```

## Design Decisions

- **CSV bulk download**: The paginated JSON API (v1.0) was fundamentally limited (4 columns, 2,283 pages, 22-minute sync, server-side throttling). The CSV bulk download returns ALL rows + ALL columns in 1 request (~1-10 seconds). Discovered by gemini + mistral + qwen during the 2026-08-24 multi-LLM code review.
- **2-step token flow**: B3 requires a token (Step 1) before downloading (Step 2). The token is valid for ~5 minutes. CRITICAL: the download URL requires a trailing slash (`/api/download/`).
- **Dynamic schema**: Table columns are created from the CSV header on first sync. This makes it resilient to B3 schema changes — no hardcoded column lists.
- **Schema migration**: If upgrading from the old 4-column JSON API schema, `ensure_schema` uses `ALTER TABLE ADD COLUMN` to add the missing columns without losing existing data.
- **One DB per table**: instruments.db, trades.db, etc. Keeps each table self-contained, allows independent sync/query.
- **Date-based replace**: Each sync deletes old rows for the same date before inserting. Idempotent re-syncs.
- **ISO-8859-1 encoding**: B3 CSVs use Latin-1 encoding (Portuguese accents). The parser decodes via `resp.content.decode("iso-8859-1")`.
- **Status line detection**: 3 of 4 tables (instruments, trades, after_hours) have a `Status do Arquivo: Final` line before the header. Derivatives does NOT. The parser auto-detects this by checking if line 0 has only 1 column.

## Performance Comparison

| Table | Rows | Columns | Old (JSON) | New (CSV) | Speedup |
|---|---|---|---|---|---|
| derivatives | 45,653 | 17 | 1,331s | ~1.3s | 1,024x |
| instruments | 146,255 | 52 | ~3,600s (est.) | ~10.5s | ~343x |
| trades | 161,855 | 15 | ~2,600s (est.) | ~2.6s | ~1,000x |
| after_hours | 633 | 15 | ~60s | ~0.4s | ~150x |

---

*Last updated: 2026-08-24 (v2.0 — CSV bulk download).*
