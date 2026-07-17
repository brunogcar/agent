# 🛠️ Tools Architecture & Meta-Tool Inventory

> **Status:** v2 — Verified July 2026 against real source via `tools/` directory and per-tool docs.

Tools are the **atomic actions** the LLM can execute. They are the "hands" of the agent — interacting with the file system, web, git, local sandbox, external APIs, and browser automation. Most tools follow a shared **meta-tool pattern** (`@meta_tool` + `DISPATCH` registry) for zero-config auto-discovery via `registry.py`.

This document provides a **high-level overview** of all tools and serves as an **index** to the detailed tool docs. For deep-dive API references, action-by-action breakdowns, and security details, see the dedicated docs in `docs/tools/`.

| Document | Tool | Key Topics |
|----------|------|------------|
| [AGENT.md](tools/AGENT.md) | Agent | 15 specialist roles, role-based dispatch, caching, context budgets |
| [BROWSER.md](tools/BROWSER.md) | Browser | Playwright automation, 20 atomic actions, session isolation, SSRF |
| [CLI.md](tools/CLI.md) | CLI | 4-layer NL→shell dispatch, proxy routing, human-readable output |
| [CONSULT.md](tools/CONSULT.md) | Consult | Cloud LLM advisory — 3 actions (advise/review/explain) via `@meta_tool`, `consult_ops/` subpackage (8 files), kill-switch, rate-limit guard |
| [FILE.md](tools/FILE.md) | File | 25+ atomic FS actions, path guard, cancellation guard, compression |
| [GITHUB.md](tools/GITHUB.md) | GitHub | PR + issue + release workflow + remote sync (16 actions: 6 PR + 5 issue + 3 release + push + pull), pagination, mergeable state, git push/pull subprocess, httpx direct (not PyGithub) |
| [GIT.md](tools/GIT.md) | Git | 20+ atomic VCS actions, semantic params, stash-based rollback |
| [MEMORY.md](tools/MEMORY.md) | Memory | 3 ChromaDB collections, tag validation, janitor, lazy loading |
| [NOTIFY.md](tools/NOTIFY.md) | Notify | Cross-platform alerts, APScheduler, graceful console fallback |
| [PARALLEL.md](tools/PARALLEL.md) | Parallel | `@meta_tool` refactor v1.0 — 3 actions (`run`/`race`/`pipeline`), `parallel_ops/` subpackage (8 files), breaking `tools`→`tasks` rename, per-call `timeout`, `PARALLEL_SAFE` (10 tools) + `_TOOL_MAP` (17 tools, lazy), 93 tests |
| [PYTHON.md](tools/PYTHON.md) | Python | 5 actions (`run`/`run_data`/`eval`/`profile`/`lint`) via `@meta_tool`, `python_ops/` subpackage (11 files), three-layer security (sandbox → imports → executors), `json_schema` validation, `timeout` override |
| [REPORT.md](tools/REPORT.md) | Report | 11 atomic actions, HTML dashboards, XSS-safe templates, lazy imports |
| [SWARM.md](tools/SWARM.md) | Swarm | Multi-model meta-tool, parallel cloud LLM fan-out, consensus/race/vote/compare/list_providers |
| [TAVILY.md](tools/TAVILY.md) | Tavily | AI-ranked search, bulk extraction, keyless mode, API budget tracking |
| [VISION.md](tools/VISION.md) | Vision | Multimodal image analysis — 3 actions (describe/extract_text/analyse_ui) via `@meta_tool`, `vision_ops/` subpackage (8 files), breaking `task`→`action`+`question` rename (with deprecated `task` alias), new params (`json_schema`/`format`/`context_type`), `core/net retry_sync` URL downloads, SSRF protection |
| [WEB.md](tools/WEB.md) | Web | SearXNG search, BeautifulSoup, parallel scraping, connection pooling |
| [WORKFLOW.md](tools/WORKFLOW.md) | Workflow | `@meta_tool` two-level dispatch (action+type), 5 actions (run/list/status/cancel/history), 7 workflow types, `workflow_ops/` subpackage (18 files), breaking `type`→`action`+`type` split (v1.0), new params (files/git_diff/dry_run) |
| [SCHEDULE.md](tools/SCHEDULE.md) | Schedule | `@meta_tool` v1.0 — 9 actions (`add_cron`/`add_interval`/`add_once`/`list`/`cancel`/`modify`/`history`/`sync_calendar`/`test`), `schedule_ops/` subpackage (13 files), cron (0=Sunday via DOW remap)/interval/one-shot jobs delivered via notify, offline missed-fire recovery (misfire_policy skip/fire_last/fire_all + grace), iCal sync, `core/time_utils.py`, 18 tools |

---

## 🏗️ The Foundation Layer

Most tools share a common foundation defined in `tools/_meta_tool.py` and the registry pattern.

| Component | File | Purpose |
|-----------|------|---------|
| **`@meta_tool`** | `tools/_meta_tool.py` | Auto-generates `Literal[...]` action enums and docstrings from a `DISPATCH` dict. Used by `browser`, `consult`, `file`, `git`, `github`, `python`, `report`, `swarm`, `tavily`, `vision`, `web`, `workflow` (v1.0 — two-level: also reads `TYPE_DISPATCH` via `register_type`), and `cli` (special case). |
| **`DISPATCH`** | `tools/*_ops/_registry.py` | Maps action names → handler metadata. Validated by `^[a-z][a-z0-9_]*$` regex. |
| **`@register_action`** | `tools/*_ops/actions/*.py` | Decorator that auto-discovers action handlers into the registry. |
| **`path_guard`** | `core/path_guard.py` | Validates all filesystem paths. Blocks traversal outside `agent_root` / `workspace_root`. |
| **`is_safe_network_address`** | `core/security.py` | SSRF protection. Blocks private IPs, localhost, and invalid URL schemes. |
| **`compress_result()`** | `tools/*_ops/helpers.py` | Auto-truncates large outputs to prevent MCP context overflow. |
| **`ensure_not_cancelled()`** | `core/runtime/cancellation.py` | Aborts mutating actions if the trace is cancelled. |

**Key design decisions:**
- **Atomic actions** — One action = one behavior. No subcommand parsing, no overloaded parameters.
- **Auto-discovery** — `@tool` + `@meta_tool` + `@register_action` = zero manual wiring in `server.py`.
- **Semantic naming** — `target` = entity name, `message` = human-readable text, `path` = file path, `query` = search text.
- **Lazy loading** — Heavy imports (pandas, plotly, playwright, chromadb) happen inside function bodies, not at module load time.
- **Thread safety** — `threading.Lock()` and `threading.local()` used where concurrent access is possible (browser, parallel, python stdout).

**Known limitations:**
- `cli()` is a **router**, not a direct tool. It delegates to other tools and returns human-readable `str`, not structured `dict`.
- `understand` workflow ignores `trace_id` and checkpoint system (see `workflows/UNDERSTAND.md`).

---

## 📁 Module Map

