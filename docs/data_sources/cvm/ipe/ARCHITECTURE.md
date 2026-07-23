<- Back to [CVM Overview](../CVM.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/cvm/ipe/__init__.py` | MANIFEST + route — sub-domain hub, 4 modes |
| `data_sources/cvm/ipe/catalog.py` | Schema constants: URL pattern, SQL schema, CSV column mapping |
| `data_sources/cvm/ipe/sync_engine.py` | Download IPE ZIPs → parse single CSV → upsert into ipe.db |
| `data_sources/cvm/ipe/query_engine.py` | Query events: query() with filters, search() |
| `data_sources/cvm/ipe/status_reporter.py` | DB stats: event count, year range, top categories |

## 🗄️ Database Schema

Single table:

```sql
eventos (id, cnpj, cd_cvm, nome, data_entrega, data_referencia,
         categoria, tipo, especie, assunto, tipo_apresentacao,
         versao, protocolo, link_download, ano_origem)
-- UNIQUE(protocolo) for dedup
```

## Design Decisions

- **Simplest CVM data source**: Single table, single CSV per ZIP. No meses, no ORDEM_EXERC, no flow/snapshot distinction.
- **Protocolo_Entrega as unique key**: CVM's filing reference. Using it for dedup means re-syncing is idempotent.
- **Event index, not content**: IPE stores metadata + download link. The actual document content (PDF/XML) is not fetched — `link_download` points to it.
- **Multi-encoding CSV**: IPE CSVs can be UTF-8-BOM, UTF-8, latin-1, or cp1252. The parser tries all 4.

---

*Last updated: 2026-07-23 (v1.0).*
