<- Back to [Skills Overview](../SKILLS.md)

# 🧠 CVM Skills

Analytical skills that combine CVM + B3 data sources with domain reasoning.

**Key characteristics:**
- **Read-only** — no sync. Skills call data_source query engines directly.
- **Bridge auto-sync** — first ticker query auto-syncs the bridge transparently.
- **Combine multiple sources** — each skill merges data from DFP, ITR, FRE, IPE, B3 dividends, etc.

## Skills

| Skill | Modes | Data Sources |
|-------|-------|--------------|
| [**financials**](cvm/FINANCIALS.md) | quarterly (default), annual, complete, summary | DFP (annual) + ITR (quarterly cumulative) + DVA (proventos) — rapina-style |
| [**shareholders**](cvm/SHAREHOLDERS.md) | shareholders, free_float, equity_structure, summary | FRE (named shareholders, free float) + DFP (equity structure in BRL) |
| [**dividends**](cvm/DIVIDENDS.md) | history, annual, payable, announcements, summary | B3 (individual events) + DFP DVA (annual totals) + DFP BPP (payable) + IPE (filings) |
| [**valuation**](cvm/VALUATION.md) | ratios, summary | investsite/b3 trades (price) + DFP (financials) + FRE/investsite (shares) — P/L, P/VPA, EV, Div Yield |

All CVM skills use `core/br_validator` for BRL/date/ticker parsing.

## Quick Start

```
# Financial statements + ratios (quarterly default — analyze new releases)
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')

# Named shareholders
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')

# Dividend events + annual totals
skill(domain="cvm", sub_domain="dividends", mode="summary", params='{"company":"PETR4"}')

# Valuation ratios (P/L, P/VPA, EV, Div Yield)
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')
```

## 🔧 Prerequisite Sync Commands

CVM skills are read-only — they need CVM data sources synced first. Run from `D:\mcp\agent>`:

```powershell
# CAD (company register — needed for bridge)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cad.sync_engine import sync; print(sync())"

# Bridge (ticker → CNPJ → CD_CVM — needed for all CVM skills)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.bridge.sync_engine import sync; print(sync(ticker='PETR4'))"

# DFP (annual financials — needed for financials, shareholders, dividends, valuation)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.dfp.sync_engine import sync; print(sync())"

# ITR (quarterly financials — needed for financials quarterly mode)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.itr.sync_engine import sync; print(sync())"

# FRE (governance + shares — needed for shareholders, valuation)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.fre.sync_engine import sync; print(sync())"

# IPE (material events — needed for dividends announcements)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.ipe.sync_engine import sync; print(sync())"
```

See [CVM Data Sources](../data_sources/CVM.md) for per-sub-domain details, and [B3 Data Sources](../data_sources/B3.md) for B3 sync commands (needed by dividends + valuation skills).

## Architecture

```
LLM → skill(domain="cvm", sub_domain=..., mode=..., params=...)  [skills/dispatcher.py @tool]
       └→ skills/cvm/__init__.py route()
          └→ skills/cvm/<skill>/__init__.py route(mode)
             └→ skills/cvm/<skill>/<skill>.py  (calls data_source query engines)
                └→ data_sources/cvm/{dfp,itr,fre,ipe,cad,bridge}/query_engine.py
                └→ data_sources/b3/dividends/query_engine.py
                └→ data_sources/cvm/_bridge.py resolve_company()
```

---

*Last updated: 2026-07-24.*
