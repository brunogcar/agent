<- Back to [Workflow Overview](../WORKFLOW.md)

# 📝 API Reference

> **v1.0 — `@meta_tool` refactor with two-level dispatch.** The `workflow()` tool now takes an `action` parameter (meta-level: what to do) plus a `type` parameter (workflow-type-level: which workflow to run). Only `action="run"` uses `type`; the other four actions are leaf operations.
>
> **v1.2 — Operator UX: resume + logs + templates + kill.** 4 new actions added (resume, logs, templates, kill). `run` action learns `template` param. New `templates/` subfolder with 4 starter templates.
>
> **v1.2.1 — Cognitive framing + compose enhancement.** `autoresearch` added to `ROUTER_WORKFLOWS` (was missing). Router prompt uses cognitive-question framing. `compose` steps support `{stepN.field}` + `{prev.field}` placeholders in goal + kwargs.

## 🔧 Tool Signature

```python
from registry import tool
from tools._meta_tool import meta_tool
from tools.workflow_ops._registry import DISPATCH  # populated by workflow_ops/__init__.py auto-discovery

@tool
@meta_tool(
    DISPATCH.get("workflow", {}),
    doc_sections=[
        "WORKFLOW TOOL — Launch and manage LangGraph workflows:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Run a workflow | workflow(run, type=research) | Execute a multi-step autonomous workflow |",
        " | List available workflows | workflow(list) | Show all workflows + their metadata |",
        " | Check workflow status | workflow(status, trace_id=...) | Check checkpoint for a running/completed workflow |",
        " | Cancel a workflow | workflow(cancel, trace_id=...) | Set cancellation flag (autocode only) |",
        " | Show recent runs | workflow(history) | Query tracer for recent workflow executions |",
        "",
        "Workflow types (for action=run): research, data, autocode, deep_research, understand (v1.4: skip_embeddings=True for graph-only mode), autoresearch, auto",
        "NOT parallel-safe — workflows are long-running blocking calls.",
    ],
)
def workflow(
    action: str = "",                      # auto-restricted by @meta_tool to Literal["run", "list", "status", "cancel", "history", "resume", "logs", "templates", "kill"]
    type: str = "",                         # workflow type — only used by action="run"
    goal: str = "",
    # data workflow
    code: str = "",
    # autocode workflow
    target_file: str = "",
    mode: str = "improve",
    error_msg: str = "",
    feature_desc: str = "",
    files: str = "",                        # v1.0 NEW — JSON dict of filename→content for autocode pass-through
    git_diff: bool = False,                 # v1.0 NEW — autocode v1.1.2 git-diff input mode
    dry_run: bool = False,                  # v1.0 NEW — pre-flight: validate params + routing without executing
    # understand / autoresearch workflow
    project_root: str = "",
    # common
    trace_id: str = "",
    resume: bool = False,
    # v1.2 NEW — logs pagination
    limit: int = 100,                       # v1.2 NEW — action="logs" max steps returned
    offset: int = 0,                        # v1.2 NEW — action="logs" skip first N steps
    # v1.2 NEW — template name for action="run"
    template: str = "",                     # v1.2 NEW — load pre-set params from templates/<name>.json
) -> dict:
    """Workflow meta-tool — run | list | status | cancel | history | resume | logs | templates | kill."""
```

