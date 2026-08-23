# 📂 Repository Structure

> Canonical map of the MCP Agent Stack repo. This is the reference for "where does X live?" — the README is a summary, this is the full layout.

Last updated: 2026-09-15 (Phase 3: ddm/_base/ extraction, skills/_base/ package split, dashboard.html JS partials)

---

## 🏛️ Top-Level Layout

```text
agent/
├── server.py              # MCP stdio entry point (DO NOT BREAK STDOUT)
├── registry.py            # @tool auto-discovery engine
├── mcp.json               # MCP server configuration (for MCP hosts)
├── requirements.txt       # Python dependencies
├── pytest.ini             # Pytest config (pythonpath, testpaths, import-mode)
├── README.md              # Landing page (this repo's front door)
│
├── core/                  # Foundation layer — 13 subsystems
├── tools/                 # 18 meta-tools exposed to the LLM
├── workflows/             # 6 LangGraph state machines
├── data_sources/          # Raw data ingestion + query (CVM, B3, BCB, DDM)
├── skills/                # Analytical views combining data sources
├── benchmark/             # Role benchmarking tool
├── docs/                  # 5-file documentation standard per component
└── tests/                 # Pytest suites mirror source structure
```

---

## 🛠️ Tools Layer (`tools/`)

18 meta-tools, each following the **`@tool` facade + `*_ops/` subpackage** pattern (v1.0 standard). The facade is a thin dispatch wrapper; all logic lives in the subpackage.

### The v1.0 pattern (every tool)

```text
tools/
├── <tool>.py                    # @tool @meta_tool facade — thin dispatch
└── <tool>_ops/                  # Subpackage (all logic lives here)
    ├── __init__.py              # Auto-imports actions/*.py (glob discovery)
    ├── _registry.py             # DISPATCH dict + @register_action decorator
    ├── helpers.py               # Shared utilities (scheduler, compression, etc.)
    ├── state.py                 # Module-level mutable state (where applicable)
    └── actions/                 # One file per action
        ├── __init__.py
        ├── send.py              # @register_action("<tool>", "send", ...)
        ├── list.py              # @register_action("<tool>", "list", ...)
        └── ...                  # One file per action; drop a file to add an action
```

**Key invariants:**
- **Auto-discovery** — `__init__.py` globs `actions/*.py`; adding an action = creating one file with `@register_action`. Zero facade edits.
- **`DISPATCH` populated before `@meta_tool` runs** — the facade imports `from tools import <tool>_ops` (triggering auto-discovery) BEFORE reading `DISPATCH` for the `action: Literal[...]` enum.
- **`ok()`/`fail()` from `core.contracts`** — every action returns a standardized envelope. Semantic status (`sent`/`scheduled`/`ok`/etc.) lives in `data.action_status`.
- **`trace_id` + `duration_ms`** in every response (facade adds `duration_ms` post-handler).

### The 18 tools

