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
5. **Add REQUIRED_SOURCES + sync guard** (MANDATORY for all skills that use data sources):
   ```python
   # skills/my_domain/__init__.py
   from skills._base import auto_discover_modes, make_route, build_manifest_modes

   REQUIRED_SOURCES = ["dfp", "itr", "bridge"]  # List ALL data sources this skill needs

   MANIFEST = {
       "sub_domain": "my_domain",
       ...
       "required_sources": REQUIRED_SOURCES,
   }

   route = make_route("sub_domain", "my_domain", MODES,
                      required_sources=REQUIRED_SOURCES)
   ```

   **Why mandatory:** The `route()` wrapper calls `ensure_fresh(REQUIRED_SOURCES)` before
   EVERY mode dispatch. Without it, the skill will NEVER trigger sync. Tests are protected
   by `CVM_SKIP_SYNC=1` (set in `tests/skills/cvm/conftest.py`).

   **Sync behavior varies by domain** (see per-domain docs for details):
   - **CVM sources** (`dfp`, `itr`, `fca`, `fre`, `ipe`, `cad`, `vlmo`, `cgvn`): ALWAYS
     HEAD-checked against CVM's server on every `route()` call. See [docs/skills/CVM.md](skills/CVM.md).
   - **B3 sources** (`cotahist`, `b3_dividends`, `brapi`, `index`, `bridge`): 24h freshness
     window. See [docs/skills/B3.md](skills/B3.md).
   - **BCB sources** (`sgs`): 24h freshness window. See [docs/skills/BCB.md](skills/BCB.md).

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

## 🏗️ Modular Skill Pattern (skills/_base/)

All skills (CVM + investsite + BCB + B3 + DDM) use a shared modular pattern built on
the `skills/_base/` package. This package provides the infrastructure so each
skill only needs ~3 lines in `_registry.py` + ~20 lines in `__init__.py`.

> **Phase 3 Commit 2 (2026-08):** `skills/_base.py` was split into a 6-file
> package. The `skills._base` module path is preserved via `__init__.py`
> re-exports — all 92 `from skills._base import X` import sites keep working.

**What `skills/_base/` provides:**

