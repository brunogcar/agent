<- Back to [ITR Overview](../ITR.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/cvm/itr/__init__.py` | MANIFEST + route — sub-domain hub, 5 modes (sync, status, query, resumo, search) |
| `data_sources/cvm/itr/catalog.py` | Schema constants (imports from DFP catalog — same CVM schema). URL pattern + FIRST_YEAR=2015. |
| `data_sources/cvm/itr/sync_engine.py` | Download ITR ZIPs → parse CSV → upsert into itr.db. Same fixes as DFP. |
| `data_sources/cvm/itr/query_engine.py` | Query quarterly cumulative data: `query()`, `resumo()`, `search()`. Returns cumulative values (NOT standalone quarters). |
| `data_sources/cvm/itr/status_reporter.py` | DB stats |

## Database Schema

Identical to DFP (see [DFP ARCHITECTURE](../dfp/ARCHITECTURE.md)). Each DB has its own copy of `empresas` + `contas` + `sync_state`.

## Design Decisions

- **Separate DB from DFP**: ITR data has a different sync cadence (quarterly vs annual) + different update frequency. Separate DBs keep each self-contained.
- **Cumulative values only**: ITR returns raw cumulative values (Jan→Mar, Jan→Jun, Jan→Sep). Standalone quarter computation (T2 = H1 − Q1, T4 = DFP_annual − 9M) belongs in the skills/ layer.
- **Same schema as DFP**: CVM uses identical CSV format for both DFP and ITR. The catalog imports statement group definitions from DFP.
- **ITR starts in 2015**: CVM started publishing ITR ZIPs from 2015 (DFP starts in 2010).

---

*Last updated: 2026-07-23 (v1.0).*
