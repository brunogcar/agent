# 📂 Repository Structure

> Canonical map of the MCP Agent Stack repo. This is the reference for "where does X live?" — the README is a summary, this is the full layout.

Last updated: 2026-07-16

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
├── skills/                # Domain knowledge packages (hub-and-spoke)
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
| `memory` | `memory_ops/` | 8 | LLM-facing memory I/O (store, recall, delete, prune, summarize, janitor) |
| `notify` | `notify_ops/` | 8 | Desktop alerts + APScheduler reminders, tz-aware via `core/time_utils.py` |
| `parallel` | `parallel_ops/` | 3 (run, race, pipeline) | Concurrent execution with `PARALLEL_SAFE` allowlist |
| `python` | `python_ops/` | 5 (run, run_data, eval, profile, lint) | Three-layer security (sandbox → imports → executors) |
| `report` | `report_ops/` | 11 | Charts, maps, dashboards, diagrams, PDF/PNG export |
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

## 🧩 Skills Layer (`skills/`)

Domain knowledge packages following the **hub-and-spoke pattern**. A single `@tool`-decorated hub per domain routes to pure-Python subdomain modules.

```text
skills/
├── dispatcher.py              # Auto-discovers domain hubs at startup
├── b3/                        # Brazilian Stock Exchange
│   ├── b3.py                  # @tool hub
│   ├── data.py                # Sync/query CSV data lake
│   ├── export.py              # Export helpers
│   └── paths.py               # Path resolution
└── cvm/                       # Brazilian SEC regulatory data
    ├── cvm.py                 # @tool hub
    └── ...
```

**To add a new domain:** create `skills/<domain>/<domain>.py` with a `@tool`-decorated function. The dispatcher auto-discovers it — no wiring in `server.py` or `registry.py`.

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

*Last updated: 2026-07-16. This document is updated when the repo structure changes (new tools/workflows/subsystems, pattern changes, naming convention updates). For the project overview, see [README.md](../README.md).*