```
tools/
├── _meta_tool.py           # @meta_tool decorator — Literal enum + docstring generation
│
├── agent.py                # Meta-cognitive dispatcher (15 roles)
├── agent_ops/
│   ├── _registry.py
│   ├── cache.py
│   ├── context.py
│   ├── json_extract.py
│   ├── metrics.py
│   ├── parse_warnings.py
│   ├── actions/
│   │   ├── clear_cache.py
│   │   ├── dispatch.py
│   │   ├── metrics.py
│   │   └── vision_delegate.py
│   └── roles/
│       ├── analyze.py
│       ├── classify.py
│       ├── code.py
│       ├── consultor.py
│       ├── critique.py
│       ├── document.py
│       ├── extract.py
│       ├── plan.py
│       ├── refactor.py
│       ├── research.py
│       ├── review.py
│       ├── route.py
│       ├── summarize.py
│       ├── test.py
│       └── vision.py
│
├── browser.py              # Playwright facade (20 atomic actions)
├── browser_ops/
│   ├── _registry.py
│   ├── factory.py
│   ├── lifecycle.py
│   ├── loop.py
│   ├── state.py
│   └── actions/
│       ├── click.py
│       ├── close.py
│       ├── cookies.py
│       ├── evaluate.py
│       ├── extract_html.py
│       ├── extract_links.py
│       ├── extract_tables.py
│       ├── fill.py
│       ├── get_url.py
│       ├── hover.py
│       ├── keyboard_press.py
│       ├── navigate.py
│       ├── screenshot.py
│       ├── scroll.py
│       ├── select_option.py
│       ├── set_viewport.py
│       ├── text_content.py
│       ├── type.py
│       ├── upload.py
│       ├── wait_for_selector.py
│       └── wait_for_url.py
│
├── cli.py                  # NL→shell router (4-layer dispatch)
├── cli_ops/
│   ├── _registry.py
│   ├── helpers.py
│   ├── patterns.py
│   ├── router.py
│   └── actions/
│       ├── cleanup.py
│       ├── file.py
│       ├── git.py
│       ├── lms.py
│       ├── memory.py
│       ├── notify.py
│       ├── python.py
│       ├── skill.py
│       ├── system.py
│       └── web.py
│
├── consult.py              # Cloud LLM advisory meta-tool — @meta_tool facade (3 actions: advise/review/explain)
├── consult_ops/
│   ├── _registry.py        # DISPATCH + register_action decorator
│   ├── __init__.py         # Auto-discovery (Path.glob actions/*.py)
│   ├── helpers.py          # _estimate_tokens, _truncate_context, _check_consultor_available, _check_rate_limit, _get_consultor_provider, _call_consultor
│   ├── prompts.py          # ADVISE/REVIEW/EXPLAIN system prompts + FORMAT_SUFFIXES + CONTEXT_TYPE_MODIFIERS
│   └── actions/
│       ├── __init__.py
│       ├── advise.py       # @register_action("consult", "advise")
│       ├── review.py       # @register_action("consult", "review")
│       └── explain.py      # @register_action("consult", "explain")
│
├── file.py                 # File system meta-tool (25+ atomic actions)
├── file_ops/
│   ├── _registry.py
│   ├── helpers.py
│   ├── index.py
│   └── actions/
│       ├── append_file.py
│       ├── copy_file.py
│       ├── create_directory.py
│       ├── delete_file.py
│       ├── directory_tree.py
│       ├── edit_file.py
│       ├── exists.py
│       ├── find_files.py
│       ├── get_file_info.py
│       ├── list_allowed_directories.py
│       ├── list_directory.py
│       ├── move_file.py
│       ├── patch_file.py
│       ├── read_docx.py
│       ├── read_file.py
│       ├── read_media_file.py
│       ├── read_multiple_files.py
│       ├── read_pdf.py
│       ├── read_pptx.py
│       ├── read_xlsx.py
│       ├── search_files.py
│       ├── write_docx.py
│       ├── write_file.py
│       ├── write_pdf.py
│       ├── write_pptx.py
│       └── write_xlsx.py
│
├── github.py               # GitHub PR + issue + release meta-tool (16 actions: 14 API + 2 subprocess [push, pull])
├── github_ops/
│   ├── _registry.py
│   ├── client.py                    # httpx.Client singleton (get_client, is_configured, repo_path,
│   │                                # parse_link_header — v1.2 pagination helper)
│   └── actions/
│       ├── pr_create.py             # POST /repos/{owner}/{repo}/pulls
│       ├── pr_list.py               # GET /repos/{owner}/{repo}/pulls (paginated — v1.2)
│       ├── pr_get.py                # GET /repos/{owner}/{repo}/pulls/{n} (incl. mergeable — v1.2)
│       ├── pr_review.py             # POST /repos/{owner}/{repo}/pulls/{n}/reviews
│       ├── pr_merge.py              # PUT /repos/{owner}/{repo}/pulls/{n}/merge
│       ├── pr_comment.py            # Dual-mode: /issues/{n}/comments OR /pulls/{n}/comments
│       ├── issue_create.py          # POST /repos/{owner}/{repo}/issues (v1.1)
│       ├── issue_list.py            # GET /repos/{owner}/{repo}/issues (paginated — v1.1 + v1.2)
│       ├── issue_get.py             # GET /repos/{owner}/{repo}/issues/{n} (v1.2)
│       ├── issue_update.py          # PATCH /issues/{n} — unified close/reopen/edit (v1.2)
│       ├── issue_comment.py         # POST /repos/{owner}/{repo}/issues/{n}/comments (v1.1)
│       ├── release_create.py        # POST /repos/{owner}/{repo}/releases (v1.1)
│       ├── release_list.py          # GET /repos/{owner}/{repo}/releases (v1.1)
│       ├── release_get.py           # GET /releases/tags/{tag} OR /releases/{id} (v1.2)
│       ├── push.py                  # Local `git push` subprocess (--force-with-lease)
│       └── pull.py                  # Local `git pull` subprocess (v1.3 — remote-sync counterpart to push)
│
├── git.py                  # Git meta-tool (20+ atomic actions)
├── git_ops/
│   ├── _registry.py
│   ├── helpers.py
│   └── actions/
│       ├── add.py
│       ├── branch_create.py
│       ├── branch_delete.py
│       ├── branch_list.py
│       ├── checkout_branch.py
│       ├── checkout_new.py
│       ├── clone.py
│       ├── commit.py
│       ├── diff.py
│       ├── init.py
│       ├── log.py
│       ├── restore.py
│       ├── rollback.py
│       ├── show.py
│       ├── snapshot.py
│       ├── status.py
│       ├── tag_create.py
│       ├── tag_delete.py
│       └── tag_list.py
│
├── memory.py               # Memory meta-tool (12 atomic actions)
├── memory_ops/
│   ├── _registry.py
│   ├── helpers.py
│   ├── state.py
│   └── actions/
│       ├── delete.py
│       ├── janitor.py
│       ├── prune.py
│       ├── recall.py
│       ├── recall_context.py
│       ├── stats.py
│       ├── store.py
│       └── summarize.py
│
├── notify.py               # Desktop notifications & scheduler
│
├── parallel.py             # Concurrent tool execution meta-tool — @meta_tool facade (3 actions: run/race/pipeline)
├── parallel_ops/           # v1.0 NEW — @meta_tool refactor subpackage (8 files)
│   ├── _registry.py        # DISPATCH + register_action decorator
│   ├── __init__.py         # Auto-discovery (Path.glob actions/*.py)
│   ├── tool_map.py         # PARALLEL_SAFE frozenset (10 tools) + _TOOL_MAP dict (17 tools, all lazy) + _get_tool_fn
│   ├── executor.py         # _parallel_depth guard, _resolve_timeout, _safe_run, dispatch_run/race/pipeline, _resolve_dot_path
│   └── actions/
│       ├── __init__.py
│       ├── run.py          # @register_action("parallel", "run") — barrier via wait()
│       ├── race.py         # @register_action("parallel", "race") — first success via as_completed()
│       └── pipeline.py     # @register_action("parallel", "pipeline") — sequential chain with feed (None|str|dict)
│
├── python.py              # Python code execution meta-tool — @meta_tool facade (5 actions: run/run_data/eval/profile/lint)
├── python_ops/
│   ├── _registry.py       # DISPATCH + register_action decorator
│   ├── __init__.py        # Auto-discovery (Path.glob actions/*.py)
│   ├── sandbox.py         # SAFE_BUILTINS, FORBIDDEN_IN_SANDBOX, DANGEROUS_* sets, _validate_sandbox_ast, _validate_eval_ast
│   ├── imports.py         # STDLIB/HEAVY/CORE_ALLOWED/BLOCKED_IMPORTS, _parse_imports
│   ├── executors.py       # _STDOUT_LOCK, _run_inprocess, _run_subprocess (timeout_override), _validate_against_schema, _validate_output_text_against_schema
│   └── actions/
│       ├── __init__.py
│       ├── run.py         # @register_action("python", "run") — strict sandbox
│       ├── run_data.py    # @register_action("python", "run_data") — controlled imports
│       ├── eval.py        # @register_action("python", "eval") — pure expression (NEW v1.0)
│       ├── profile.py     # @register_action("python", "profile") — cProfile top-20 (NEW v1.0, NOT sandboxed)
│       └── lint.py        # @register_action("python", "lint") — ruff/flake8 pre-check (NEW v1.0)
│
├── report.py               # Report meta-tool (11 atomic actions)
├── report_ops/
│   ├── _registry.py
│   ├── charts.py
│   ├── compare.py
│   ├── contracts.py
│   ├── data.py
│   ├── diagrams.py
│   ├── export.py
│   ├── html.py
│   ├── maps.py
│   ├── paths.py
│   ├── scorecard.py
│   ├── timeline.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── chart.html
│   │   ├── compare.html
│   │   ├── dashboard.html
│   │   ├── diagram.html
│   │   ├── macros.html
│   │   ├── map.html
│   │   ├── report.html
│   │   ├── scorecard.html
│   │   └── timeline.html
│   └── actions/
│       ├── chart.py
│       ├── compare.py
│       ├── dashboard.py
│       ├── diagram.py
│       ├── export.py
│       ├── help.py
│       ├── list.py
│       ├── map.py
│       ├── report.py
│       ├── scorecard.py
│       └── timeline.py
│
├── swarm.py                # Multi-model swarm meta-tool (5 actions)
├── swarm_ops/
│   ├── _registry.py
│   ├── helpers.py
│   └── actions/
│       ├── consensus.py
│       ├── race.py
│       ├── vote.py
│       ├── compare.py
│       └── list_providers.py
│
├── tavily.py               # Tavily AI search meta-tool (5 actions)
├── tavily_ops/
│   ├── _registry.py
│   ├── bridge.py
│   ├── client.py
│   ├── errors.py
│   ├── state.py
│   └── actions/
│       ├── crawl.py
│       ├── extract.py
│       ├── map.py
│       ├── research.py
│       └── search.py
│
├── vision.py               # Multimodal image analysis meta-tool — @meta_tool facade (3 actions: describe/extract_text/analyse_ui)
├── vision_ops/
│   ├── _registry.py        # DISPATCH + register_action decorator
│   ├── __init__.py         # Auto-discovery (Path.glob actions/*.py)
│   ├── helpers.py          # _validate_vision_inputs, _file_to_block, _b64_to_block, _do_download,
│   │                       #   _download_image_to_data_uri (core/net retry_sync), _check_vision_available,
│   │                       #   _build_image_block, _call_vision
│   ├── prompts.py          # DESCRIBE/EXTRACT_TEXT/ANALYSE_UI system prompts (base + JSON variants)
│   │                       #   + FORMAT_SUFFIXES + CONTEXT_TYPE_MODIFIERS
│   └── actions/
│       ├── __init__.py
│       ├── describe.py     # @register_action("vision", "describe")
│       ├── extract_text.py # @register_action("vision", "extract_text")
│       └── analyse_ui.py   # @register_action("vision", "analyse_ui")
│
├── web.py                  # Web search & scraping meta-tool (4 actions)
├── web_ops/
│   ├── _registry.py
│   ├── client.py
│   ├── state.py
│   ├── utils.py
│   └── actions/
│       ├── read.py
│       ├── scrape.py
│       ├── search.py
│       └── search_and_read.py
│
├── workflow.py                  # Workflow meta-tool facade (@tool @meta_tool, 174 lines, thin router)
└── workflow_ops/                # v1.0 NEW — two-level dispatch subpackage (18 files)
└── schedule_ops/                # v1.0 NEW — scheduling subpackage (13 files)
    ├── _registry.py             # DISPATCH + @register_action
    ├── __init__.py              # auto-imports actions/*.py
    ├── state.py                 # _scheduler singleton, _job_registry, persistence (agent_root/.schedule_jobs/), mark_fired, catch_up_missed_jobs
    ├── helpers.py               # _get_scheduler, _fire_job (→notify), _resolve_delivery
    └── actions/                 # 9 action files + __init__.py
        ├── add_cron.py          # cron-scheduled recurring job
        ├── add_interval.py      # interval-scheduled recurring job
        ├── add_once.py          # one-shot job (DateTrigger)
        ├── list.py              # list all jobs + metadata
        ├── cancel.py            # cancel by job_id
        ├── modify.py            # update schedule/delivery/misfire policy
        ├── history.py           # recent deliveries (in-memory log)
        ├── sync_calendar.py     # iCal (.ics) URL → add_once jobs
        └── test.py              # fire a test delivery via notify
    ├── __init__.py              # imports _registry, _type_registry, actions, types (in order)
    ├── _registry.py             # ACTION_DISPATCH + register_action() decorator
    ├── _type_registry.py        # TYPE_DISPATCH + register_type() decorator (second level)
    ├── helpers.py               # _make_error, _ensure_trace_id, _validate_goal,
    │                            #   _execute_workflow (single entry to run_workflow),
    │                            #   _get_all_workflow_metadata, _WORKFLOW_MODULES map
    ├── actions/                 # META-level: what to do (5 actions)
    │   ├── __init__.py          # auto-discovery via Path.glob("*.py")
    │   ├── run.py               # @register_action("workflow", "run")
    │   ├── list_workflows.py    # @register_action("workflow", "list")
    │   ├── status.py            # @register_action("workflow", "status")
    │   ├── cancel.py            # @register_action("workflow", "cancel")
    │   └── history.py           # @register_action("workflow", "history")
    └── types/                   # WORKFLOW-TYPE-level: which workflow to run (7 types)
        ├── __init__.py          # auto-discovery via Path.glob("*.py")
        ├── research.py          # @register_type("research")
        ├── data.py              # @register_type("data")
        ├── autocode.py          # @register_type("autocode")  — fail-fast param guards
        ├── deep_research.py     # @register_type("deep_research")
        ├── understand.py        # @register_type("understand")
        ├── autoresearch.py      # @register_type("autoresearch")
        └── auto.py              # @register_type("auto")  — router dispatch + confidence guard
```