### Parameter Table

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | `Literal["run", "list", "status", "cancel", "history", "resume", "logs", "templates", "kill"]` | **Yes** | `""` | What to do. Auto-restricted by `@meta_tool`. Empty string returns an error. v1.2: +4 actions (resume, logs, templates, kill). |
| `type` | `str` | Only for `action="run"` | `""` | Workflow type. Valid: `research`, `data`, `autocode`, `deep_research`, `understand`, `autoresearch`, `auto`. Validated against `TYPE_DISPATCH`. |
| `goal` | `str` | Only for `action="run"` | `""` | Human-readable task description. Validated by `_validate_goal()`. |
| `code` | `str` | No | `""` | Python code for `data` workflow (e.g. pandas analysis). Forwarded only when non-empty. |
| `target_file` | `str` | Yes for `type="autocode"` / `type="autoresearch"` | `""` | File path. Autocode: file to modify. Autoresearch: script to modify + run repeatedly. |
| `mode` | `str` | No | `"improve"` | Autocode mode: `improve`, `fix_error`, `add_feature`. |
| `error_msg` | `str` | Required when `type="autocode"` + `mode="fix_error"` | `""` | Error message for autocode `fix_error` mode. |
| `feature_desc` | `str` | Required when `type="autocode"` + `mode="add_feature"` | `""` | Feature description for autocode `add_feature` mode. |
| `files` | `str` (JSON) | No | `""` | **v1.0 NEW.** JSON dict of `filename → content` for autocode pass-through. Forwarded only when non-empty. |
| `git_diff` | `bool` | No | `False` | **v1.0 NEW.** Use git-diff input mode (autocode v1.1.2). Forwarded only when `True`. |
| `dry_run` | `bool` | No | `False` | **v1.0 NEW.** Pre-flight: validate params + routing without executing. Forwarded only when `True`. |
| `project_root` | `str` | Yes for `type="understand"`, optional for `type="autoresearch"` | `""` | Project directory. Understand: directory to scan. Autoresearch: git repo for experiment branch. |
| `trace_id` | `str` | No | `""` | Observability threading ID. Auto-generated by `_ensure_trace_id()` if missing. |
| `resume` | `bool` | No | `False` | Continue interrupted workflow from checkpoint. Forwarded to `run_workflow(resume=...)`. |
| `limit` | `int` | No | `100` | **v1.2 NEW.** Max steps returned by `action="logs"`. Use with `offset` for paging. |
| `offset` | `int` | No | `0` | **v1.2 NEW.** Skip first N steps in `action="logs"`. Use with `limit` for paging. |
| `template` | `str` | No | `""` | **v1.2 NEW.** Template name for `action="run"` — loads pre-set params from `templates/<name>.json`. Caller params override template params. Template's `type` field is authoritative (caller can't override `type` when using a template). |

### ⚠️ Breaking Change (v1.0)

```python
# ❌ OLD (Pre-v1) — no longer works
workflow(type="research", goal="Find the best Python async database drivers")
# → returns {"status": "error", "error": "action is required (run | list | status | cancel | history)", "trace_id": ""}

# ✅ NEW (v1.0) — action="run" is now required
workflow(action="run", type="research", goal="Find the best Python async database drivers")
```

The `type` param name is KEPT (not renamed to `workflow_type`) to minimize call-site churn. The migration is purely additive: prepend `action="run",` to every existing call.

---

## ⚡ Actions (9)

### `action="run"`

Launch a multi-step autonomous workflow. The ONLY action that uses `type` and dispatches into `TYPE_DISPATCH`.

| Required | Optional | Description |
|----------|----------|-------------|
| `action="run"`, `type`, `goal` | `code`, `target_file`, `mode`, `error_msg`, `feature_desc`, `files`, `git_diff`, `dry_run`, `project_root`, `trace_id`, `resume`, `template` | See [§ Workflow Types](#-workflow-types-7) below for which params apply to which `type`. `template` (v1.2 NEW) loads pre-set params from a template JSON file — see [§ Templates](#-templates). |

**Examples:**
```python
workflow(action="run", type="research", goal="Survey LLM agent frameworks")
workflow(action="run", type="data", goal="Analyze sales.csv", code="print(df.head())")
workflow(action="run", type="autocode", goal="Fix login bug", target_file="auth.py", mode="fix_error", error_msg="KeyError: user")
workflow(action="run", type="autocode", goal="Add auth", target_file="auth.py", mode="add_feature", feature_desc="JWT auth with refresh tokens", files='{"auth.py": "...", "models.py": "..."}', dry_run=True)
workflow(action="run", type="understand", goal="Map codebase", project_root="/path/to/repo")
workflow(action="run", type="auto", goal="Find recent papers on RAG")
# v1.2 NEW — run via template (cleaner than re-specifying mode + goal every time):
workflow(action="run", template="bug-fix", target_file="auth.py", error_msg="KeyError: user")
workflow(action="run", template="refactor", target_file="utils.py")
workflow(action="run", template="index-codebase", project_root="/path/to/repo")
workflow(action="run", template="index-quick", project_root="/path/to/repo")
```

**Returns:** workflow-specific dict. Always includes `status`, `trace_id`, `duration_ms`. Possible `status` values: `success`, `error`, `routed` (auto→direct only), `needs_clarification` (auto→low confidence only).

**`template` param (v1.2):** When non-empty, loads the template's pre-set params, sets `type` from the template (caller can't override `type` when using a template — the template defines the type), merges caller-supplied params on top (caller wins), validates all `required` params are present, then forwards the merged params to the type handler. Returns `_make_error("Template not found: ...", available_templates=sorted(TEMPLATES.keys()))` if the template name doesn't exist. Returns `_make_error("Template '...' requires params that are missing or empty: [...]")` if any required param is absent.

