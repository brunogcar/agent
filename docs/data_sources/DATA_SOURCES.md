<- Back to [README](../README.md)

# 📊 Data Sources

Data sources are the **raw data ingestion + query layer**. Each data source syncs data from an external API (CVM, B3) into a local SQLite database, then provides query modes for reading it.

**Key characteristics:**
- **Single entry point** — `data_source(domain, sub_domain, mode, params)` @tool in `data_sources/dispatcher.py`
- **Auto-discovery** — domains and sub-domains are auto-discovered at startup. Adding a new sub-domain = creating one folder with `__init__.py` + `MANIFEST` + `route()`.
- **JSON params** — `params='{"company":"PETR4","limit":5}'`. Natural for LLMs, stable typed signature forever.
- **Sync + query** — each sub-domain has `sync` (download) + `query`/`lookup`/`search` (read) modes.
- **Read-only after sync** — no writes except during sync. Query modes never mutate.

---

## 🏗️ Architecture

```
LLM → data_source(domain, sub_domain, mode, params)  [@tool in dispatcher.py]
       └→ data_sources/<domain>/__init__.py route()
          └→ data_sources/<domain>/<sub_domain>/__init__.py route(mode)
             └→ sync_engine.py (download + store)
             └→ query_engine.py (read-only queries)
             └→ status_reporter.py (DB stats)
             └→ catalog.py (schema constants)
```

### Zero-maintenance design

Adding a new domain:
1. Create `data_sources/<domain>/__init__.py` with `MANIFEST` + `route()`
2. Done. Dispatcher auto-discovers it on next server restart.

Adding a new sub-domain:
1. Create `data_sources/<domain>/<sub_domain>/__init__.py` with `MANIFEST` + `route()`
2. Done. Domain router auto-discovers it.

---

## 📈 Domains

### B3 (Brasil, Bolsa, Balcão)

Brazilian stock exchange data. See [B3 Overview](b3/B3.md).

| Sub-domain | What | Storage |
|------------|------|---------|
| [API](b3/API.md) | Market data: instruments, trades, derivatives (paginated JSON API) | `memory_db/b3/{table}.db` |
| [DIVIDENDS](b3/DIVIDENDS.md) | Corporate actions: cash/stock dividends, subscriptions (per-ticker) | `memory_db/b3/dividends.db` |

### CVM (Comissão de Valores Mobiliários)

Brazilian SEC data. See [CVM Overview](cvm/CVM.md).

| Sub-domain | What | Storage |
|------------|------|---------|
| [DFP](cvm/DFP.md) | Annual financial statements | `memory_db/cvm/dfp.db` |
| [ITR](cvm/ITR.md) | Quarterly financial statements (cumulative) | `memory_db/cvm/itr.db` |
| [FRE](cvm/FRE.md) | Formulário de Referência (governance + ownership) | `memory_db/cvm/fre.db` |
| [IPE](cvm/IPE.md) | Material events index | `memory_db/cvm/ipe.db` |
| [CAD](cvm/CAD.md) | Company register (CNPJ → CD_CVM + names) | `memory_db/cvm/cad.db` |
| [BRIDGE](cvm/BRIDGE.md) | B3-CVM identity bridge (ticker → cd_cvm → CNPJ) | `memory_db/cvm/bridge.db` |

---

## 🚀 Quick Start

```
# Sync CVM DFP (annual financials)
data_source(domain="cvm", sub_domain="dfp", mode="sync")

# Sync CVM CAD (company register — needed for bridge)
data_source(domain="cvm", sub_domain="cad", mode="sync")

# Sync B3 dividends for PETR4 (per-ticker)
data_source(domain="b3", sub_domain="dividends", mode="sync", params='{"ticker":"PETR4"}')

# Bridge PETR4 (ticker → CNPJ → CD_CVM)
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')

# Query DFP financials by ticker
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')
```

---

## 🔗 Relationship to Skills

Data sources provide raw data. **Skills** (see [SKILLS.md](../SKILLS.md)) sit on top, combining multiple data sources with domain reasoning to produce analytical views.

| Layer | Purpose | Example |
|-------|---------|---------|
| data_sources | Raw data ingestion + query | `data_source(domain="cvm", sub_domain="fre", mode="shareholders")` |
| skills | Analytical views combining sources | `skill(domain="cvm", sub_domain="shareholders", mode="summary")` |

---

## 📁 File Layout (per sub-domain)

```
data_sources/<domain>/<sub_domain>/
├── __init__.py        # MANIFEST + route(mode)
├── catalog.py         # Schema constants (SQL, URLs, column mappings)
├── sync_engine.py     # Download + parse + store
├── query_engine.py    # Read-only query modes
└── status_reporter.py # DB stats (table counts, sync dates, year ranges)
```

---

*Last updated: 2026-07-23.*