---

## 📚 Tool Catalog

The agent currently exposes **18 tools** to the LLM.

### 1. 🤖 Agent — [tools/AGENT.md](tools/AGENT.md)

**Status:** v1.0 — 15 specialist roles with per-role model routing and context budgets.

**Purpose:** Meta-cognitive dispatcher that routes tasks to specialist sub-agents based on `role`.

**Key characteristics:**
- **15 roles** — `classify`, `route`, `research`, `summarize`, `extract`, `critique`, `analyze`, `code`, `review`, `plan`, `consultor`, `document`, `refactor`, `test`, `vision`
- **Per-role model routing** — Router uses fast 2B models, Executor uses 9B models, Planner uses 32K context
- **Per-role context budgets** — Router: 4K tokens, Planner: 32K tokens
- **Structured output** — JSON mode for `extract`, prompt-only JSON for `route`, `plan`, `code`, `review`
- **Response caching** — Deterministic roles (`classify`, `route`) cached with 5-min TTL
- **NOT_PARALLEL_SAFE** — Serialized via global LLM client queue

**Safety:** Context trimming via `tiktoken`, JSON extraction fallback, parse warning tracking.

**Output:**
```json
{
  "status": "success",
  "result": "APPROVE",
  "role": "critique",
  "trace_id": "abc123"
}
```

---

### 2. 🌐 Browser — [tools/BROWSER.md](tools/BROWSER.md)

**Status:** v1.0 — 20 atomic Playwright actions with session isolation.

**Purpose:** Automate web browsers for JavaScript-rendered pages, interactive forms, and screenshots.

**Key characteristics:**
- **20 atomic actions** — `navigate`, `click`, `fill`, `type`, `screenshot`, `text_content`, `evaluate`, `select_option`, `keyboard_press`, `get_url`, `close`, `wait_for_selector`, `scroll`, `wait_for_url`, `hover`, `cookies`, `set_viewport`, `extract_html`, `extract_links`, `extract_tables`, `upload`
- **Session isolation** — Each `trace_id` gets its own `BrowserContext` (isolated cookies, localStorage)
- **Global singleton** — One Chromium instance shared; contexts are per-trace
- **Screenshot auto-cleanup** — Files older than 7 days deleted on startup and every 6 hours
- **Screenshot-on-failure** — Failed actions automatically capture debug screenshots
- **Navigate retry** — Exponential backoff on transient failures (1s, 2s, 4s, ... capped at 8s)

**Safety:** SSRF protection (`is_safe_network_address`), URL scheme validation (blocks `file://`, `javascript:`, `data:`), safe JS injection via Playwright's `evaluate`.

**Output:**
```json
{
  "status": "success",
  "result": "Page text content...",
  "screenshot_path": "workspace/screenshots/abc123_navigate.png",
  "trace_id": "abc123"
}
```

---

### 3. 🖥️ CLI — [tools/CLI.md](tools/CLI.md)

**Status:** v1.0 — 4-layer natural-language dispatch.

**Purpose:** Translate natural-language commands into shell operations by routing to other tools.

**Key characteristics:**
- **4-layer dispatch** — Patterns (zero tokens) → Shell whitelist (zero tokens) → Router LLM → Executor LLM
- **Meta-tool router** — `cli("git status")` → pattern match → `git:status` proxy → `tools/git.py`
- **Human-readable output** — Returns formatted `str`, not structured `dict`
- **No `action` parameter** — `@meta_tool` skips `Literal` patch, generates docstring from flattened dispatch
- **Delegates only** — Does not perform operations itself; routes to `git`, `file`, `web`, `python`, `memory`, `notify`

**Safety:** Shell whitelist, flag blocking, operator rejection, path guard integration, `shell=False` subprocess.

**Output:**
```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update...)
        modified:   tools/web.py
```

---

### 4. 🔍 Consult — [tools/CONSULT.md](tools/CONSULT.md)

**Status:** v1.0 — Opt-in cloud LLM advisory meta-tool with 3 actions.

**Purpose:** High-stakes tasks requiring stronger reasoning, domain expertise, or external validation.

**Key characteristics:**
- **`@meta_tool` facade** — `action: Literal["advise", "explain", "review"]` auto-generated from `DISPATCH`. Adding a new action = drop a file in `consult_ops/actions/`; the facade updates itself.
- **3 actions** — `advise` (architectural advisory, default), `review` (structured code review with severity tags across 5 dimensions), `explain` (educator persona with analogies + step-by-step). Same LLM call, different system prompts.
- **8-file `consult_ops/` subpackage** — `_registry.py`, `__init__.py`, `helpers.py`, `prompts.py`, `actions/{__init__,advise,review,explain}.py`.
- **New v1.0 params** — `trace_id` (observability, threaded through all return paths), `format` (`markdown`/`json`/`bullet_points`), `context_type` (`""`/`code`/`logs`/`architecture`).
- **Cloud LLM dispatch** — Routes to dedicated `CONSULTOR_MODEL` via separate provider chain
- **Kill-switch ready** — Returns `{"status": "disabled"}` if `CONSULTOR_MODEL` is empty
- **Rate-limit guard** — Pre-flight `check_rate_limit()` prevents accidental API quota burn
- **Token-aware truncation** — `tiktoken` (cl100k_base) pruning before dispatch (hard 2000-token ceiling)
- **NOT_PARALLEL_SAFE** — Excluded from aggressive routing

**Safety:** No fallback chain — if unset, role does not exist in registry. Clear error messages for all disabled states. `_call_consultor` indirection centralizes LLM access for clean test patching.

**Output:**
```json
{
  "status": "success",
  "action": "advise",
  "provider": "openai",
  "model": "gpt-4o",
  "advice": "The trade-offs between async and sync drivers...",
  "trace_id": "abc123",
  "duration_ms": 1842
}
```
> Response payload key is action-specific: `advice` / `review` / `explanation`. `trace_id` only included when caller passed one. `warnings` only included on truncation. `duration_ms` always present.

---

### 5. 📁 File — [tools/FILE.md](tools/FILE.md)

**Status:** v1.0 — 25+ atomic file system actions.

**Purpose:** CRUD operations, directory traversal, document parsing, and SQLite FTS search.

**Key characteristics:**
- **25+ atomic actions** — `read_file`, `write_file`, `append_file`, `create_directory`, `list_directory`, `directory_tree`, `search_files`, `find_files`, `move_file`, `copy_file`, `delete_file`, `get_file_info`, `exists`, `patch_file`, `edit_file`, `read_media_file`, `read_pdf`, `read_docx`, `read_xlsx`, `read_pptx`, `write_pdf`, `write_docx`, `write_xlsx`, `write_pptx`, and more
- **Path guard integration** — All operations validate through `core.path_guard`; blocks protected files
- **Cancellation guard** — Mutating actions abort if trace is cancelled
- **Result compression** — Large outputs auto-truncate to prevent MCP context overflow
- **10MB read limit** — `read_file` capped; `read_media_file` capped at 5MB

**Safety:** Null-byte injection protection, protected file list (`server.py`, `core/*`, `registry.py`), atomic writes (no `.bak` garbage), XSS-safe output.

**Output:**
```json
{
  "status": "success",
  "result": "file content...",
  "path": "tools/web.py",
  "size": 4096,
  "trace_id": "abc123"
}
```

---

### 6. 🌿 Git — [tools/GIT.md](tools/GIT.md)

**Status:** v1.0 — 20+ atomic version control actions.

**Purpose:** Atomic git operations with semantic parameter names and stash-based safety.

**Key characteristics:**
- **20+ atomic actions** — `status`, `log`, `diff`, `commit`, `init`, `restore`, `rollback`, `snapshot`, `show`, `branch_create`, `branch_delete`, `branch_list`, `checkout_branch`, `checkout_new`, `tag_create`, `tag_delete`, `tag_list`, `add`, `clone`
- **Semantic parameters** — `target` = entity name, `message` = human-readable text, `root` = repo directory
- **Stash-based rollback** — `rollback` defaults to safe stash recovery; `force=True` for permanent discard
- **System git via subprocess** — NOT GitPython; uses `subprocess` for reliability
- **Auto-generated schema** — `@meta_tool` builds `Literal` enum from `DISPATCH`

**Safety:** Path guard integration, cancellation guard on mutating actions, protected files, stash-based recovery prevents data loss.

**Output:**
```json
{
  "status": "success",
  "result": "Committed 3 files with message 'Fix web search retry'",
  "commit_sha": "a1b2c3d",
  "trace_id": "abc123"
}
```

---

### 7. 🧠 Memory — [tools/MEMORY.md](tools/MEMORY.md)

**Status:** v1.0 — LLM-facing interface to 3-collection ChromaDB store.

**Purpose:** Store, recall, delete, prune, summarize, and get stats across episodic, semantic, and procedural collections.

**Key characteristics:**
- **12 atomic actions** — `store`, `recall`, `recall_context`, `delete`, `prune`, `summarize`, `stats`, `janitor`, `update`, `export`, `import`, `extract`
- **Lazy loading** — ChromaDB imported only on first non-janitor call
- **Janitor bypass** — `archive_old_episodes()` and `purge_stale_rules()` run without touching memory store
- **Tag validation** — MED-05 compliant: rejects `< > " ' \` |`, max 6 tags, alphanumeric/hyphens only
- **Result compression** — Success responses pass through `compress_result()`; errors skipped (v1.1)
- **Duration tracking** — `duration_ms` included in all responses (v1.2)

**Safety:** Write-only lock pattern (MED-01) for 30-50% throughput boost, XSS/injection prevention via tag validation, fail-fast on invalid `memory_type`.

