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

### CSV → DB Column Mapping

The sync engine renames CVM CSV columns to shorter DB column names. This is
intentional (v1.0 design decision — keeps SQL queries concise). When writing
raw SQL against `dfp.db` or `itr.db`, use the **DB column name**, not the CSV name:

| CVM CSV column | DB column | Type | Notes |
|---|---|---|---|
| `CNPJ_CIA` | `empresas.cnpj` | TEXT | Digits only (no formatting) |
| `DENOM_CIA` | `empresas.nome` | TEXT | Company name |
| `CD_CVM` | `empresas.cd_cvm` | TEXT | CVM company ID |
| `DT_FIM_EXERC` | `empresas.ano` + `contas.data_fim_exerc` | TEXT | `ano` = fiscal year (first 4 chars) |
| `CD_CONTA` | `contas.codigo` | TEXT | Account code (e.g. "1.1.01")
| `DS_CONTA` | `contas.descricao` | TEXT | Account description |
| `GRUPO_DFP` | `contas.grupo` | TEXT | Statement group (BPA/BPP/DRE/DFC/DVA) |
| `DT_INI_EXERC` | `contas.data_ini_exerc` | TEXT | Empty for snapshots (BPA/BPP) |
| `VL_CONTA` | `contas.valor` | REAL | **Multiply by `escala` for BRL amounts** |
| `ESCALA_MOEDA` | `contas.escala` | TEXT | "MIL" (thousands) or "MILHOES" (millions) |
| `MOEDA` | `contas.moeda` | TEXT | Usually "REAL" |
| `ORDEM_EXERC` | `contas.ordem_exerc` | TEXT | "ÚLTIMO" or "PENÚLTIMO" |
| `VERSAO` | `contas.versao` | INTEGER | Filing version |
| `ST_CONTA_FIXA` | `contas.st_conta_fixa` | TEXT | Fixed account flag |

> **Note:** ITR (`itr.db`) uses the same schema + column names. See [ITR ARCHITECTURE](../itr/ARCHITECTURE.md).
>
> **Other CVM data sources** (FRE, IPE, VLMO, CGVN, FCA) keep the CSV column names as-is in the DB — no renaming. Only DFP + ITR use this abbreviated schema.
>
> **Statement charts of accounts** — for the per-statement code maps + label quirks (DRE 3.01-3.11, DVA 7.xx, BPA 1.xx, etc.) used by the `financials` skill modes (`bpa`, `dre`, `dva`, `complete`), see:
> - [architecture/BPA.md](architecture/BPA.md) — BPA chart of accounts (codes 1.xx, old vs new chart, multiple labels per code)
> - [architecture/DRE.md](architecture/DRE.md) — DRE chart of accounts (codes, multiple labels per code, DRE vs DRA)
> - [architecture/DVA.md](architecture/DVA.md) — DVA chart of accounts (7.xx codes, old vs new format, grupo filter bug)

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

*Last updated: 2026-07-30 (v1.9 — added cross-link to BPA chart of accounts).*
