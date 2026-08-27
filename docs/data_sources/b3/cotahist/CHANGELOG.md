<- Back to [COTAHIST Overview](../COTAHIST.md)

# 🗺️ Changelog

## v1.1 — 2026-08-27

**Incremental sync — only INSERT new rows (no gaps, no DELETE).**

### I12: Incremental sync

- `_sync_year(force=False)` now checks `MAX(refdate)` in the DB. If the year
  is already synced, it downloads the ZIP but only INSERTs rows with
  `refdate > MAX(refdate)`. This avoids re-parsing + re-inserting ~170K rows
  when only 1 new trading day was added.
- New `_parse_and_store_filtered()` function — same streaming logic as
  `_parse_and_store()` but skips rows whose `refdate <= latest_in_db`.
  No DELETE (preserves existing rows).
- Past years are skipped entirely (already synced, no new data).
- When `force=True`, full-refresh (DELETE year + re-INSERT all rows).
- **No gaps**: the full ZIP is still downloaded + parsed, but only new rows
  are written. If you sync after a gap (e.g., didn't sync for a week), all
  missing days are inserted in one pass.
- The 87MB ZIP is still downloaded (B3 doesn't offer daily COTAHIST files
  at a public URL), but DB writes are reduced by ~99%.

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-24 | **BDI filter + query fix + docstring fix.** (1) Added BDI filter at sync time — only keeps equities (02), FIIs (12), ETFs (14), fractional (96). Reduces DB from ~5.7GB to ~1GB by dropping ~85% of rows (options, bonds, warrants). (2) Query now defaults to `market_type=10` (lote padrão) to avoid duplicate rows from fractional market. (3) Fixed stale docstring (said "02" trades, should be "01"). |
| v1.0 | 2026-07-24 | **Initial implementation.** 3 modes: sync (one or more years), query (by ticker, date range, year), status. Streaming parser (line-by-line, not loading full 765MB). Batch inserts every 50K rows. 12 tests. Parser verified against real VALE3 data. |

---

## 🔄 In Progress / Next Up

- **COTAHIST as historical price source** — wire into valuation skill for historical price queries (>1 year back). COTAHIST is official + instant (local), bypasses network.
- **Dividend-adjusted prices** — use B3 dividends to adjust COTAHIST close prices for splits/bonuses. Without adjustment, historical charts show false crashes.
- **Incremental sync** — only fetch current year's ZIP on update, not all years.

---

## 🚫 Deferred / Out of Scope

- **Options/bonds/warrants data** — intentionally filtered out by BDI code. If needed in the future, add a `bdi_filter` param to sync.

---

*Last updated: 2026-07-24 (v1.0.1).*
