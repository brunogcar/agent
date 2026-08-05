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

All skills (CVM + investsite + BCB + B3) use a shared modular pattern built on
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
│   ├── _shared_report/               # Shared dashboard builders (all CVM skills)
│   ├── financials/
│   │   ├── __init__.py               # ~20 lines: auto_discover + MANIFEST + route
│   │   ├── _registry.py              # ~3 lines: MODES, register_mode = make_registry()
│   │   ├── report.py                 # Dashboard composition helpers
│   │   ├── fetchers.py / helpers.py  # Internal utilities (optional)
│   │   └── modes/
│   │       ├── __init__.py           # Empty marker
│   │       ├── quarterly.py          # @register_mode("quarterly", ...)
│   │       ├── annual.py             # @register_mode("annual", ...)
│   │       └── dashboard.py          # @register_mode("dashboard", ...)
│   ├── valuation/                    # Same pattern
│   ├── governance/                   # Same pattern
│   └── ... (8 more CVM skills)
├── investsite/
│   ├── __init__.py                   # ~25 lines (accept_sub_domain=True)
│   ├── _registry.py                  # ~3 lines
│   ├── fetcher.py / parsers.py       # Internal utilities
│   ├── report.py
│   └── modes/
│       └── ... (6 mode files)
├── bcb/                              # BCB domain (Brazilian Central Bank)
│   ├── __init__.py                   # Domain hub
│   └── macro/                        # Macro skill (5-tab dashboard)
│       ├── __init__.py               # MANIFEST + route (required_sources=["sgs"])
│       ├── _registry.py              # MODES + register_mode (with standalone fallback)
│       ├── helpers.py                # format_value, annualize_rate, compute_stats
│       ├── report.py                 # build_kpi_card, build_chart_section, build_table_section
│       └── modes/
│           ├── dashboard.py          # @register_mode("dashboard") 5-tab composition
│           ├── rates.py              # @register_mode("rates") Selic/CDI/TR/Copom
│           ├── inflation.py          # @register_mode("inflation") IPCA/IGP-M
│           └── fx.py                 # @register_mode("fx") USD/BRL
└── b3/                               # B3 domain (Brazilian Stock Exchange)
    ├── __init__.py                   # B3 domain hub (routes sub_domain → skill)
    └── index/                        # Index skill (3 modes: dashboard, compare, ticker)
        ├── __init__.py               # MANIFEST + route (required_sources=["index"])
        ├── _registry.py              # MODES + register_mode (delegates to skills/_base.py)
        ├── helpers.py                # compute_jaccard, compute_sector_breakdown, compute_returns
        ├── report.py                 # dashboard section builders (KPI cards, tables, charts)
        └── modes/
            ├── dashboard.py          # @register_mode("dashboard") — single-index deep dive
            ├── compare.py            # @register_mode("compare")   — multi-index side-by-side
            └── ticker.py             # @register_mode("ticker")    — reverse-lookup
```

### How to Create a New Skill

#### 1. Create the skill directory
```
skills/<domain>/my_skill/
├── __init__.py
├── _registry.py
├── report.py         (only if the skill has a dashboard mode)
└── modes/
    └── __init__.py   (empty marker)
```

#### 2. Write `_registry.py` (3 lines)
```python
"""skills/<domain>/my_skill/_registry.py — Mode registry for my_skill."""
from skills._base import make_registry, build_manifest_modes, list_modes, get_mode
MODES, register_mode = make_registry()
```

#### 3. Write mode files in `modes/`
```python
# skills/<domain>/my_skill/modes/my_mode.py
from skills.<domain>.my_skill._registry import register_mode

@register_mode(
    "my_mode",
    description="What this mode does.",
    include_in_all=True,  # True = default mode when mode="all"
    params={
        "index": "str. Index symbol (IBOV). Required.",
        "periods": "int. Number of periods. Default: 5.",
    },
    examples=[
        'skill(domain="b3", sub_domain="my_skill", mode="my_mode", params=\'{"index":"IBOV"}\')',
    ],
)
def my_mode(index: str = "", periods: int = 5) -> dict:
    """Implement the mode logic here."""
    if not index:
        return {"status": "error", "error": "index is required"}
    # ... query data_sources, compute, return dict
    return {"status": "ok", "index": index, "data": ...}
```

#### 4. Write `__init__.py` (~20 lines)
```python
"""skills/<domain>/my_skill/__init__.py -- My skill manifest + router."""
from __future__ import annotations
from skills._base import auto_discover_modes, make_route, build_manifest_modes
from skills.<domain>.my_skill._registry import MODES  # noqa: F401

REQUIRED_SOURCES = ["index"]  # sync guard: force-sync stale data sources

auto_discover_modes(__name__)

MANIFEST = {
    "sub_domain":  "my_skill",
    "description": "What this skill does.",
    "source":      "which data_sources it reads from",
    "storage":     "read-only — no own database",
    "modes":       build_manifest_modes(MODES),
}