| Component | Module | Purpose | Version |
|-----------|--------|---------|---------|
| `ModeSpec` dataclass | `registry.py` | Mode metadata (name, fn, description, params, examples) | v1.0 |
| `make_registry()` | `registry.py` | Creates a per-skill MODES dict + `register_mode` decorator | v1.0 |
| `build_manifest_modes(MODES)` | `registry.py` | Turns registry into MANIFEST["modes"] dict | v1.0 |
| `list_modes(MODES)` / `get_mode(MODES, name)` | `registry.py` | Registry accessors | v1.0 |
| `auto_discover_modes(__name__)` | `registry.py` | Importlib-based modes/*.py auto-discovery | v1.0 |
| `make_route(...)` | `route.py` | Generates the route() dispatcher | v1.0 |
| `_dispatch(...)` | `route.py` | Internal dispatch (filters kwargs by signature) | v1.0 |
| `_route_with_sync_guard(...)` | `route.py` | Wraps sync check + dispatch with re-entrancy guard | v1.14 |
| `_SYNC_CHECKED` ContextVar | `route.py` | Re-entrancy guard (nested route calls run ensure_fresh once) | v1.14 |
| `_auto_generate_html(...)` | `html_gen.py` | Writes dashboard-mode HTML to workspace/reports/ | v5 |
| `_ENGINE_CACHE` ContextVar | `engine_cache.py` | Per-call engine cache slot | v1.9 F7 |
| `@engine_cached` decorator | `engine_cache.py` | Caches engine at_fn/periods_fn within a scope (3-layer) | v1.9 F7 |
| `engine_cache_scope` context manager | `engine_cache.py` | Activates the engine cache for its block | v1.9 F7 |
| `SYNC_FRESHNESS_HOURS = 24` | `sync_guard.py` | Freshness window constant | v1.14 |
| `ensure_fresh(sources, ...)` | `sync_guard.py` | Force-syncs stale data sources before dispatch | v1.14 |
| `_source_is_stale(source)` | `sync_guard.py` | Checks sync_state timestamp against 24h window | v1.14 |
| `_source_last_sync(source)` | `sync_guard.py` | Reads last-sync ISO timestamp from skills/_freshness.py | v1.14 |
| `_cvm_has_new_data(source, year)` | `sync_guard.py` | HEAD check before downloading (CVM only) | v1.14 |
| `_cvm_has_new_data_cached(source, year)` | `sync_guard.py` | TTL-cached HEAD check (1h) | v1.14 |
| `_trigger_sync(source, company, ...)` | `sync_guard.py` | Maps source name to sync fn with right args | v1.14 |
| `build_kpi_card(label, value, *, subtitle, unit, formatted, format_fn)` | `kpi.py` | Shared KPI card dict shape (`{label, value, raw, subtitle, unit}`); used by 7 DDM skills (Phase 4 C1) | v1.0 |
| `build_error_section(title, error)` | `error.py` | Shared error text section (`{type:"text", title, body:"Erro ao consultar: ..."}`); used by 7 DDM skills (Phase 4 C1) | v1.0 |

### Architecture

```
skills/
├── _base/                            # Shared infrastructure package (Phase 3 C2 split)
│   ├── __init__.py                   # Re-exports all public + private names (backward compat)
│   ├── registry.py                   # ModeSpec + make_registry + accessors + auto_discover_modes
│   ├── route.py                      # make_route + _route_with_sync_guard + _dispatch + _SYNC_CHECKED
│   ├── html_gen.py                   # _auto_generate_html (dashboard HTML writer)
│   ├── engine_cache.py               # _ENGINE_CACHE + engine_cached + engine_cache_scope
│   ├── sync_guard.py                 # SYNC_FRESHNESS_HOURS + ensure_fresh + _trigger_sync + HEAD checks
│   ├── kpi.py                        # [Phase 4 C1] build_kpi_card — shared KPI card dict shape
│   └── error.py                      # [Phase 4 C1] build_error_section — shared error text section
├── _freshness.py                     # Cross-domain freshness dict (CVM + B3 + BCB + DDM) — stays separate
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
├── b3/                               # B3 skills (Phase 1)
│   ├── __init__.py                   # Domain hub
│   ├── index/                        # 3-tab dashboard (composition + history + ticker) + compare + ticker
│   ├── price/                        # 7-tab dashboard + quote mode (cotahist OHLCV)
│   ├── options/                      # 3-tab dashboard (Cadeia de Opções / Put-Call / Volume)
│   └── term/                         # 3-tab dashboard (Contratos Ativos / Spread / Volume)
└── ddm/                              # DDM skills (Phase 2) — mirrors data_sources/ddm/ sub-domains
    ├── __init__.py                   # Domain hub (auto-discovers sub-domains)
    ├── inflation/                    # 4-tab dashboard (IGP-M + IPCA + INPC + Comparativo)
    ├── juros/                        # 4-tab dashboard (Selic + Meta Selic + CDI + Comparativo)
    ├── poupanca/                     # 1-tab dashboard (Poupança)
    ├── acoes/                        # 1-tab dashboard (Ações — sortable-table feature + price-distribution chart)
    ├── focus/                        # 13-tab dashboard (Boletim Focus market expectations)
    ├── fluxo/                        # 5-tab dashboard (B3 investment flow by investor type)
    └── dividends/                    # Dividends dashboard (corporate actions history)
```

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
- `data_sources.cvm.bridge` — ticker ↔ CNPJ ↔ CD_CVM resolution
- `data_sources.bcb.sgs` — BCB macro series (Selic, CDI, IPCA, USD/BRL, etc.)

Skills never write to databases. They assume data is already synced via
`data_source(domain="cvm", sub_domain="dfp", mode="sync")`.

### Performance Infrastructure (v1.8 F7)

`skills/_base/engine_cache.py` provides a **ContextVar-scoped engine cache** that
eliminates redundant DB queries when multiple metrics compose the same
engine within a single `compute_all_ratios()` call.

### Force Sync Guard (v1.14)

When a user calls a skill, the `route()` wrapper (generated by `make_route()`)
checks if the required data sources are fresh (synced within 24h). If stale,
it force-syncs them BEFORE running the skill.

**Escape hatches:**
- `CVM_SKIP_SYNC=1` env var (for tests)
- `route(..., skip_sync=True)` per-call kwarg

**BCB macro skill note:** `required_sources=["sgs"]` is wired, and
`skills/_base/sync_guard.py`'s `_trigger_sync.sync_map` now includes the `sgs` entry (v1.2
docs — the wiring shipped in an earlier commit but was undocumented). The
sync guard triggers `sync_all(force=True)` when SGS is stale (>24h or
missing).

---

## 📈 Current Skill Domains

### B3 (Brasil, Bolsa, Balcão)

**Location**: `skills/b3/`
**Purpose**: Ingest, sync, and query Brazilian stock market data from Brasil, Bolsa, Balcão (Brazilian Stock Exchange).

**Sub-domains:**
- **index**: 3-tab dashboard (composition + history + ticker) + compare + ticker modes. Reads from `data_sources/b3/index` + `data_sources/b3/api` + CVM bridge.
- **price**: 7-tab dashboard (Cotação / Médias / Volume / Indicadores / Retornos / Volatilidade / Fibonacci) + quote mode. Reads from `data_sources/b3/cotahist` + `data_sources/b3/dividends`.
- **options**: 3-tab dashboard (Cadeia de Opções / Put/Call Ratio / Volume por Strike). Reads from `data_sources/b3/cotahist_derivatives` (shared `cotahist.db`). `REQUIRED_SOURCES=["cotahist"]` (derivatives ride on the cotahist sync — no separate sync).
- **term**: 3-tab dashboard (Contratos Ativos + Spread Termo vs Spot + Volume Histórico). Reads from `data_sources/b3/cotahist` (derivatives table). `REQUIRED_SOURCES=["cotahist"]`.

See [B3 Skills](skills/B3.md) for the B3 landing page.

### CVM (Comissão de Valores Mobiliários)

**Location**: `skills/cvm/`
**Purpose**: Regulatory, financial statement, and shareholder data from the Brazilian SEC equivalent.

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

### DDM (Dados de Mercado)

**Location**: `skills/ddm/`
**Purpose**: Brazilian financial-data dashboard scraped from
  dadosdemercado.com.br (no auth, no JS, regex-parsed HTML).

**Sub-domains:**
- **inflation**: 4-tab dashboard (IGP-M + IPCA + INPC + Comparativo) with
  subtabs (Histórico + Matriz) per index. Reads from `data_sources/ddm/inflation`.
  `REQUIRED_SOURCES=["ddm"]`.
- **juros**: 4-tab dashboard (Selic + Meta Selic + CDI + Comparativo) with
  subtabs per index. Reads from `data_sources/ddm/juros`. `REQUIRED_SOURCES=["ddm"]`.
- **poupanca**: 1-tab dashboard (Poupanca) with subtabs (Histórico + Matriz).
  Reads from `data_sources/ddm/poupanca`. `REQUIRED_SOURCES=["ddm"]`.
- **acoes**: 1-tab dashboard (Ações) with KPIs + sortable stocks table +
  price-distribution chart. Reads from `data_sources/ddm/acoes`.
  `REQUIRED_SOURCES=["ddm-acoes"]` (own source key — separate from the other
  DDM skills). The acoes skill introduces the **sortable-table feature**
  (clickable headers, JS sortTable, data-value attributes on numeric cells)
  + the shared `skills/_colors/price.py` 16-range palette used by the chart.
- **focus**: 13-tab dashboard (Boletim Focus market expectations survey).
  1 Focus tab with 4 year subtabs (2026-2029, each showing all 12 indicators)
  + 12 per-indicator tabs (IPCA, PIB Total, Câmbio, Selic, ...) each with a
  grouped bar chart + 3 time-window subtabs (Há 4 semanas, 1 sem, Hoje).
  Reads from `data_sources/ddm/focus`. `REQUIRED_SOURCES=["ddm-focus"]`
  (own source key — the focus page is CloudFront-protected, so the fetcher
  sends the full Chrome 127 browser header set to bypass the WAF). Values
  are preserved as PT-BR strings verbatim ("5,151%", "R$ 5,200").
- **fluxo**: 5-tab dashboard (B3 investment flow by investor type). 1
  Fluxo tab (group: Fluxo) with KPIs + 4-dataset daily bar chart +
  sortable table of all daily observations + 4 per-investor tabs (group:
  Investidores: Estrangeiro, Institucional, Pessoa física, Inst. Financeira)
  each with 3 subtabs (Diário/Mensal/Anual) showing a daily bar chart, a
  monthly cumulative line chart, and a running annual cumulative line
  chart. Reads from `data_sources/ddm/fluxo`.
  `REQUIRED_SOURCES=["ddm-fluxo"]` (own source key — the fluxo page is
  CloudFront-protected, so the fetcher sends the full Chrome 127 browser
  header set to bypass the WAF). Values are parsed to REAL (floats in
  millions R$) at the fetcher boundary; dates are normalized to YYYY-MM-DD.

**Freshness tracking** (v1 — added with the acoes skill):
`skills/_freshness.get_freshness()` returns the last-sync timestamp for
ALL 7 DDM sub-domains in a single dict (`{"ddm": ..., "ddm-juros": ...,
"ddm-poupanca": ..., "ddm-acoes": ..., "ddm-focus": ..., "ddm-fluxo": ...,
"ddm-dividends": ...}`). Consumers can poll a single dict instead of importing
per-subdomain helpers.

See [DDM Skills](#) for the DDM landing pages (one per sub-domain:
[INFLATION.md](skills/ddm/INFLATION.md), [JUROS.md](skills/ddm/JUROS.md),
[POUPANCA.md](skills/ddm/POUPANCA.md), [ACOES.md](skills/ddm/ACOES.md),
[FOCUS.md](skills/ddm/FOCUS.md), [FLUXO.md](skills/ddm/FLUXO.md)).

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
[Investsite Overview](skills/INVESTSITE.md) for the investsite landing page, or
[BCB Skills Overview](skills/BCB.md) for the BCB landing page.

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
| [macro](skills/bcb/MACRO.md) | bcb | 5 | ✅ | ✅ (v1.2 docs) | MACRO.md |
| [index](skills/b3/INDEX.md) | b3 | 3 | ✅ | ✅ | INDEX.md |
| [price](skills/b3/PRICE.md) | b3 | 7 | ✅ | ✅ | PRICE.md |
| [options](skills/b3/OPTIONS.md) | b3 | 3 | ✅ | ✅ | OPTIONS.md |
| [term](skills/b3/TERM.md) | b3 | 3 | ✅ | ✅ | TERM.md |
| [inflation](skills/ddm/INFLATION.md) | ddm | 4 | ✅ | ✅ | INFLATION.md |
| [juros](skills/ddm/JUROS.md) | ddm | 4 | ✅ | ✅ | JUROS.md |
| [poupanca](skills/ddm/POUPANCA.md) | ddm | 1 | ✅ | ✅ | POUPANCA.md |
| [acoes](skills/ddm/ACOES.md) | ddm | 1 | ✅ | ✅ | ACOES.md |
| [focus](skills/ddm/FOCUS.md) | ddm | 13 | ✅ | ✅ | FOCUS.md |
| [fluxo](skills/ddm/FLUXO.md) | ddm | 5 | ✅ | ✅ | FLUXO.md |

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

## 🚀 Future Skill Domains (Planned)

- **`ibge`**: Brazilian Institute of Geography and Statistics (macroeconomic indicators, census data).
- **`receita_federal`**: Brazilian IRS (tax regulations, corporate tax filings).
- **`ans`**: National Agency of Supplementary Health (healthcare market data).

Each new domain follows the same Hub-and-Spoke pattern, making it easy to extend the agent's domain expertise without modifying core infrastructure.

---

## 📊 Dashboard Output Standard (v1.22+)

All dashboard modes (`dashboard()`) MUST follow this output pattern for PowerShell
terminal visibility + performance debugging. This is NOT optional — it's how we
identify bottlenecks and verify parallelism is working.

### Required Output Format

```
[skill] Starting dashboard for {company}...
[skill]   {task} done ({elapsed_from_start:.1f}s)
[skill]   {N}/{total} {metric} ({per_metric:.1f}s, total {running:.1f}s) = {value}
[skill] All data fetched in {total:.1f}s (cache: {hits} hits, {misses} misses)
[skill] Building sections...
[skill]   {section_name}...
[skill] Done! {N} tabs, {N} KPIs in {total:.1f}s.
```

### Rules

1. **Start line**: `[skill] Starting dashboard for {company}...`
2. **Per-task timing**: Every parallel/sequential task shows elapsed from start:
   `[skill]   {task_name} done ({elapsed:.1f}s)`
3. **Per-metric timing**: `compute_all_ratios` shows EVERY metric:
   `  [ratios] {N}/{total} {name} ({per_metric:.2f}s, total {running:.1f}s) = {value}`
4. **Cache stats**: After all data fetched:
   `[skill] All data fetched in {total:.1f}s (cache: {hits} hits, {misses} misses)`
5. **Section building**: Each section name:
   `[skill]   {section_name}...`
6. **End line**: `[skill] Done! {N} tabs, {N} KPIs in {total:.1f}s.`

### Timer Implementation

```python
from datetime import datetime as _dt
_t0 = _dt.now()
print(f"[skill] Starting dashboard for {company}...", flush=True)

# ... each step:
_elapsed = (_dt.now() - _t0).total_seconds()
print(f"[skill]   {task} done ({_elapsed:.1f}s)", flush=True)

# ... end:
_total = (_dt.now() - _t0).total_seconds()
print(f"[skill] Done! {len(tabs)} tabs, {len(kpis)} KPIs in {_total:.1f}s.", flush=True)
```

### brapi Timing (data_sources/b3/brapi/fetcher.py)

All brapi calls show timing:
```
[brapi] Fetching quote: {ticker}
[brapi] {ticker} quote OK ({elapsed:.2f}s, price={price})
[brapi] {ticker} quote FAILED ({elapsed:.2f}s): {error}
[brapi] Fetching history: {ticker} ({range}/{interval})
[brapi] {ticker} OK ({elapsed:.2f}s, {N} bars)
[brapi] {ticker} FAILED ({elapsed:.2f}s): {error}
[brapi] {ticker} not_found ({elapsed:.2f}s)
```

On 401 Unauthorized: `[brapi] DISABLED for this session: 401 Unauthorized on {ticker}`
— all subsequent brapi calls skip entirely (no HTTP request, instant return).

### Cache (engine_cache_scope)

- **Sequential** `compute_all_ratios` is FASTER than parallel — shared cache
  means `earnings_at(PETR4, today)` is queried ONCE (used by 11 metrics).
  Parallel workers each get their own cache → re-query N times.
- **Historical** dashboard: summaries + quartiles share the SAME cache scope.
  `fetch_series()` calls the same `history_fn` that `summary()` already called
  → cache HIT → instant. No re-fetching.
- **Financials** dashboard: 6 parallel fetches (annual, quarterly, statements,
  TTM, YoY, ratios) — each is independent, no shared engines between them.
  Parallel is correct here.
- **Valuation** dashboard: `ratios()` calls `compute_all_ratios` (sequential,
  shared cache) + 11 parallel engine calls (earnings, revenue, ebit, pl, debt,
  cash, da, fco, fci, shares, dividends) — parallel is correct here (each
  engine fetches a different DB table).

### What NOT to do

- Do NOT use `F7` as a name — it was just a tag. Use `cache` or `engine cache`.
- Do NOT create separate cache scopes for summaries vs quartiles — they MUST
  share the same scope so `fetch_series` gets cache hits.
- Do NOT parallelize `compute_all_ratios` — sequential with shared cache is
  faster (shared engines queried once vs N times).
- Do NOT use `*_periods()` in `*_at()` functions — `*_periods` fetches ALL
  data; `*_at` fetches only the most recent period ≤ date (cached, fast).

---

*Last updated: 2026-09-15 (Phase 3 doc sweep — updated `_base.py` → `_base/` package split footprints across dependent docs; corrected `skills/_price_colors.py` ref to `skills/_colors/price.py`; refreshed DDM skills freshness dict to 7 sub-domains). Prior: v1.24 — added DDM skills: inflation, juros, poupanca, acoes; added `skills/_freshness.py` top-level freshness helper; added sortable-table feature in macros.html + base.html; added shared 16-range palette.*
