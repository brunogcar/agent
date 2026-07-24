<- Back to [COTAHIST Overview](../COTAHIST.md)

# 🗺️ Changelog

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