**Output:**
```json
{
  "status": "success",
  "result": "Memory stored successfully",
  "collection": "episodic",
  "duration_ms": 45,
  "trace_id": "abc123"
}
```

---

### 8. 🔔 Notify — [tools/NOTIFY.md](tools/NOTIFY.md)

**Status:** v1.0 — Cross-platform desktop notifications with scheduling.

**Purpose:** Send immediate alerts and schedule delayed reminders.

**Key characteristics:**
- **Cross-platform** — Windows (`plyer`), Linux (`notify-send`), universal console fallback
- **Graceful fallback** — Never silently fails; prints to console if desktop APIs fail
- **Scheduler integration** — APScheduler `BackgroundScheduler` for delayed reminders
- **Job registry** — In-memory tracking of scheduled jobs with metadata
- **Special status schema** — Uses `sent`/`scheduled`/`ok`/`cancelled`/`error` (not generic `success`)

**Safety:** No destructive operations, optional dependencies (`apscheduler`, `plyer`), clear error on missing deps.

**Output:**
```json
{
  "status": "sent",
  "result": "Notification delivered",
  "trace_id": "abc123"
}
```

---

### 9. ⚡ Parallel — [tools/PARALLEL.md](tools/PARALLEL.md)

**Status:** v1.0 — `@meta_tool` refactor with 3 actions: `run` / `race` / `pipeline`.

**Purpose:** Execute multiple independent tool calls concurrently to reduce latency. v1.0 collapsed the pre-v1 single-mode `parallel(tools, ...)` facade into a 117-line thin `@meta_tool` dispatch wrapper + 8-file `parallel_ops/` subpackage. **Breaking change:** `tools` param renamed to `tasks`; `action` is now required.

**Key characteristics:**
- **3 actions via `@meta_tool`** — `run` (barrier via `concurrent.futures.wait()` — wait for all), `race` (`as_completed()` — first success wins, cancel rest), `pipeline` (sequential chain with result feeding — NOT parallel despite the tool name). `action: Literal["pipeline","race","run"]` auto-generated from `DISPATCH`.
- **8-file `parallel_ops/` subpackage** — `_registry.py`, `__init__.py` (auto-discovery via `Path.glob`), `tool_map.py`, `executor.py`, `actions/{__init__,run,race,pipeline}.py`. Auto-discovery: drop a new file in `actions/` to add a 4th action — no facade edits needed.
- **Pipeline "feed" mechanism** — Per-task `feed` key (`None` \| `str` dot-path \| `dict` of arg-name → dot-path) controls how each result flows into the next call's args. `str` replaces args entirely (resolved value must be a dict); `dict` merges into args (missing paths yield `None` — soft error, chain continues).
- **Real global timeout** — `concurrent.futures.wait()` with `cfg.worker_timeout` (default 60s) for `run` (NOT broken `as_completed()` per-future timeout); `as_completed()` for `race` (legitimate — needs completion order); per-step for `pipeline`. Per-call `timeout` param overrides the global default.
- **Nested-call guard** — `threading.local()` (`_parallel_depth`) prevents `parallel → parallel` recursion / deadlock. All three engines increment it; pipeline stages that call `parallel()` are also blocked.
- **`PARALLEL_SAFE` allowlist (10 tools)** + **`_TOOL_MAP` (17 tools, all lazy-imported)** — v1.0 expanded `PARALLEL_SAFE` from 6 → 10 (added `consult`, `vision`, `report`, `agent`); expanded `_TOOL_MAP` from 9 → 17. `parallel` itself intentionally omitted from `_TOOL_MAP` (nested-parallel guard at validator layer).
- **Backwards-compat shim** — `core/parallel_executor.py` is now a 37-line re-export from `tools.parallel_ops.*`. Existing imports (`dispatch_parallel`, `PARALLEL_SAFE`, `_parallel_depth`, `_safe_run`) continue to work; `dispatch_parallel` is an alias for `dispatch_run`.
- **`duration_ms` in every response** — Facade times the handler call and adds `duration_ms` to the response. Mirrors `consult.py` / `swarm.py` pattern.

**Safety:** Write-heavy tools (`git`, `memory`, `cli`, `browser`, `tavily`, `swarm`, `workflow`) excluded by design. Nested `parallel()` calls blocked. Timeout prevents runaway execution. `pipeline` does NOT enforce `PARALLEL_SAFE` (sequential — no concurrency hazard).

**Output:**
```json
// action="run"
{
  "status": "success",
  "trace_id": "abc123",
  "results": [
    {"tool": "web", "status": "success", "result": {"status": "success", "data": "..."}, "trace_id": "abc123"}
  ],
  "errors": [],
  "completed": 1,
  "failed": 0,
  "duration_ms": 1234
}

// action="race" — winner may be null if all tasks fail
{
  "status": "success",
  "trace_id": "abc123",
  "winner": {"tool": "web", "status": "success", "result": {...}, "trace_id": "abc123"},
  "cancelled": ["tavily"],
  "failed": [],
  "duration_ms": 567
}

// action="pipeline" — same shape as run
{
  "status": "success",
  "trace_id": "abc123",
  "results": [...],
  "errors": [...],
  "completed": 2,
  "failed": 0,
  "duration_ms": 3456
}
```

---

### 10. 🐍 Python — [tools/PYTHON.md](tools/PYTHON.md)

**Status:** v1.0 — `@meta_tool` refactor with 5 actions: `run` / `run_data` / `eval` / `profile` / `lint`.

**Purpose:** Execute Python code with three-layer security (sandbox → imports → executors) and optional `json_schema` validation. Replaces the Pre-v1 dual-mode `python(mode, code)` facade.

**Key characteristics:**
- **5 actions via `@meta_tool`** — `run` (strict sandbox, no imports), `run_data` (controlled imports, stdlib in-process + heavy in subprocess), `eval` (pure expression, value returned directly), `profile` (cProfile top-20, NOT sandboxed), `lint` (ruff/flake8 pre-check, 10s hard cap)
- **11-file `python_ops/` subpackage** — `_registry.py`, `__init__.py`, `sandbox.py` (Layer 1), `imports.py` (Layer 2), `executors.py` (Layer 3), `actions/{__init__,run,run_data,eval,profile,lint}.py`
- **Three-layer security** — Sandbox (`SAFE_BUILTINS` + `_validate_sandbox_ast` / `_validate_eval_ast`) → Imports (`BLOCKED_IMPORTS` + `ALL_ALLOWED`) → Executors (`_STDOUT_LOCK` + subprocess isolation). Each layer owned by a separate module and fails independently
- **`json_schema` validation** — Graceful for `run`/`run_data` (warnings on mismatch); strict for `eval` (`fail` on mismatch); ignored by `profile`/`lint`. Best-effort, no `jsonschema` dependency (supports `type`/`enum`/`required`/`properties`/`items`)
- **`timeout` override** — `-1` → `cfg.execution_timeout`; any non-negative int → overrides. Honored by `run_data`/`profile` (subprocess); ignored by `run`/`eval` (in-process); fixed 10s hard cap for `lint`
- **AST-based sandbox** — `_validate_sandbox_ast()` blocks imports, dangerous builtins, MRO traversal, metaclass attacks, context managers, dynamic subscripts; `_validate_eval_ast()` is stricter (rejects all statements)
- **Thread-safe stdout** — Module-level `_STDOUT_LOCK` prevents cross-thread clobbering in `parallel()`
- **Import allowlisting** — `STDLIB_IMPORTS` + `HEAVY_IMPORTS` + `CORE_ALLOWED` (`core.br_validator` only) with `BLOCKED_IMPORTS` security boundary (`os`, `sys`, `subprocess`, etc.)
- **Result pruning** — `prune_text()` prevents MCP context overflow on large outputs

**Breaking change (v1.0):** `mode` parameter renamed to `action`. Legacy `python(mode="run", ...)` returns `{"status": "error", "error": "action is required (run | run_data | eval | profile | lint)"}`. Update all callers to `python(action="run", ...)`. The `run` and `run_data` behaviors are otherwise unchanged.

**Safety:** Two-layer defense (fast-path string check + deep AST tree walking), subprocess isolation for heavy libs, timeout enforcement (configurable + 10s hard cap for lint), temp file cleanup in `finally` blocks. 145 tests across 10 files (3 existing Pre-v1 files updated + 7 new v1.0 files including `conftest.py`).

**Output:**
```json
{
  "status": "success",
  "data": "4950",
  "mode": "sandbox",
  "trace_id": "abc123",
  "warnings": ["json_schema validation failed: ..."],
  "duration_ms": 12
}
```

---

### 11. 📊 Report — [tools/REPORT.md](tools/REPORT.md)

**Status:** v1.0 — 11 atomic actions for interactive HTML reports.

**Purpose:** Generate self-contained interactive HTML dashboards, charts, maps, and diagrams.

**Key characteristics:**
- **11 atomic actions** — `chart`, `map`, `report`, `dashboard`, `diagram`, `export`, `compare`, `timeline`, `scorecard`, `list`, `help`
- **Lazy heavy imports** — pandas, jinja2, plotly, playwright imported inside function bodies only
- **XSS-safe templates** — Jinja2 autoescape + no `| safe` on user-controlled text
- **Atomic file writes** — `_atomic_write` prevents partial/corrupted files on crash
- **Output root** — `workspace/reports/{trace_id}/`

**Safety:** Path guard integration, cancellation guard, XSS-safe templates, atomic writes, optional Playwright for PDF/PNG export.

**Output:**
```json
{
  "status": "success",
  "result": "Report generated",
  "path": "workspace/reports/abc123/revenue_chart.html",
  "trace_id": "abc123"
}
```

---

### 12. 🔬 Tavily — [tools/TAVILY.md](tools/TAVILY.md)

**Status:** v1.0 — AI-optimized web search and bulk extraction.

**Purpose:** Superior ranking and citations via Tavily API; complements `web` for research queries.

**Key characteristics:**
- **5 atomic actions** — `search`, `extract`, `crawl`, `map`, `research`
- **AI-ranked results** — Superior relevance vs raw SearXNG for research queries
- **Automatic citations** — Every result includes URL, title, and confidence score
- **Bulk extraction** — `extract` processes up to 10 URLs in one call
- **Keyless mode** — Works without API key for `search` and `extract` (rate-limited)
- **Resilient** — Circuit breaker, rate-limit retry, structured error codes, API budget tracking

**Safety:** SSRF protection, timeout enforcement, clear error codes for API key issues, rate-limit handling.

