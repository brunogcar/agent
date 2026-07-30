<- Back to [FRE Overview](../FRE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-07-30 | **P0: Column name mismatch fix + shareholders() date filter.** The sync engine used abbreviated column names (`Pct_Total_Circulacao`, `Qtd_ON`, `Orgao`, etc.) but CVM FRE CSVs use full names (`Percentual_Total_Acoes_Circulacao`, `Quantidade_Acao_Ordinaria_Circulacao`, `Orgao_Administracao`, etc.). This caused **all** pct/qtd values in `distribuicao_capital`, `posicao_acionaria`, `capital_social`, and `remuneracao_orgao` to be stored as NULL since v1.0 (11,378 rows, 0 non-NULL). Fix: updated 4 sync functions to use the correct CVM column names (verified against the official CVM metadata at `dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/META/`). Also fixed `shareholders()` query in `query_engine.py` — had no date filter + sorted by `pct_total DESC` across ALL years, returning stale 2010 data instead of the latest filing. Now filters to `MAX(data_referencia)` for the company. **Re-sync required** — existing fre.db has NULLs that can only be fixed by re-running sync. |
| v1.0.1 | 2026-07-23 | **P1 hotfix: bridge tuple unpacking.** `_resolve_fre_company` called `_resolve_via_bridge()` expecting a string, but bridge v1.2 changed it to return `(cnpj, cd_cvm)` tuple — caused `sqlite3.ProgrammingError: type 'tuple' is not supported` on every ticker query. Fix: unpack the tuple. 1 regression test added. |
| v1.0 | 2026-07-23 | **Initial implementation.** Ported from `_legacy_skills/cvm/cvm_fre_sync.py`. Imports 5 tables from 50+ CSVs in the FRE ZIP: documentos, posicao_acionaria, distribuicao_capital, remuneracao_orgao, capital_social. Uses ID_DOC as primary key (globally unique CVM filing ID). 7 query modes: sync, status, shareholders, free_float, compensation, capital, search. Shared _db.py updated with fre_db_path() + connect_fre(). |

---

*Last updated: 2026-07-30 (v1.1).*
