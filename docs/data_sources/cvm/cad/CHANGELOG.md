<- Back to [CAD Overview](../CAD.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-08-04 | **CNPJ normalization + verbose sync.** `sync()` now normalizes `CNPJ_CIA` and `CNPJ_AUDITOR` to 14 plain digits via `cnpj_digits()` (was storing raw formatted `33.000.167/0001-01`). Added `verbose=True` param — prints download size, row count, and store confirmation to stderr. Re-sync with `force=True` to normalize existing data. |
| v1.0 | 2026-07-23 | **Initial implementation.** Ported from `_legacy_skills/cvm/cvm_register/`. Renamed from `register` to `cad` (Cadastro). Single CSV download (no ZIP). Full replace each sync (file is a complete snapshot). 5 modes: sync, status, lookup (by CNPJ/CD_CVM/name), search (with filters: setor, sit, controle, uf), sectors. 46 columns stored; DEFAULT_COLS returns 24 key columns. _db.py updated with cad_db_path() + connect_cad(). 12 CAD query tests. |

---

*Last updated: 2026-08-04 (v1.1 — CNPJ normalization + verbose sync).*
