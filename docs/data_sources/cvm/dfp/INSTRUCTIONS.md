<- Back to [CVM Overview](../CVM.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never compute standalone quarters (T1/T2/T3/T4) in the data source layer — that belongs in the skills/ layer which combines DFP + ITR.
2. Never compute ratios (margins, EBITDA) in the data source layer — same reason.
3. Never store `PENÚLTIMO` rows except for 2009 backfill (creates duplicate prior-year data).
4. Never set `empresas.ano` from the URL year — always use `DT_FIM_EXERC[:4]` (fiscal year).
5. Never bucket `meses=15` to 12 — preserve transition periods.
6. Never use `print()` — use `core.tracer` for logging.
7. Never create `.bak` files.

## ✅ ALWAYS DO

1. Always compute `meses` with the inclusive formula: `(anoF-anoI)*12 - mesI + mesF + 1`.
2. Always default `meses=12` when `DT_INI_EXERC=""` (BPA/BPP snapshots).
3. Always store `data_ini_exerc` — needed to distinguish flows from snapshots.
4. Always dedup `VERSAO` — keep only the highest version per (CNPJ, ano).
5. Always use `INSERT OR IGNORE` for empresas + `INSERT OR REPLACE` for contas.
6. Always skip META/dicionario files in the ZIP parser.
7. Always return `{"status": "not_synced"}` when the DB doesn't exist (don't crash).

---

*Last updated: 2026-07-23 (v1.0).*
