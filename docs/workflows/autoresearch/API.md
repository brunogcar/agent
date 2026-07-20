<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 📝 API Reference

Facade signature, configuration, per-node reference, state fields. For module tree, mermaid diagram, and design decisions see [ARCHITECTURE.md](ARCHITECTURE.md). For AI-editing rules see [INSTRUCTIONS.md](INSTRUCTIONS.md).

---

## 🚀 Facade — `run_workflow("autoresearch", ...)`

The autoresearch workflow is invoked through the shared `run_workflow()` facade in `workflows/base.py`. There is no autoresearch-specific facade function — callers use `run_workflow("autoresearch", ...)` directly.

```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="autoresearch",
    goal="minimize val_bpb",            # required
    target_file="train.py",              # default: cfg.autoresearch_target_file
    project_root="/path/to/repo",        # default: cfg.workspace_root
    metric_name="val_bpb",               # forwarded (v1.3 P2-2)
    metric_direction="lower",            # forwarded (v1.3 P2-2)
    time_budget=300,                     # forwarded (v1.3 P2-2)
    branch="autoresearch/my-run",        # forwarded (v1.3 P2-2)
    results_path="/path/to/results.tsv", # forwarded (v1.3 P2-2)
    max_iterations=20,                   # [v1.4] stop after 20 experiments (0=unlimited)
    trace_id="autoresearch_001",         # auto-created if empty
)
```

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `workflow_type` | `str` | (required) | Must be `"autoresearch"`. |
| `goal` | `str` | (required) | What to optimize, e.g. `"minimize val_bpb"`. Injected verbatim into the LLM proposal prompt. |
| `target_file` | `str` | `cfg.autoresearch_target_file` (`"train.py"`) | File to modify each iteration. Must resolve INSIDE `project_root` (v1.3 P1-3) and not be on `cfg.is_protected()`. |
| `project_root` | `str` | `cfg.workspace_root` | Git repo root. Experiments run with `cwd=project_root`. Must be a git repo for `_git_reset_hard` (v1.3 P1-4). |
| `metric_name` | `str` | `cfg.autoresearch_metric_name` (`"val_bpb"`) | Metric name. `evaluate` greps for `{metric_name}: <float>` (last occurrence). |
| `metric_direction` | `str` | `cfg.autoresearch_metric_direction` (`"lower"`) | `"lower"` or `"higher"`. Used by `decide`. |
| `time_budget` | `int` | `cfg.autoresearch_time_budget` (`300`) | Per-experiment wall-clock seconds. |
| `branch` | `str` | `"autoresearch/{YYYYMMDD-HHMMSS}"` | Git branch for experiment commits. Setup creates it or reuses if it exists. |
| `results_path` | `str` | `"{project_root}/results.tsv"` | Path to the results ledger. Setup writes the header if the file doesn't exist. |
| `max_iterations` | `int` | `0` (unlimited) | **[v1.4]** Hard cap on experiments. `0` = unlimited (legacy v1.3 behavior). Also settable via `AUTORESEARCH_MAX_ITERATIONS` env var. |
| `trace_id` | `str` | (auto-created) | Trace correlation ID. |

**Dispatcher behavior:** Initializes state via `_default_state()`, merges in caller kwargs (caller wins), invokes the graph with `config={"recursion_limit": 1000}`. **[v1.3 P0-2]** `GraphRecursionError` is caught explicitly and returned as `{"status": "success"}` (was: caught by generic `except Exception` → `status="failed"`, state lost). **[v1.4]** If `max_iterations > 0`, the loop stops at N experiments via `route_after_log` (before recursion_limit is hit).

**Graph order:** `setup → propose → modify → run_experiment → evaluate → decide → log → reflect → propose (loop)` (v1.5 N1 added `reflect`; v1.3 P0-1 set `evaluate → decide → log`; v1.4 made the back-edge conditional). The `reflect → propose` back-edge is **conditional** (v1.4 — was a direct edge in v1.3): `route_after_log` checks `max_iterations` + convergence + stuck before looping. `node_reflect` (v1.5 N1) sits between `log` and `route_after_log` — it's a no-op most iterations but every `autoresearch_reflect_interval` (default 5; 0=disabled) it calls the planner LLM to refresh `state["reflect_notes"]`. All 3 stopping conditions default OFF → v1.4 preserves v1.3 "loop forever" behavior unless caller opts in. See [ARCHITECTURE.md](ARCHITECTURE.md) for the mermaid diagram + module tree.

---

## ⚙️ Configuration