route = make_route("sub_domain", "my_skill", MODES,
                   required_sources=REQUIRED_SOURCES)
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
  cross-skill mode name pollution (e.g., "dashboard" exists in all skills
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
3. Builds multi-tab payload (each tab has typed sections: text/table/chart)
4. Returns `{"status": "ok", "company": ..., "tabs": [...], "kpis": [...]}`

When a sub-mode call fails, the dashboard returns `status: ok` with the full
tab structure (KPIs as "—", error message in Overview text) — not a bare error.
This ensures the HTML dashboard always renders with the proper layout.

**Dashboard section shapes** (must match `tools/report_ops/templates/dashboard.html`):
- KPI: `{"label": "...", "value": "...", "delta": optional}` (top-level only)
- Tab: `{"name": "...", "group": "...", "sections": [...]}`
- Chart: `{"type": "chart", "title": ..., "chart_data": {Chart.js config}}`
- Table: `{"type": "table", "title": ..., "columns": [...], "rows": [[...], ...]}`
- Text: `{"type": "text", "title": ..., "body": ...}`

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
- `data_sources.b3.index` — B3 index composition + history (IBOV, SMLL, BDRX, IFIX, IDIV + 26 catalogued)
- `data_sources.cvm.bridge` — ticker ↔ CNPJ ↔ CD_CVM resolution
- `data_sources.bcb.sgs` — BCB macro series (Selic, CDI, IPCA, USD/BRL, etc.)

Skills never write to databases. They assume data is already synced via
`data_source(domain="cvm", sub_domain="dfp", mode="sync")`.

### Performance Infrastructure (v1.8 F7)

`skills/_base.py` provides a **ContextVar-scoped engine cache** that
eliminates redundant DB queries when multiple metrics compose the same
engine within a single `compute_all_ratios()` call.

### Force Sync Guard (v1.14)

When a user calls a skill, the `route()` wrapper (generated by `make_route()`)
checks if the required data sources are fresh (synced within 24h). If stale,
it force-syncs them BEFORE running the skill.

**Escape hatches:**
- `CVM_SKIP_SYNC=1` / `B3_SKIP_SYNC=1` env var (for tests)
- `route(..., skip_sync=True)` per-call kwarg

**BCB macro skill note:** `required_sources=["sgs"]` is wired, but
`skills/_base._trigger_sync.sync_map` does not yet know "sgs" (only CVM/B3
sources). The sync guard records an error in `result["_sync"]["errors"]` and
proceeds with available data. Users must run `sync_all` manually until the
sync_map is extended (tracked in BCB macro ROADMAP P2).

**B3 index skill note (v1.0):** `required_sources=["index"]` is wired AND
`skills/_base._trigger_sync.sync_map` knows "index" → `data_sources.b3.index.sync_engine.sync_all`.
Sync guard fully functional: first call of the day force-syncs all 5 active
indices (~30s), subsequent calls are fast.

---

## 📈 Current Skill Domains

### B3 (Brasil, Bolsa, Balcão)

**Location**: `skills/b3/`
**Purpose**: Analytical skills over Brazilian stock exchange data.

**Sub-domains:**
- **index**: 3 modes — dashboard (single-index deep dive, 4-tab), compare (multi-index side-by-side, 3-tab), ticker (reverse-lookup). Reads from `data_sources/b3/index` (composition + history) + `data_sources/b3/api` (sector join).

**Example Usage:**
```python
# Index dashboard (IBOV)
skill(domain="b3", sub_domain="index", mode="dashboard", params='{"index":"IBOV"}')

# Compare indices
skill(domain="b3", sub_domain="index", mode="compare", params='{"indices":["IBOV","SMLL"]}')

# Reverse-lookup: which indices include a ticker
skill(domain="b3", sub_domain="index", mode="ticker", params='{"ticker":"PETR4"}')
```

See [B3 Skills Overview](skills/B3.md) for the B3 landing page.

### CVM (Comissão de Valores Mobiliários)

**Location**: `skills/cvm/`
**Purpose**: Regulatory, financial statement, and shareholder data from the Brazilian SEC equivalent.

See [CVM Skills Overview](skills/CVM.md) for the CVM landing page.

### BCB (Banco Central do Brasil)

**Location**: `skills/bcb/`
**Purpose**: Macro-economic dashboard from the Brazilian Central Bank's SGS API.

**Sub-domains:**
- **macro**: 5-tab dashboard (Resumo / Juros / Inflacao / Cambio / Atividade) + 3 focused modes (rates, inflation, fx). Reads from `data_sources/bcb/sgs`.

**Example Usage:**
```python
# Full dashboard
skill(domain="bcb", sub_domain="macro", mode="dashboard")

# Focused modes
skill(domain="bcb", sub_domain="macro", mode="rates")
skill(domain="bcb", sub_domain="macro", mode="inflation")
skill(domain="bcb", sub_domain="macro", mode="fx")
```

See [BCB Skills](skills/BCB.md) for the BCB landing page.

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

### All Skills

See [CVM Skills Overview](skills/CVM.md) for the CVM landing page,
[Investsite Overview](skills/INVESTSITE.md) for the investsite landing page,
[BCB Skills Overview](skills/BCB.md) for the BCB landing page, or
[B3 Skills Overview](skills/B3.md) for the B3 landing page.

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
| [macro](skills/bcb/MACRO.md) | bcb | 5 | ✅ | P2 (sgs not in sync_map) | MACRO.md |
| [index](skills/b3/INDEX.md) | b3 | 4 | ✅ | ✅ | INDEX.md |

**Notes:**

- **Dashboard Tabs**: Each skill has a `dashboard` mode returning a multi-tab
  payload (`{"status": "ok", "tabs": [...], "kpis": [...]}`). The tab count
  reflects the current `len(result["tabs"])`.
- **Charts**: ✅ = dashboard emits Chart.js-compatible `chart_data` sections
  (line / bar / doughnut / stacked bar).
- **Sync Guard**: ✅ = `route()` calls `ensure_fresh()` to force-sync stale
  data sources before dispatch. `N/A (web)` for investsite (live web scraping,
  no local DB). `P2` for BCB macro — `required_sources=["sgs"]` is wired but
  `sync_map` doesn't know "sgs" yet. ❌ = sync guard not yet wired.

### Architecture

```
LLM → skill(domain, sub_domain, mode, params)  [skills/dispatcher.py @tool]
       └→ skills/<domain>/__init__.py route()
          └→ skills/<domain>/<skill>/__init__.py route(mode)
             └→ skills/<domain>/<skill>/<skill>.py  (calls data_source query engines)
                └→ data_sources/...
```

Skills call data_source query engines directly (no JSON round-trip).

---

## 🏗️ Domain Creation Guidance

When adding a brand-new **skills domain** (e.g., `skills/b3/`), follow this checklist:

1. **Create the domain folder** — `skills/<new_domain>/`.
2. **Write the domain hub** — `skills/<new_domain>/__init__.py` with a `route(sub_domain, mode, params)` that dispatches to the right skill. Mirror `skills/cvm/__init__.py` or `skills/b3/__init__.py`.
3. **Register with the dispatcher** — `skills/dispatcher.py` auto-discovers domains by scanning `skills/*/`. No edits needed if the domain follows the hub convention.
4. **Create the first skill** under `skills/<new_domain>/<skill>/` using the **Modular Skill Pattern** (`_registry.py` + `__init__.py` + `modes/`) described above.
5. **Wire `REQUIRED_SOURCES`** — if the skill reads from a data source, declare it (e.g., `REQUIRED_SOURCES = ["index"]`) AND ensure `skills/_base.py`'s `_trigger_sync.sync_map` knows how to sync that source. If it doesn't, add a branch (and a test).
6. **Set the test escape hatch** — add `<DOMAIN>_SKIP_SYNC=1` (e.g., `B3_SKIP_SYNC=1`) to the domain's `conftest.py` so tests skip the sync guard. Mirror `tests/skills/cvm/conftest.py`.
7. **Create docs**:
   - `docs/skills/<NEW_DOMAIN>.md` — domain landing page (mirror `docs/skills/B3.md` or `docs/skills/CVM.md`).
   - `docs/skills/<new_domain>/<SKILL>.md` — skill landing page (mirror `docs/skills/b3/INDEX.md` or `docs/skills/cvm/FINANCIALS.md`).
   - `docs/skills/<new_domain>/<skill>/{API,ARCHITECTURE,CHANGELOG,INSTRUCTIONS,ROADMAP}.md` — 5 detail docs in the subfolder.
8. **Update top-level docs** — add the new domain row to `docs/SKILLS.md` (Current Skill Domains + All Skills table + architecture tree).

### Adding a new skill to an existing domain

If the domain already exists (e.g., adding a second B3 skill alongside `index`):

1. Create `skills/<domain>/<new_skill>/` with `_registry.py` + `__init__.py` + `modes/`.
2. Add `REQUIRED_SOURCES` if the skill reads from a data source.
3. Create `docs/skills/<domain>/<NEW_SKILL>.md` + `docs/skills/<domain>/<new_skill>/{API,ARCHITECTURE,CHANGELOG,INSTRUCTIONS,ROADMAP}.md`.
4. Add a row to the domain landing page (`docs/skills/<DOMAIN>.md` Skills table).
5. Add a row to the **All Skills** table in `docs/SKILLS.md`.

---

## 🚀 Future Skill Domains (Planned)

- **`ibge`**: Brazilian Institute of Geography and Statistics (macroeconomic indicators, census data).
- **`receita_federal`**: Brazilian IRS (tax regulations, corporate tax filings).
- **`ans`**: National Agency of Supplementary Health (healthcare market data).

Each new domain follows the same Hub-and-Spoke pattern, making it easy to extend the agent's domain expertise without modifying core infrastructure.

---

*Last updated: 2026-08-05.*
