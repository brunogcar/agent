<- Back to [IPE Overview](../IPE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-23 | **P1 hotfix: bridge tuple unpacking.** `query()` called `_resolve_via_bridge()` expecting a string, but bridge v1.2 changed it to return `(cnpj, cd_cvm)` tuple — caused `sqlite3.ProgrammingError: type 'tuple' is not supported` on ticker queries. Fix: unpack the tuple. |
| v1.0 | 2026-07-23 | **Initial implementation.** Ported from `_legacy_skills/cvm/cvm_ipe_sync.py`. Single table (eventos), single CSV per ZIP. Uses Protocolo_Entrega as unique dedup key. 4 modes: sync, status, query (with filters: company, categoria, tipo, keyword, date range), search. _db.py updated with ipe_db_path() + connect_ipe(). 11 IPE query tests. |

---

*Last updated: 2026-07-23 (v1.0.1).*
