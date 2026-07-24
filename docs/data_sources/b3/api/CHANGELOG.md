<- Back to [API Overview](../API.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.5 | 2026-07-24 | **Date fallback + performance.** (1) Date fallback: B3 publishes trade data with a delay — today returns 0 pages. Now tries up to 7 days back, finding the first date with data. (2) Workers 10→30: I/O bound (CPU at 0%), more concurrent HTTP = faster. (3) Batch size 500→100: more frequent SQLite commits for better resume. |
| v1.0.4 | 2026-07-23 | **Batch commit + resume.** Commits every BATCH_SIZE pages so cancelled syncs keep progress. ThreadPoolExecutor(10 workers). Resume from last committed page. |
| v1.0 | 2026-07-23 | **Initial implementation.** New paginated JSON API (old 3-step CSV download broken — B3 migrated to React SPA). Dynamic schema creation from API column metadata. 4 tables: instruments, trades, after_hours, derivatives. 5 modes: sync, status, query, lookup_ticker, search_company. 12 B3 API query tests. |

---

*Last updated: 2026-07-24 (v1.0.5).*
