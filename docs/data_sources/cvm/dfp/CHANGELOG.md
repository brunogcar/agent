<- Back to [DFP Overview](../DFP.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2.0 | 2026-08-05 | **DELETE-before-INSERT.** Added per-period DELETE-before-INSERT to prevent ghost rows (rapinav2 pattern). Review fixes from collective LLM review. |
| v1.1.0 | 2026-08-04 | **VERSAO dedup fix + sync progress + one-time data repair.** Fixed critical VERSAO dedup bug: cache key was `cnpj_ano` but each quarter has its own VERSAO, so restated Q2 (VERSAO=2) silently dropped Q1/Q3 (VERSAO=1). Changed to `cnpj_ano_dt_fim`. Added `verbose=True` to `sync()` for progress output. DFP purge confirmed 0 non-2009 PENÚLTIMO rows. CNPJ normalized to 14 plain digits + duplicate empresa rows merged. Repair scripts added to `data_sources/cvm/_repair/`. |
| v1.0.1 | 2026-07-23 | **Claude review fixes (5 fixes).** (P0) DMPL excluded from ingestion — 2D statement (COLUNA_DF) collides on PK, silently corrupting data. rapinav2 also excludes DMPL. (P1) RESUMO_ACCOUNTS labels corrected: 3.05 is EBIT (not "EBITDA proxy"), 3.09 is "Resultado Líquido (Operações Continuadas)" (not "EBIT"), added 3.06 "Resultado Financeiro", removed fake "EBITDA (proxy)" (computed metric, belongs in skills layer). (P2) ITR FIRST_YEAR 2015→2011 (CVM has ITR data from 2011). (P2) Ambiguous name search in _bridge.py — now guards against multiple distinct CNPJs matching, returns disambiguation error instead of silently merging. (P3) st_conta_fixa column added to schema + both sync engines. CAD (cad.db) wired into _bridge.py as primary name resolver. |
| v1.0 | 2026-07-23 | **Initial implementation.** Rebuilt from `_legacy_skills/cvm/cvm_dfp_itr/` with 6 critical fixes: (1) `meses` computed with rapinav2's inclusive formula (was off-by-one, 15→12 bucketed). (2) `empresas.ano` = fiscal year from `DT_FIM_EXERC[:4]` (was filing year from URL). (3) `ORDEM_EXERC` filter — keeps only `ÚLTIMO` (+ `PENÚLTIMO` for 2009 backfill); was storing all rows including comparative duplicates. (4) `VERSAO` dedup — keeps only highest version per (CNPJ, ano). (5) `data_ini_exerc` stored as a column (needed to distinguish flows from snapshots). (6) DFP + ITR split into separate sub-domains with separate DBs. Shared code (`_db.py`, `_bridge.py`, `_meses.py`) lives at domain level. 23 `_meses` tests + 12 DFP query tests. |

---

## 🔧 v1.1.0 Changes

### P0: VERSAO dedup bug (silent data loss)
The VERSAO dedup cache was keyed on `f"{cnpj}_{ano}"` — but each quarter
(Q1/Q2/Q3) is a separate CVM filing with its own VERSAO number. When a
company restated Q2 (VERSAO=2), the dedup logic incorrectly dropped Q1
and Q3 rows (VERSAO=1) because it thought they were older versions of
the same annual filing.

**Fix:** Changed cache key to `f"{cnpj}_{ano}_{dt_fim}"` so each quarter's
version is tracked independently.

### P1: Sync progress output
`sync()` now accepts `verbose=True` (default). Prints to stderr:
```
[dfp] Starting DFP sync — 1 year(s): 2026..2026
[dfp] [1/1] Year 2026 ...
[dfp]   downloading https://dados.cvm.gov.br/...
[dfp]   downloaded 12.4 MB in 8.1s
[dfp]   parsing [1/12] dfp_cia_aberta_BPA_con_2026.csv
[dfp]     15,832 rows stored
...
[dfp] Done in 45.3s — 9,204 total rows, 0 errors
```

### One-time data repair
- DFP purge confirmed 0 non-2009 PENÚLTIMO rows (sync engine correct since v1.0)
- CNPJ normalized to 14 plain digits + duplicate empresa rows merged
- No DFP re-sync needed (ÚLTIMO rows were already correct, but VERSAO fix
  requires re-sync to recover Q1/Q3 data that was silently dropped)

---

*Last updated: 2026-08-04 (v1.1.0 — VERSAO fix + sync progress + data repair).*