---

### `action="list"`

List all available workflows with their metadata. Reads `WORKFLOW_METADATA` from each workflow module's `graph.py` via `_get_all_workflow_metadata()`, then augments with `TYPE_DISPATCH` entries not in the static `_WORKFLOW_MODULES` map (specifically `auto`).

| Required | Optional | Description |
|----------|----------|-------------|
| `action="list"` | `trace_id` | No other params. The `type` param is ignored. |

**Example:**
```python
workflow(action="list")
```

**Returns:**
```json
{
  "status": "success",
  "workflows": {
    "research":      {"name": "Research",      "version": "1.0", "description": "...", "entry_point": "..."},
    "data":          {"name": "data",          "error": "metadata not available"},
    "autocode":      {"name": "Autocode",      "version": "2.0-alpha", "description": "...", "entry_point": "..."},
    "deep_research": {"name": "Deep Research", "version": "1.0", "description": "...", "entry_point": "..."},
    "understand":    {"name": "understand",    "error": "metadata not available"},
    "autoresearch":  {"name": "autoresearch",  "error": "metadata not available"},
    "auto":          {"name": "auto",          "description": "Let the Router classify the goal and choose the workflow.", "version": "?", "entry_point": ""}
  },
  "count": 7,
  "trace_id": "abc123"
}
```

Modules that can't be imported (e.g. heavy optional dep missing) show up as `{"name": <type>, "error": "metadata not available"}` rather than crashing the list action.

---

### `action="status"`

Check the status of a workflow by `trace_id`. Looks up both the checkpoint journal and the tracer.

| Required | Optional | Description |
|----------|----------|-------------|
| `action="status"`, `trace_id` | — | The `type` param is ignored. |

**Example:**
```python
workflow(action="status", trace_id="abc123")
```

**Returns:**
```json
{
  "status": "success",
  "trace_id": "abc123",
  "checkpoint": true,
  "checkpoint_node": "node_git_commit",
  "checkpoint_status": "running",
  "tracer_summary": {"steps": 12, "errors": 0, "elapsed_ms": 45000}
}
```

If the checkpoint module isn't available or the tracer db errors, the action returns success with `checkpoint=false` and/or `tracer_summary=null` — it never crashes.

---

### `action="cancel"`

Request cancellation of a running workflow by `trace_id`. Currently only the autocode workflow supports cancellation (via `workflows.autocode_impl.helpers.request_cancellation()`).

| Required | Optional | Description |
|----------|----------|-------------|
| `action="cancel"`, `trace_id` | — | The `type` param is ignored. |

**Example:**
```python
workflow(action="cancel", trace_id="abc123")
```

**Returns (autocode installed):**
```json
{
  "status": "success",
  "message": "Cancellation requested for trace_id=abc123. Only autocode workflow supports cancellation. Other workflows will complete their current step.",
  "trace_id": "abc123"
}
```

**Returns (autocode not installed — `ImportError`):**
```json
{
  "status": "success",
  "message": "Cancellation requested for trace_id=abc123, but no cancellation mechanism is available in this deployment (workflows.autocode_impl.helpers not installed).",
  "trace_id": "abc123"
}
```

Other workflows will complete their current step before noticing the flag — that's documented in the response message. See the roadmap for graceful cancel across all workflow types.

---

### `action="history"`

Show recent workflow runs from the tracer. Filters to traces with a `workflow` field OR `category == "workflow"`.

| Required | Optional | Description |
|----------|----------|-------------|
| `action="history"` | `trace_id` | The `type` param is ignored. Returns up to 10 recent runs. |

**Example:**
```python
workflow(action="history")
```

**Returns:**
```json
{
  "status": "success",
  "runs": [
    {"trace_id": "abc123", "workflow": "research", "goal": "Survey LLM agent frameworks", "status": "success", "elapsed": 45000},
    {"trace_id": "def456", "workflow": "autocode", "goal": "Fix login bug in auth.py — KeyError on user lookup...", "status": "failed", "elapsed": 12000}
  ],
  "count": 2,
  "trace_id": "abc123"
}
```

The `goal` is truncated to 80 chars per entry to keep the response compact for LLM context. Non-workflow traces (tool calls, LLM calls) are filtered out.

