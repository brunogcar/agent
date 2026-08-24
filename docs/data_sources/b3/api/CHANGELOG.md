<- Back to [API Overview](../API.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v2.1 | 2026-08-24 | **Hardening.** (1) CSV parser: swapped naive `split(";")` to `csv.reader` for proper quoting/escaping (handles semicolons in company names in the 52-column instruments table). (2) Retry with backoff: 3 attempts on both `_get_download_token` (1s/2s) and `_download_csv` (2s/4s). (3) Column name sanitization: validates alphanumeric + underscore before `ALTER TABLE ADD COLUMN`. (4) Partial data skip: `_parse_csv` now returns a status ("Final"/"Parcial") from the "Status do Arquivo" line. If "Parcial" (intraday), the sync skips and keeps the previous Final data. (Claude 1+2 review findings + user request.) |
| v2.0 | 2026-08-24 | **CSV bulk download.** Complete rewrite — replaced the paginated JSON API (2,283 requests, 4 columns, 22-minute sync with server-side throttling + 504 timeouts) with a 2-step CSV bulk download (1 request, ALL rows, 15-52 columns, ~1-10s). Token flow: `/api/download/requestname` → `/api/download/?token=`. Schema migration via ALTER TABLE ADD COLUMN (handles old 4-column tables). ISO-8859-1 encoding. Discovered by gemini + mistral + qwen during multi-LLM code review. |
| v1.0.5 | 2026-07-24 | **Date fallback + performance.** Date fallback (7 days back). Workers 10→30. Batch size 500→100. |
| v1.0.4 | 2026-07-23 | **Batch commit + resume.** Commits every BATCH_SIZE pages. ThreadPoolExecutor(10). Resume from last page. |
| v1.0 | 2026-07-23 | **Initial implementation.** Paginated JSON API (4 columns, 20 rows/page). 4 tables. 5 modes. |

---

*Last updated: 2026-08-24 (v2.1 — hardening: CSV parser + retry + partial data skip + column validation).*
