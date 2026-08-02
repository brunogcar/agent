# 🧩 Skills Architecture & Domain Guide

Skills are domain-specific knowledge packages that extend the agent's capabilities beyond general-purpose tools. Unlike core meta-tools (which implement atomic actions), skills encapsulate **domain expertise, data pipelines, and specialized workflows** for specific industries or use cases.

## 🏗️ Skill Creation Guidelines

### The Hub-and-Spoke Pattern

Skills do **not** use the `@tool` decorator on every function. Instead, they rely on `skills/dispatcher.py` to auto-discover **Domain Hubs**.

**The Hub** (`<domain>.py`): A single entry-point file that acts as the MCP tool. It receives the user's intent and routes it to the correct subdomain.

**The Subdomains**: Pure Python modules containing the actual business logic, API wrappers, and data processing. They are **not** exposed directly to the LLM.

**The Dispatcher**: `skills/dispatcher.py` scans the `skills/` directory, identifies these Hubs, and registers them as top-level tools (e.g., a tool named `b3` and a tool named `cvm`).

### Step-by-Step: Adding a New Skill Domain

1. **Create the Domain Folder**: `skills/my_domain/`
2. **Create the Hub**: Create `skills/my_domain/my_domain.py`. This file must implement the main execution logic that `dispatcher.py` expects.
3. **Create Subdomains**: Create modules like `skills/my_domain/api_client.py` or `skills/my_domain/analytics.py`.
4. **Wire the Hub**: Inside `my_domain.py`, import your subdomains and route the `action` argument to them.

```python
# skills/my_domain/my_domain.py (The Hub)
from . import api_client, analytics

def execute(action: str, **kwargs) -> dict:
    """Main entry point registered by skills/dispatcher.py"""
    if action == "fetch_data":
        return api_client.fetch(**kwargs)
    elif action == "analyze":
        return analytics.run(**kwargs)
    return {"status": "error", "error": f"Unknown action: {action}"}
```

### ⚠️ AI Agent Constraints for Skills

- **Hub Responsibility**: The Hub is responsible for input validation and error handling before passing data to subdomains.
- **No Direct MCP Decorators**: Do **not** use `@tool` inside subdomain files. Only the Hub is registered as a tool.
- **Logging**: Use `core.tracer` for all logging. Never use `print()`.
- **Data Lake**: Store downloaded datasets in `WORKSPACE_ROOT/data/<domain>/` for persistence across sessions.

---

## 🏗️ Modular Skill Pattern (skills/_base.py)

All 11 skills (10 CVM + investsite) use a shared modular pattern built on
`skills/_base.py`. This file provides the infrastructure so each skill only
needs ~3 lines in `_registry.py` + ~20 lines in `__init__.py`.

**What `skills/_base.py` provides:**

