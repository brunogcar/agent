# 📊 Data Sources

Data sources are external data connectors that sync from APIs (CVM, B3, BCB) into local SQLite DBs, plus a query interface. They follow the hub-and-spoke pattern: a single `@tool`-decorated dispatcher routes to domain hubs, which route to sub-domains.

**vs skills/**: Data sources handle raw data storage + retrieval. The skills/ layer handles domain reasoning that combines multiple data sources (e.g., computing standalone quarters from DFP + ITR, or valuation ratios). See [SKILLS.md](SKILLS.md).

## Domains

| Domain | What | Landing Page |
|--------|------|--------------|
| **CVM** | Brazilian SEC data: DFP (annual), ITR (quarterly), FRE (governance), IPE (events), CAD (register), Bridge (ticker→CNPJ) | [CVM.md](data_sources/CVM.md) |
| **B3** | Brazilian stock exchange: API (instruments, trades, derivatives), Dividends (corporate actions), BRAPI (quotes/OHLCV), COTAHIST (historical), INDEX (IBOV, SMLL, BDRX, IFIX, IDIV + 26 catalogued) | [B3.md](data_sources/B3.md) |
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
│   ├── dividends/                 # Corporate actions (cash/stock dividends, subscriptions)
│   └── index/                     # B3 indices (IBOV, SMLL, BDRX, IFIX, IDIV + 26 catalogued)
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
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.index.sync_engine import sync_all; print(sync_all())"

# BCB — sync all 12 macro series (Selic, CDI, TR, IPCA, IGP-M, USD/BRL, PIB, Salario minimo)
python3 -c "from data_sources.bcb.sgs.sync_engine import sync_all; print(sync_all())"
```

See [CVM.md](data_sources/CVM.md), [B3.md](data_sources/B3.md), and [BCB.md](data_sources/BCB.md) for full sync commands per sub-domain.

## 🔧 Configuration

Data sources store data in `cfg.memory_root / "<domain>/"` (e.g., `memory_db/cvm/dfp.db`, `memory_db/bcb/sgs.db`, `memory_db/b3/index.db`).

No env vars required — data sources use the existing `cfg.memory_root` from `core/config`.

---

## 🏗️ Domain Creation Guidance

When adding a new data source **sub-domain** (e.g., `data_sources/b3/index/`), follow this checklist:

1. **Pick the parent domain** — `cvm/`, `b3/`, or `bcb/`. If none fits, create a new domain folder (see below).
2. **Create the sub-domain folder** — `data_sources/<domain>/<sub_domain>/`.
3. **Write 4 Python modules** (no `__init__.py` for the sub-domain; the domain's `__init__.py` routes via dispatcher):
   - `catalog.py` — schema constants, URL templates, SQL DDL, DB path/connect helpers.
   - `sync_engine.py` — `sync_*` functions (download → parse → store). DELETE + INSERT for idempotency.
   - `query_engine.py` — query functions (filter, sort, paginate).
   - `status_reporter.py` — DB stats (rows, last sync, etc.).
4. **Wire the route** — add the sub-domain to `data_sources/<domain>/__init__.py` MANIFEST + route dispatch (mirrors existing sub-domains like `b3/cotahist`).
5. **Add `required_sources` integration** — if a skill will read this sub-domain, add its short name (e.g., `"index"`) to the skill's `REQUIRED_SOURCES` list AND to `skills/_base.py`'s `_trigger_sync.sync_map` so the sync guard knows which sync function to call.
6. **Create docs** in `docs/data_sources/<domain>/`:
   - `<SUB_DOMAIN>.md` — landing page (Quick Start, Configuration, Sync Commands, Subfile Directory).
   - `<sub_domain>/API.md` — modes (sync_* + query modes + status).
   - `<sub_domain>/ARCHITECTURE.md` — file map, DB schema (table-by-table), design decisions.
   - `<sub_domain>/CHANGELOG.md` — version history (v1.0 entry on launch).
   - `<sub_domain>/INSTRUCTIONS.md` — AI editing rules (NEVER DO + ALWAYS DO).
7. **Update the domain landing page** — add a row to the sub-domains table in `docs/data_sources/<DOMAIN>.md`.
8. **Update `docs/DATA_SOURCES.md`** — add the sub-domain mention to the parent domain row + extend the architecture tree + add a sync command to Quick Start.

### Adding a brand-new domain

If the sub-domain doesn't fit under `cvm/`, `b3/`, or `bcb/`:

1. Create `data_sources/<new_domain>/__init__.py` with a domain hub (mirrors `data_sources/b3/__init__.py`).
2. Register the domain in `data_sources/dispatcher.py` so the `@tool data_source(domain=...)` accepts the new value.
3. Add a row to the **Domains** table at the top of this file.
4. Add a subtree to the **Architecture** tree above.
5. Create `docs/data_sources/<NEW_DOMAIN>.md` (domain landing page) following the pattern of [B3.md](data_sources/B3.md) or [CVM.md](data_sources/CVM.md).
6. Add sync commands to the **Quick Start** section.
7. Add the new domain to **skills/_base.py `_trigger_sync.sync_map`** if any skill will declare it in `REQUIRED_SOURCES`.

---

*Last updated: 2026-08-05.*