| Knob (.env) | `cfg` attribute | Default | Purpose |
|-------------|-----------------|---------|---------|
| `AUTORESEARCH_TIME_BUDGET` | `cfg.autoresearch_time_budget` | `300` | Per-experiment wall-clock seconds |
| `AUTORESEARCH_TARGET_FILE` | `cfg.autoresearch_target_file` | `"train.py"` | File to modify each iteration |
| `AUTORESEARCH_METRIC_NAME` | `cfg.autoresearch_metric_name` | `"val_bpb"` | Metric name to extract |
| `AUTORESEARCH_METRIC_DIRECTION` | `cfg.autoresearch_metric_direction` | `"lower"` | `"lower"` or `"higher"` |
| `AUTORESEARCH_MAX_ITERATIONS` | `cfg.autoresearch_max_iterations` | `0` | **[v1.4]** Hard cap on experiments (0=unlimited) |
| `AUTORESEARCH_CONVERGENCE_WINDOW` | `cfg.autoresearch_convergence_window` | `10` | **[v1.4]** Stop after N consecutive non-improvements |
| `AUTORESEARCH_CONVERGENCE_EPSILON` | `cfg.autoresearch_convergence_epsilon` | `0.001` | **[v1.4]** Metric plateau threshold (stuck detector) |
| `AUTORESEARCH_REFLECT_INTERVAL` | `cfg.autoresearch_reflect_interval` | `5` | **[v1.5 N1]** Reflect every N iterations (0=disabled, legacy v1.4 behavior) |

Also uses `cfg.autocode_max_file_chars` (default 6000) to cap target file content in the proposal prompt (v1.3 P1-5) and `cfg.is_protected(path)` to block writes to `.env`, `pyproject.toml`, agent source, etc. (v1.3 P1-3).

---

## 📤 Output

The workflow returns a `dict` (the final LangGraph state). The dispatcher wraps the graph result with `trace_id` + `status` + `error` normalization.

**Normal exit (recursion limit hit — the EXPECTED exit, v1.3 P0-2):**

```json
{
  "status": "success",
  "result": "Recursion limit reached — check results.tsv for experiment count and best metric",
  "trace_id": "autoresearch_001",
  "experiment_count": 0,
  "current_best": 0.0
}
```

> **Note:** `experiment_count` and `current_best` in the recursion-limit response come from `ar_state` (initial state), NOT from the final graph state — `GraphRecursionError` is raised BEFORE `graph.invoke()` returns, so accumulated state is trapped inside the graph. Operators should inspect `results.tsv` for the actual count + best metric.

**Setup failure (baseline metric not found):**

```json
{
  "status": "failed",
  "error": "baseline metric 'val_bpb' not found in target_file output",
  "result": "",
  "artifacts": [],
  "trace_id": "autoresearch_001"
}
```