| Component | Purpose | Version |
|-----------|---------|---------|
| `ModeSpec` dataclass | Mode metadata (name, fn, description, params, examples) | v1.0 |
| `make_registry()` | Creates a per-skill MODES dict + `register_mode` decorator | v1.0 |
| `build_manifest_modes(MODES)` | Turns registry into MANIFEST["modes"] dict | v1.0 |
| `auto_discover_modes(__name__)` | Importlib-based modes/*.py auto-discovery | v1.0 |
| `make_route(manifest_key, skill_name, MODES, ...)` | Generates the route() dispatcher | v1.0 |
| `_dispatch(...)` | Internal dispatch (filters kwargs by signature) | v1.0 |
| `@engine_cached` decorator | Caches engine at_fn/periods_fn within a scope | v1.9 F7 |
| `engine_cache_scope` context manager | Activates the engine cache for its block | v1.9 F7 |
| `ensure_fresh(sources, ...)` | Force-syncs stale data sources before dispatch | v1.14 |
| `_source_is_stale(source)` | Checks sync_state timestamp against 24h window | v1.14 |
| `_cvm_has_new_data(source, year)` | HEAD check before downloading (CVM only) | v1.14 |
| `_trigger_sync(source, company, ...)` | Maps source name to sync fn with right args | v1.14 |
| `_route_with_sync_guard(...)` | Wraps sync check + dispatch with re-entrancy guard | v1.14 |

### Architecture

```
skills/
├── _base.py                          # Shared infrastructure (ModeSpec, make_registry, make_route)
├── dispatcher.py                     # Auto-discovers skill domains
├── cvm/
│   ├── __init__.py                   # CVM domain hub (routes sub_domain → skill)
│   ├── _shared_report/               # [v1.16.1] Shared dashboard builders (all CVM skills)
│   │   ├── __init__.py               # Exports: build_company_header, build_price_chart, get_tooltip
│   │   ├── company_header.py         # FCA + CAD + COTAHIST company info card
│   │   ├── price_chart.py            # Historical price chart with Tudo/5A/1A/1M range selector
│   │   └── tooltips.py               # PT-BR formula tooltips for ratio_grid indicators
│   ├── financials/
│   │   ├── __init__.py               # ~20 lines: auto_discover + MANIFEST + route
│   │   ├── _registry.py              # ~3 lines: MODES, register_mode = make_registry()
│   │   ├── report.py                 # Dashboard composition helpers (imports from _shared_report)
│   │   ├── fetchers.py / helpers.py  # Internal utilities (optional)
│   │   └── modes/
│   │       ├── __init__.py           # Empty marker
│   │       ├── quarterly.py          # @register_mode("quarterly", ...)
│   │       ├── annual.py             # @register_mode("annual", ...)
│   │       └── dashboard.py          # @register_mode("dashboard", ...)
│   ├── valuation/                    # Same pattern (imports from _shared_report)
│   ├── governance/                   # Same pattern
│   └── ... (8 more CVM skills)
└── investsite/
    ├── __init__.py                   # ~25 lines (accept_sub_domain=True)
    ├── _registry.py                  # ~3 lines
    ├── fetcher.py / parsers.py       # Internal utilities (KEPT — not split)
    ├── report.py
    └── modes/
        └── ... (6 mode files)
```

### Shared Report Builders (`skills/cvm/_shared_report/`)

[v1.16.1] Extracted from `financials/report.py` so all CVM skill dashboards
can reuse the same company header, price chart, and tooltip system without
copying code. Prevents the copy-paste-drift pattern identified by
collective LLM review.

**Usage:**
```python
from skills.cvm._shared_report import build_company_header, build_price_chart, get_tooltip

# Company header (FCA + CAD + COTAHIST)
header = build_company_header("PETR4")
# → {"ticker": "PETR4", "name": "PETROLEO BRASILEIRO S.A. PETROBRAS", "cnpj": "33.000.167/0001-01", ...}

# Historical price chart with time-range selector
chart = build_price_chart("PETR4")
# → {"type": "chart", "price_range_selector": True, "price_full_labels": [...], ...}

# Tooltip for a metric
tooltip = get_tooltip("roe", spec)
# → "ROE = Lucro Líquido / Patrimônio Líquido. Rentabilidade do capital dos acionistas."
```

**Modules:**
| File | Exports | Purpose |
|------|---------|---------|
| `company_header.py` | `build_company_header(company)` | FCA (name, CNPJ, CD_CVM, sector, listing segment, control type, website, fiscal year-end) + CAD (trade name, UF) + COTAHIST (ISIN, latest close) |
| `price_chart.py` | `build_price_chart(company)` | 10Y daily closes from COTAHIST + Tudo/5A/1A/1M range selector (client-side JS filtering) |
| `tooltips.py` | `get_tooltip(metric_name, spec)`, `_METRIC_TOOLTIPS` | 38 PT-BR formula strings; falls back to `MetricSpec.tooltip` field (calculations `_registry.py`) |

**Adding a new CVM skill dashboard:**
1. Import `build_company_header` + `build_price_chart` + `get_tooltip` from `_shared_report`.
2. Call `build_company_header(company)` once, store in `result["company_header"]` + insert as `company_info` section at top of Overview tab.
3. Call `build_price_chart(company)`, insert as chart section after header.
4. Use `get_tooltip(metric_name, spec)` when building `ratio_grid` items.

The financials dashboard (`skills/cvm/financials/modes/dashboard.py`) is the
reference implementation — valuation/historical/governance will follow the
same pattern.

### How to Create a New Skill

#### 1. Create the skill directory
```
skills/cvm/my_skill/
├── __init__.py
├── _registry.py
├── report.py         (only if the skill has a dashboard mode)
└── modes/
    └── __init__.py   (empty marker)
```

#### 2. Write `_registry.py` (3 lines)
```python
"""skills/cvm/my_skill/_registry.py — Mode registry for my_skill."""
from skills._base import make_registry, build_manifest_modes, list_modes, get_mode
MODES, register_mode = make_registry()
```

#### 3. Write mode files in `modes/`
```python
# skills/cvm/my_skill/modes/my_mode.py
from skills.cvm.my_skill._registry import register_mode

@register_mode(
    "my_mode",
    description="What this mode does.",
    include_in_all=True,  # True = default mode when mode="all"
    params={
        "company": "str. B3 ticker (PETR4). Required.",
        "periods": "int. Number of periods. Default: 5.",
    },
    examples=[
        'skill(domain="cvm", sub_domain="my_skill", mode="my_mode", params=\'{"company":"PETR4"}\')',
    ],
)
def my_mode(company: str = "", periods: int = 5) -> dict:
    """Implement the mode logic here."""
    if not company:
        return {"status": "error", "error": "company is required"}
    # ... query data_sources, compute, return dict
    return {"status": "ok", "company": company, "data": ...}
```

#### 4. Write `__init__.py` (~20 lines)
```python
"""skills/cvm/my_skill/__init__.py -- My skill manifest + router."""
from __future__ import annotations
from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.cvm.my_skill._registry import MODES  # noqa: F401

auto_discover_modes(__name__)

MANIFEST = {
    "sub_domain":  "my_skill",
    "description": "What this skill does.",
    "source":      "which data_sources it reads from",
    "storage":     "read-only — no own database",
    "modes":       build_manifest_modes(MODES),
}

route = make_route("sub_domain", "my_skill", MODES)
```

#### 5. For a top-level flat domain (like investsite)
Use `"domain"` instead of `"sub_domain"` + `accept_sub_domain=True`:
```python
MANIFEST = {
    "domain":          "my_domain",
    "has_sub_domains": False,
    # ...
}
route = make_route("domain", "my_domain", MODES, accept_sub_domain=True)
```

### Key Design Decisions

- **Each skill gets its own MODES dict** via `make_registry()`. This prevents
  cross-skill mode name pollution (e.g., "dashboard" exists in all 11 skills
  but each is a different function).
- **`@register_mode` is a closure** over the skill's MODES dict. The decorator
  API stays the same regardless of which skill it's used in.
- **`auto_discover_modes(__name__)`** uses the package's `__name__` to find its
  `modes/` subdirectory — works for both `skills.cvm.governance` and
  `skills.investsite`.
- **`make_route()`** generates a `route()` with the right signature (CVM skills
  don't accept `sub_domain`; investsite does for dispatcher compat).
- **Adding a new mode** = drop a file in `modes/` + `@register_mode(...)`. No
  edits to `__init__.py` or `_registry.py` needed.
- **Adding a new skill** = create the directory + 3 files (_registry.py +
  __init__.py + modes/). The dispatcher auto-discovers it on next server restart.

### Dashboard Mode Convention

Every skill has a `dashboard` mode that:
1. Calls 1-3 of the skill's other modes (wrapped in try/except for graceful degradation)
2. Builds top-level KPI cards (formatted via `report.py` helpers)
3. Builds multi-tab payload (each tab has typed sections: text/table)
4. Returns `{"status": "ok", "company": ..., "tabs": [...], "kpis": [...]}`

When a sub-mode call fails, the dashboard returns `status: ok` with the full
tab structure (KPIs as "—", error message in Overview text) — not a bare error.
This ensures the HTML dashboard always renders with the proper layout.

### Data Source Integration

Skills are **read-only** — they call `data_sources/` query engines directly:
- `data_sources.cvm.dfp` — annual financial statements (DFP)
- `data_sources.cvm.itr` — quarterly financial statements (ITR)
- `data_sources.cvm.fre` — shareholders + free float (FRE)
- `data_sources.cvm.ipe` — material events (IPE)
- `data_sources.cvm.cad` — company register (CAD)
- `data_sources.cvm.vlmo` — insider trading (VLMO)
- `data_sources.cvm.cgvn` — governance practices (CGVN)
- `data_sources.cvm.fca` — listing segment (FCA)
- `data_sources.b3.dividends` — B3 dividend events
- `data_sources.cvm.bridge` — ticker ↔ CNPJ ↔ CD_CVM resolution

Skills never write to databases. They assume data is already synced via
`data_source(domain="cvm", sub_domain="dfp", mode="sync")`.

### Performance Infrastructure (v1.8 F7)

`skills/_base.py` provides a **ContextVar-scoped engine cache** that
eliminates redundant DB queries when multiple metrics compose the same
engine within a single `compute_all_ratios()` call.

**How it works:**
- Each engine's `at_fn` + `periods_fn` is decorated with `@engine_cached`
  at module definition time (before any metric imports the function).
- The decorator checks a `ContextVar`-scoped dict; if no scope is active,
  it's a passthrough (zero overhead for standalone calls).
- `compute_all_ratios()` wraps its loop in `with engine_cache_scope():`
  to activate the cache for the duration of the call.
- Engines shared across metrics (`earnings` used by 11 metrics, `pl` by 10,
  `debt` by 10, `revenue` by 15) are queried ONCE per `(company, date)`
  instead of N times — ~60% fewer DB queries.

**Why decorator (not monkey-patch):** Metrics use
`from engines.earnings import ttm_earnings_at` — a direct reference bound
at import time. Monkey-patching the module attribute after import is
invisible to metrics. The decorator is applied at definition time, so
`spec.at_fn` and `module.fn` are the same wrapper object, permanently.

**Thread safety:** `ContextVar` is per-thread + per-asyncio-task. No lock
needed. **Reentrancy:** If `compute_all_ratios()` is called nested, the
inner call reuses the outer scope's cache instead of wiping it.

**To add a new engine:** Just apply `@engine_cached` to the engine's
`at_fn` + `periods_fn`:

```python
# engines/my_engine.py
from skills._base import engine_cached

@engine_cached
def my_engine_at(company, date):
    ...

@engine_cached
def my_engine_periods(company):
    ...
```

### Force Sync Guard (v1.14)

When a user calls a skill, the `route()` wrapper (generated by `make_route()`)
checks if the required data sources are fresh (synced within 24h). If stale,
it force-syncs them BEFORE running the skill. This is on-demand (not auto-sync
cron) — the first call of the day may take 30+ seconds; subsequent calls are
fast.

**How it works:**
- Each skill declares `REQUIRED_SOURCES` in `__init__.py`:
  - financials: `["dfp", "itr", "bridge"]`
  - valuation: `["dfp", "itr", "fca", "cotahist", "bridge"]`
- `make_route()` accepts `required_sources` param; the generated `route()`
  calls `ensure_fresh()` before dispatching.
- For CVM sources (dfp/itr/fca): HEAD check before downloading — only syncs
  if CVM's `Last-Modified` header is newer than the last sync (or HEAD fails).
- Force-sync uses `force=True` for current year only (not full history).
- bridge syncs only the requested ticker, not all tickers.
- Sync report attached to every result as `result["_sync"]`.
- Re-entrancy guard: nested `route()` calls (e.g., dashboard composes
  annual + quarterly) trigger `ensure_fresh()` at most once.

**Escape hatches:**
- `CVM_SKIP_SYNC=1` env var (for tests — set in `tests/skills/cvm/conftest.py`)
- `route(..., skip_sync=True)` per-call kwarg

**Failure path:** If sync fails (network down, CVM unreachable), the skill
proceeds with stale data + the error is recorded in `result["_sync"]["errors"]`.
Stale-but-available is better than no answer for a dashboard use case.

**To wire a new skill:**
```python
# skills/<domain>/<skill>/__init__.py
REQUIRED_SOURCES = ["dfp", "itr", "bridge"]
route = make_route("sub_domain", "<skill>", MODES,
                   required_sources=REQUIRED_SOURCES)
```

---

## 📈 Current Skill Domains

### 1. B3 (Brasil, Bolsa, Balcão)

**Location**: `skills/b3/`  
**Purpose**: Ingest, sync, and query Brazilian stock market data from Brasil, Bolsa, Balcão (Brazilian Stock Exchange).

#### 🏛️ Domain Hub: `skills/b3/b3.py`

The central router for all B3-related operations. It exposes a single `b3` tool to the LLM.

**Routing Logic**: Inspects the `action` and `subdomain` parameters to delegate tasks.

**Data Lake Management**: Manages the local CSV cache in `WORKSPACE_ROOT/data/b3/`.

**Modes**:
- **`sync`**: Triggers background downloaders to update local datasets (daily CSVs from B3 endpoints).
- **`query`**: Executes pandas/SQL logic against local data for analysis.
- **`status`**: Reports on data freshness and cache health.

#### 📂 Subdomains

**`b3_api`**:
- **Function**: Core data ingestion and management.
- **Capabilities**: Handles direct HTTP interaction with B3 endpoints, manages daily CSV downloads, file parsing, and local storage synchronization.
- **Data Types**: Daily trading volumes, price histories, corporate actions.

**`b3_dividends`**:
- **Function**: Dividend and payout tracking.
- **Capabilities**: Tracks dividend payouts, yield histories, ex-dividend dates, and corporate actions (splits, bonuses).
- **Use Case**: "Show me all stocks with dividend yield > 5% in the last 12 months."

**`b3_cvm`** (Cross-domain bridge):
- **Function**: Maps B3 tickers to CVM regulatory IDs (CNPJ/CVM codes).
- **Capabilities**: Handles data integration logic that requires context from both the stock exchange and the securities commission.
- **Use Case**: Linking market data with regulatory filings.

#### 💡 Example Usage

```python
# Sync latest B3 data
b3(action="sync", subdomain="dividends", date_range="2024-01-01_to_2024-12-31")

# Query high-yield stocks
b3(action="query", subdomain="dividends", 
   query="SELECT ticker, dividend_yield FROM dividends WHERE yield > 0.05 ORDER BY yield DESC")

# Check data freshness
b3(action="status")
```

---

### 2. CVM (Comissão de Valores Mobiliários)

**Location**: `skills/cvm/`  
**Purpose**: Regulatory, financial statement, and shareholder data from the Brazilian SEC equivalent.

#### 🏛️ Domain Hub: `skills/cvm/cvm.py`

The central router for all CVM regulatory data. It exposes a single `cvm` tool to the LLM.

**Routing Logic**: Directs requests to specific subdomains based on the data type required (e.g., financials vs. shareholders).

**Rate Limiting**: Implements global rate limiting for CVM portal requests to avoid IP bans (CVM has strict scraping policies).

**Integration**: Orchestrates data fetching between `cvm_dfp_itr` (raw data) and analytical subdomains.

#### 📂 Subdomains

**`cvm_dfp_itr`**:
- **Function**: Low-level HTTP wrapper for the CVM Open Data portal.
- **Capabilities**: Handles session management, ZIP extraction, and raw CSV parsing for DFP (Demonstrações Financeiras Padronizadas) and ITR (Informações Trimestrais) filings.
- **Data Types**: Balance sheets, income statements, cash flow statements.

**`cvm_dividends`**:
- **Function**: Financial analysis module.
- **Capabilities**: Cross-references CVM financial statements (DFP/ITR) with B3 data to verify dividend declarations and payout ratios.
- **Use Case**: "Verify if Company X's declared dividend matches their reported net income."

**`cvm_shareholders`**:
- **Function**: Ownership tracking.
- **Capabilities**: Parses FRE (Formulário de Referência) data to track institutional ownership changes, insider trading disclosures, and major shareholder movements.
- **Use Case**: "Show me all insider transactions for PETR4 in the last 90 days."

#### 💡 Example Usage

```python
# Fetch latest financial statements
cvm(action="fetch", subdomain="dfp_itr", company="PETROBRAS", year=2024)

# Analyze dividend sustainability
cvm(action="analyze", subdomain="dividends", 
    ticker="PETR4", metric="payout_ratio", period="5y")

# Track insider trading
cvm(action="query", subdomain="shareholders", 
    query="SELECT * FROM insider_trades WHERE ticker='VALE3' AND date > '2024-01-01'")
```

---

## 🔄 Skill Integration with Workflows

Skills are automatically discovered and can be invoked by workflows:

- **Research Workflow**: May call `b3(action="query")` to gather market data before synthesizing a report.
- **Data Workflow**: Can use `cvm(action="analyze")` to perform financial analysis on datasets.
- **Autocode Workflow**: May reference skill documentation when generating code that interacts with Brazilian market APIs.

### Data Lake Structure

All skills store persistent data in `WORKSPACE_ROOT/data/`:

```
workspace/data/
├── b3/
│   ├── dividends_2024.csv
│   ├── trading_volumes_2024.csv
│   └── corporate_actions.csv
└── cvm/
    ├── dfp_petrobras_2024.zip
    ├── itr_vale_2024_q3.csv
    └── shareholders_insider_trades.csv
```

This structure allows:
- **Offline analysis**: Query historical data without re-downloading.
- **Incremental updates**: Only fetch new data since last sync.
- **Cross-session persistence**: Data survives agent restarts.

---

## 🐛 Troubleshooting & Common Patterns

### Rate Limiting Issues

**Problem**: CVM or B3 endpoints return 429 (Too Many Requests).

**Solution**: Skills implement automatic backoff. If you see rate limit errors in logs:
- Increase delay between requests in the subdomain config.
- Use `sync` mode during off-peak hours (late night/weekends).
- Check if your IP is temporarily banned (wait 24h).

### Data Freshness

**Problem**: Query returns stale data.

**Solution**: Run `b3(action="status")` or `cvm(action="status")` to check last sync date. If outdated, trigger a manual sync:
```python
b3(action="sync", force=True)  # Force re-download even if recent
```

### Missing Subdomain

**Problem**: LLM tries to call a subdomain that doesn't exist.

**Solution**: Check the Hub's routing logic. The Hub should return a clear error listing valid subdomains:
```python
return {
    "status": "error", 
    "error": f"Unknown subdomain '{subdomain}'. Valid: dividends, api, cvm"
}
```

---

## 📊 Current Skills (v1.0 — implemented)

The skills layer is now live. Skills are analytical views that combine multiple
data sources with domain reasoning. They are read-only (no sync) and sit on top
of `data_sources/`.

### Entry point

```
skill(domain, sub_domain, mode, params)  # @tool in skills/dispatcher.py
```

Identical pattern to `data_source()` — JSON params string, auto-discovery.

### All 11 Skills

See [CVM Skills Overview](skills/CVM.md) for the CVM landing page, or
[Investsite Overview](skills/INVESTSITE.md) for the investsite landing page.

| Skill | Domain | Dashboard Tabs | Charts | Sync Guard | Doc |
|-------|--------|---------------|--------|------------|-----|
| [financials](skills/cvm/FINANCIALS.md) | cvm | 7 | ✅ | ✅ | FINANCIALS.md |
| [valuation](skills/cvm/VALUATION.md) | cvm | 6 | ✅ | ✅ | VALUATION.md |
| [historical](skills/cvm/HISTORICAL.md) | cvm | 5 | ✅ | ✅ | HISTORICAL.md |
| [backtest](skills/cvm/BACKTEST.md) | cvm | 3 | ✅ | ✅ | BACKTEST.md |
| [dividends](skills/cvm/DIVIDENDS.md) | cvm | 3 | ✅ | ✅ | DIVIDENDS.md |
| [governance](skills/cvm/GOVERNANCE.md) | cvm | 3 | ✅ | ✅ | GOVERNANCE.md |
| [shareholders](skills/cvm/SHAREHOLDERS.md) | cvm | 4 | ✅ | ✅ | SHAREHOLDERS.md |
| [insider](skills/cvm/INSIDER.md) | cvm | 4 | ✅ | ❌ | INSIDER.md |
| [screener](skills/cvm/SCREENER.md) | cvm | 3 | ✅ | ❌ | SCREENER.md |
| [comparison](skills/cvm/COMPARISON.md) | cvm | 5 | ✅ | ❌ | COMPARISON.md |
| [investsite](skills/INVESTSITE.md) | investsite | 3 | ✅ | N/A (web) | INVESTSITE.md |

**Notes:**

- **Dashboard Tabs**: Each skill has a `dashboard` mode returning a multi-tab
  payload (`{"status": "ok", "tabs": [...], "kpis": [...]}`). The tab count
  reflects the current `len(result["tabs"])`.
- **Charts**: ✅ = dashboard emits Chart.js-compatible `chart_data` sections
  (bar / line / doughnut / stacked bar).
- **Sync Guard**: ✅ = `route()` calls `ensure_fresh()` to force-sync stale
  data sources (dfp/itr/fca/cotahist/bridge) before dispatch. `N/A (web)` for
  investsite (live web scraping, no local DB). ❌ = sync guard not yet wired.

### Architecture

```
LLM → skill(domain, sub_domain, mode, params)  [skills/dispatcher.py @tool]
       └→ skills/<domain>/__init__.py route()
          └→ skills/<domain>/<skill>/__init__.py route(mode)
             └→ skills/<domain>/<skill>/<skill>.py  (calls data_source query engines)
                └→ data_sources/...
```

Skills call data_source query engines directly (no JSON round-trip). The bridge
auto-syncs on first ticker query (`resolve_company(auto_sync=True)`).

---

## 🚀 Future Skill Domains (Planned)

- **`ibge`**: Brazilian Institute of Geography and Statistics (macroeconomic indicators, census data).
- **`bacen`**: Central Bank of Brazil (interest rates, exchange rates, monetary policy).
- **`receita_federal`**: Brazilian IRS (tax regulations, corporate tax filings).
- **`ans`**: National Agency of Supplementary Health (healthcare market data).

Each new domain follows the same Hub-and-Spoke pattern, making it easy to extend the agent's domain expertise without modifying core infrastructure.