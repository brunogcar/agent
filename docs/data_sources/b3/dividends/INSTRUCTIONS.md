<- Back to [B3 Overview](../B3.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never use `print()` — use `core.tracer` for logging.
2. Never create `.bak` files.
3. Never fetch all tickers at once — sync is per-ticker.

## ✅ ALWAYS DO

1. Always use the first 4 chars of the ticker as issuingCompany for the API call.
2. Always normalize dates from DD/MM/YYYY to YYYY-MM-DD.
3. Always parse rates replacing comma with dot for decimal separator.
4. Always DELETE old data for the ticker before INSERT (idempotent re-syncs).
5. Always validate rows: skip if isin_code or approved_on is empty.
6. Always return `{"status": "not_synced"}` when the DB doesn't exist.

---

*Last updated: 2026-07-23 (v1.0).*
