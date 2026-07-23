<- Back to [CVM Overview](../CVM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-23 | **P1 hotfix: bridge tuple unpacking.** `_resolve_fre_company` called `_resolve_via_bridge()` expecting a string, but bridge v1.2 changed it to return `(cnpj, cd_cvm)` tuple — caused `sqlite3.ProgrammingError: type 'tuple' is not supported` on every ticker query. Fix: unpack the tuple. 1 regression test added. |
| v1.0 | 2026-07-23 | **Initial implementation.** Ported from `_legacy_skills/cvm/cvm_fre_sync.py`. Imports 5 tables from 50+ CSVs in the FRE ZIP: documentos, posicao_acionaria, distribuicao_capital, remuneracao_orgao, capital_social. Uses ID_DOC as primary key (globally unique CVM filing ID). 7 query modes: sync, status, shareholders, free_float, compensation, capital, search. Shared _db.py updated with fre_db_path() + connect_fre(). |

---

*Last updated: 2026-07-23 (v1.0.1).*