| Tool | Subpackage | Actions | Notes |
|------|------------|---------|-------|
| `agent` | `agent_ops/` | 5 (dispatch, clear_cache, metrics, subagent, vision_delegate) | 15 specialist sub-roles in `roles/` |
| `browser` | `browser_ops/` | 20 | Playwright automation, session isolation |
| `cli` | `cli_ops/` | 10 | 4-layer NL→shell dispatch (patterns → whitelist → router LLM → executor LLM) |
| `consult` | `consult_ops/` | 3 (advise, explain, review) | Cloud LLM advisory, kill-switch, rate-limit guard |
| `file` | `file_ops/` | 25+ | CRUD, directory traversal, document parsing, SQLite FTS |
| `git` | `git_ops/` | 20+ | Commit, diff, rollback, snapshot, branch/tag management |
| `github` | `github_ops/` | 16 | PR + issue + release workflow + push/pull |
| `memory` | `memory_ops/` | 12 | LLM-facing memory I/O (store, recall, recall_context, delete, prune, summarize, stats, janitor, update, export, import, extract) |
| `notify` | `notify_ops/` | 8 | Desktop alerts + APScheduler reminders, tz-aware via `core/time_utils.py` |
| `parallel` | `parallel_ops/` | 3 (run, race, pipeline) | Concurrent execution with `PARALLEL_SAFE` allowlist |
| `python` | `python_ops/` | 5 (run, run_data, eval, profile, lint) | Three-layer security (sandbox → imports → executors) |
| `report` | `report_ops/` | 12 | Charts, maps, dashboards, diagrams, tables, PDF/PNG/xlsx export |
| `schedule` | `schedule_ops/` | 9 | Cron/interval/one-shot + iCal sync; delivers via notify; offline catch-up |
| `swarm` | `swarm_ops/` | 5 (consensus, race, vote, compare, list_providers) | Multi-model fan-out across cloud providers |
| `tavily` | `tavily_ops/` | 5 | AI-ranked search, bulk extraction, keyless mode |
| `vision` | `vision_ops/` | 3 (describe, extract_text, analyse_ui) | Multimodal image analysis |
| `web` | `web_ops/` | 5 (search, scrape, read, crawl, search_and_read) | SearXNG + BeautifulSoup, SSRF protection |
| `workflow` | `workflow_ops/` | 5 (run, list, status, cancel, history) | LangGraph workflow launcher, two-level dispatch (action + type) |

### Naming conventions
- **`list.py`** (not `list_workflows.py`) — bare action names; aligns with `report_ops` convention. v1.1 cleaned up the legacy `list_workflows.py` / `test_notify.py` outliers.
- **`test.py`** is safe in `tools/` — pytest only collects under `tests/`.
- **Action files use bare names** — the `action_name` is set by `@register_action`, NOT the filename.

### Notable per-tool subdirectories
- **`tools/report_ops/templates/`** — Jinja2 HTML templates (`base.html`, `dashboard.html`, `macros.html`, + per-action templates). As of **Phase 3 C3**, `dashboard.html` is 296 lines (down from 676) — its inline JS was extracted to `templates/js/dashboard_charts.html` (chart-rendering helpers) + `templates/js/dashboard_theme_override.html` (theme CSS overrides), pulled into `dashboard.html` via `{% include "js/dashboard_charts.html" %}`. The 8 per-chart `<script>` loops stay inline (per-chart config is data-driven). `sortTable` stays in `base.html` (used by every sortable table, not just dashboard). See [tools/REPORT.md](tools/REPORT.md).

---

## 🔄 Workflows Layer (`workflows/`)

6 LangGraph state machines, each following the **facade + `*_impl/` subpackage** pattern. Triggered via `workflow(action="run", type="...", goal="...")`.

### The v1.0 pattern (every workflow)

```text
workflows/
├── <workflow>.py                # Facade — build_<workflow>_graph() + WORKFLOW_METADATA
└── <workflow>_impl/             # Subpackage (all logic lives here)
    ├── __init__.py
    ├── graph.py                 # build_<workflow>_graph() — StateGraph construction
    ├── state.py                 # <Workflow>State TypedDict
    ├── routes.py                # Conditional edge routing functions
    ├── helpers.py               # Shared node utilities
    └── nodes/                   # One file per graph node
        ├── __init__.py
        ├── node_init.py
        ├── node_search.py
        └── ...
```

### The 6 workflows

| Workflow | Subpackage | Nodes | Notes |
|----------|------------|-------|-------|
| `research` | `research_impl/` | 8 | Quick info gathering: search → scrape → synthesize |
| `deep_research` | `deep_research_impl/` | 13 | Iterative ReAct loop with convergence detection + budget tracking |
| `data` | `data_impl/` | 5 | Pandas/numpy analysis, sandboxed `run_data` mode |
| `autocode` | `autocode_impl/` | 29 | Autonomous TDD code generation, git scoping, debug loop, swarm fallback |
| `understand` | `understand_impl/` | 4 | AST-based codebase knowledge graph + doc indexing |
| `autoresearch` | `autoresearch_impl/` | 8 | Autonomous metric optimization (evolutionary loop) |

