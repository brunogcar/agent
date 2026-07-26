<- Back to [CGVN Overview](../CGVN.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/cvm/cgvn/__init__.py` | MANIFEST + route — sub-domain hub, 3 modes |
| `data_sources/cvm/cgvn/catalog.py` | Schema constants: SQL schema (tables + indexes + sync_state), DB path/connect (delegates to _db.py), ensure_schema() |
| `data_sources/cvm/cgvn/sync_engine.py` | Download annual ZIPs from CVM → parse CSVs (latin-1) → batch INSERT (5K). Supports single-year + full_history. Year-based delete for incremental sync. httpx downloads. |
| `data_sources/cvm/cgvn/query_engine.py` | Query: governance practices by company (CNPJ/ticker/name). Bridge resolution with auto-sync fallback. |
| `data_sources/cvm/cgvn/status_reporter.py` | Status: cgvn.db stats (row counts, company count, date range, sync state). |

## Data Flow

```
Download: http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/CGVN/DADOS/cgvn_cia_aberta_cia_aberta_{year}.zip
  ↓
Unzip → CSV files (latin-1 encoding, semicolon-delimited)
  ↓
Parse CSV: DictReader → batch INSERT (5,000 rows per transaction)
  ↓
Numeric fields: comma→dot conversion (Preco_Unitario, Quantidade, Volume)
  ↓
Record sync_state (year, rows_synced)
```

## Design Decisions

- **CSV name matching by prefix**: CVM adds year suffix to filenames (cgvn_cia_aberta_cia_aberta_con_2025.csv). Matching by prefix (cgvn_cia_aberta in name) instead of exact suffix handles this.
- **Year-based delete**: Before re-inserting a year, DELETE WHERE Data_Referencia starts with the year. This allows incremental sync without losing other years.
- **Latin-1 encoding**: CVM CSVs use latin-1 (not UTF-8). Decoding with latin-1 avoids UnicodeDecodeError on Portuguese accented characters.
- **Batch INSERT (5K)**: Reduces SQLite write overhead for large datasets.
- **Bridge resolution**: Ticker → CNPJ via bridge (FCA first → bridge.db → B3 API). Auto-sync on miss.
- **CGVN_FIRST_YEAR = 2018**: Sync starts from 2018 (first year CVM published CGVN data).

---

*Last updated: 2026-07-25 (v1.0).*
