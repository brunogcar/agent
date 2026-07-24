<- Back to [CAD Overview](../CAD.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-07-23 | **Initial implementation.** Ported from `_legacy_skills/cvm/cvm_register/`. Renamed from `register` to `cad` (Cadastro). Single CSV download (no ZIP). Full replace each sync (file is a complete snapshot). 5 modes: sync, status, lookup (by CNPJ/CD_CVM/name), search (with filters: setor, sit, controle, uf), sectors. 46 columns stored; DEFAULT_COLS returns 24 key columns. _db.py updated with cad_db_path() + connect_cad(). 12 CAD query tests. |

---

*Last updated: 2026-07-23 (v1.0).*