### Shared infrastructure
- `workflows/base.py` — `WorkflowState` base + node helpers + dispatcher
- `workflows/helpers/` — checkpoint journal

---

## 🧠 Core Layer (`core/`)

13 subsystems. Most follow the **thin facade + `*_backend/` subpackage** pattern (mirrors the tools layer).

### The facade pattern

```text
core/
├── <subsystem>.py              # Thin facade (re-exports public symbols)
└── <subsystem>_backend/        # Implementation subpackage
    ├── __init__.py
    ├── client.py               # Main client
    ├── ...                     # Implementation modules
    └── validation.py           # Startup checks (where applicable)
```

### The 13 subsystems

| Subsystem | Facade | Subpackage | Purpose |
|-----------|--------|------------|---------|
| Config | `core/config.py` | `core/config_backend/` | Singleton `.env` loader, 9 builders, tiered model roles, path hierarchy |
| LLM | `core/llm.py` | `core/llm_backend/` | Role-based dispatch, circuit breakers, 10 providers, JSON parsing |
| Memory | `core/memory_engine.py` | `core/memory_backend/` | 3-collection ChromaDB, 4-layer dedup, decay scoring, two learning subsystems |
| Router | `core/router.py` | `core/router_backend/` | 15s timeout classification, model + heuristic + swarm fallback |
| Gateway | `core/gateway.py` | `core/gateway_backend/` | FastAPI REST API, Bearer auth, rate limiting, SQLite task store |
| Runtime | `core/runtime/` | (direct) | Activity tracking, watchdog, health checks, cancellation guards |
| Sleep & Learn | `core/sleep_learn/` | (direct) | Background meta-learning daemon (trace → rule → prompt injection) |
| Knowledge Graph | `core/kgraph/` | (direct) | AST-based codebase analysis, dependency graphs, test targeting |
| Tracer | `core/tracer.py` | `core/observability/tracer_engine.py` | Structured JSONL logging, trace ID propagation, MCP stdio safety |
| Observability | (under `core/observability/`) | `core/observability/` | Tracer engine + reader + metrics (Prometheus) |
| NET | `core/net/` | (direct) | HTTP error classification, SSRF protection, retry/backoff, API budget |
| Context Pruner | `core/context_pruner.py` | (direct) | Cognitive context budgeting for LLM calls |
| Standalone | (individual files) | (direct) | Shared utilities: `contracts.py`, `path_guard.py`, `time_utils.py`, `utils.py`, `citations.py`, `br_validator.py` |

### Standalone modules (`core/*.py`)
Self-contained library code with no subpackage structure. Each is a single file imported directly by consumers.

| File | Purpose |
|------|---------|
| `core/contracts.py` | `ok()`/`fail()` standardized responses, `ToolCall`/`ToolResult` schemas |
| `core/path_guard.py` | Path validation, protected files, git operation scoping |
| `core/time_utils.py` | Tz-aware time + cron helpers (replaces `@mcpcentral/mcp-time` MCP dep) |
| `core/utils.py` | `compress_result()`, `truncate_output()` — recursive output compression |
| `core/citations.py` | Per-trace citation tracking (thread-safe) |
| `core/br_validator.py` | Brazilian financial data parsing (BRL, dates, tickers) |
| `core/json_extract.py` | Consolidated JSON extraction (3 functions, used by router + autocode) |

---

## 📊 Data Sources Layer (`data_sources/`)

Raw data ingestion + query. Each sub-domain syncs data from an external API into a local SQLite database, then provides query modes. See [DATA_SOURCES.md](DATA_SOURCES.md).

