<- Back to [Skills Overview](../SKILLS.md)

# 🧠 CVM Skills

Analytical skills that combine CVM + B3 data sources with domain reasoning.

**Key characteristics:**
- **Read-only** — no sync. Skills call data_source query engines directly.
- **Force-sync guard** — every CVM skill declares `required_sources` in `__init__.py`. The `route()` wrapper HEAD-checks CVM's server before EVERY dispatch (see below).
- **Bridge auto-sync** — first ticker query auto-syncs the bridge transparently.
- **Combine multiple sources** — each skill merges data from DFP, ITR, FRE, IPE, B3 dividends, etc.

## 🔄 Force Sync (HEAD Check)

Every CVM skill declares `REQUIRED_SOURCES` in its `__init__.py`. When you call
`route(mode=..., company=...)`, the `route()` wrapper (from `skills/_base/route.py`,
the `make_route()` factory) calls `ensure_fresh(REQUIRED_SOURCES)` (defined in
`skills/_base/sync_guard.py`) BEFORE dispatching to the mode function.

**CVM sources ALWAYS get a HEAD check** against CVM's server — not just a 24h
freshness window. This catches new quarterly filings published within the 24h
window. The 8 CVM sources and their HEAD-check URLs:

| Source | HEAD URL |
|--------|----------|
| `dfp` | `dados.cvm.gov.br/.../DFP/DADOS/dfp_cia_aberta_{year}.zip` |
| `itr` | `dados.cvm.gov.br/.../ITR/DADOS/itr_cia_aberta_{year}.zip` |
| `fca` | `dados.cvm.gov.br/.../FCA/DADOS/fca_cia_aberta_{year}.zip` |
| `fre` | `dados.cvm.gov.br/.../FRE/DADOS/fre_cia_aberta_{year}.zip` |
| `ipe` | `dados.cvm.gov.br/.../IPE/DADOS/ipe_cia_aberta_{year}.zip` |
| `vlmo` | `dados.cvm.gov.br/.../VLMO/DADOS/vlmo_cia_aberta_{year}.zip` |
| `cgvn` | `dados.cvm.gov.br/.../CGVN/DADOS/cgvn_cia_aberta_{year}.zip` |
| `cad` | `dados.cvm.gov.br/.../CAD/DADOS/cad_cia_aberta.csv` |

**How it works** (visible in stderr):
```
  [sync] Checking CVM dfp HEAD...
  [sync] dfp HEAD: up to date (no sync needed)       ← Last-Modified ≤ last sync
  [sync] Checking CVM itr HEAD...
  [sync] itr HEAD: new data available → force-sync   ← Last-Modified > last sync
  [sync] Force-syncing itr (kwargs: {...})...
  [sync] itr done.
```

If the HEAD request fails (network error, timeout), it syncs anyway (safer to
sync than skip). Non-CVM sources in `REQUIRED_SOURCES` (e.g., `cotahist`,
`brapi`, `bridge`) use a 24h freshness window — see [B3.md](B3.md) and
[BCB.md](BCB.md) for those.

**Escape hatches:** `CVM_SKIP_SYNC=1` env var (used in tests) or
`skip_sync=True` kwarg.

**Re-entrancy:** `ensure_fresh()` runs at most once per top-level `route()`
call. If `dashboard()` internally calls `annual()` (which calls `route()`),
the inner call skips the sync check — it's already been done by the outer call.

## 📄 Auto-HTML Generation

Every `route(mode="dashboard", ...)` call **auto-generates an HTML file** —
the result dict includes an `html_path` key pointing to the rendered dashboard.
The HTML file is written to the **reports root** with a company prefix:

```
workspace/reports/{company}_{skill}_dashboard.html
```

Example: `route(mode="dashboard", company="PETR4")` on valuation produces
`workspace/reports/PETR4_valuation_dashboard.html`.

```
r = route(mode="dashboard", company="PETR4")
print(r["html_path"])  # → workspace/reports/PETR4_valuation_dashboard.html
```

**Escape hatch:** `CVM_SKIP_HTML=1` env var (set automatically in tests).

## 🗄️ Engine Result Cache

Engine `*_at(company, date)` results are cached persistently in
`memory_db/cache/engine_cache.db` (via `data_sources/_cache.py`). This eliminates
redundant engine computation across skills — when valuation computes
`revenue_at("PETR4", "2024-06-30")` and then financials computes the same, the
second call is a cache hit.

**3-layer cache** (in `@engine_cached` decorator, `skills/_base/engine_cache.py`):
1. **In-memory** (ContextVar `engine_cache_scope`) — within one `route()` call
2. **DB cache** (persistent) — cross-skill, cross-process
3. **Real engine fn** — queries DFP/ITR/COTAHIST/SGS

