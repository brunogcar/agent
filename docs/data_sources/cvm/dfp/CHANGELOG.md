<- Back to [DFP Overview](../DFP.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-23 | **Claude review fixes (5 fixes).** (P0) DMPL excluded from ingestion — 2D statement (COLUNA_DF) collides on PK, silently corrupting data. rapinav2 also excludes DMPL. (P1) RESUMO_ACCOUNTS labels corrected: 3.05 is EBIT (not "EBITDA proxy"), 3.09 is "Resultado Líquido (Operações Continuadas)" (not "EBIT"), added 3.06 "Resultado Financeiro", removed fake "EBITDA (proxy)" (computed metric, belongs in skills layer). (P2) ITR FIRST_YEAR 2015→2011 (CVM has ITR data from 2011). (P2) Ambiguous name search in _bridge.py — now guards against multiple distinct CNPJs matching, returns disambiguation error instead of silently merging. (P3) st_conta_fixa column added to schema + both sync engines. CAD (cad.db) wired into _bridge.py as primary name resolver. |
| v1.0 | 2026-07-23 | **Initial implementation.** Rebuilt from `_legacy_skills/cvm/cvm_dfp_itr/` with 6 critical fixes: (1) `meses` computed with rapinav2's inclusive formula (was off-by-one, 15→12 bucketed). (2) `empresas.ano` = fiscal year from `DT_FIM_EXERC[:4]` (was filing year from URL). (3) `ORDEM_EXERC` filter — keeps only `ÚLTIMO` (+ `PENÚLTIMO` for 2009 backfill); was storing all rows including comparative duplicates. (4) `VERSAO` dedup — keeps only highest version per (CNPJ, ano). (5) `data_ini_exerc` stored as a column (needed to distinguish flows from snapshots). (6) DFP + ITR split into separate sub-domains with separate DBs. Shared code (`_db.py`, `_bridge.py`, `_meses.py`) lives at domain level. 23 `_meses` tests + 12 DFP query tests. |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred |
|---|---------|--------------|
| 1 | Trimestral transformation (standalone quarters) | Belongs in the skills/ layer — combines DFP + ITR data |
| 2 | Ratio computation (margins, EBITDA) | Belongs in the skills/ layer |
| 3 | xlsx export | Belongs in the skills/ layer |
| 4 | Bridge.db sync (ticker→CNPJ mapping) | Separate sub-domain (b3_cvm) — will be migrated from _legacy_skills |

---

*Last updated: 2026-07-23 (v1.0).*