```text
data_sources/
├── dispatcher.py              # @tool data_source(domain, sub_domain, mode, params)
├── _cache.py                  # [engine-cache] Persistent engine result cache (cross-skill)
│                              # → memory_db/cache/engine_cache.db
│                              # 3-layer: in-memory (ContextVar) → DB cache → real engine fn
│                              # Per-company invalidation via fingerprint (MAX(versao)+MAX(date))
├── cvm/                       # Brazilian SEC data
│   ├── __init__.py            # Domain manifest + route
│   ├── _db.py                 # Shared: paths, cnpj_digits(), parse_escala(), connect_*
│   │                          # + _get_company_fingerprint() for cache invalidation
│   ├── _bridge.py             # Shared: resolve_company() — ticker → CNPJ → empresa_ids
│   ├── _freshness.py          # Shared: data freshness (sync timestamps for all DBs)
│   ├── _meses.py              # Shared: rapinav2-compatible meses computation
│   ├── _repair/               # One-time repair scripts (purge, normalize, verify) — v1.1.0
│   ├── dfp/                   # Annual financial statements
│   ├── itr/                   # Quarterly financial statements
│   ├── fre/                   # Governance + ownership (Formulário de Referência)
│   ├── ipe/                   # Material events index
│   ├── cad/                   # Company register (CNPJ → CD_CVM)
│   ├── vlmo/                  # Insider trading disclosures (Valores Mobiliários)
│   ├── cgvn/                  # Governance practices (Código de Governança)
│   ├── fca/                   # Registration form (ticker → CNPJ + listing segment) — primary bridge
│   └── bridge/                # B3-CVM identity bridge (FCA first → bridge.db → B3 API → ISIN)
├── b3/                        # Brazilian stock exchange data
│   ├── __init__.py            # Domain manifest + route
│   ├── api/                   # Market data: instruments, trades, derivatives
│   ├── brapi/                 # brapi.dev quotes + OHLCV + ticker list
│   ├── cotahist/              # COTAHIST historical OHLCV (fixed-width ZIP)
│   │                          # (also stores cotahist_derivatives table — same DB)
│   └── dividends/             # Corporate actions: cash/stock dividends, subscriptions
├── bcb/                       # Brazilian Central Bank data
│   ├── __init__.py            # Domain manifest + route
│   └── sgs/                   # SGS macro series (Selic, CDI, IPCA, etc.)
└── ddm/                       # Dados de Mercado (dadosdemercado.com.br) — Phase 2 + Phase 3 C1
    ├── __init__.py            # Domain manifest + route (auto-discovers sub-domains)
    ├── _parsers.py            # Shared: HTML regex extractors (matrix table, historical table,
    │                          # acoes flat table, focus 4-year tables, fluxo daily table)
    ├── _base/                 # [Phase 3 C1] Shared infrastructure package — 6 modules:
    │   ├── __init__.py        #   Re-exports the public API
    │   ├── catalog_base.py    #   BaseDDMCatalog: db_path()/connect()/ensure_schema() scaffold
    │   ├── fetcher_base.py    #   BaseDDMFetcher: HTTP + cache + concurrency + Chrome 127 WAF
    │   ├── sync_base.py       #   BaseDDMSyncEngine: sync_all() concurrency scaffold + DELETE+INSERT
    │   ├── status_base.py     #   BaseDDMStatusReporter: DB stats scaffold
    │   └── route_base.py      #   BaseDDMRoute: route() dispatcher scaffold (used by domain hub)
    ├── inflation/             # Brazilian inflation indices (IGP-M, IPCA, INPC)
    ├── juros/                 # Brazilian interest-rate indices (Selic, Meta Selic, CDI)
    ├── poupanca/              # Brazilian savings-account monthly yield
    ├── acoes/                 # B3 listed stocks (~380 flat snapshot rows)
    ├── focus/                 # Boletim Focus (market expectations, 4 yearly tables)
    ├── fluxo/                 # B3 investment flow (daily by investor type)
    └── dividends/             # DDM dividends (corporate actions history)
```