---

### `action="resume"`

Resume an interrupted workflow by `trace_id`, OR list all incomplete workflows when no `trace_id` is given. Cleaner API than `run` with `resume=True` because the caller doesn't need to know the workflow type — the resume action reads it from the checkpoint.

**Mode 1: Resume a specific workflow**

| Required | Optional | Description |
|----------|----------|-------------|
| `action="resume"`, `trace_id` | — | Reads the checkpoint via `get_latest(trace_id)`, extracts `workflow` type + `goal` from the checkpoint state, calls `run_workflow(workflow_type=..., goal=..., trace_id=trace_id, resume=True, **checkpoint_overrides)`. The checkpoint_overrides are the non-control fields from the checkpoint state (project_root, target_file, mode, etc.). |

**Example:**
```python
workflow(action="resume", trace_id="abc123")
```

**Returns:** the resumed workflow's result dict (same shape as `action="run"`).

**Error cases:**
- If `trace_id` is given but no checkpoint exists: `{status: "error", error: "No checkpoint found for trace_id=...", trace_id}`.
- If the checkpoint's workflow type isn't in `TYPE_DISPATCH`: `{status: "error", error: "Checkpoint workflow type '...' is not registered...", valid_types}`.

**Mode 2: List incomplete workflows**

| Required | Optional | Description |
|----------|----------|-------------|
| `action="resume"` (no `trace_id`) | — | Calls `scan_incomplete()` to find workflows with non-terminal status in the last 48h. For each `trace_id`, calls `get_latest()` to get the workflow type + goal + last node. |

**Example:**
```python
workflow(action="resume")
```

**Returns:**
```json
{
  "status": "success",
  "incomplete": [
    {"trace_id": "abc123", "workflow": "autocode", "goal": "Fix login bug", "last_node": "node_apply_patch", "status": "running"},
    {"trace_id": "def456", "workflow": "understand", "goal": "Map repo", "last_node": "parse_and_store", "status": "running"}
  ],
  "count": 2,
  "trace_id": ""
}
```

If no incomplete workflows exist: `{status: "success", incomplete: [], count: 0, message: "No incomplete workflows found"}`.

---

### `action="logs"`

Fetch the full step-by-step timeline for a workflow by `trace_id`. Goes beyond `status` (current/last node) and `history` (recent runs) — returns every node entry/exit + the workflow's metadata + result.

| Required | Optional | Description |
|----------|----------|-------------|
| `action="logs"`, `trace_id` | `limit` (default 100, cap on steps returned), `offset` (default 0, skip first N steps) | Pagination for paging through long traces. Use them together: `limit=50, offset=0` for first page, `limit=50, offset=50` for second page. |

**Examples:**
```python
workflow(action="logs", trace_id="abc123")
workflow(action="logs", trace_id="abc123", limit=50, offset=100)
```

**Returns:**
```json
{
  "status": "success",
  "trace_id": "abc123",
  "workflow": "research",
  "goal": "Survey LLM agents",
  "trace_status": "success",
  "started_at": "2026-07-25 10:00:00",
  "elapsed_s": 12.5,
  "result": "5 sources synthesized",
  "steps": [
    {"ts": 1, "event": "step", "node": "planner", "message": "planning"},
    {"ts": 2, "event": "step", "node": "search", "message": "searching"},
    {"ts": 3, "event": "step", "node": "synthesize", "message": "done"}
  ],
  "total_steps": 3,
  "offset": 0,
  "limit": 100,
  "trace_id_out": "abc123"
}
```

If the trace isn't found: `{status: "error", error: "Trace not found: ...", trace_id}`.

---

### `action="templates"`

List available workflow templates from `tools/workflow_ops/templates/`. Templates are pre-configured parameter sets for common tasks.

| Required | Optional | Description |
|----------|----------|-------------|
| `action="templates"` | `trace_id` | No other params. |

**Example:**
```python
workflow(action="templates")
```

