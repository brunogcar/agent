<- Back to [ITR Overview](../ITR.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1.0 | 2026-08-04 | **VERSAO dedup fix + sync progress + one-time data repair.** Fixed critical VERSAO dedup bug: cache key was `cnpj_ano` but each quarter has its own VERSAO, so restated Q2 (VERSAO=2) silently dropped Q1/Q3 (VERSAO=1). Changed to `cnpj_ano_dt_fim`. Added `verbose=True` to `sync()` for progress output. ITR database purged and re-synced from scratch (12,979,222 rows, 2011-2026). Repair scripts added to `data_sources/cvm/_repair/`. |
| v1.0.1 | 2026-07-23 | **Claude review fixes.** DMPL excluded (P0). ITR FIRST_YEAR 2015→2011 (P2 — CVM has ITR from 2011). st_conta_fixa added to schema. |
| v1.0 | 2026-07-23 | **Initial implementation.** Split from DFP as a separate sub-domain with its own DB. Same sync fixes as DFP (meses, ano, ORDEM_EXERC, VERSAO, data_ini_exerc). Returns RAW cumulative values (meses=3/6/9) — standalone quarter computation belongs in the skills/ layer. 11 ITR query tests. |

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

**Impact:** PETR4 was missing Q1 2025 (meses=3) and Q3 2025 (meses=9)
current-period data. This affected any company that filed a restatement
with a higher VERSAO number than other quarters.

### P1: Sync progress output
`sync()` now accepts `verbose=True` (default). Prints to stderr:
```
[itr] Starting ITR sync — 16 year(s): 2011..2026
[itr] [1/16] Year 2011 ...
[itr]   downloading https://dados.cvm.gov.br/...
[itr]   downloaded 45.2 MB in 12.3s
[itr]   parsing [1/12] itr_cia_aberta_BPA_con_2011.csv
[itr]     38,245 rows stored
...
[itr] Done in 458.2s — 12,979,222 total rows, 0 errors
```

### One-time data repair
- ITR database purged and re-synced from scratch
- CNPJ normalized to 14 plain digits + duplicate empresa rows merged
- Repair scripts in `data_sources/cvm/_repair/`:
  - `purge_penultimo.py` — delete legacy PENÚLTIMO rows (idempotent)
  - `normalize_cnpj.py` — normalize CNPJ + merge duplicates (idempotent)
  - `verify.py` — 6-check data integrity verifier (recurring health check)

---

*Last updated: 2026-08-04 (v1.1.0 — VERSAO fix + sync progress + data repair).*