**Output:**
```json
{
  "status": "success",
  "data": {
    "keyless": true,
    "results": [
      {"title": "...", "url": "...", "content": "...", "score": 0.95}
    ]
  },
  "trace_id": "abc123"
}
```

---

### 13. 👁️ Vision — [tools/VISION.md](tools/VISION.md)

**Status:** v1.0 — Multimodal image analysis meta-tool with 3 actions.

**Purpose:** Analyze images via local file, base64, or URL using a dedicated vision model. Three action-specific system prompts cover the common image-analysis use cases: general description, OCR-style text extraction, and UI/UX critique.

**Key characteristics:**
- **`@meta_tool` facade** — 3 actions (`describe` / `extract_text` / `analyse_ui`) auto-discovered from `vision_ops/actions/` via the `DISPATCH` registry. Adding a new action = drop a file; the `action: Literal[...]` annotation and docstring update themselves.
- **8-file `vision_ops/` subpackage** — `_registry.py`, `__init__.py`, `helpers.py`, `prompts.py`, `actions/{__init__,describe,extract_text,analyse_ui}.py`.
- **3 actions, same LLM** — All three route to one configured `vision` role (`cfg.vision_model`). Only the system prompt differs (base + format suffix + context-type modifier). `describe` preserves the Pre-v1 `_VISION_SYSTEM` behavior; `extract_text` adds an OCR specialist prompt (reading order, location notes, `[unclear]` for low-confidence); `analyse_ui` adds a senior UI/UX designer prompt (8-section critique with severity-tagged issues).
- **Breaking `task`→`action`+`question` rename** — the Pre-v1 `vision(task="...")` is replaced by `vision(action="describe", question="...")`. A **deprecated `task` alias** is kept for backward compat with `tools/agent_ops/actions/vision_delegate.py` — when `action` is empty AND `task` is non-empty, mapped to `action="describe"` + `question=task` with a deprecation warning. **Will be removed in v2.0.**
- **New v1.0 params** — `trace_id` (observability, threaded through all return paths), `format` (`markdown`/`json`/`bullet_points` — appended suffix to base prompt), `context_type` (`""`/`screenshot`/`diagram`/`photo`/`document` — appended modifier), `json_schema` (structured output via `llm.call(json_schema=...)`).
- **3 input sources** — `file_path`, `base64`, or `url` (exactly one required). URL downloads go through `core/net retry_sync` (max 2 retries, `is_retryable_error` classification, central backoff constants from `core/net/default.py`).
- **SSRF protection** — `is_safe_network_address()` blocks localhost and private IP ranges for URL inputs (runs in `_validate_vision_inputs()`).
- **JSON mode + JSON schema** — `json_mode=True` selects the action's `*_JSON_SYSTEM` prompt variant; `json_schema='...'` forwards a parsed schema dict to `llm.call(json_schema=...)`. `parsed` + `parse_warning` in the response.
- **`_call_vision` indirection** — Action handlers never reference `llm` directly; they call `helpers._call_vision()` so conftest only needs one patch point (`tools.vision_ops.helpers.llm`).
- **Kill-switch ready** — Clear error if `VISION_MODEL` is unset (returns `status=disabled`).
- **NOT parallel-safe** — Uses LLM calls; excluded from `PARALLEL_SAFE`.

**Safety:** SSRF protection (`is_safe_network_address()`) for URL inputs, file size limits (`VISION_MAX_FILE_BYTES` = 20MB), base64 length limits (`VISION_MAX_BASE64_LEN` = 10M chars), URL scheme validation (http/https only), `core/net retry_sync` for resilient URL downloads with bounded retries (max 2).

**Output:**
```json
{
  "status": "success",
  "action": "describe",
  "description": "Overview: A dashboard showing sales metrics...\nKey Elements: ...",
  "model": "gpt-4o",
  "elapsed": 2.34,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150},
  "trace_id": "abc123",
  "duration_ms": 2362
}
```
> Response payload key is action-specific: `describe` → `description`, `extract_text` → `text_extracted`, `analyse_ui` → `analysis`. `trace_id` only included when caller passed one. `parsed` + `parse_warning` only when `json_mode`/`json_schema` is active. `duration_ms` always present.

---

### 14. 🌐 Web — [tools/WEB.md](tools/WEB.md)

**Status:** v1.0 — SearXNG search and BeautifulSoup scraping.

**Purpose:** Free, self-hosted web search and static HTML content extraction.

**Key characteristics:**
- **4 atomic actions** — `search`, `read`, `scrape`, `search_and_read`
- **Free / self-hosted** — Requires only a running SearXNG instance (no API keys)
- **Parallel scraping** — `search_and_read` fans out to `ThreadPoolExecutor` for concurrent page fetching
- **Connection pooling** — Singleton `httpx.Client` reuses TCP/TLS connections
- **User-agent rotation** — Rotates through browser UAs to reduce 403 blocks
- **Retry with backoff** — One retry on transient errors (503, 429, timeout)

**Safety:** SSRF protection (`is_safe_network_address`), content-type guard (rejects PDFs/images/oversized responses), URL validation.

**Output:**
```json
{
  "status": "success",
  "results": [
    {"title": "...", "url": "...", "snippet": "..."}
  ],
  "trace_id": "abc123"
}
```

---

### 15. 🔄 Workflow — [tools/WORKFLOW.md](tools/WORKFLOW.md)

**Status:** v1.0 — `@meta_tool` refactor with **two-level dispatch** (action + type). v1.0 collapsed the 263-line monolithic facade into a 174-line thin router + 18-file `workflow_ops/` subpackage. **Breaking change:** `type` alone no longer works — callers MUST use `action="run"` + `type="..."`. Pre-v1.1 added `autoresearch` workflow; Pre-v1.2 added `deep_research` + removed `report`; Pre-v1.1 fixed Bugs #3 (`understand` project_root forwarding) and #6 (auto-routing low-confidence guard).

**Purpose:** Launch and manage multi-step autonomous LangGraph workflows (research, data, autocode, autoresearch, etc.). 5 actions cover the full lifecycle: run, list, status, cancel, history.