The return dict contains the same fields as `AutoresearchState` (see [State Fields](#-state-fields-autoresearchstate) below). The dispatcher always guarantees `trace_id`, `status`, `result`, `error`, `artifacts`.

---

## 🗂️ State Fields (AutoresearchState)

The state is a `TypedDict(total=False)` defined in `workflows/autoresearch_impl/state.py` — extends `WorkflowState`. See [ARCHITECTURE.md](ARCHITECTURE.md#-state-typeddict) for the TypedDict definition + field groups.

| Field | Type | Default | Purpose / source |
|-------|------|---------|-------------------|
| `workflow` | `str` | `"autoresearch"` | Workflow name (set once). |
| `goal` | `str` | `""` | What to optimize. Read by `node_propose`. |
| `trace_id` | `str` | `""` | Trace correlation ID. |
| `project_root` | `str` | `cfg.workspace_root` | Git repo root (`cwd` for experiments). |
| `target_file` | `str` | `cfg.autoresearch_target_file` | File to modify each iteration. |
| `metric_name` | `str` | `cfg.autoresearch_metric_name` | Metric to extract from output. |
| `metric_direction` | `str` | `cfg.autoresearch_metric_direction` | `"lower"` or `"higher"`. |
| `time_budget` | `int` | `cfg.autoresearch_time_budget` | Per-experiment seconds. |
| `branch` | `str` | `"autoresearch/{YYYYMMDD-HHMMSS}"` | Git branch (set by `node_setup`). |
| `results_path` | `str` | `"{project_root}/results.tsv"` | Path to the TSV ledger (set by `node_setup`). |
| `experiment_count` | `int` | `0` | Total experiments completed (incremented by `node_log`). |
| `baseline_metric` | `float` | `0.0` | Metric from unmodified target_file (set by `node_setup`). |
| `current_best` | `float` | `0.0` | Best metric so far. Updated only on keep (`node_decide`). |
| `max_iterations` | `int` | `0` | **[v1.4]** Hard cap on experiments. `0` = unlimited (legacy v1.3 behavior). Also settable via `AUTORESEARCH_MAX_ITERATIONS` env var. |
| `convergence_window` | `int` | `10` | **[v1.4]** Stop after N consecutive non-improvements (last N all discarded OR last N within ε of best). |
| `convergence_epsilon` | `float` | `0.001` | **[v1.4]** Metric plateau threshold (stuck detector). |
| `reflect_notes` | `str` | `""` | **[v1.5 N1]** LLM strategy reflection (updated every `autoresearch_reflect_interval` iterations by `node_reflect`; surfaced to the next `node_propose` prompt). |
| `experiment_history` | `list[dict]` | `[]` | All experiments (capped at 100, v1.3 P2-3). Read by `node_propose` (last 20) + `node_modify` (dedup, v1.4 N8). Each entry: `{iteration, description, metric, status, commit, content_hash}`. |
| `current_experiment` | `dict` | `{}` | The proposal being processed. Annotated by `decide`, cleared by `log`. |
| `experiment_output` | `str` | `""` | Combined stdout+stderr (truncated to 50KB). Set by `node_setup` + `node_run_experiment`. |
| `current_metric` | `float` | `0.0` | Metric from last experiment. Set by `node_setup` + `node_evaluate`. |
| `status` | `str` | `"running"` | `"running"` / `"success"` / `"failed"`. **[v1.3 P0-1]** Reset by `node_decide` (was: `node_log`). |
| `error` | `str` | `""` | Error message on failure. Cleared by `node_decide` (v1.3 P0-1). |
| `result` | `str` | `""` | Final summary (set by dispatcher on recursion-limit exit). |
| `artifacts` | `list[str]` | `[]` | Ledger path (set by dispatcher). |

---

## ⚡ Per-Node Reference

Nodes in graph-execution order: `setup → propose → modify → run_experiment → evaluate → decide → log → reflect → propose (loop)`. Each node returns a partial state dict (LangGraph pattern — only changed keys). For full logic, read the source file.

| # | Node | Source | Purpose / key behavior |
|---|------|--------|------------------------|
| 1 | `node_setup` | `nodes/setup.py` | Create branch `autoresearch/{tag}` via `git(action="checkout_new")` (fallback `checkout_branch` if exists; non-fatal). Compute `results_path`; write TSV header IF file doesn't exist (resume). Run baseline via `helpers.run_target_subprocess` (v1.3 P2-1). Extract baseline metric via `helpers.extract_metric`; if missing → `status="failed"`. **Returns:** `branch`, `results_path`, `baseline_metric`, `current_best=baseline_metric`, `experiment_output`, `current_metric=baseline_metric`, `status`. |
| 2 | `node_propose` | `nodes/propose.py` | Compute `iteration = experiment_count + 1`. Read `target_file`; **[v1.3 P1-5]** truncate to first+last half with `[TRUNCATED]` marker if `len > cfg.autocode_max_file_chars` (6000). Format `experiment_history` (most-recent-first, capped 20). **[v1.5 N4]** Lazy-recall procedural memories via `memory.recall(collections=["procedural"], top_k=3, min_score=0.3)`; non-fatal try/except. **[v1.5 N1]** If `state["reflect_notes"]` non-empty, append a `Strategist reflection` block to the prompt. Call `_call_planner` via `agent(action="subagent", role="planner")` with 3× retry + 2s/4s backoff (v1.3 P1-2). Parse via `core.json_extract.extract_json()` (falls back to `"(unparseable proposal)"` + empty `new_content`). **[v1.1+]** Subagent dispatch (NOT `_call()`); no `_call()` fallback. **Returns:** `current_experiment = {iteration, description, rationale, new_content}`, `status`. |
| 3 | `node_modify` | `nodes/modify.py` | Read `new_content = current_experiment["new_content"]`. **[v1.4 N8]** md5-hash `new_content`; if hash matches any prior `experiment_history.content_hash`, return `status="failed"` with a "duplicate" error (no write). Store hash on `current_experiment.content_hash` for `node_log` to persist. If empty → `status="failed"`. Compute `target_path`. **[v1.3 P1-3]** Path traversal guard via `relative_to(project_root.resolve())`. **[v1.3 P1-3]** Protected-file check via `cfg.is_protected(target_path)`. Otherwise `_atomic_write`: `tempfile.mkstemp(dir=parent)` + `os.fsync` + `os.replace` (tempfile `os.unlink`'d on failure). **Returns:** `status` + `error`. |
| 4 | `node_run_experiment` | `nodes/run_experiment.py` | If `status=="failed"`: skip run, return existing `experiment_output` (decide discards). Build `cmd = [sys.executable, target_file]`. **[v1.3 P2-1]** Call `helpers.run_target_subprocess(target_file, project_root, time_budget)`. On `TimeoutExpired`: return partial output + sentinel. On `FileNotFoundError`: return sentinel. Truncate to last 50KB if larger. **Returns:** `experiment_output`, `status="running"`, `error=""`. |
| 5 | `node_evaluate` | `nodes/evaluate.py` | If `status=="failed"`: propagate (return `current_metric=0.0`; decide discards). Use `helpers.extract_metric(output, metric_name)` (shared regex, v1.2.1) — escapes metric name, accepts `:` or `=` separator, takes `matches[-1]` (last occurrence). If no match: `current_metric=0.0` + `status="failed"` + `error="metric '{metric_name}' not found ..."`. **Returns:** `current_metric`, `status`. |
| 6 | `node_decide` | `nodes/decide.py` | **[v1.3 P0-1]** Runs BEFORE `node_log`. Annotates `current_experiment` with `status` + `commit` + `metric`. Takes over `status="running"` + `error=""` reset (was `log`'s job). If `status=="failed"`: always discard. `_is_improvement` — `"lower"` → `new < best`; `"higher"` → `new > best`; equality NOT improvement. If NOT improved: `_git_reset_hard` (`git reset --hard HEAD` + `git clean -fd`); annotate `status="discard"`. **[v1.5 N4]** Call `_record_failure_memory(...)` on both discard paths (prior-failure + no-improvement) — lazily imports `core.memory_engine.memory`, checks for an existing similar failure (min_score=0.7) — if hit, traces "repeated failure pattern detected"; else calls `memory.store_procedural(importance=5, tags="source:autoresearch,category:failed_experiment", outcome="failure")`. Non-fatal (try/except). If improved: `_git_commit` (`git add <target_file>` + `git commit -m` + `git rev-parse --short HEAD`). **[v1.3 P1-1]** Empty SHA → discard (don't update `current_best`). Otherwise annotate `status="keep"`, `commit=sha`, update `current_best`. **Returns:** `current_experiment` (annotated), `current_best`, `status="running"`, `error=""`. |
| 7 | `node_log` | `nodes/log.py` | **[v1.3 P0-1]** Runs AFTER `decide`. Reads the ANNOTATED `current_experiment`. Sanitize `description` (collapse whitespace). Append `f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\n"` via `_append_to_ledger` (non-fatal). Append `{iteration, description, metric, status, commit, content_hash}` to `experiment_history` (copy the list, don't mutate). **[v1.4 N8]** `content_hash` added (md5 of `new_content`, set by `node_modify`) for dedup. **[v1.3 P2-3]** Cap `experiment_history` at 100. Increment `experiment_count`. Clear `current_experiment`. No longer returns `status`/`error` — `decide` does the reset. **Returns:** `experiment_history`, `experiment_count`, `current_experiment={}`. |
| 8 | `node_reflect` | `nodes/reflect.py` | **[v1.5 N1]** No-op most iterations (returns `{}`). Every `autoresearch_reflect_interval` iterations (default 5; `0=disabled`), calls `_call_planner(REFLECT_SYSTEM, user, tid)` (reuses the same subagent dispatch + 3× retry as `node_propose`) with the full experiment history (capped at 100 entries). Stores the reflection in `state["reflect_notes"]` (overwrites any prior reflection). The next `node_propose` surfaces the reflection in its prompt (when non-empty) so the LLM has strategic context. Failures non-fatal — returns `{}` on LLM error so the loop continues with whatever reflection was previously stored. **Returns:** `{"reflect_notes": reflection}` on reflect iterations, `{}` otherwise. |

---

## 🔀 Routes

`workflows/autoresearch_impl/routes.py` defines **2 routing functions** (v1.4: was 1 in v1.3 — `route_after_log` added). Both are conditional — the experiment loop now has an OPT-IN auto-stop (default OFF → v1.3 "loop forever" behavior preserved).

### `route_after_setup(state) -> str`

**Returns:** `"propose"` on success, `"end"` on failure. **Rationale:** v1.2.1 (P1-1) — if setup fails (baseline metric not extracted), the workflow used to spin infinitely. Now routes to END.

### `route_after_log(state) -> str` — **[v1.4]**

**Returns:** `"propose"` to continue the loop, `"end"` to stop. **Rationale:** v1.4 replaces the v1.3 direct `log → propose` edge with a conditional edge that checks 3 stopping conditions in order. **[v1.5 N1]** The conditional edge is now wired from `reflect` (was `log`) — `log → reflect → route_after_log → propose` is the new loop tail. `node_reflect` is a no-op most iterations, so the v1.4 stopping semantics are unchanged.

| # | Condition | Default | Trigger |
|---|-----------|---------|---------|
| 1 | `max_iterations` reached | `0` (unlimited) | `max_iter > 0 and experiment_count >= max_iter` |
| 2 | Convergence: last N all discarded | N=`10` | `len(history) >= window and all(h.status == "discard" for h in recent)` |
| 3 | Stuck: last N within ε of best | N=`10`, ε=`0.001` | `len(history) >= window and all(abs(h.metric - current_best) < ε for h in recent)` |

All 3 default OFF → v1.4 preserves v1.3 "loop forever" behavior unless caller opts in via `max_iterations=N` or env vars. Each condition 2/3 requires `len(history) >= window` so the first few iterations never false-positive.

### [v1.3 P2-5] DELETED: `route_after_evaluate` + `route_after_decide`

Both were unconditional single-destination "fake" conditionals (always returned the same value). Replaced with direct `add_edge` calls in `graph.py`: `evaluate → decide` (was: `evaluate → log`); `decide → log` (was: `log → decide`). The graph order changed from `evaluate → log → decide` to `evaluate → decide → log` (v1.3 P0-1).

---

## 📝 Error Handling (summary)

The loop is **fail-soft by design**: every per-node failure (except baseline-metric-missing) sets `status="failed"` and propagates through `run_experiment → evaluate → decide` (discards via `_git_reset_hard`) → `log` (records the attempt as `discard`). The loop continues — only the failed iteration is lost. Critical cases:

- **Baseline metric not found** (`node_setup`): **FATAL** — `status="failed"`. Operator must fix `target_file`. `route_after_setup` routes to END.
- **LLM call fails** (`node_propose._call_planner`): **[v1.3 P1-2]** Retries 3× with 2s/4s backoff. After all 3 fail, raises `RuntimeError`; `node_propose` returns `status="failed"`. `node_decide` discards.
- **Empty SHA** (`node_decide._git_commit` returns `""`): **[v1.3 P1-1]** Treated as DISCARD — runs `_git_reset_hard`, sets `status="discard"`, does NOT update `current_best`.
- **Path traversal / protected file** (`node_modify`): **[v1.3 P1-3]** Returns `status="failed"`. `node_decide` discards.
- **Duplicate `new_content`** (`node_modify`): **[v1.4 N8]** md5 hash matches a prior `experiment_history` entry → returns `status="failed"` with a "duplicate" error. `node_decide` discards. Prevents re-running the same experiment.
- **[v1.5 N1] Reflect LLM call fails** (`node_reflect._call_planner`): **Non-fatal.** `node_reflect` catches the exception, traces a warning, and returns `{}` — the loop continues with whatever reflection was previously stored (or no reflection at all on the first failed attempt). The `autoresearch_reflect_interval=0` env var disables reflection entirely.
- **[v1.5 N4] Cross-run learning unavailable** (`node_decide._record_failure_memory` / `node_propose` memory recall): **Non-fatal.** If `core.memory_engine.memory` is unavailable (e.g. chromadb not installed) or any memory call raises, the `try/except Exception: pass` swallows it and the loop continues without cross-run learning. Operators without chromadb see no behavior change.
- **`_git_reset_hard` with no `project_root` or non-repo**: **[v1.3 P1-4]** `tracer.warning`, returns `False`, skips reset. Prevents resetting the agent's own working tree.
- **`GraphRecursionError`** (dispatcher): **[v1.3 P0-2]** **EXPECTED exit.** Caught explicitly and returned as `{"status": "success", "result": "Recursion limit reached — ..."}`. **[v1.4]** `route_after_log` may terminate the loop BEFORE recursion_limit is hit if a stopping condition is met.
- **Non-fatal failures** (branch creation, ledger init/append, git reset failure): `tracer.warning` and continue — in-memory `experiment_history` is the LLM's source of truth; `results.tsv` is the human audit trail (best-effort).

For AI-editing rules around these failure modes, see [INSTRUCTIONS.md](INSTRUCTIONS.md).

---

*Last updated: 2026-07-21 (v1.5). See [CHANGELOG.md](CHANGELOG.md) for version history.*
