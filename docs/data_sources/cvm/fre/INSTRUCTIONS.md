<- Back to [CVM Overview](../CVM.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never compute financial ratios or analysis in the FRE data source — that belongs in the skills/ layer.
2. Never import all 50+ CSVs from the FRE ZIP — only the 5 analytically useful tables.
3. Never use `print()` — use `core.tracer` for logging.
4. Never create `.bak` files.
5. Never skip the documentos table — it's the filing index + provides company resolution for all other tables.

## ✅ ALWAYS DO

1. Always use ID_DOC as the primary key for documentos (globally unique CVM filing ID).
2. Always use INSERT OR REPLACE for dedup (idempotent re-syncs).
3. Always normalize CNPJ to 14 digits via `cnpj_digits()` from `_db.py`.
4. Always skip META/dicionario files in the ZIP parser.
5. Always return `{"status": "not_synced"}` when the DB doesn't exist (don't crash).
6. Always resolve companies via the `documentos` table (FRE has no `empresas` table).

---

*Last updated: 2026-07-23 (v1.0).*
