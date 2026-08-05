# 📊 Data Sources

Data sources are external data connectors that sync from APIs (CVM, B3, BCB) into local SQLite DBs, plus a query interface. They follow the hub-and-spoke pattern: a single `@tool`-decorated dispatcher routes to domain hubs, which route to sub-domains.

**vs skills/**: Data sources handle raw data storage + retrieval. The skills/ layer handles domain reasoning that combines multiple data sources (e.g., computing standalone quarters from DFP + ITR, or valuation ratios). See [SKILLS.md](SKILLS.md).

## Domains

| Domain | What | Landing Page |
|--------|------|--------------|
| **CVM** | Brazilian SEC data: DFP (annual), ITR (quarterly), FRE (governance), IPE (events), CAD (register), Bridge (ticker→CNPJ) | [CVM.md](data_sources/CVM.md) |
| **B3** | Brazilian stock exchange: API (instruments, trades, derivatives), Dividends (corporate actions), BRAPI (quotes/OHLCV), COTAHIST (historical) | [B3.md](data_sources/B3.md) |
| **BCB** | Brazilian Central Bank: SGS (12 curated macro series - Selic, CDI, TR, IPCA, IGP-M, USD/BRL, PIB, Salario minimo). Public API, no auth. | [BCB.md](data_sources/BCB.md) |

## 🏗️ Architecture

```text
data_sources/
├── dispatcher.py                  # @tool data_source(domain, sub_domain, mode, params)
│
├── cvm/                           # CVM domain
│   ├── __init__.py                # Domain hub
│   ├── _db.py                     # Shared: paths, CNPJ, parse_escala, connect helpers
│   ├── _bridge.py                 # Shared: resolve_company (ticker → CNPJ → empresa_ids)
│   ├── _meses.py                  # Shared: meses computation (rapinav2 formula)
│   ├── dfp/                       # Annual financial statements → dfp.db
│   ├── itr/                       # Quarterly financial statements → itr.db
│   ├── fre/                       # Governance + shareholders → fre.db
│   ├── ipe/                       # Material events → ipe.db
│   ├── cad/                       # Company register → cad.db
│   └── bridge/                    # B3-CVM identity bridge → bridge.db + isin_index.db
│
├── b3/                            # B3 domain
│   ├── __init__.py                # Domain hub
│   ├── api/                       # Market data (instruments, trades, derivatives)
│   ├── brapi/                     # brapi.dev API (quotes, OHLCV, tickers)
│   ├── cotahist/                  # B3 official historical trade data (COTAHIST)
│   └── dividends/                 # Corporate actions (cash/stock dividends, subscriptions)
│
└── bcb/                           # BCB domain (Brazilian Central Bank)
    ├── __init__.py                # Domain hub
    └── sgs/                       # SGS (Sistema Gerenciador de Series Temporais) → sgs.db
        ├── catalog.py             # 12 curated series + schema
        ├── fetcher.py             # Thread-safe HTTP (Semaphore(5), 5-min cache)
        ├── sync_engine.py         # sync_series / sync_all / sync_series_range
        ├── query_engine.py        # series / last / search / summary
        └── status_reporter.py     # DB stats
```

## 🚀 Quick Start

```powershell
# CVM — sync all (run from D:\mcp\agent>)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cad.sync_engine import sync; print(sync())"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.dfp.sync_engine import sync; print(sync())"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.itr.sync_engine import sync; print(sync())"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.fre.sync_engine import sync; print(sync())"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.ipe.sync_engine import sync; print(sync())"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.bridge.sync_engine import sync; print(sync(ticker='PETR4'))"

# B3 — sync all
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.brapi.sync_engine import sync_tickers; print(sync_tickers())"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.brapi.sync_engine import sync_history; print(sync_history(ticker='PETR4'))"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.dividends.sync_engine import sync; print(sync(ticker='PETR4'))"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.api.sync_engine import sync; print(sync(table='trades'))"
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync_full_history; print(sync_full_history())"

# BCB — sync all 12 macro series (Selic, CDI, TR, IPCA, IGP-M, USD/BRL, PIB, Salario minimo)
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_all; print(sync_all())"
```

See [CVM.md](data_sources/CVM.md), [B3.md](data_sources/B3.md), and [BCB.md](data_sources/BCB.md) for full sync commands per sub-domain.

## 🔧 Configuration

Data sources store data in `cfg.memory_root / "<domain>/"` (e.g., `memory_db/cvm/dfp.db`, `memory_db/bcb/sgs.db`).

No env vars required — data sources use the existing `cfg.memory_root` from `core/config`.

---

*Last updated: 2026-07-24.*