**Key characteristics:**
- **Two-level dispatch** — `action` (META-level: what to do — `run | list | status | cancel | history`) + `type` (workflow-type-level: which workflow). Only `action="run"` dispatches into `TYPE_DISPATCH`; the other 4 actions are leaf operations on tracer/checkpoint.
- **5 actions** — `run` (launch a workflow), `list` (show all 7 workflows + metadata), `status` (checkpoint journal + tracer summary), `cancel` (autocode-only cancellation flag), `history` (last 10 workflow traces from tracer)
- **7 workflow types** — `research`, `data`, `autocode`, `deep_research`, `understand`, `autoresearch`, `auto` (router-classified)
- **`workflow_ops/` subpackage** — 18 files: `_registry.py` (ACTION_DISPATCH), `_type_registry.py` (TYPE_DISPATCH), `helpers.py`, `actions/` (5 files), `types/` (7 files) + 2 `__init__.py` auto-discovery globs
- **`@meta_tool` facade** — `action: Literal["run", "list", "status", "cancel", "history"]` auto-generated from `DISPATCH`. Decorator order: `@tool` (outer) → `@meta_tool` (inner).
- **Type registry replaces `VALID_WORKFLOWS`** — `TYPE_DISPATCH` populated by `@register_type` decorators (auto-discovered via `types/__init__.py` glob). Adding a type = drop a new file in `types/`, no facade edits.
- **Validation in type handlers, NOT facade** — Autocode's `target_file`/`error_msg`/`feature_desc` guards live in `types/autocode.py`. Understand's `project_root` guard lives in `types/understand.py`. The `run` action only validates that `type` is non-empty + registered.
- **Auto-routing** — `type="auto"` calls `router.route()` to classify the goal. Three outcomes: `direct` (not a workflow), `low` confidence (needs clarification — Bug #6 fix: fires even with empty questions), routed type (delegates to that type's handler).
- **`_execute_workflow()` is the single entry to `run_workflow()`** — Type handlers call `helpers._execute_workflow(wf_type, goal, trace_id, resume, **type_specific_kwargs)` which builds kwargs conditionally per type and guarantees `trace_id` in the result.
- **New params (v1.0)** — `files` (JSON dict of filename→content for autocode pass-through), `git_diff` (autocode v1.1.2 git-diff input mode), `dry_run` (pre-flight: validate params + routing without executing). Forwarded only when non-empty/`True`.
- **Guaranteed observability** — Every return dict (success or error) contains `trace_id` (auto-generated via `_ensure_trace_id()`) AND `duration_ms` (attached by facade).
- **Resume support** — `resume=True` continues interrupted workflows from checkpoint. Forwarded through `_execute_workflow()` to `run_workflow(resume=...)`.
- **NOT parallel-safe** — workflows are long-running blocking calls. Do NOT add to `PARALLEL_SAFE`.
- **98 tests across 11 files** — `conftest.py` + 10 `test_*.py` files. `mock_tracer` fixture patches tracer in THREE modules simultaneously via `ExitStack` (Python `from x import y` binding pitfall).

**Safety:** Type-specific parameter validation before any side effects (autocode guards live in `types/autocode.py` and fire BEFORE git snapshots). `_make_error()` (NOT `fail()`) preserves `trace_id` on every error response. `status`/`cancel` actions catch `ImportError` separately and return success with explanatory messages — resilient to partial deployments (e.g. autocode not installed). Lazy router import inside `types/auto.py` body prevents startup circular dependencies.

**Output (action="run"):**
```json
{
  "status": "success",
  "result": "Research complete: 5 sources synthesized",
  "trace_id": "abc123",
  "duration_ms": 45000
}
```

**Output (action="list"):**
```json
{
  "status": "success",
  "workflows": {
    "research":      {"name": "Research", "version": "1.0", "description": "...", "entry_point": "..."},
    "data":          {"name": "data", "error": "metadata not available"},
    "autocode":      {"name": "Autocode", "version": "2.0-alpha", "description": "...", "entry_point": "..."},
    "deep_research": {"name": "Deep Research", "version": "1.0", "description": "...", "entry_point": "..."},
    "understand":    {"name": "understand", "error": "metadata not available"},
    "autoresearch":  {"name": "autoresearch", "error": "metadata not available"},
    "auto":          {"name": "auto", "description": "Let the Router classify the goal and choose the workflow.", "version": "?", "entry_point": ""}
  },
  "count": 7,
  "trace_id": "abc123",
  "duration_ms": 120
}
```

---

### 16. 🐝 Swarm — [tools/SWARM.md](tools/SWARM.md)

**Status:** v1.0 — Multi-model parallel cloud LLM meta-tool.

**Purpose:** Fan a single question out to all configured cloud LLM providers in parallel and combine responses via a coordination strategy (consensus, race, vote, compare, or list_providers).

**Key characteristics:**
- **5 coordination actions** — `consensus`, `race`, `vote`, `compare`, `list_providers`
- **Parallel fan-out** — `ThreadPoolExecutor` (max 5 workers) calls every configured cloud provider concurrently
- **Direct provider calls** — Calls `provider.chat_completion()` directly (NOT through `llm.complete()`), bypassing role routing, circuit breakers, and rate limiting
- **Cloud-only** — Skips `lmstudio` (local); requires `*_API_KEY` + `*_BASE_MODEL` env vars per provider
- **Deterministic output** — Results sorted by provider name (except `race`, which preserves winner-first ordering)
- **NOT parallel-safe** — Uses ThreadPoolExecutor internally; excluded from `PARALLEL_SAFE`; do NOT nest inside `parallel()`
- **Per-provider error isolation** — Provider failures captured in result dict; action only fails if ALL providers fail

**Safety:** No filesystem operations (no path_guard needed); no SSRF surface (calls only trusted cloud LLM endpoints); API keys read by provider layer, never by swarm itself. Bypasses `llm.complete()` rate limiting — callers should be aware of per-call API cost (N providers = N API calls).

**Output:**
```json
{
  "status": "success",
  "responses": [
    {"provider": "claude", "model": "claude-3-5-sonnet-20241022", "text": "...", "latency": 2.31, "tokens": 412, "error": ""},
    {"provider": "openai", "model": "gpt-4o-mini", "text": "...", "latency": 1.84, "tokens": 388, "error": ""}
  ],
  "synthesis": "Combined answer combining the strongest points from each response...",
  "provider_count": 4,
  "successful_count": 3,
  "trace_id": "abc123",
  "duration_ms": 5421
}
```

---

### 17. 🐙 GitHub — [tools/GITHUB.md](tools/GITHUB.md)

**Status:** v1.3 — 16-action PR + issue + release + remote-sync meta-tool (14 GitHub REST API actions + 2 local `git push` / `git pull` subprocesses). v1.0 shipped 7 PR/push actions; v1.1 added 5 issue/release actions; v1.2 added `issue_get`, `issue_update` (unified close/reopen/edit), `release_get`, pagination on `pr_list`/`issue_list`, `mergeable`/`mergeable_state` in `pr_get`, and bug fixes for `number=0`/`line=0` facade-default validation; **v1.3 added `pull` (remote-sync counterpart to `push`) + autocode integration** — the new `node_publish` workflow node + `github_ops.py` helper wire in `push` / `pr_create` / `pr_merge` (gated by `AUTOCODE_PUSH_ON_COMMIT` / `AUTOCODE_OPEN_PR` / `AUTOCODE_AUTO_MERGE`); `node_systematic_debug` wires in `pr_comment` for low-confidence swarm verdicts; `node_git_branch` wires in `pull` (`AUTOCODE_PULL_BEFORE_BRANCH`). All gated off by default.

**Purpose:** Open, list, get, review, merge, and comment on pull requests; open, list, get, update (close/reopen/edit), and comment on issues; create, list, and get releases — all via the GitHub REST API. Plus push local branches to `origin` and pull recent commits from `origin` as the remote-sync pair (pull before branching → push after committing) bookending the PR workflow. Conceptually paired with `git()` — `git` operates on the **local** VCS, `github` operates on the **remote** PR/issue/release workflow + remote sync.

**Key characteristics:**
- **16 actions** — `pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `push` (v1.0) + `issue_create`, `issue_list`, `issue_comment`, `release_create`, `release_list` (v1.1) + `issue_get`, `issue_update`, `release_get` (v1.2) + `pull` (v1.3)
- **GitHub REST API via httpx** — Direct HTTPS calls to `https://api.github.com` (hardcoded base URL). NO PyGithub dependency. Singleton `httpx.Client` with auth headers (connection pooling). v1.2 added `parse_link_header()` helper in `client.py`.
- **`push` + `pull` are subprocesses, NOT API calls** (v1.3 — `pull` added) — `subprocess.run(["git", "push"|"pull", ...])` with list args (NOT `shell=True`). No `GITHUB_TOKEN` needed for either. Together they form the **remote-sync pair** (pull before branching → push after committing). Both live in `github_ops/` (NOT `git_ops/`) because they're part of the remote workflow.
- **`--force-with-lease` (not `--force`) — `push` only** — `force=True` on `push` uses `--force-with-lease`, which refuses to overwrite remote refs that have moved since the last fetch. Safer than bare `--force`. `pull` has no `force` param (force semantics don't apply to pull).
- **PARALLEL_SAFE for API actions, NOT for `push`/`pull`** (v1.3 — `pull` added) — Facade declares `_NOT_PARALLEL_SAFE = frozenset({"push", "pull"})`; both excluded from `PARALLEL_SAFE` (subprocess lock contention). All 14 API actions are parallel-safe.
- **Pagination on `pr_list` + `issue_list`** (v1.2) — `page` param + `Link` header parsing via `parse_link_header()`. Response includes `page` / `has_next` / `next_page`.
- **`mergeable` + `mergeable_state` in `pr_get`** (v1.2) — surfaced for pre-merge checks. `mergeable` can be `true`/`false`/`null` (null = still computing, retry).
- **`issue_update` unifies close/reopen/edit** (v1.2) — single PATCH action handles state changes AND field edits. `state=""` (the v1.2 facade default) means "don't change"; list actions normalize empty → `"open"`.
- **Dual-mode `pr_comment`** — General comment via `/issues/{n}/comments` OR line-level comment via `/pulls/{n}/comments` (XOR validation on `path`/`line`).
- **Default `merge_method="squash"`** — Keeps history clean (one commit per PR). Override with `merge` (merge commit) or `rebase` (linear).
- **Requires `GITHUB_TOKEN` + `GITHUB_OWNER` + `GITHUB_REPO`** — All three in `.env` (commented out by default). `is_configured()` short-circuits on first empty value. `push` and `pull` are the only actions that do NOT require configuration (local subprocess).
- **Auto-discovered** — `@tool` + `@meta_tool` + `@register_action` = zero manual wiring in `server.py`
- **Autocode integration** (v1.3) — `workflows/autocode_impl/github_ops.py` helper module + new `node_publish` workflow node wire in the GitHub workflow. All integrations gated by opt-in env vars (default OFF) — autocode v1.3 behaves identically to v1.2 when no GitHub env vars or flags are set.

**Safety:** No filesystem operations outside `git push` / `git pull`. No `path_guard` needed (the `path` param on `pr_comment` is a GitHub file path, not a local FS path). No SSRF surface (hardcoded `https://api.github.com`). Token read once at httpx.Client construction, embedded in `Authorization` header, never logged or returned in any result dict. `push` and `pull` both use list-form subprocess (NOT `shell=True`) + shell-metacharacter rejection (defense in depth).

**Output:**
```json
{
  "status": "success",
  "data": {
    "number": 42,
    "title": "Fix timeout bug",
    "url": "https://github.com/owner/repo/pull/42",
    "state": "open",
    "head": "fix/timeout",
    "base": "main"
  },
  "error": null,
  "duration_ms": 845,
  "trace_id": "abc123"
}
```

---

### 16. ⏰ Schedule — [tools/SCHEDULE.md](tools/SCHEDULE.md)

**Status:** v1.0 — new tool. Schedules cron / interval / one-shot jobs that **deliver via notify** at fire time. notify stays focused on delivery; schedule owns scheduling logic + offline recovery + iCal sync. 9 actions via `@meta_tool`: `add_cron` / `add_interval` / `add_once` / `list` / `cancel` / `modify` / `history` / `sync_calendar` / `test`.

- **`schedule_ops/` subpackage** — 13 files: `_registry.py`, `__init__.py` (auto-discovery), `state.py` (scheduler singleton + `_job_registry` + persistence + `catch_up_missed_jobs`), `helpers.py` (`_get_scheduler` + `_fire_job`→notify + `_resolve_delivery`), `actions/` (9 action files + `__init__.py`).
- **Standard cron semantics (0=Sunday)** — `core/time_utils._build_cron_trigger` remaps the DOW field to APScheduler day-names, sidestepping APScheduler's `from_crontab` 0=Monday trap. `"0 9 * * 1"` = Monday 9am (not Tuesday).
- **Offline recovery** — if the server is offline when a job is due, APScheduler never queues it. On next boot, `catch_up_missed_jobs()` (server.py startup daemon) computes missed fires per job, applies `misfire_grace` (default 24h) + `misfire_policy` (`skip` / `fire_last` [default] / `fire_all`), delivers via notify, and advances `last_fired_at` (idempotent — never re-processes the same window).
- **`core/time_utils.py`** — new shared module: tz-aware `now`/`parse_iso`/`parse_human`/`parse_duration`/`cron_next_fire`/`compute_missed_fires`, all reading `cfg.timezone` (`AGENT_TZ` env, default = system local). Replaces the external `@mcpcentral/mcp-time` MCP dependency for our own tooling (removed from `mcp.json`).
- **Delivery backend (v1.0 = notify only)** — `schedule(action="add_cron", cron="0 9 * * *", title="Standup", message="...")` builds the delivery internally; pass `delivery={...}` for full control. ntfy.sh / Slack / Discord / Telegram / email planned for v2.0.
- **iCal sync** — `sync_calendar` fetches a `.ics` URL, parses VEVENT DTSTART/SUMMARY/DESCRIPTION (TZID + VALUE=DATE aware), creates `add_once` jobs for upcoming events. RRULE recurrence + CalDAV two-way sync deferred to v2.0.
- **NOT `PARALLEL_SAFE`** — owns a `BackgroundScheduler` singleton + shared `_job_registry`; concurrent calls could race on job creation. In `_TOOL_MAP` (lazy) so `parallel` can dispatch to it, just not concurrently with itself.
- **Persistence** — `agent_root/.schedule_jobs/jobs.json` (atomic write; mirrors `.understand/` convention, NOT `workspace/`).

## 🔄 Tool Comparison

| Aspect | Agent | Browser | CLI | Consult | File | GitHub | Git | Memory | Notify | Parallel | Python | Report | Swarm | Tavily | Vision | Web | Workflow |
|--------|-------|---------|-----|---------|------|--------|-----|--------|--------|----------|--------|--------|-------|--------|--------|-----|----------|
| **Interface** | `role` param | `action` param | `command` str | `action` param | `action` param | `action` param | `action` param | `action` param | `action` param | `action`+`tasks` params | `action` param | `action` param | `action` param | `action` param | `action` param | `action` param | `action`+`type` params (two-level) |
| **Meta-tool** | ❌ Role dispatch | ✅ @meta_tool | ✅ @meta_tool (special) | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool | ❌ Direct | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool (no Literal) | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool | ✅ @meta_tool (two-level: action+type) |
| **PARALLEL_SAFE** | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Read only | ✅ API only (push ❌) | ❌ No | ❌ No | ✅ Yes | N/A (orchestrator) | ✅ Yes | ❌ No | ❌ No | ✅ Yes | ❌ No | ✅ Yes | ❌ No |
| **LLM required** | ✅ Yes | ❌ No | ✅ Router/Executor | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Planner synthesis | ✅ Yes | ✅ Yes | ❌ No | ✅ Router |
| **Subprocess** | ❌ No | ❌ No | ✅ Shell (Layer 2) | ❌ No | ❌ No | ✅ `git push` (push only) | ✅ System git | ❌ No | ❌ No | ✅ ThreadPool | ✅ run_data/profile/lint | ❌ No | ❌ No (ThreadPool) | ❌ No | ❌ No | ❌ No | ✅ Workflow graphs |
| **Lazy imports** | ❌ No | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes (_TOOL_MAP: 17 tools) | ❌ No | ✅ Yes | ❌ No | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| **Primary use** | Specialist LLM | JS page automation | NL command router | Cloud advisory | File CRUD | PR workflow | Version control | Memory I/O | Alerts | Concurrent execution | Code execution | HTML reports | Multi-model consensus | AI search | Image analysis | Web search | Workflow orchestration |

---

## 📋 Unified Return Schema

All tools MUST return a dictionary with at least:

**Success:**
```json
{
  "status": "success",
  "result": "...",
  "trace_id": "abc123"
}
```

**Error:**
```json
{
  "status": "error",
  "error": "Descriptive error message",
  "trace_id": "abc123"
}
```

**Special status schemas** (non-standard):
- **Notify** — `sent`, `scheduled`, `ok`, `cancelled`, `error`
- **Consult** — `disabled`, `rate_limited`
- **Workflow** — `success` | `failed` (from graph, not tool layer)

**Guaranteed keys for all tools:** `status`, `trace_id`.

---

## 🛠️ Tool Creation Guidelines

### The `@tool` Auto-Discovery Pattern

Tools rely on **zero-config auto-discovery** via `registry.py`. You do not need to manually wire new tools into `server.py`.

1. Create a new Python file in the `tools/` directory (e.g., `tools/my_tool.py`).
2. Import the decorator: `from registry import tool`.
3. Decorate your function.
4. Type hints automatically generate the MCP JSON schema.
5. Docstrings become the LLM-visible prompt/description.

```python
# tools/my_tool.py
from registry import tool

@tool
def my_custom_tool(action: str, param: str = "", dry_run: bool = False) -> dict:
    """
    Performs a custom action for task automation.
    Use dry_run=True to preview changes without applying them.
    """
    if not param:
        return {"status": "error", "error": "Parameter 'param' is required."}

    if action == "do_something":
        if dry_run:
            return {"status": "success", "preview": f"Would do something with {param}"}
        return {"status": "success", "result": f"Done something with {param}"}

    return {"status": "error", "error": f"Unknown action '{action}'"}
```

### The `@meta_tool` Pattern (for multi-action tools)

For tools with multiple atomic actions, use `@meta_tool` to auto-generate the `Literal` enum and docstring:

```python
from tools._meta_tool import meta_tool
from tools.my_tool_ops._registry import DISPATCH
from registry import tool

@tool
@meta_tool(DISPATCH["my_tool"], doc_sections=["Usage notes here"])
def my_tool(action: str = "", ...) -> dict:
    """Facade auto-populated by @meta_tool."""
    ...
```

---

## 🆕 New Tool Checklist

When adding a **new tool** to the MCP Agent Stack, update **all** of the following files. Missing any one of them causes drift between the source code, the docs, and the LLM's tool schema.

> **v1.4 update:** `complete_with_tools()` is now implemented (see [`docs/core/llm/API.md`](core/llm/API.md)). Tools that want to be callable by the LLM natively (via native tool-calling APIs) should register tool definitions — see checklist item #12 below.

| # | File | What to update |
|---|------|----------------|
| 1 | `tools/<tool>.py` | The `@tool` facade — validation, dispatch, compression. Thin wrapper, no business logic. |
| 2 | `tools/<tool>_ops/` | Subpackage: `_registry.py` (DISPATCH + `@register_action`), `__init__.py` (auto-imports `actions/`), `actions/` (one file per action), `helpers.py` (shared utilities). |
| 3 | `core/router.py` | Add tool name to `ROUTER_TOOLS` list; add routing rules; add heuristic regex patterns for NL→tool routing. |
| 4 | `tools/parallel_ops/tool_map.py` | Add to `PARALLEL_SAFE` frozenset **only if** the tool is parallel-safe (no internal ThreadPoolExecutor, no shared mutable state). Most tools are NOT parallel-safe. (v1.0: `PARALLEL_SAFE` and `_TOOL_MAP` moved here from `core/parallel_executor.py`, which is now a backwards-compat shim.) |
| 5 | `tools/parallel_ops/tool_map.py` | Add to `_TOOL_MAP` dict (mirrors `PARALLEL_SAFE`) **and** add the matching lazy-import branch in `_get_tool_fn`. A new key with `None` value but no `elif name == "X":` branch returns `None` silently. |
| 6 | `docs/system_prompts/system_prompt.md` | Add the new tool to the tool list + describe its capabilities so the LLM knows when to use it. |
| 7 | `docs/TOOLS.md` | (a) Bump tool count in "## 📚 Tool Catalog" intro; (b) add row to the summary Document/Tool/Key Topics table; (c) add `<tool>_ops/` block to the Module Map; (d) add `### N. <Tool>` detailed entry; (e) optionally add column to the Tool Comparison table. |
| 8 | `docs/tools/<TOOL>.md` | Landing page — title, key characteristics, quick start, configuration, when-to-use table, subfile directory table. Follow `GIT.md` / `WEB.md` format. |
| 9 | `docs/tools/<tool>/` | 4 subfiles following the 5-file standard: `API.md` (signature, params, actions, security), `ARCHITECTURE.md` (source ref, module tree, dispatch flow, design decisions, testing), `CHANGELOG.md` (version history, breaking changes, completed, in-progress, deferred), `INSTRUCTIONS.md` (NEVER DO, ALWAYS DO, anti-patterns). |
| 10 | `benchmark/benchmark.py` | Add to `ROLE_GROUPS` / `ROLE_TO_GROUP` **only if** benchmark tasks exist for the new tool. Skip if no benchmark tasks. |
| 11 | `server.py` | Check the tool-count warning threshold (>20 tools triggers a warning). Bump the expected count if hardcoded. |
| 12 | `core/llm_backend/tools.py` | **(v1.4)** If the tool should be callable by the LLM natively via `complete_with_tools()`, verify `tool_def_from_meta_tool()` generates a valid `ToolDefinition` from `__tool_metadata__`. No registration needed — the generator reads metadata at call time. See `docs/core/llm/API.md`. |

**Order of operations (recommended):**
1. Write `tools/<tool>_ops/` first (subpackage + actions + helpers + registry).
2. Write `tools/<tool>.py` facade (depends on the subpackage).
3. Run `python -c "from tools import <tool>"` to verify imports + DISPATCH auto-discovery.
4. Update `core/router.py` + `tools/parallel_ops/tool_map.py` (if parallel-safe; add to `PARALLEL_SAFE` + `_TOOL_MAP` + the `_get_tool_fn` lazy-import chain).
5. Update `docs/TOOLS.md` (count, summary table, module map, detailed entry).
6. Write `docs/tools/<TOOL>.md` + `docs/tools/<tool>/` subfiles.
7. Update `docs/system_prompts/system_prompt.md`.
8. Run `compileall` + `pytest` before committing.
9. Restart LM Studio (cached tool schemas require full restart to refresh).

**Common mistakes:**
- Forgetting `__init__.py` in `actions/` — actions silently not registered.
- Adding a tool to `PARALLEL_SAFE` that uses `ThreadPoolExecutor` internally (e.g. `swarm`) — causes nested-parallelism risk.
- Forgetting to bump the tool count in `docs/TOOLS.md` — doc drift.
- Writing the facade before the subpackage — ImportError on first run.
- Not restarting LM Studio after schema changes — LLM sees stale tool list.

---

## 🛡️ Security & Architecture Rules

### 1. MCP Stdio Safety (CRITICAL)
NEVER use `print()` or write to `sys.stdout` inside any tool. The MCP protocol uses `stdout` for JSON-RPC communication. Writing to stdout will corrupt the payload and crash the server. Use `core.tracer` or `sys.stderr` for all logging.

### 2. Standardized Returns
Always return a dictionary containing at least `{"status": "success"}` or `{"status": "error", "error": "descriptive message"}`. Include `trace_id` in all responses for observability.

### 3. Input Validation
Always validate file paths (prevent directory traversal outside `WORKSPACE_ROOT`) and sanitize inputs to prevent injection attacks. Use `core.path_guard` for filesystem operations and `core.security.is_safe_network_address` for network URLs.

### 4. Timeouts
Wrap external HTTP calls, subprocess executions, and heavy computations in timeouts to prevent blocking the LLM execution loops. Respect `cfg.worker_timeout` and `cfg.execution_timeout`.

### 5. No `.bak` Files
Creating `.bak` backup files is forbidden by project rules. Use atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) instead.

### 6. AST Sandbox Validation (Python Tool)
The Python execution sandbox (Layer 1 — `python_ops/sandbox.py`) blocks:
- Direct imports, dangerous builtins (`eval`, `exec`, `compile`, `open`, `__import__`)
- Dynamic resolution (`getattr`, `setattr`, `delattr`)
- Subscript access to `__builtins__` (e.g. `__builtins__["eval"]`)
- Module attribute calls (`os.system()`)
- MRO traversal vectors (`__class__`, `__subclasses__`, `__mro__`, `__dict__`)
- Direct name access (`__builtins__`)
- Definition-time execution (`ast.ClassDef`, `ast.With`, `ast.AsyncFunctionDef`)

Two-layer defense: fast-path string check (`FORBIDDEN_IN_SANDBOX`) + deep AST tree walking (`_validate_sandbox_ast` / `_validate_eval_ast`). The `eval` action is stricter — it rejects ALL statements (only pure expressions survive `ast.parse(mode='eval')`). 31 pytest cases across `test_sandbox_security.py` + `test_sandbox_ast_bypass.py` verify blocking of obfuscated attacks. See [docs/tools/python/ARCHITECTURE.md § Security Layers](tools/python/ARCHITECTURE.md#-security-layers) for the full three-layer model (sandbox → imports → executors).

### 7. Git Rollback Safety
Default `rollback` action uses stash-based recovery: stashes uncommitted changes before `git reset --hard HEAD`. Returns `stash_ref` for manual recovery. Only `force=True` performs permanent discard + `git clean -fd`.

### 8. Path Guard
All filesystem paths must:
- Resolve relative to `cfg.agent_root` or `cfg.workspace_root`
- Validate symlinks (must resolve inside root)
- Block protected files (`server.py`, `core/*`, `registry.py`)
- Reject Windows ADS (Alternate Data Streams)
- Reject null-byte injection

### 9. Cancellation Guard
Mutating actions (write, delete, commit, rollback) must call `ensure_not_cancelled()` before executing. Prevents ghost mutations on cancelled traces.

---

## 🧪 Testing Quick Reference

| Tool | Test Command |
|------|-------------|
| Agent | `.\venv\Scripts\pytest tests/tools/agent/ -W error --tb=short -v` |
| Browser | `.\venv\Scripts\pytest tests/tools/browser/ -W error --tb=short -v` |
| CLI | `.\venv\Scripts\pytest tests/tools/cli/ -W error --tb=short -v` |
| Consult | `.\venv\Scripts\pytest tests/tools/consult/ -W error --tb=short -v` |
| File | `.\venv\Scripts\pytest tests/tools/file/ -W error --tb=short -v` |
| GitHub | `.\venv\Scripts\pytest tests/tools/github/ -W error --tb=short -v` |
| Git | `.\venv\Scripts\pytest tests/tools/git/ -W error --tb=short -v` |
| Memory | `.\venv\Scripts\pytest tests/tools/memory/ -W error --tb=short -v` |
| Notify | `.\venv\Scripts\pytest tests/tools/notify/ -W error --tb=short -v` |
| Parallel | `.\venv\Scripts\pytest tests/tools/parallel/ -W error --tb=short -v` |
| Python | `.\venv\Scripts\pytest tests/tools/python/ -W error --tb=short -v` |
| Report | `.\venv\Scripts\pytest tests/tools/report/ -W error --tb=short -v` |
| Tavily | `.\venv\Scripts\pytest tests/tools/tavily/ -W error --tb=short -v` |
| Vision | `.\venv\Scripts\pytest tests/tools/vision/ -W error --tb=short -v` |
| Web | `.\venv\Scripts\pytest tests/tools/web/ -W error --tb=short -v` |
| Workflow | `.\venv\Scripts\pytest tests/tools/workflow/ -W error --tb=short -v` |

> **Note:** Verify exact test directory names against `tests/tools/` on disk. Some tools may share test directories or have different naming conventions.

---

## 🧩 Chunking (chonkie) — Where It Applies and Why

Text chunking via [chonkie](https://github.com/chonkie-ai/chonkie) is available as a **soft dependency** (lazy import — non-chunk operations work without it installed). As of file tool v1.2, memory tool v1.3, and workflow base v1.3, chunking is integrated in **two tools and one workflow utility**. This section explains why, so future AI editors don't re-investigate the same question.

### The two patterns where chunking adds value

| Pattern | Why chunking helps | Where it applies |
|---------|-------------------|-----------------|
| **Persistent text for retrieval** | Recall finds the specific paragraph, not the whole blob | ✅ Memory tool (v1.3) — `memory(action="store", chunk=True)` |
| **Large persistent text for navigation** | LLM can read specific sections instead of one truncated blob | ✅ File tool (v1.2) — `file(action="read_file", chunk=True)` |
| **Workflow state eviction** | Evict chunks individually (precise recall later) + keep preview in state | ✅ Workflow base `trim_state()` (v1.3) — see `docs/WORKFLOWS.md` |

The key word is **persistent** — the text survives between calls and the LLM needs to navigate or retrieve it later. For ephemeral tool output, reactive truncation (`compress_result`) is correct.

### Why other tools don't need chunking

| Tool(s) | Current handling | Why chunking doesn't fit |
|---------|-----------------|-------------------------|
| **web**, **tavily**, **browser** | `max_chars` truncation + `prune_tool_dict` (head+tail+artifact) + `compress_result` | Web content is **ephemeral** — LLM consumes it immediately. If truncated, LLM increases `max_chars` or uses `browser(selector="...")` to target sections. The `research`/`deep_research` workflows handle multi-page synthesis. |
| **git** | `diff` has `max_lines` (preserves headers, truncates middle); `log` uses `--max-count=n` | Git has native navigation — `git diff --stat`, `git diff -- pathspec`, `git diff -U5`. Chunking would duplicate git's native filtering. |
| **cli** | Returns raw output, `compress_result` truncates | CLI is for quick shell queries. For large file reading, LLM uses `file(read_file, chunk=True)`. System prompt scopes CLI to "trivial ops." |
| **agent**, **consult** | `budget.py` 7-tier priority truncation on `content` param | Chunked processing (map-reduce) is a **workflow** concern — `deep_research` already does decompose→search→synthesize. Adding chunking to the agent tool would break the "one tool call = one LLM call" contract and duplicate workflow logic. |
| **report**, **parallel**, **notify**, **workflow**, **vision**, **python** | N/A — don't process large text | Either generate output (report), execute code (python), or orchestrate (workflow/parallel). No large-text input pattern. |

### The architectural principle

```
file (persistent text on disk)       → chunk=True for navigation    ✅ v1.2
memory (persistent text in ChromaDB) → chunk=True for retrieval     ✅ v1.3
workflow state (eviction to memory)  → chunked eviction + preview   ✅ v1.3
web/tavily/browser (ephemeral text)  → truncation + compress_result ✅ correct
agent/workflows (LLM processing)     → budget.py + map-reduce       ✅ correct
```

`compress_result` in `core/utils.py` (truncates to 4000 chars with "chars truncated" message) is the right pattern for **ephemeral** tool output — reactive (handles overflow after it happens) rather than proactive (chunking before it's needed). For ephemeral output, reactive is correct — you don't know which part the LLM needs until it reads it.

### Workflow integration points (roadmap)

Chunking may add value in **workflows** in 2 additional places. See `docs/WORKFLOWS.md` § "Chunking in Workflows" for details:

| Workflow | Integration point | Value | Priority |
|----------|------------------|-------|----------|
| **understand** | `core/kgraph/embeddings.py` — extend to `.md`/`.txt` docs (tree-sitter can't parse prose; chonkie sentence chunking would handle it) | Medium — depends on understand supporting docs first (separate feature) | P2 |
| **autocode** #37 | Debug-loop history compression | Low — current `debug.py` is stateless per iteration. Would only apply if autocode is refactored to accumulate debug history. | P3 (future) |

---

*Architecture: @meta_tool + DISPATCH registry + atomic actions + path guard + cancellation guard + standardized returns + MCP stdio safety.*

---

---

## 🕷️ Crawl4ai Integration (web tool v1.3 prototype)

The `web` tool has a new `crawl` action (v1.3) that integrates [crawl4ai](https://github.com/unclecode/crawl4AI) — an open-source LLM-friendly web crawler. This is a **prototype** to evaluate whether crawl4ai should replace the current scrape + browser fallback chain.

### What crawl4ai does

| Feature | Current approach | crawl4ai |
|---------|-----------------|----------|
| **JS-heavy pages** (React/Angular/Vue SPAs) | `web(scrape)` fails → `browser(text_content)` fallback (2 calls) | `web(crawl)` handles JS natively (1 call) |
| **Output format** | Plain text (BeautifulSoup extraction) | Clean LLM-ready markdown |
| **Structured extraction** | Not supported (use `browser(extract_links/tables)`) | CSS/XPath selectors (no LLM) or LLM schema (optional, heavy deps) |
| **Stealth mode** | User-agent rotation (4 UAs) | Bot detection evasion (mimics real users) |
| **Cost** | Free | Free (open-source) |

### Current status: prototype

`web(action="crawl")` is available as a **new action** (additive — no workflow changes). It's a **soft dependency** (lazy import — non-crawl actions work without crawl4ai installed). Does NOT fall back to scrape on failure (caller retries explicitly).

### Potential workflow refactoring (roadmap, not implemented)

If crawl4ai quality is validated, two workflows could be simplified:

| Workflow | Current | With crawl4ai | Benefit |
|----------|---------|---------------|---------|
| **research** | `web(read)` + `_browser_fallback_scrape` for JS walls | `web(crawl)` handles JS natively | Eliminates browser fallback — simpler graph, fewer nodes |
| **deep_research** | Three-tier: `tavily` → `web` → `browser` | Two-tier: `tavily` → `web(crawl)` | Browser tier eliminated for scraping |

**This refactoring is NOT done.** The prototype action exists to enable evaluation. After testing crawl4ai on real JS-heavy pages, a separate commit would update the workflows.

### Dependency tiers

| Tier | Dependencies | Already installed? | Use case |
|------|-------------|-------------------|----------|
| **Base (markdown + JS)** | Playwright, BeautifulSoup, lxml | ✅ All already installed (browser + web tools) | `web(action="crawl")` — returns clean markdown |
| **LLM extraction** | transformers, PyTorch | ❌ Heavy (~2GB), not installed | `web(action="crawl", extract_schema={...})` — structured data extraction (deferred) |

**Recommendation:** Only the base tier is needed for the prototype. LLM extraction is P3 in the web CHANGELOG roadmap — deferred until the base crawl action is validated.

### See also

- `docs/tools/web/CHANGELOG.md` → v1.3 entry + roadmap
- `docs/tools/web/API.md` → `crawl` action section
- `docs/workflows/research/CHANGELOG.md` → roadmap (potential refactor)
- `docs/workflows/deep_research/CHANGELOG.md` → roadmap (potential refactor)

---

## 🔗 Cross-References

- **Core:** See `docs/CORE.md`
- **Workflows:** See `docs/WORKFLOWS.md`
- **Skills:** See `docs/SKILLS.md`
- **Environment:** See `.env.example` in repo root