**Invalidation is per-company** via fingerprint:
- DFP/ITR engines: `MAX(versao) + MAX(data_fim_exerc)` for that CNPJ
- COTAHIST engines: `MAX(refdate)` for that ticker
- BCB SGS engines: `MAX(ref_date)` for the series
- FRE engines: `MAX(data_referencia)` for that CNPJ

If CVM publishes a new filing (new `versao` or new period), the fingerprint
changes → cache miss → recompute. This is more precise than the HEAD-check
timestamp (which is per-source, not per-company).

**Escape hatch:** `CVM_SKIP_DB_CACHE=1` env var (set automatically in tests).

See [DATA_SOURCES.md](../DATA_SOURCES.md#-engine-result-cache-_cachepy) for
full architecture details.

## Skills

| Skill | Modes | Data Sources |
|-------|-------|--------------|
| [**financials**](cvm/FINANCIALS.md) | quarterly (default), annual, complete, summary, dashboard | DFP (annual) + ITR (quarterly cumulative) + DVA (proventos) — rapina-style |
| [**shareholders**](cvm/SHAREHOLDERS.md) | shareholders, free_float, equity_structure, summary, dashboard | FRE (named shareholders, free float) + DFP (equity structure in BRL) |
| [**dividends**](cvm/DIVIDENDS.md) | history, annual, payable, announcements, summary, dashboard | B3 (individual events) + DFP DVA (annual totals) + DFP BPP (payable) + IPE (filings) |
| [**valuation**](cvm/VALUATION.md) | ratios, summary, dashboard | b3 price + DFP/ITR TTM financials + FRE shares — P/L, P/VPA, EV, ROIC, Graham Number |
| [**comparison**](cvm/COMPARISON.md) | side_by_side (default), summary, growth, dashboard | Orchestrates financials + valuation + dividends per ticker — multi-ticker compare |
| [**screener**](cvm/SCREENER.md) | sector, compare, dashboard | Orchestrates CAD + bridge + valuation + financials + FCA (listing segment) — sector peers + medians |
| [**insider**](cvm/INSIDER.md) | history, by_role, summary, dashboard | VLMO (insider trading disclosures) — insider buy/sell + sentiment |
| [**governance**](cvm/GOVERNANCE.md) | practices, score, by_chapter, dashboard | CGVN (governance practices) — % adopted, chapter breakdown |

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
| dividends history / annual / summary / dashboard | `dividends_history` / `dividends_annual` / `dividends_summary` / `dividends_dashboard` |
| comparison side_by_side / summary / growth / dashboard | `comparison_side_by_side` / `comparison_summary` / `comparison_growth` / `comparison_dashboard` |
| screener sector / dashboard | `screener_sector` / `screener_dashboard` |
| shareholders shareholders / free_float / equity_structure / summary / dashboard | `shareholders_shareholders` / `shareholders_free_float` / `shareholders_equity_structure` / `shareholders_summary` / `shareholders_dashboard` |
| insider history / by_role / summary / dashboard | `insider_history` / `insider_by_role` / `insider_summary` / `insider_dashboard` |
| governance practices / score / by_chapter / dashboard | `governance_practices` / `governance_score` / `governance_by_chapter` / `governance_dashboard` |
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
             ├─ ALL 10 CVM skills now use the modular pattern (financials v1.6, valuation v1.4,
             │    backtest v1.1, comparison v1.5, dividends v1.1, governance v1.1, historical v1.2,
             │    screener v1.4, shareholders v1.1, insider v1.1):
             │    └→ skills/cvm/<skill>/modes/<mode>.py  (auto-discovered via _registry.py)
             │       └→ helpers.py + report.py (+ fetchers.py / metrics.py where needed)
             │          └→ data_source query engines + calculations engines
             │
             └─ (no CVM skills remain on the single-file pattern — all migrated)
```

**All 10 CVM skills** now use the **modular `modes/ + _registry.py` pattern** (auto-discovery via `importlib` on `modes/*.py`, mirroring `skills/cvm/calculations/_registry.py` + `tools/git_ops/actions/`): `financials` (v1.6), `valuation` (v1.4), `backtest` (v1.1), `comparison` (v1.5), `dividends` (v1.1), `governance` (v1.1), `historical` (v1.2), `screener` (v1.4), `shareholders` (v1.1), `insider` (v1.1). Adding a new mode = drop a file in `modes/` + `@register_mode(...)`; no edits to `__init__.py`. Every CVM skill also has a `dashboard` mode + matching `<skill>_dashboard` report adapter.

---

*Last updated: 2026-09-15 (Phase 3 doc sweep — updated `skills/_base.py` references to point at the split `_base/` package modules: `route.py` for `make_route`, `engine_cache.py` for `@engine_cached`). Prior: v1.8 — screener/shareholders/insider/investsite modular splits + dashboard modes.*
