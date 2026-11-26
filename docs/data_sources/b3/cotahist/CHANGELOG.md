<- Back to [COTAHIST Overview](../COTAHIST.md)

# 🗺️ Changelog

## v1.2 — 2026-11-26

**BDRs join the DB + the quotable universe widens (WebUI v1.28.2).**

### BDRs in the sync (BDI 34/35/36)

- `BDI_FILTER` extended {2, 12, 14, 96} → {2, 12, 14, 34, 35, 36, 96}: BDR
  Nível I/II/III rows (AAPL34, MSFT34, GOGL34…) are stored now — they were
  dropped at sync, so the WebUI Painel's "Maiores Altas BDR" card screened
  a universe that never reached the DB ("Sem dados" on every real machine).
- **One-time backfill**: the incremental sync only inserts rows NEWER than
  the latest refdate, so it can't backfill BDR rows for ingested dates.
  `_sync_year` now probes `_bdr_rows_missing(conn, year)` — when the CURRENT
  year is synced but carries zero BDR rows, it falls through to the full
  path once (delete year + rebuild with the extended filter). Past years
  keep their pre-BDR state unless force-synced by hand.

### The share-like quote universe

- New `BDI_SHARE_LIKE = {2, 12, 14, 34, 35, 36}` in catalog.py — the
  quotable set (everything except fractional duplicates).
- `market_snapshot()` / `quotes_for()` scope `bdi_code IN BDI_SHARE_LIKE`
  instead of `bdi_code = 2`: ETFs (BDI 14) reach the quotes now — the old
  equities-only scope left the Painel's BOVA11/SMAL11/IVVB11 KPI row empty
  on every real DB and would have left ETF/FII/BDR portfolio positions
  quote-less. Each symbol row exposes its `bdi_code` so callers slice the
  universe (the Painel's four ranking cards stay equities-only).
- 6 new tests (TestShareLikeUniverse + TestBdrBackfillProbe) in
  tests/data_sources/b3/cotahist/test_cotahist.py.

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
| v1.2 | 2026-11-26 | **BDRs join the DB + the quotable universe widens.** BDI 34/35/36 (BDR Nível I/II/III) added to the sync filter; one-time current-year backfill via `_bdr_rows_missing` (the incremental path can't backfill old dates); `market_snapshot()`/`quotes_for()` quote the share-like set (equities + FIIs + ETFs + BDRs) instead of equities-only, with `bdi_code` exposed per row. |
| v1.1 | 2026-08-27 | **Incremental sync — only INSERT new rows (no gaps, no DELETE).** |
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

*Last updated: 2026-11-26 (v1.2 — BDRs in the filter + the share-like quote universe).*
