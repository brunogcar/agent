# 🔄 Workflow Tool

The `workflow()` tool launches **multi-step autonomous LangGraph workflows** for complex tasks: research, data analysis, autocode, deep research, codebase understanding, and autonomous metric optimization. It acts as the primary entry point for long-running operations that require planning, execution, and iteration.

> **v1.0** — `@meta_tool` refactor with **two-level dispatch**. The facade is a thin router; all implementation lives in the `workflow_ops/` subpackage. **Breaking change:** `type` alone no longer works — callers MUST use `action="run"` + `type="..."`. See [CHANGELOG.md](workflow/CHANGELOG.md) for the full migration guide.

**Key characteristics:**
- **Two-level dispatch** — `action` (META-level: what to do — `run | list | status | cancel | history`) + `type` (workflow-type-level: which workflow — `research | data | autocode | deep_research | understand | autoresearch | auto`). Only `action="run"` uses `type`.
- **5 actions** — `run` (launch a workflow), `list` (show all workflows + metadata), `status` (check checkpoint + tracer for a trace), `cancel` (request cancellation — autocode only), `history` (recent workflow runs from the tracer)
- **7 workflow types** — `research`, `data`, `autocode`, `deep_research`, `understand`, `autoresearch`, `auto` (router-classified)
- **`workflow_ops/` subpackage** — 18 files: `_registry.py` (ACTION_DISPATCH), `_type_registry.py` (TYPE_DISPATCH), `helpers.py`, `actions/` (5 files), `types/` (7 files) + 2 `__init__.py` auto-discovery globs
- **`@meta_tool` facade** — `action: Literal["run", "list", "status", "cancel", "history"]` auto-generated from `DISPATCH`. Decorator order: `@tool` (outer) → `@meta_tool` (inner).
- **Fail-fast parameter guards** — Autocode validates `target_file`, `error_msg`, `feature_desc` BEFORE git snapshots — validation lives in `types/autocode.py`, not the facade
- **Auto-routing** — `type="auto"` lazily imports the Router model to classify the goal and select the correct workflow. Low-confidence routing aborts with clarifying questions (Bug #6 fix: fires even if questions are empty).
- **Guaranteed observability** — Every return dict (success or error) contains `trace_id`. Auto-generated via `_ensure_trace_id()` if not provided by MCP host. Every response also includes `duration_ms`.
- **New params (v1.0)** — `files` (JSON dict of filename→content for autocode pass-through), `git_diff` (autocode v1.1.2 git-diff input mode), `dry_run` (pre-flight: validate params + routing without executing)
- **Resume support** — `resume=True` continues interrupted workflows from checkpoint
- **NOT parallel-safe** — workflows are long-running blocking calls. Do NOT add to `PARALLEL_SAFE`.
- **98 tests across 11 files** — `conftest.py` + 10 `test_*.py` files covering validation, autocode params, understand params, auto-routing, run dispatch, list, status, cancel, history, dispatch registry

---

## 🚀 Quick Start

```python
# ─── action="run" — launch a workflow ────────────────────────────────────────

# Research workflow
workflow(action="run", type="research", goal="Find the best Python async database drivers")

# Data analysis workflow
workflow(action="run", type="data", goal="Analyse sales_data.csv for Q3 trends", code="import pandas as pd")

# Autocode — fix a bug
workflow(action="run", type="autocode", goal="Fix the null pointer", target_file="src/main.py", mode="fix_error", error_msg="NullPointerException at line 42")

# Autocode — add a feature (with NEW v1.0 files/git_diff/dry_run params)
workflow(action="run", type="autocode", goal="Add user authentication", target_file="src/auth.py", mode="add_feature", feature_desc="JWT-based auth with refresh tokens", files='{"auth.py": "...", "models.py": "..."}', dry_run=True)

# Deep research (ReAct loop)
workflow(action="run", type="deep_research", goal="Survey state-of-the-art RAG architectures")

# Understand codebase
workflow(action="run", type="understand", goal="Map the auth module", project_root="/path/to/repo")

# Autoresearch (autonomous metric optimization — runs INDEFINITELY)
workflow(action="run", type="autoresearch", goal="minimize val_bpb", target_file="train.py")

# Auto-routing (let the router decide)
workflow(action="run", type="auto", goal="Generate a report on our Q3 performance")

# ─── other actions ───────────────────────────────────────────────────────────

# List all available workflows + their metadata
workflow(action="list")

# Check the status of a running/completed workflow
workflow(action="status", trace_id="abc123")

# Request cancellation (autocode only — other workflows complete current step)
workflow(action="cancel", trace_id="abc123")

# Show recent workflow runs from the tracer (up to 10)
workflow(action="history")
```

> ⚠️ **Breaking change (v1.0):** The Pre-v1 API `workflow(type="research", goal="...")` no longer works. You MUST prepend `action="run",`. The `type` param name is unchanged — only the `action` prefix is new.

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `DISPATCH["workflow"]` | `tools/workflow_ops/_registry.py` | populated by `actions/__init__.py` auto-discovery | Maps action name → `{func, help, examples}`. Drives the `action: Literal[...]` enum. |
| `TYPE_DISPATCH` | `tools/workflow_ops/_type_registry.py` | populated by `types/__init__.py` auto-discovery | Maps type name → `{func, help}`. Drives `type` validation in the `run` action. |
| `trace_id` | Caller / auto-generated | — | Execution trace identifier. Auto-generated by `_ensure_trace_id()` if not provided. |
| `resume` | Caller | `False` | Continue interrupted workflow from checkpoint. Forwarded to `run_workflow(resume=...)`. |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick web search | `web` | Single call, no planning overhead |
| Single file edit | `file` | Direct, no workflow orchestration |
| Git operation | `git` | Atomic, immediate |
| Run a multi-step research workflow | `workflow(action="run", type="research")` | Planning, web search, synthesis, citation |
| Run a data analysis pipeline | `workflow(action="run", type="data")` | Pandas, numpy, chart generation |
| Fix a bug / add a feature | `workflow(action="run", type="autocode")` | TDD, git snapshots, safety checks |
| Iterative deep research | `workflow(action="run", type="deep_research")` | ReAct loop, budget tracking, convergence detection |
| Build a codebase Knowledge Graph | `workflow(action="run", type="understand")` | AST parsing, dependency analysis |
| Autonomous metric optimization | `workflow(action="run", type="autoresearch")` | Evolutionary loop — runs INDEFINITELY, NOT for one-shot fixes |
| Let the router pick the workflow | `workflow(action="run", type="auto")` | Router classifies goal and selects workflow |
| Report/dashboard generation | `report` tool | HTML/PDF dashboards — call `report(action="...")` directly, NOT via workflow |
| Discover what workflows exist | `workflow(action="list")` | Returns metadata for all 7 types |
| Check a workflow's progress | `workflow(action="status", trace_id=...)` | Checkpoint journal + tracer summary |
| Cancel a running workflow | `workflow(action="cancel", trace_id=...)` | Autocode only — sets cancellation flag |
| See recent workflow runs | `workflow(action="history")` | Last 10 workflow traces from the tracer |
| Unclear task type | `workflow(action="run", type="auto")` | Router classifies and selects workflow |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](workflow/ARCHITECTURE.md) | Source code reference (18 files in `workflow_ops/`), module tree with two sub-dispatchers, two-level dispatch flow (action → type for `run`), `_execute_workflow()` entry point, `_get_all_workflow_metadata()` for `list`, checkpoint + tracer integration for `status`/`history`, 11-file test layout (98 tests), key design decisions |
| [API.md](workflow/API.md) | Full `@meta_tool` signature, 5 action sections (`run`/`list`/`status`/`cancel`/`history`) with params + returns + examples, 7 type sections with type-specific params, new params (`files`/`git_diff`/`dry_run`), breaking change documentation, error handling table |
| [CHANGELOG.md](workflow/CHANGELOG.md) | v1.0 entry (`@meta_tool` refactor, two-level dispatch, breaking `type`→`action`+`type` rename, 5 actions, 7 types, new params), completed features (P0/P1 moved to done), 12-item roadmap (compose, timeout, graceful cancel, streaming, templates, parallel, resume action, logs, compare, export, dynamic registration, `templates/` subfolder), deferred items |
| [INSTRUCTIONS.md](workflow/INSTRUCTIONS.md) | 20 NEVER DO rules (incl. never call `run_workflow()` directly from facade, never add types without `@register_type`, never validate type-specific params in facade, never replace `_make_error()` with `fail()`), 15 ALWAYS DO rules, anti-patterns (two-level dispatch rationale, `@meta_tool` enum generation, validation in type handlers, Bug #3 / #6 / mock_tracer three-module patching / cancel `ImportError` separation) |

---

*Last updated: 2026-07-15 (v1.0). See subfiles for detailed documentation.*
