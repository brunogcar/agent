<- Back to [CVM Overview](../CVM.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never fetch document content (PDF/XML) — IPE is the event INDEX only. `link_download` points to the document.
2. Never use `print()` — use `core.tracer` for logging.
3. Never create `.bak` files.

## ✅ ALWAYS DO

1. Always use `protocolo` as the dedup key (CVM's unique filing ID).
2. Always normalize CNPJ to 14 digits via `cnpj_digits()`.
3. Always try multiple encodings for IPE CSVs (UTF-8-BOM, UTF-8, latin-1, cp1252).
4. Always skip META/dicionario files in the ZIP parser.
5. Always return `{"status": "not_synced"}` when the DB doesn't exist.

---

*Last updated: 2026-07-23 (v1.0).*
