<- Back to [FRE Overview](../FRE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/cvm/fre/__init__.py` | MANIFEST + route — sub-domain hub, 7 modes |
| `data_sources/cvm/fre/catalog.py` | Schema constants: URL pattern, CSV encoding, SQL schema, FRE_TABLES registry |
| `data_sources/cvm/fre/sync_engine.py` | Download FRE ZIPs → parse 5 CSVs → upsert into fre.db |
| `data_sources/cvm/fre/query_engine.py` | Query governance data: shareholders, free_float, compensation, capital, search |
| `data_sources/cvm/fre/status_reporter.py` | DB stats: table row counts, year range, synced years |

## 🗄️ Database Schema

5 tables + sync_state (see catalog.py SCHEMA_SQL for full DDL):

| Table | Source CSV | Key Columns | Dedup |
|---|---|---|---|
| `documentos` | `fre_cia_aberta_{year}.csv` | id_doc (PK), cnpj, cd_cvm, nome, dt_refer, link_doc | INSERT OR REPLACE on id_doc |
| `posicao_acionaria` | `fre_cia_aberta_posicao_acionaria_{year}.csv` | cnpj, acionista, pct_on/pn/total, qtd_on/pn/total | UNIQUE(id_documento, cpf_cnpj_acionista) |
| `distribuicao_capital` | `fre_cia_aberta_distribuicao_capital_{year}.csv` | cnpj, pct_circulacao, qtd_acionistas | UNIQUE(id_documento) |
| `remuneracao_orgao` | `fre_cia_aberta_remuneracao_total_orgao_{year}.csv` | cnpj, orgao, salario, bonus, total_remuneracao | UNIQUE(id_documento, orgao, dt_ini_exercicio) |
| `capital_social` | `fre_cia_aberta_capital_social_{year}.csv` | cnpj, tipo_capital, valor_capital, qtd_acoes_on/pn/total | UNIQUE(id_documento, tipo_capital) |

## Design Decisions

- **5 tables only**: The FRE ZIP contains 50+ CSVs, but most are text-heavy governance sections (board bios, related-party text, policies) with low analytical value. We import only the 5 tables most useful for stock analysis. The rest are accessible via `link_doc` (download URL for the full document).
- **ID_DOC as primary key**: CVM assigns globally unique ID_DOC per filing. Using it as PK means re-syncing is idempotent — same doc always maps to same row.
- **No meses/flow/snapshot**: Unlike DFP/ITR, FRE data is point-in-time snapshots from annual filings, not period flows. No DT_INI_EXERC/DT_FIM_EXERC computation needed.
- **No ORDEM_EXERC filter**: FRE doesn't have comparative columns like DFP. Dedup is via UNIQUE constraints on natural keys.
- **Company resolution via documentos table**: FRE doesn't have an `empresas` table — company lookup goes through `documentos.cnpj` instead of the DFP/ITR bridge.

---

*Last updated: 2026-07-23 (v1.0).*