**Each sub-domain has:** `__init__.py` (MANIFEST + route), `catalog.py` (schema), `fetcher.py` (HTTP + parse), `sync_engine.py` (download → store), `query_engine.py` (read), `status_reporter.py` (stats). **DDM sub-domains** additionally inherit shared infrastructure from `data_sources/ddm/_base/` (Phase 3 C1) — catalog/fetcher/sync_engine/status_reporter keep only source-specific constants + thin re-exports of the base class.

**`_repair/` subpackage (v1.1.0):** One-time data repair scripts for CVM databases. Auto-skipped by `__init__.py` discovery (underscore prefix). Run as modules:
- `python -m data_sources.cvm._repair.purge_penultimo --vacuum` — delete legacy PENÚLTIMO rows
- `python -m data_sources.cvm._repair.normalize_cnpj` — normalize CNPJ to 14 digits + merge duplicates
- `python -m data_sources.cvm._repair.verify` — 6-check data integrity verifier (recurring health check)

---

## 🧩 Skills Layer (`skills/`)

Analytical views that combine multiple data sources with domain reasoning. Read-only (no sync) — they call data_source query engines directly. See [SKILLS.md](SKILLS.md).

```text
skills/
├── dispatcher.py              # @tool skill(domain, sub_domain, mode, params)
├── _base/                     # [Phase 3 C2] Shared infrastructure package (was skills/_base.py)
│   ├── __init__.py            #   Re-exports all public + private names (backward compat —
│   │                          #   `from skills._base import make_registry` still works)
│   ├── registry.py            #   ModeSpec + make_registry + accessors + auto_discover_modes
│   ├── route.py               #   make_route + _route_with_sync_guard + _dispatch + _SYNC_CHECKED
│   ├── html_gen.py            #   _auto_generate_html (dashboard HTML writer)
│   ├── engine_cache.py        #   _ENGINE_CACHE + @engine_cached + engine_cache_scope (3-layer)
│   └── sync_guard.py          #   SYNC_FRESHNESS_HOURS + ensure_fresh + _trigger_sync + HEAD checks
├── _freshness.py              # Cross-domain freshness dict (CVM + B3 + BCB + DDM) — stays separate
├── _colors/                   # Shared color palettes (price 16-range, dpa dividend bands)
│   ├── __init__.py
│   ├── price.py               # price 16-range red→pink→yellow→green→teal→blue palette
│   └── dpa.py                 # dividend-band palette
├── cvm/                       # CVM analytical skills
│   ├── __init__.py            # Domain manifest + route
│   ├── _shared_report/        # Shared dashboard builders (all CVM skills)
│   ├── calculations/          # Shared engine/metric library (18 engines + 21 metrics)
│   ├── financials/            # Financial statements + ratios (DFP + ITR + DVA) — rapina-style
│   ├── valuation/             # Valuation ratios (b3 price + DFP TTM + FRE shares + ROIC + Graham)
│   ├── historical/            # Historical metric time-series + quartiles
│   ├── comparison/            # Multi-ticker compare (orchestrates financials + valuation + dividends)
│   ├── screener/              # Sector screener (orchestrates CAD + bridge + valuation + FCA)
│   ├── shareholders/          # Named shareholders + equity structure (FRE + DFP)
│   ├── dividends/             # Dividend events + annual totals + filings (B3 + DFP + IPE)
│   ├── insider/               # Insider trading analysis (VLMO disclosures)
│   ├── governance/            # Governance practices analysis (CGVN score)
│   └── backtest/              # Backtesting (historical price + fundamentals scenarios)
├── investsite/                # Investsite.com.br scraper (indicators, statements, events)
├── b3/                        # B3 analytical skills
│   ├── __init__.py            # Domain manifest + route
│   ├── index/                 # Index dashboard + compare + ticker (IBOV, SMLL, BDRX, IFIX, IDIV)
│   ├── price/                 # Price dashboard + quote (cotahist OHLCV + candlestick + MAs)
│   ├── options/               # Options dashboard (Cadeia de Opções + Put/Call Ratio + Volume)
│   └── term/                  # Term dashboard (Contratos Ativos + Spread + Volume Histórico)
├── bcb/                       # BCB analytical skills
│   ├── __init__.py            # Domain manifest + route
│   └── macro/                 # Macro skill (5-tab dashboard: Resumo / Juros / Inflação / Câmbio / Atividade)
└── ddm/                       # DDM analytical skills (Phase 2)
    ├── __init__.py            # Domain manifest + route (auto-discovers sub-domains)
    ├── inflation/             # 4-tab dashboard (IGP-M + IPCA + INPC + Comparativo)
    ├── juros/                 # 4-tab dashboard (Selic + Meta Selic + CDI + Comparativo)
    ├── poupanca/              # 1-tab dashboard (Poupança)
    ├── acoes/                 # 1-tab dashboard (Ações sortable table + price-distribution chart)
    ├── focus/                 # 13-tab dashboard (Boletim Focus market expectations)
    ├── fluxo/                 # 5-tab dashboard (B3 investment flow by investor type)
    └── dividends/             # Dividends dashboard (corporate actions history)
```

