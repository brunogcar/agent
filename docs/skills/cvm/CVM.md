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
| [**financials**](FINANCIALS.md) | quarterly (default), annual, complete, summary | DFP (annual) + ITR (quarterly cumulative) + DVA (proventos) — rapina-style |
| [**shareholders**](SHAREHOLDERS.md) | shareholders, free_float, equity_structure, summary | FRE (named shareholders, free float) + DFP (equity structure in BRL) |
| [**dividends**](DIVIDENDS.md) | history, annual, payable, announcements, summary | B3 (individual events) + DFP DVA (annual totals) + DFP BPP (payable) + IPE (filings) |

## Quick Start

```
# Financial statements + ratios (quarterly default — analyze new releases)
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')

# Named shareholders
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')

# Dividend events + annual totals
skill(domain="cvm", sub_domain="dividends", mode="summary", params='{"company":"PETR4"}')
```

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