**Returns:**
```json
{
  "status": "success",
  "templates": [
    {"name": "bug-fix", "type": "autocode", "description": "Fix a bug. Operator provides error_msg + target_file.", "params": {"mode": "fix_error", "goal": "Fix the bug described in error_msg"}, "required": ["target_file", "error_msg"]},
    {"name": "refactor", "type": "autocode", "description": "Refactor a file for clarity. Operator provides target_file.", "params": {"mode": "improve", "goal": "Refactor {target_file} for clarity"}, "required": ["target_file"]},
    {"name": "index-codebase", "type": "understand", "description": "Full codebase index with embeddings. Operator provides project_root.", "params": {"goal": "Index the codebase for search + dependency graph", "skip_embeddings": false}, "required": ["project_root"]},
    {"name": "index-quick", "type": "understand", "description": "Graph-only index (~5s). Skips embeddings. Operator provides project_root.", "params": {"goal": "Quick graph-only index of the codebase", "skip_embeddings": true}, "required": ["project_root"]}
  ],
  "count": 4,
  "trace_id": ""
}
```

See [§ Templates](#-templates) below for the template format + how to use them with `action="run", template=...`.

---

### `action="kill"`

Forcibly request termination of a running workflow by `trace_id`. Stronger than `cancel` — same mechanism under the hood (Python threads can't be force-killed — no `thread.kill()` exists), but different intent + trace message.

| Required | Optional | Description |
|----------|----------|-------------|
| `action="kill"`, `trace_id` | — | Calls `request_workflow_cancel(trace_id)` (same as cancel) + logs a `tracer.warning`. |

**Example:**
```python
workflow(action="kill", trace_id="abc123")
```

**Returns:**
```json
{
  "status": "success",
  "trace_id": "abc123",
  "message": "Kill requested. Workflow will stop at the next cancellation check point. Python threads cannot be force-killed mid-operation."
}
```

**`cancel` vs `kill`:**
- `cancel` = "I changed my mind, please stop when convenient." Logs `tracer.step`.
- `kill` = "This is stuck/hung, stop as forcefully as you can." Logs `tracer.warning`.

Neither can interrupt a mid-LLM-call or mid-subprocess operation — those complete (or time out) before the cancellation flag is observed at the next check point.

---

## 📂 Templates

Templates are pre-configured parameter sets for common workflow tasks. They live in `tools/workflow_ops/templates/` as JSON files alongside `actions/` and `types/`. Each template defines:

- `name` — unique key (matches the filename stem).
- `type` — workflow type (must be a registered type in `TYPE_DISPATCH`).
- `description` — human-readable summary.
- `params` — dict of pre-set params applied when the template is loaded.
- `required` — list of params the operator MUST still provide (either from caller kwargs or via the template's `params`).

### Starter Templates (4)

| Name | Type | Description | Pre-set Params | Required |
|------|------|-------------|----------------|----------|
| `bug-fix` | autocode | Fix a bug. Operator provides `error_msg` + `target_file`. | `mode=fix_error`, `goal="Fix the bug described in error_msg"` | `target_file`, `error_msg` |
| `refactor` | autocode | Refactor a file for clarity. Operator provides `target_file`. | `mode=improve`, `goal="Refactor {target_file} for clarity"` (placeholder resolved at load time) | `target_file` |
| `index-codebase` | understand | Full codebase index with embeddings. Operator provides `project_root`. | `goal="Index the codebase for search + dependency graph"`, `skip_embeddings=False` | `project_root` |
| `index-quick` | understand | Graph-only index (~5s). Skips embeddings. Operator provides `project_root`. | `goal="Quick graph-only index of the codebase"`, `skip_embeddings=True` | `project_root` |

### Using a Template

Pass `template="<name>"` to `action="run"`. The template's `type` field sets the workflow type (caller can't override `type` when using a template — the template defines the type). The template's `params` are applied as the base; caller-supplied params override them (caller wins). All `required` params must be present after the merge.

```python
# Bug-fix template:
workflow(action="run", template="bug-fix", target_file="auth.py", error_msg="KeyError: user")
# → type=autocode (from template), mode=fix_error (from template),
#   goal="Fix the bug described in error_msg" (from template),
#   target_file="auth.py" (from caller), error_msg="KeyError: user" (from caller)

# Refactor template (note: {target_file} placeholder is resolved at load time):
workflow(action="run", template="refactor", target_file="utils.py")
# → type=autocode, mode=improve, goal="Refactor utils.py for clarity", target_file="utils.py"

# Caller can override template params — caller wins:
workflow(action="run", template="bug-fix", target_file="auth.py",
         error_msg="KeyError: user", goal="Custom caller goal")
# → goal="Custom caller goal" (caller wins over template's goal)
```

### Template Loader

`tools/workflow_ops/templates/_registry.py`:
- `TEMPLATES: dict[str, dict]` — loaded at import time by scanning `Path(__file__).parent.glob("*.json")`.
- `get_template(name: str) -> dict | None` — returns the template dict or `None`.
- `list_templates() -> list[dict]` — returns all templates as a list.
- Each template dict has the JSON keys + a `_source_file` key for debugging (basename of the JSON file).

### Adding a New Template

Drop a new `<name>.json` file into `tools/workflow_ops/templates/`. The loader picks it up automatically on next import — no edits to `_registry.py` needed.

---

## 📂 Workflow Types (8)

The `type` parameter is only used by `action="run"`. Each type has its own handler in `tools/workflow_ops/types/` that validates type-specific params and calls `_execute_workflow()`.

### `type="research"`

Gathers information from web sources, synthesizes findings, and generates cited reports.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `trace_id`, `resume` | Research topic or question |

**Handler:** `tools/workflow_ops/types/research.py` → `_type_research()` → `_execute_workflow("research", goal, trace_id, resume)`.

---

### `type="data"`

Analyses datasets with pandas/numpy, generates charts, and produces data reports.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `code`, `trace_id`, `resume` | `code` provides initial Python code. Forwarded only when non-empty. |

**Handler:** `tools/workflow_ops/types/data.py` → `_type_data()` → `_execute_workflow("data", goal, trace_id, resume, code=code)`.

---

### `type="autocode"`

Fixes bugs, adds features, or refactors code with TDD and safety checks (git snapshots).

| Required | Optional | Description |
|----------|----------|-------------|
| `goal`, `target_file` | `mode`, `error_msg`, `feature_desc`, `files`, `git_diff`, `dry_run`, `trace_id`, `resume` | `mode` controls behaviour. `error_msg` required for `fix_error`. `feature_desc` required for `add_feature`. `files`/`git_diff`/`dry_run` are v1.0 NEW pass-through params (forwarded only when non-empty/`True`). |

**Handler:** `tools/workflow_ops/types/autocode.py` → `_type_autocode()` — fail-fast guards BEFORE git snapshots → `_execute_workflow("autocode", goal, trace_id, resume, target_file=..., mode=..., error_msg=..., feature_desc=..., files=..., git_diff=..., dry_run=...)`.

**Modes:**

| Mode | Required extra params | Behavior |
|------|----------------------|----------|
| `improve` (default) | — | Refactor + improve the target_file |
| `fix_error` | `error_msg` | Diagnose + fix the reported error |
| `add_feature` | `feature_desc` | Implement the described feature |

---

### `type="deep_research"`

Iterative, multi-faceted research for complex questions. Uses a ReAct-style loop with self-evaluation, budget tracking, and convergence detection.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `trace_id`, `resume` | Research question. The workflow decomposes, searches, and synthesizes iteratively until convergence or max iterations. |

**Handler:** `tools/workflow_ops/types/deep_research.py` → `_type_deep_research()` → `_execute_workflow("deep_research", goal, trace_id, resume)`.

---

### `type="understand"`

Builds a codebase Knowledge Graph for dependency analysis and navigation.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal`, `project_root` | `trace_id`, `resume` | `project_root` is the directory to scan. **Bug #3 fix:** `project_root` is now forwarded to `run_workflow()` (was previously validated but dropped). |

**Handler:** `tools/workflow_ops/types/understand.py` → `_type_understand()` → `_execute_workflow("understand", goal, trace_id, resume, project_root=project_root)`.

---

### `type="autoresearch"`

Autonomous experiment-driven optimization (modify → run → measure → keep/discard → repeat). Inspired by karpathy/autoresearch.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal`, `target_file` | `project_root`, `trace_id`, `resume` | `target_file` is the script the workflow will modify + run repeatedly. `project_root` is the git repo where the experiment branch is created. |

**Handler:** `tools/workflow_ops/types/autoresearch.py` → `_type_autoresearch()` → `_execute_workflow("autoresearch", goal, trace_id, resume, target_file=target_file, project_root=project_root)`.

---

### `type="auto"`

Lets the Router classify the goal and dynamically select the correct workflow.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `trace_id`, `resume`, plus any params for the routed type | The Router decides which workflow to run. If it routes to e.g. `autocode`, the autocode type handler re-validates `target_file` etc. |

**Handler:** `tools/workflow_ops/types/auto.py` → `_type_auto()` → `router.route(goal, trace_id)` → three outcomes:

| Outcome | Status | Description |
|---------|--------|-------------|
| Router returns `workflow="direct"` | `routed` | Router decides this is not a workflow task. Returns `tool` and `reason` for the LLM to use. |
| Router returns `confidence="low"` | `needs_clarification` | Goal is too vague. Returns `clarifying_questions` for the user. **Bug #6 fix:** fires EVEN IF `clarifying_questions` is empty/None (provides default question). |
| Router returns a specific type with non-low confidence | (delegated to that type) | Delegates to `TYPE_DISPATCH[routed_type]["func"]` — re-validates type-specific params. Falls back to `_execute_workflow` directly for unknown routed types. |

---

### `type="compose"` (v1.1 — `{stepN.field}` placeholders added in v1.2.1)

Chain multiple workflows sequentially — pass the output of one as the input to the next. Stops on the first step failure and preserves all completed step results in the `steps` field.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal`, `steps` | `trace_id`, `resume` | `steps` is a non-empty list of step dicts (see below). Each step has its own `type` + `goal` + type-specific kwargs. |

**Handler:** `tools/workflow_ops/types/compose.py` → `_type_compose()` → for each step calls `_execute_workflow(step_type, step_goal, trace_id, **step_kwargs)`.

**Step dict shape:**

```python
{"type": "research", "goal": "Find LLM frameworks", ...type-specific kwargs}
```

**Forwarded to each step:**
- `prev_result` — full result dict of step N-1 (only set when step N > 1).
- `step_results` — list of ALL prior step result dicts (snapshot — frozen at the moment step N is invoked).

**`{stepN.field}` + `{prev.field}` placeholders (v1.2.1):**

Step goals + string-valued step kwargs support placeholders that resolve against prior step results BEFORE the step is executed. This lets step N reference a specific field from a specific prior step (not just the whole `prev_result` dict).

| Placeholder | Resolves to |
|---|---|
| `{step1.target_file}` | `step_results[0]["target_file"]` (1-indexed: step1 = index 0) |
| `{step2.files_parsed}` | `step_results[1]["files_parsed"]` |
| `{prev.result}` | `step_results[-1]["result"]` — alias for the most recent step |

**Unresolved placeholders are left as-is.** If `{step5.target_file}` appears in a 2-step chain (step 5 doesn't exist), or the named field is missing, the original placeholder text survives so the caller sees a clear signal rather than a silent blank. Non-string kwargs (lists, ints, bools) are skipped — only string values are scanned.

**Example:**

```python
workflow(
    action="run", type="compose",
    goal="understand then fix",
    steps=[
        {"type": "understand", "goal": "Map the auth module", "project_root": "/repo"},
        {
            "type": "autocode",
            "goal": "Fix the bug in {step1.target_file}",   # resolved to step1's target_file
            "mode": "fix_error",
            "target_file": "{step1.target_file}",            # also resolved in kwargs
            "error_msg": "KeyError on login",
        },
    ],
)
```

If step 1 returns `{"status": "success", "target_file": "/repo/auth.py", ...}`, step 2 is invoked with `goal="Fix the bug in /repo/auth.py"` and `target_file="/repo/auth.py"`.

---

## 📤 Output

### Success (research / data / deep_research / understand / autoresearch)
```json
{
  "status": "success",
  "result": "Research complete: 5 sources synthesized",
  "trace_id": "abc123",
  "duration_ms": 45000
}
```

### Auto-routing — Direct
```json
{
  "status": "routed",
  "workflow": "direct",
  "tool": "web",
  "reason": "This is a simple factual query best handled by web search.",
  "trace_id": "abc123",
  "duration_ms": 1200
}
```

### Auto-routing — Needs Clarification
```json
{
  "status": "needs_clarification",
  "reason": "The task goal is too vague or ambiguous to proceed confidently.",
  "clarifying_questions": [
    "What programming language is the project using?",
    "Which specific module should I focus on?"
  ],
  "message": "To help me understand your request better, please clarify:\n- What programming language is the project using?\n- Which specific module should I focus on?",
  "trace_id": "abc123",
  "duration_ms": 980
}
```

### Validation Error — Missing `action`
```json
{
  "status": "error",
  "error": "action is required (run | list | status | cancel | history)",
  "trace_id": "abc123"
}
```

### Validation Error — Unknown `action`
```json
{
  "status": "error",
  "error": "Unknown action 'execute'. Use: cancel | history | list | run | status",
  "trace_id": "abc123"
}
```

### Validation Error — Invalid `type` for `run`
```json
{
  "status": "error",
  "error": "Invalid workflow type 'coding'. Valid: ['autocode', 'auto', 'data', 'deep_research', 'research', 'understand', 'autoresearch']",
  "trace_id": "abc123",
  "valid_types": ["autocode", "auto", "data", "deep_research", "research", "understand", "autoresearch"]
}
```

### Validation Error — Missing type-specific param
```json
{
  "status": "error",
  "error": "target_file is required for autocode workflow",
  "trace_id": "abc123",
  "workflow_type": "autocode"
}
```

### Execution Error
```json
{
  "status": "error",
  "error": "Workflow action failed: <exception>",
  "trace_id": "abc123",
  "duration_ms": 12000
}
```

---

## 🛡️ Error Handling

| Error Type | Trigger | Status | Returned Keys | Notes |
|------------|---------|--------|---------------|-------|
| Missing `action` | `action` is empty/whitespace | `error` | `error`, `trace_id` | First check in facade. |
| Unknown `action` | `action` not in `DISPATCH["workflow"]` | `error` | `error` (lists valid actions), `trace_id` | Facade case-insensitive (`action.strip().lower()`). |
| Handler exception | Action handler raises | `error` | `error` (wraps exception), `trace_id` | Caught in facade `try/except Exception`. Logs via `tracer.error()`. |
| Handler returned non-dict | Handler returned `str` / `None` / etc. | `error` | `error` (`Handler returned X, expected dict.`), `trace_id` | Defense against malformed handlers. |
| Missing `type` for `run` | `type` empty/whitespace | `error` | `error`, `trace_id`, `valid_types` | Returned by `_action_run`. |
| Invalid `type` for `run` | `type` not in `TYPE_DISPATCH` | `error` | `error`, `trace_id`, `valid_types` | Case-insensitive (`type.strip().lower()`). |
| Missing `goal` | `goal` empty/whitespace | `error` | `error`, `trace_id`, `workflow_type` | Returned by type handler. Logged via `tracer.error()`. |
| Missing type-specific param | e.g. autocode without `target_file` | `error` | `error`, `trace_id`, `workflow_type` (+ `mode` for autocode mode-specific errors) | Fail-fast BEFORE git snapshots. |
| Router exception | `router.route()` raises | `error` | `error` (`Failed to route workflow: ...`), `trace_id` | Caught in `_type_auto`. |
| Checkpoint module missing | `core.observability.checkpoint` ImportError | (success) | `checkpoint=false`, `tracer_summary=...` | `status` action returns success with `checkpoint=false`. |
| Tracer db error | `tracer.summary()` raises | (success) | `checkpoint=...`, `tracer_summary=null` | `status` action returns success with `tracer_summary=null`. |
| Autocode helpers missing | `workflows.autocode_impl.helpers` ImportError | (success) | `message` notes "no cancellation mechanism" | `cancel` action returns success — distinct from runtime failure. |

**Guaranteed keys for ALL responses:** `status`, `trace_id`. Every response also includes `duration_ms` (attached by the facade).

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **Type allowlist** | `TYPE_DISPATCH` registry prevents LLM hallucination of non-existent types. Unknown types fail fast in `_action_run` with `valid_types` in the error. |
| **Action allowlist** | `DISPATCH["workflow"]` registry + `@meta_tool`-generated `Literal[...]` enum restricts `action` to the 5 registered names. |
| **Parameter guards** | Autocode validates `target_file`, `error_msg`, `feature_desc` BEFORE any filesystem mutation (git snapshots). Validation lives in `types/autocode.py`, not the facade. |
| **Trace ID guarantee** | Every response contains `trace_id`. `_ensure_trace_id()` auto-generates one if not provided by the MCP host. Called by every type handler. |
| **Router confidence guard** | Low-confidence auto-routing aborts with clarifying questions instead of wasting 15+ minutes of execution time. Fires even if `clarifying_questions` is empty (Bug #6 fix). |
| **Lazy imports** | `core.router` imported inside `types/auto.py`'s `_type_auto()` body to prevent startup circular dependencies. |
| **Resilient to partial deployments** | `status` / `cancel` actions catch `ImportError` separately and return success with explanatory messages — a deployment without autocode installed can still call these actions. |

---

*Last updated: 2026-07-26 (v1.2.1 — cognitive framing + autoresearch added to ROUTER_WORKFLOWS + compose `{stepN.field}` placeholders + compose type section added). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
