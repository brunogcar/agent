<- Back to [DFP Overview](../DFP.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/cvm/dfp/__init__.py` | MANIFEST + route — sub-domain hub, 5 modes (sync, status, query, resumo, search) |
| `data_sources/cvm/dfp/catalog.py` | Schema constants: GRUPOS, RESUMO_ACCOUNTS, CSV_COLUMNS, URL_PATTERN |
| `data_sources/cvm/dfp/sync_engine.py` | Download DFP ZIPs → parse CSV → upsert into dfp.db. Fixes: meses, ano, ORDEM_EXERC, VERSAO |
| `data_sources/cvm/dfp/query_engine.py` | Query annual statements: `query()`, `resumo()`, `search()`. Returns raw annual values |
| `data_sources/cvm/dfp/status_reporter.py` | DB stats: empresas, contas, year range, synced years, meses distribution |

## 🗄️ Database Schema

```sql
empresas (id, cnpj, nome, ano, cd_cvm)  -- UNIQUE(cnpj, ano)
contas   (id_empresa, codigo, descricao, grupo, consolidado,
          data_ini_exerc, data_fim_exerc, meses, ordem_exerc, versao,
          valor, escala, moeda)  -- PK(id_empresa, codigo, consolidado, data_ini_exerc, data_fim_exerc)
sync_state (form, year, synced_at, row_count, file_size)
```

## Data Flow

```
CVM ZIP → parse CSV → compute meses → filter ORDEM_EXERC → dedup VERSAO → upsert dfp.db
```

## Design Decisions

- **`ano` = fiscal year** (from `DT_FIM_EXERC[:4]`), not filing year. The old implementation used the URL year (filing year), which was off-by-one — `dfp_cia_aberta_2024.zip` contains fiscal year 2023 data.
- **ORDEM_EXERC filter**: CVM DFP ZIPs contain both `ÚLTIMO` (current year) and `PENÚLTIMO` (prior year comparative). Storing both creates duplicate data. rapinav2 keeps only `ÚLTIMO` (+ `PENÚLTIMO` for 2009 backfill, since CVM DFP starts in 2010).
- **BPA/BPP snapshots**: `DT_INI_EXERC=""` → `meses=12`. These are point-in-time balances, not period flows. The `data_ini_exerc` column distinguishes them from DRE/DFC/DVA flows (which also have `meses=12` but non-empty `data_ini_exerc`).
- **Raw data only**: This data source stores raw annual values. Standalone quarter computation (T4 = annual − 9M) and ratio computation belong in the skills/ layer.

---

*Last updated: 2026-07-23 (v1.0).*
