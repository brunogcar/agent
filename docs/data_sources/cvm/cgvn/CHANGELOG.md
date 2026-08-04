<- Back to [CGVN Overview](../CGVN.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-08-04 | **CNPJ normalization.** `_parse_and_insert_csv()` now normalizes `CNPJ_Companhia` to 14 plain digits via `cnpj_digits()` (was storing raw formatted `33.000.167/0001-01`). Re-sync with `force=True` to normalize existing data. |
| v1.0 | 2026-07-25 | **Initial implementation.** 3 modes: sync (single-year + full_history), query (by company), status. CSV parsing (latin-1, semicolon-delimited). Batch INSERT (5K). Year-based incremental sync. Bridge resolution (FCA first → bridge.db → B3 API). |

---

*Last updated: 2026-08-04 (v1.1 — CNPJ normalization).*
