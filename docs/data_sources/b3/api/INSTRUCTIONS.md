<- Back to [B3 Overview](../B3.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never use the old 3-step CSV download flow (publications → token → CSV). The token endpoint returns 400. Use the new paginated JSON API instead.
2. Never hardcode column lists — the API returns column metadata dynamically. Read it from the response and create the table accordingly.
3. Never use `print()` — use `core.tracer` for logging.
4. Never create `.bak` files.

## ✅ ALWAYS DO

1. Always use `/tabelas/table/{tableName}/{date}/{page}` for downloading.
2. Always create table schema dynamically from the API's column response on first sync.
3. Always paginate through all pages (page 1 to pageCount).
4. Always DELETE old rows for the same date before INSERT (idempotent re-syncs).
5. Always return `{"status": "not_synced"}` when the DB doesn't exist.
6. Always store `_ingested_at` timestamp on each row for freshness checks.

---

*Last updated: 2026-07-23 (v1.0).*
