# 🧠 CVM Skills

Analytical skills that combine multiple CVM data sources with domain reasoning.

## Skills

| Skill | What | Data Sources |
|-------|------|--------------|
| [shareholders](shareholders/) | Named shareholders + free float + equity structure | FRE (posicao_acionaria, distribuicao_capital) + DFP (BPP 2.03.*) |
| [dividends](dividends/) | Individual events + annual totals + payable + filings | B3 dividends + DFP (DVA 7.08.04.*, BPP 2.01.05.02.*) + IPE |

## Skills vs Data Sources

- **data_sources** = raw data ingestion + query (sync, status, query modes)
- **skills** = analytical views that combine data sources + reasoning (read-only, no sync)

Skills call data_source query engines directly (no JSON round-trip). They assume
data is already synced.

## Usage

```
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="dividends", mode="summary", params='{"company":"PETR4"}')
```

## Architecture

```
LLM → skill(domain, sub_domain, mode, params)  [skills/dispatcher.py @tool]
       └→ skills/cvm/__init__.py route()
          └→ skills/cvm/<skill>/__init__.py route(mode)
             └→ skills/cvm/<skill>/<skill>.py  (calls data_source query engines)
                └→ data_sources/cvm/{fre,dfp,ipe}/query_engine.py
                └→ data_sources/b3/dividends/query_engine.py
                └→ data_sources/cvm/_bridge.py resolve_company()
```

---

*Last updated: 2026-07-23.*
