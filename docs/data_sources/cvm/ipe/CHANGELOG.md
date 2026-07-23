<- Back to [CVM Overview](../CVM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-07-23 | **Initial implementation.** Ported from `_legacy_skills/cvm/cvm_ipe_sync.py`. Single table (eventos), single CSV per ZIP. Uses Protocolo_Entrega as unique dedup key. 4 modes: sync, status, query (with filters: company, categoria, tipo, keyword, date range), search. _db.py updated with ipe_db_path() + connect_ipe(). 11 IPE query tests. |

---

*Last updated: 2026-07-23 (v1.0).*