**Each skill uses the modular pattern** (was 1 big `<skill>.py`; now `_registry.py` + `__init__.py` + `modes/` + optional `report.py` / `helpers.py` / `fetchers.py`):
- `__init__.py` (~20 lines) — auto_discover_modes() + MANIFEST + `route = make_route(...)`
- `_registry.py` (~3 lines) — `MODES, register_mode = make_registry()`
- `modes/<mode>.py` — one file per mode, decorated with `@register_mode(...)`
- `report.py` (optional) — dashboard composition helpers
- `helpers.py` / `fetchers.py` (optional) — internal utilities

**Adding a new mode** = drop a file in `modes/` + `@register_mode(...)`. No edits to `__init__.py` or `_registry.py`.

**Adding a new skill** = create `skills/<domain>/<skill>/` with 3 files (`_registry.py` + `__init__.py` + `modes/__init__.py`). The domain router auto-discovers it on next server restart.

**Report wiring (v1.2):** Skills stay read-only and report-agnostic. The report tool's `tools/report_ops/adapters/` package flattens each skill's JSON into the `table` action (and `export` xlsx) via `config["adapter"]` (e.g. `financials_quarterly`, `valuation_ratios`). See [tools/REPORT.md](tools/REPORT.md).

---

## 📚 Documentation (`docs/`)

Every component follows the **5-file documentation standard**: `INDEX` (overview) · `ARCHITECTURE` (file map + design decisions) · `API` (contract) · `CHANGELOG` (history + roadmap) · `INSTRUCTIONS` (AI editing rules).

```text
docs/
├── DOCUMENTATION_GUIDE.md     # The 5-file standard itself
├── STRUCTURE.md               # THIS FILE — repo layout reference
├── SESSION_WORKFLOW.md        # AI-assisted dev session workflow
├── TOOLS.md                   # Tool catalog index
├── WORKFLOWS.md               # Workflow catalog index
├── CORE.md                    # Core subsystem index
├── SKILLS.md                  # Skills layer index
├── BENCHMARK.md               # Role benchmarking tool
├── system_prompts/            # Per-role LLM contracts (output schemas, guardrails)
├── tools/                     # Per-tool docs (18 tools)
│   ├── <TOOL>.md              # Landing page (INDEX)
│   └── <tool>/                # {ARCHITECTURE, API, CHANGELOG, INSTRUCTIONS}.md
├── core/                      # Per-subsystem docs (13 subsystems)
│   ├── <SUBSYSTEM>.md         # Landing page (INDEX)
│   └── <subsystem>/           # {ARCHITECTURE, API, CHANGELOG, INSTRUCTIONS}.md
└── workflows/                 # Per-workflow docs (6 workflows + base)
    ├── <WORKFLOW>.md          # Landing page (INDEX)
    └── <workflow>/            # {ARCHITECTURE, API, CHANGELOG, INSTRUCTIONS}.md
```

