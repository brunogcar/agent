<- Back to [CVM Overview](../CVM.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/cvm/cad/__init__.py` | MANIFEST + route — sub-domain hub, 5 modes |
| `data_sources/cvm/cad/catalog.py` | Schema constants: CSV URL, ALL_COLS (46), DEFAULT_COLS (24), SQL schema |
| `data_sources/cvm/cad/sync_engine.py` | Download cad_cia_aberta.csv → full replace into cad.db |
| `data_sources/cvm/cad/query_engine.py` | Query: lookup() (CNPJ/CD_CVM/name), search() (filters), sectors() |
| `data_sources/cvm/cad/status_reporter.py` | DB stats: total/active/cancelled, last sync, top sectors, market types |

## 🗄️ Database Schema

Single table with all 46 CVM columns:

```sql
cia_aberta (CNPJ_CIA, DENOM_SOCIAL, DENOM_COMERC, DT_REG, DT_CONST,
            DT_CANCEL, MOTIVO_CANCEL, SIT, DT_INI_SIT, CD_CVM,
            SETOR_ATIV, TP_MERC, CATEG_REG, DT_INI_CATEG,
            SIT_EMISSOR, DT_INI_SIT_EMISSOR, CONTROLE_ACIONARIO,
            ... 28 more contact/address columns ...
            CNPJ_AUDITOR, AUDITOR)
-- No explicit PK (CVM file may have duplicates on re-download)
-- Indexes on: CNPJ_CIA, CD_CVM, DENOM_COMERC, DENOM_SOCIAL, SIT, SETOR_ATIV, CONTROLE_ACIONARIO, SIT_EMISSOR

sync_state (synced_at, rows, size_kb)
```

## Design Decisions

- **Single CSV, no ZIP**: CAD is the only CVM data source that downloads a direct CSV (not a ZIP). The file is ~1.5MB.
- **Full replace each sync**: The CSV is a complete snapshot (~3500 companies). DELETE + INSERT is simpler + faster than upsert.
- **Daily skip**: If already synced today, skip unless `force=True`. CVM updates the file weekly.
- **Bridge data source**: The primary purpose is company resolution — CD_CVM links to DFP/ITR/FRE filings, CNPJ links to B3 instruments. Without CAD, other data sources can't resolve tickers to CD_CVM.
- **46 columns stored, 24 returned by default**: Contact/address fields are stored for completeness but DEFAULT_COLS returns only the analytically useful columns. `full=True` returns all 46.
- **CNPJ comparison via REPLACE**: CNPJ_CIA in the CSV is formatted ("33.000.167/0001-01"). Lookup normalizes to 14 digits and uses `REPLACE(REPLACE(REPLACE(CNPJ_CIA,'.',''),'/',''),'-','')` for comparison.

---

*Last updated: 2026-07-23 (v1.0).*
