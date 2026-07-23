<- Back to [CVM Overview](../CVM.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never compute standalone quarters (T1/T2/T3/T4) in the ITR data source — that belongs in the skills/ layer which combines DFP + ITR.
2. Never return standalone quarter values — ITR returns CUMULATIVE values only.
3. Never store `PENÚLTIMO` rows except for 2009 backfill.
4. Never set `empresas.ano` from the URL year — always use `DT_FIM_EXERC[:4]`.
5. Never bucket `meses=15` to 12.
6. Never use `print()` — use `core.tracer`.

## ✅ ALWAYS DO

1. Always include a `"note"` field in query results stating values are CUMULATIVE.
2. Always compute `meses` with the inclusive formula (same as DFP).
3. Always store `data_ini_exerc` — needed to distinguish flows from snapshots.
4. Always import shared constants from `data_sources.cvm.dfp.catalog` (same CVM schema).
5. Always return `{"status": "not_synced"}` when the DB doesn't exist.

---

*Last updated: 2026-07-23 (v1.0).*
