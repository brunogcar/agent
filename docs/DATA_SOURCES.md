# 📊 Data Sources

Data sources are external data connectors that sync from APIs (CVM, B3, etc.) into local SQLite DBs, plus a query interface. They follow the hub-and-spoke pattern: a single `@tool`-decorated dispatcher routes to domain hubs, which route to sub-domains.

**vs skills/**: Data sources handle raw data storage + retrieval. The skills/ layer (future) handles domain reasoning that combines multiple data sources (e.g., computing standalone quarters from DFP + ITR, or financial ratios).

| Document | Domain | Key Topics |
|----------|--------|------------|
| [CVM.md](data_sources/CVM.md) | CVM | Brazilian SEC data: DFP (annual) + ITR (quarterly) |

---

## 🏗️ Architecture

```text
data_sources/
├── __init__.py                    # Package marker
├── dispatcher.py                  # @tool entry point: data_source(domain, sub_domain, mode, params)
│
└── cvm/                           # CVM domain
    ├── __init__.py                # MANIFEST + route (domain hub)
    ├── _db.py                     # Shared: path resolution, CNPJ, connect helpers
    ├── _bridge.py                 # Shared: ticker→CNPJ→empresa_id resolution
    ├── _meses.py                  # Shared: meses computation (rapinav2 formula)
    │
    ├── dfp/                       # Annual filings (DFP) → dfp.db
    │   ├── __init__.py            # MANIFEST + route (sub-domain hub)
    │   ├── catalog.py             # Schema constants, RESUMO_ACCOUNTS
    │   ├── sync_engine.py         # Download CVM ZIPs → populate dfp.db
    │   ├── query_engine.py        # Query annual statements
    │   └── status_reporter.py     # DB stats
    │
    └── itr/                       # Quarterly filings (ITR) → itr.db
        ├── __init__.py            # MANIFEST + route (sub-domain hub)
        ├── catalog.py             # Schema constants (same as DFP)
        ├── sync_engine.py         # Download CVM ZIPs → populate itr.db
        ├── query_engine.py        # Query quarterly cumulative data
        └── status_reporter.py     # DB stats
```

## 🚀 Quick Start

```python
from data_sources.cvm.dfp.sync_engine import sync as dfp_sync
from data_sources.cvm.itr.sync_engine import sync as itr_sync

# Sync current year only (~30s each)
dfp_sync()         # → dfp.db
itr_sync()         # → itr.db

# Sync specific years
dfp_sync(years=[2023, 2024])

# Sync full history
dfp_sync(full_history=True)   # 2010-present
itr_sync(full_history=True)   # 2015-present
```

## 🔧 Configuration

Data sources store data in `cfg.memory_root / "<domain>/"` (e.g., `memory_db/cvm/dfp.db`).

No env vars required — data sources use the existing `cfg.memory_root` + `cfg.workspace_root` from `core/config`.

---

*Last updated: 2026-07-23.*
