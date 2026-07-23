<- Back to [CVM Overview](../CVM.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never use incremental/dedup logic for CAD sync — the CSV is a full snapshot. DELETE + INSERT.
2. Never use `print()` — use `core.tracer` for logging.
3. Never create `.bak` files.
4. Never return all 46 columns by default — use DEFAULT_COLS (24 key columns). `full=True` returns all.

## ✅ ALWAYS DO

1. Always normalize CNPJ to 14 digits for comparison (CSV stores formatted CNPJ).
2. Always use `REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','')` for CNPJ matching.
3. Always skip sync if already done today (unless `force=True`).
4. Always return `{"status": "not_synced"}` when the DB doesn't exist.
5. Always search both DENOM_SOCIAL (legal) and DENOM_COMERC (commercial) names.
6. Always default to `active_only=True` in search (most queries are for listed companies).

---

*Last updated: 2026-07-23 (v1.0).*