### Where to look first
1. **README.md** — project overview + navigation
2. **This file (STRUCTURE.md)** — where things live
3. **`docs/TOOLS.md` / `WORKFLOWS.md` / `CORE.md`** — per-layer indexes
4. **Component's `INSTRUCTIONS.md`** — what NOT to break
5. **Component's `ARCHITECTURE.md`** — file map + design decisions

---

## 🧪 Tests (`tests/`)

Pytest suites mirror the source structure. Run with `python -m pytest tests -v -W error --tb=short`.

```text
tests/
├── core/                      # Per-subsystem test suites
│   ├── router/
│   ├── config/
│   ├── llm/
│   └── ...
├── tools/                     # Per-tool test suites (one folder per tool)
│   ├── notify/
│   ├── schedule/
│   ├── parallel/
│   └── ...
└── workflows/                 # Per-workflow test suites
    ├── autocode/
    ├── deep_research/
    └── ...
```

**Conventions:**
- `conftest.py` per tool/workflow folder — fixtures + autouse state reset
- `-W error` treats warnings as errors (catches drift early)
- `--import-mode=importlib` (in `pytest.ini`) prevents test-dir name collisions

---

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Local config (gitignored) — model names, API keys, paths |
| `.env.example` | Template (committed) — documents all env vars |
| `mcp.json` | MCP server config (for LM Studio / Claude Desktop / Cursor hosts) |
| `pytest.ini` | Pytest config — `pythonpath`, `testpaths`, `import-mode`, warning filters |
| `requirements.txt` | Python dependencies |

### Key env vars
- `PLANNER_MODEL`, `EXECUTOR_MODEL`, `ROUTER_MODEL` — LLM role models (required)
- `AGENT_ROOT`, `WORKSPACE_ROOT` — filesystem paths
- `AGENT_TZ` — timezone for `core/time_utils.py` (default = system local)
- `GATEWAY_SECRET` — REST API auth (must change from `changeme`)
- `*_API_KEY` — cloud LLM providers (OpenAI, DeepSeek, Mistral, Qwen, Kimi, Claude, Gemini, Z.ai, MiMo)

---

## 📐 Naming Conventions

| Convention | Example | Why |
|------------|---------|-----|
| `*_ops/` subpackage | `tools/notify_ops/` | v1.0 standard — separates facade from logic |
| `*_impl/` subpackage | `workflows/autocode_impl/` | Workflow equivalent of `*_ops/` |
| `*_backend/` subpackage | `core/llm_backend/` | Core equivalent (thin facade pattern) |
| Bare action filenames | `actions/list.py` (not `list_workflows.py`) | v1.1 cleanup — aligns with `report_ops` |
| `@meta_tool` + `DISPATCH` | every tool facade | Auto-generates `Literal[...]` enum + docstring |
| `@register_action` | every action file | Auto-populates `DISPATCH` |
| `ok()`/`fail()` from `core.contracts` | every action return | Standardized response envelope |
| `from __future__ import annotations` | every Python file | Postponed annotation evaluation |

---

## 🔗 Cross-References

- [README.md](../README.md) — project landing page
- [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md) — the 5-file doc standard
- [SESSION_WORKFLOW.md](SESSION_WORKFLOW.md) — AI-assisted dev session workflow
- [TOOLS.md](TOOLS.md) — tool catalog
- [WORKFLOWS.md](WORKFLOWS.md) — workflow catalog
- [CORE.md](CORE.md) — core subsystem index

---

*Last updated: 2026-09-15 (Phase 3 doc sweep — DDM `_base/` extraction + `skills/_base/` package split + `templates/js/` partials). This document is updated when the repo structure changes (new tools/workflows/subsystems, pattern changes, naming convention updates). For the project overview, see [README.md](../README.md).*
