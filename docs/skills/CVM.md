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
| [**financials**](cvm/FINANCIALS.md) | quarterly (default), annual, complete, summary, dashboard | DFP (annual) + ITR (quarterly cumulative) + DVA (proventos) — rapina-style |
| [**shareholders**](cvm/SHAREHOLDERS.md) | shareholders, free_float, equity_structure, summary | FRE (named shareholders, free float) + DFP (equity structure in BRL) |
| [**dividends**](cvm/DIVIDENDS.md) | history, annual, payable, announcements, summary | B3 (individual events) + DFP DVA (annual totals) + DFP BPP (payable) + IPE (filings) |
| [**valuation**](cvm/VALUATION.md) | ratios, summary, dashboard | b3 price + DFP/ITR TTM financials + FRE shares — P/L, P/VPA, EV, ROIC, Graham Number |
| [**comparison**](cvm/COMPARISON.md) | side_by_side (default), summary, growth | Orchestrates financials + valuation + dividends per ticker — multi-ticker compare |
| [**screener**](cvm/SCREENER.md) | sector, compare | Orchestrates CAD + bridge + valuation + financials + FCA (listing segment) — sector peers + medians |
| [**insider**](cvm/INSIDER.md) | history, by_role, summary | VLMO (insider trading disclosures) — insider buy/sell + sentiment |
| [**governance**](cvm/GOVERNANCE.md) | practices, score, by_chapter | CGVN (governance practices) — % adopted, chapter breakdown |

All CVM skills use `core/br_validator` for BRL/date/ticker parsing.

## 📊 Report Integration (v1.2)

CVM skills return nested JSON. To render or export that data, pipe a skill result
into the `report` tool's `table` action (or `export` xlsx) with the matching
adapter in `config["adapter"]`. The report tool stays domain-agnostic — adapters
live in `tools/report_ops/adapters/`.

```
# 1. Get the data
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')
#    -> <financials JSON>

# 2a. Render as an HTML table
report(action="table", title="PETR4 Financials",
       data=<financials JSON>, config={"adapter":"financials_quarterly"})

# 2b. Or export to Excel
report(action="export", title="PETR4 Financials",
       data=<financials JSON>, config={"format":"xlsx","adapter":"financials_quarterly"})
```

| Skill (mode) | Adapter |
|--------------|---------|
| financials quarterly / annual / summary | `financials_quarterly` / `financials_annual` / `financials_summary` |
| financials quarterly (chart) | `financials_quarterly_chart` (multi-series line chart) |
| valuation ratios / summary | `valuation_ratios` / `valuation_summary` |
| shareholders shareholders / free_float / equity_structure / summary | `shareholders_shareholders` / `shareholders_free_float` / `shareholders_equity_structure` / `shareholders_summary` |
| dividends history / annual / summary | `dividends_history` / `dividends_annual` / `dividends_summary` |
| comparison side_by_side / summary / growth | `comparison_side_by_side` / `comparison_summary` / `comparison_growth` |
| screener sector | `screener_sector` |
| insider history / by_role / summary | `insider_history` / `insider_by_role` / `insider_summary` |
| governance practices / score / by_chapter | `governance_practices` / `governance_score` / `governance_by_chapter` |
| b3 cotahist (price history) | `cotahist_close_chart` (line) / `cotahist_candlestick_chart` (candlestick) |

Number formatting (BRL, %) is handled by the report tool's shared `formats.py`
spec vocabulary — skills don't need to format anything. See
[tools/REPORT.md](../tools/REPORT.md) and [report API](../tools/report/API.md).

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
             │
             ├─ financials (v1.6) + valuation (v1.4):
             │    └→ skills/cvm/<skill>/modes/<mode>.py  (auto-discovered via _registry.py)
             │       └→ fetchers.py + helpers.py + report.py (+ metrics.py for financials)
             │          └→ data_source query engines + calculations engines
             │
             └─ other CVM skills (shareholders/dividends/comparison/screener/insider/governance):
                  └→ skills/cvm/<skill>/<skill>.py  (calls data_source query engines)
                     └→ data_sources/cvm/{dfp,itr,fre,ipe,cad,bridge}/query_engine.py
                     └→ data_sources/b3/dividends/query_engine.py
                     └→ data_sources/cvm/_bridge.py resolve_company()
```

`financials` (v1.6) and `valuation` (v1.4) use the **modular `modes/ + _registry.py` pattern** (auto-discovery via `importlib` on `modes/*.py`, mirroring `skills/cvm/calculations/_registry.py` + `tools/git_ops/actions/`). Adding a new mode = drop a file in `modes/` + `@register_mode(...)`; no edits to `__init__.py`. Other CVM skills still use the single-file `<skill>.py` pattern — they will be migrated to the modular pattern incrementally.

---

*Last updated: 2026-07-29.*
