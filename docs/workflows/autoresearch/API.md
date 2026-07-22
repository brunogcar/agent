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
    parallel_count=4,                   # [v1.6] run 4 experiments in parallel per iteration (1 = v1.5 single mode)
    resume=True,                         # [v1.7 N3] restore from checkpoint (skip baseline + branch, reload history)
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
| `parallel_count` | `int` | `1` | **[v1.6]** N parallel experiments per iteration. `1` = v1.5 single-experiment mode (default). `>1` activates the parallel path: N LLM proposals via ThreadPoolExecutor, N temp files, N subprocesses, pick-best, N ledger rows. Also settable via `AUTORESEARCH_PARALLEL_COUNT` env var. |
| `resume` | `bool` | `False` | **[v1.7 N3]** Restore from the `core.observability.checkpoint` journal (`get_latest(trace_id)`). When a checkpoint exists, the dispatcher merges in `experiment_count` / `current_best` / `baseline_metric` / `experiment_history` / `branch` / `results_path` / `reflect_notes` and sets `ar_state["resume"] = True`. `node_setup` then skips branch creation (when `branch` is non-empty) AND skips the baseline run (when `current_best > 0.0`), and reloads `experiment_history` from `results.tsv` via `_load_history_from_ledger`. Checkpoints are written by `node_decide` after every successful `_git_commit` (v1.7 N7). When `False` (default), behavior is exactly v1.6. |
| `trace_id` | `str` | (auto-created) | Trace correlation ID. |

**Dispatcher behavior:** Initializes state via `_default_state()`, merges in caller kwargs (caller wins), invokes the graph with `config={"recursion_limit": 1000}`. **[v1.3 P0-2]** `GraphRecursionError` is caught explicitly and returned as `{"status": "success"}` (was: caught by generic `except Exception` → `status="failed"`, state lost). **[v1.4]** If `max_iterations > 0`, the loop stops at N experiments via `route_after_log` (before recursion_limit is hit). **[v1.6]** If `parallel_count > 1`, each iteration produces N experiments (N ledger rows per iteration; `experiment_count` increments by N). **[v1.7 N3]** If `resume=True`, the dispatcher calls `get_latest(trace_id)` AFTER `_ar_default(...)`; if a checkpoint exists, it merges in autoresearch-specific fields and sets `ar_state["resume"] = True` so `node_setup` activates its resume path (skip baseline + branch creation, reload history from `results.tsv`).

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
| `AUTORESEARCH_PARALLEL_COUNT` | `cfg.autoresearch_parallel_count` | `1` | **[v1.6]** N parallel experiments per iteration (1 = v1.5 single-experiment mode) |
| `AUTORESEARCH_RECURSION_LIMIT` | `cfg.autoresearch_recursion_limit` | `1000` | **[v1.9 D3]** LangGraph `recursion_limit` for the autoresearch loop (was: hardcoded 1000). Raise for very long overnight runs (each iteration = 8 nodes; 1000 → ~125 iterations). |
| `AUTORESEARCH_LOG_DIR_MAX_MB` | `cfg.autoresearch_log_dir_max_mb` | `1024` | **[v1.9 D2]** Cap on `.autoresearch/logs/` size in MB. When exceeded, new log writes are SKIPPED + a tracer warning is emitted. 0 = no cap. |

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
| `parallel_count` | `int` | `1` | **[v1.6]** N parallel experiments per iteration. `1` = v1.5 single-experiment mode (default). When `> 1`, all nodes use the plural fields below. |
| `current_experiments` | `list[dict]` | `[]` | **[v1.6]** N proposals being evaluated (parallel mode only). Set by `node_propose`; cleared by `node_log`. |
| `experiment_outputs` | `list[str]` | `[]` | **[v1.6]** N outputs from N subprocesses (parallel mode only). Set by `node_run_experiment`. |
| `current_metrics` | `list[float]` | `[]` | **[v1.6]** N metrics from N evaluations (parallel mode only). Set by `node_evaluate`. |
| `resume` | `bool` | `False` | **[v1.7 N3]** Set to `True` by the dispatcher's autoresearch branch when `run_workflow(resume=True)` is called AND a checkpoint exists (via `get_latest(trace_id)`). When `True` AND `state["branch"]` is non-empty: `node_setup` skips branch creation. When ALSO `state["current_best"] > 0.0`: `node_setup` skips the baseline run AND reloads `experiment_history` from `results.tsv` via `_load_history_from_ledger`. When `False` (default), `node_setup` behaves exactly as v1.6 (new branch, run baseline, fresh ledger). |
| `experiment_history` | `list[dict]` | `[]` | All experiments (capped at 100, v1.3 P2-3). Read by `node_propose` (last 20) + `node_modify` (dedup, v1.4 N8). Each entry: `{iteration, description, metric, status, commit, content_hash, tokens}`. **[v1.8 N6]** `tokens` added — total LLM tokens used by the planner call (sum across entries to estimate LLM cost per run). |
| `current_experiment` | `dict` | `{}` | The proposal being processed. Annotated by `decide`, cleared by `log`. **[v1.8 N6]** Includes `tokens` (total LLM tokens used) set by `node_propose` from the subagent's `usage` dict. |
| `experiment_output` | `str` | `""` | Combined stdout+stderr (truncated to 50KB). Set by `node_setup` + `node_run_experiment`. **[v1.8 N5]** The FULL (untruncated) output is also written to `.autoresearch/logs/{iteration}.log` by `node_run_experiment` for operator debugging. |
| `pre_extracted_metric` | `Optional[float]` | `None` | **[v1.8 N10]** Metric extracted from the FULL output BEFORE truncation to 50KB. Set by `node_run_experiment` (single path). `node_evaluate` reads this FIRST and skips re-extracting from the (possibly truncated) `experiment_output` — prevents false negatives when the metric was printed early and pushed out of the 50KB tail. `None` when no metric in full output (evaluate falls back to extracting from output). Parallel mode does NOT populate this field (explicitly cleared to `None`). |
| `iteration_count` | `int` | `0` | **[v1.9 D5]** Increments by 1 PER ITERATION in `node_log` (NOT by N — counts iterations, not experiments). `node_reflect` fires on `iteration_count % interval == 0` (was: `experiment_count` — with `parallel_count=4` and `interval=5`, `experiment_count` jumped 4→8→12→16→20 and never hit a multiple of 5 → reflect NEVER fired pre-v1.9). |
| `seen_hashes` | `list[str]` | `[]` | **[v1.9 C4]** Deduped list of md5 `content_hash` strings (capped at 1000). Used by `node_modify` to detect duplicates that were evicted from the 100-entry `experiment_history` cap. Populated from the reloaded ledger on resume. |
| `consecutive_discards` | `int` | `0` | **[v1.9 B1]** Count of trailing `experiment_history` entries with `status="discard"`. Recomputed on resume by scanning the reloaded history tail (was: reset to 0 — convergence detector wouldn't fire until N MORE discards happened). |
| `consecutive_no_improvement` | `int` | `0` | **[v1.9 B1]** Count of trailing history entries whose `metric` is NOT strictly better than `current_best` per direction. Recomputed on resume alongside `consecutive_discards`. |
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
| 1 | `node_setup` | `nodes/setup.py` | Create branch `autoresearch/{tag}` via `git(action="checkout_new")` (fallback `checkout_branch` if exists; non-fatal). Compute `results_path`; write TSV header IF file doesn't exist (resume). **[v1.9 A2]** TSV header is now 6-col (`iteration\tcommit\tmetric\tstatus\tdescription\tcontent_hash`). Run baseline via `helpers.run_target_subprocess` (v1.3 P2-1). Extract baseline metric via `helpers.extract_metric`; if missing → `status="failed"`. **[v1.9 B2]** Cleans up stale `{project_root}/.autoresearch/parallel/` dir from prior crashed runs BEFORE creating a new branch. **[v1.7 N3]** When `state["resume"]=True` AND `state["branch"]` non-empty: skip branch creation. When ALSO `state["current_best"] > 0.0`: skip the baseline run, reload `experiment_history` from `results.tsv` via `_load_history_from_ledger` (now parses 6 cols; corrupt rows log a `tracer.warning`), set `experiment_count = len(history)`, **[v1.9 B1]** recompute `consecutive_discards` + `consecutive_no_improvement` from the reloaded history tail, **[v1.9 C4]** populate `seen_hashes` from the reloaded history's `content_hash` values, return early with the prior `current_best` + `baseline_metric` preserved. **Returns:** `branch`, `results_path`, `baseline_metric`, `current_best=baseline_metric`, `experiment_output`, `current_metric=baseline_metric`, `status` (fresh-run path) OR `branch`, `results_path`, `experiment_count`, `baseline_metric`, `current_best`, `experiment_history`, `consecutive_discards`, `consecutive_no_improvement`, `seen_hashes`, `status` (resume path). |
| 2 | `node_propose` | `nodes/propose.py` | Compute `iteration = experiment_count + 1`. Read `target_file`; **[v1.3 P1-5]** truncate to first+last half with `[TRUNCATED]` marker if `len > cfg.autocode_max_file_chars` (6000). Format `experiment_history` (most-recent-first, capped 20). **[v1.5 N4 / v1.9 D6]** Lazy-recall procedural memories via `memory.recall(collections=["procedural"], top_k=3, min_score=0.3, tags_filter="source:autoresearch")` — the tag filter ensures only autoresearch-stored memories are surfaced (falls back to no filter on TypeError if the API doesn't accept it). **[v1.5 N1]** If `state["reflect_notes"]` non-empty, append a `Strategist reflection` block to the prompt. Call `_call_planner` via `agent(action="subagent", role="planner")` with 3× retry + 2s/4s backoff (v1.3 P1-2). **[v1.9 B4]** `_call_planner` catches only `(RuntimeError, ConnectionError, TimeoutError, OSError, ValueError)` — KeyboardInterrupt/SystemExit/ImportError/AttributeError propagate immediately. **[v1.8 N6]** `_call_planner` returns `(response, usage)` tuple; captures `usage.get("total", 0)` on the proposal as `tokens`. **[v1.6]** When `parallel_count > 1`: dispatches N `_call_planner` calls via `ThreadPoolExecutor(max_workers=N)`. **[v1.9 C6]** Each call sleeps `i*0.5s` (capped at 2.0s) before submitting — avoids thundering-herd 429s. **[v1.9 D4]** Each call gets a distinct `variant_seed=str(i)` directive appended to the prompt — guarantees diversity even at `temperature=0`. Per-call failures recorded as failed-proposal placeholders. Returns `current_experiments` (N proposals, each with `tokens`) + mirrors the first to `current_experiment`. **Returns:** `current_experiment = {iteration, description, rationale, new_content, tokens}`, `status` (single mode) OR `current_experiments`, `current_experiment`, `status` (parallel mode). |
| 3 | `node_modify` | `nodes/modify.py` | Read `new_content = current_experiment["new_content"]`. **[v1.4 N8 / v1.9 C4]** md5-hash `new_content`; if hash matches any prior `experiment_history.content_hash` OR is in `state["seen_hashes"]` (a 1000-entry list that survives the 100-entry history cap), return `status="failed"` with a "duplicate" error (no write). Store hash on `current_experiment.content_hash` for `node_log` to persist. If empty → `status="failed"`. Compute `target_path`. **[v1.3 P1-3]** Path traversal guard via `relative_to(project_root.resolve())`. **[v1.3 P1-3]** Protected-file check via `cfg.is_protected(target_path)`. Otherwise `_atomic_write`: `tempfile.mkstemp(dir=parent)` + `os.fsync` + `os.replace` (tempfile `os.unlink`'d on failure). **[v1.6]** When `parallel_count > 1`: writes each proposal to `{project_root}/.autoresearch/parallel/{i}/{target_file}` (NOT the real `target_file`). Per-proposal failures (empty content, dedup, path, protected) set `proposal["status"]="failed"` with an `error` reason. The real `target_file` is only touched by `node_decide` (which copies the winner back). **Returns:** `status` + `error` (single mode) OR `current_experiments` + `current_experiment` + `status` (parallel mode). |
| 4 | `node_run_experiment` | `nodes/run_experiment.py` | If `status=="failed"`: skip run, return existing `experiment_output` (decide discards). Build `cmd = [sys.executable, target_file]`. **[v1.3 P2-1]** Call `helpers.run_target_subprocess(target_file, project_root, time_budget)`. On `TimeoutExpired`: return partial output + sentinel. On `FileNotFoundError`: return sentinel. **[v1.8 N5 / v1.9 D1]** Write the FULL output to `.autoresearch/logs/{iteration}.log` (single) or `{iteration}_{i}.log` (parallel) BEFORE truncation — operators can inspect the full output for debugging. **[v1.9 D1]** Log dir relocated from `{results_path}.d/` to `.autoresearch/logs/` (user request: "we use logs/ if needed, create subfolder there more descriptive than .d/"). **[v1.9 D2]** Before writing, check the total size of `.autoresearch/logs/`; if it exceeds `cfg.autoresearch_log_dir_max_mb` (default 1024 = 1GB), SKIP the write + trace a warning. Non-fatal (disk errors swallowed). **[v1.8 N10]** Single path: extract metric from FULL output BEFORE truncating to 50KB, store in `pre_extracted_metric`. Truncate to last 50KB if larger. **[v1.6]** When `parallel_count > 1`: runs N subprocesses concurrently via `ThreadPoolExecutor(max_workers=N)` — each in its own temp dir under `.autoresearch/parallel/{i}/` as cwd. Missing temp files (modify marked failed) produce a `"skipped"` sentinel. Per-experiment subprocess crashes are isolated — the batch is never aborted by one bad subprocess. Returns `experiment_outputs` (N outputs) + mirrors the first to `experiment_output` + explicitly clears `pre_extracted_metric=None`. **Returns:** `experiment_output`, `pre_extracted_metric`, `status="running"`, `error=""` (single mode) OR `experiment_outputs`, `experiment_output`, `pre_extracted_metric=None`, `status` (parallel mode). |
| 5 | `node_evaluate` | `nodes/evaluate.py` | If `status=="failed"`: propagate (return `current_metric=0.0`; decide discards). **[v1.8 N10]** Single path: check `state["pre_extracted_metric"]` FIRST — when set (not None), trust it and skip re-extracting from the (possibly truncated) `experiment_output`. When None, fall through to extraction-from-output. Use `helpers.extract_metric(output, metric_name)` (shared regex, v1.2.1) — escapes metric name, accepts `:` or `=` separator, takes `matches[-1]` (last occurrence). If no match: `current_metric=0.0` + `status="failed"` + `error="metric '{metric_name}' not found ..."`. **[v1.6]** When `parallel_count > 1`: extracts N metrics from N outputs in `experiment_outputs` (does NOT read `pre_extracted_metric` — parallel run_experiment doesn't populate it). Outputs that yield no metric get `0.0` for that slot (the downstream `node_decide` skips experiments whose proposal was marked `status="failed"` by modify). Returns `current_metrics` (N metrics) + mirrors the first to `current_metric` (v1.5 backward compat). **Returns:** `current_metric`, `status` (single mode) OR `current_metrics`, `current_metric`, `status` (parallel mode). |
| 6 | `node_decide` | `nodes/decide.py` | **[v1.3 P0-1]** Runs BEFORE `node_log`. Annotates `current_experiment` with `status` + `commit` + `metric`. Takes over `status="running"` + `error=""` reset. If `status=="failed"`: always discard. `_is_improvement` — `"lower"` → `new < best`; `"higher"` → `new > best`; equality NOT improvement. **[v1.9 E1]** Explicit NaN handling: `new != new` (canonical NaN self-test) → returns False. If NOT improved: `_git_reset_hard` (`git reset --hard HEAD` + `git clean -fd`); annotate `status="discard"`. **[v1.9 B3]** `_git_reset_hard` now verifies `git rev-parse --show-toplevel` matches `Path(project_root).resolve()` before resetting — prevents nuking a different repo when `project_root` is a junction/symlink. **[v1.5 N4]** Call `_record_failure_memory(...)` on both discard paths. If improved: `_git_commit`. **[v1.3 P1-1]** Empty SHA → discard. Otherwise annotate `status="keep"`, update `current_best`. **[v1.7 N7]** `save_checkpoint(tid, "keep", state)` after successful commit (non-fatal). **[v1.6]** When `parallel_count > 1`: picks the BEST of N experiments. **[v1.9 A3]** Copies the winner's temp-file content to the REAL `target_file` via `_atomic_write` (was: non-atomic `write_text`). **[v1.9 A1]** `_record_failure_memory(...)` is gated on `not _is_improvement(metrics[i], current_best, direction)` — a loser that DID improve over the OUTER `current_best` (but lost to the winner) is NOT recorded as a failure (was: every loser got the call → procedural memory poisoned with false failures). Cleans up the temp dir on EVERY exit path. `save_checkpoint` only when the winner was actually committed. If no experiment improves, all N are discarded and `current_best` is unchanged. **Returns:** `current_experiment` (annotated), `current_best`, `status="running"`, `error=""` (single mode) OR `current_experiments`, `current_experiment`, `current_best`, `status` (parallel mode). |
| 7 | `node_log` | `nodes/log.py` | **[v1.3 P0-1]** Runs AFTER `decide`. Reads the ANNOTATED `current_experiment`. Sanitize `description` + `content_hash` (collapse whitespace). **[v1.9 A2]** Append `f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\t{safe_hash}\n"` (6-col TSV with content_hash — was: 5-col, hash lived only in-memory). **[v1.9 C1]** `_append_to_ledger` now does `f.flush()` + `os.fsync(f.fileno())` before close (crash-safety); the parallel path batches all N rows into a SINGLE `open("a")` call (was: N separate calls — atomic on POSIX for writes < PIPE_BUF=4096). Append `{iteration, description, metric, status, commit, content_hash, tokens}` to `experiment_history`. **[v1.4 N8]** `content_hash` added for dedup. **[v1.8 N6]** `tokens` added. **[v1.3 P2-3]** Cap `experiment_history` at 100. **[v1.9 C4]** Append `content_hash` to `state["seen_hashes"]` (deduped, capped at 1000) — survives the 100-entry history cap. **[v1.9 D5]** Increment `iteration_count` by 1 per iteration (NOT by N — counts iterations, not experiments). Increment `experiment_count` by 1 (single) or N (parallel). Clear `current_experiment`. **[v1.6]** When `parallel_count > 1`: loops through `current_experiments`, appends N rows in a single batched write, N entries to history, increments `experiment_count` by N + `iteration_count` by 1. Clears both `current_experiments` and `current_experiment`. **Returns:** `experiment_history`, `experiment_count`, `iteration_count`, `seen_hashes`, `current_experiment={}` (single mode) OR `experiment_history`, `experiment_count`, `iteration_count`, `seen_hashes`, `current_experiments=[]`, `current_experiment={}` (parallel mode). |
| 8 | `node_reflect` | `nodes/reflect.py` | **[v1.5 N1]** No-op most iterations (returns `{}`). **[v1.9 D5]** Fires on `iteration_count % interval == 0` (was: `experiment_count` — with `parallel_count=4`, `experiment_count` jumped 4→8→12→16→20 and never hit a multiple of 5 → reflect NEVER fired pre-v1.9). Every `autoresearch_reflect_interval` iterations (default 5; `0=disabled`), calls `_call_planner(REFLECT_SYSTEM, user, tid)` with the experiment history. **[v1.9 C5]** History capped at 20 entries in the prompt (was: 100 — could blow the planner's context window on long runs). **[v1.8 N6]** `_call_planner` returns a `(response, usage)` tuple — `node_reflect` discards `usage`. Stores the reflection in `state["reflect_notes"]`. Failures non-fatal — returns `{}` on LLM error. **Returns:** `{"reflect_notes": reflection}` on reflect iterations, `{}` otherwise. |

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
- **[v1.6] Parallel LLM call fails** (`node_propose` parallel path): **Non-fatal for the batch.** Per-call failures (after the v1.3 P1-2 retry logic) are recorded as failed-proposal placeholders (`status="failed"`); the batch continues with the remaining N-1 calls. If ALL N calls fail, `node_propose` returns `status="failed"` for the iteration (mirrors v1.5 single-call failure).
- **[v1.6] Parallel subprocess fails** (`node_run_experiment` parallel path): **Isolated.** Per-experiment subprocess crashes are caught and produce a sentinel output for that slot. `node_evaluate` extracts no metric (yields `0.0`) → `node_decide` skips that experiment. The batch is never aborted by one bad subprocess.
- **[v1.6] Parallel `node_decide` commit fails** (empty SHA): **Winner discarded too.** Mirrors v1.5 P1-1: empty SHA → all N experiments annotated `status="discard"`, `current_best` NOT updated. Temp dir still cleaned up.
- **[v1.7 N7] Checkpoint write fails** (`node_decide.save_checkpoint`): **Non-fatal.** The try/except wraps the entire `save_checkpoint` call so a disk-full / permission error / serialization failure never blocks the experiment loop. The keep still completes (commit + `current_best` update + return); only the checkpoint journal isn't written. A subsequent resume via `run_workflow(resume=True)` falls back to the previous checkpoint (or starts fresh if there is none).
- **[v1.7 N3] Resume requested but no checkpoint found**: The dispatcher traces a warning `"autoresearch: no checkpoint found, starting fresh"` and proceeds with `ar_state["resume"] = False` (the `_ar_default` value). `node_setup` then runs the full v1.6 fresh-start path (new branch + baseline).
- **[v1.8 N5] Full-output log write fails** (`node_run_experiment._write_full_output_log`): **Non-fatal.** The try/except wraps the entire log-write call so a disk-full / permission error / path-resolution failure never blocks the experiment loop. The experiment still runs + truncates + returns its normal result; only the per-iteration log file isn't written. Operators debugging that iteration must re-run it manually (or look at the truncated `experiment_output` in the trace).
- **[v1.8 N6] Subagent doesn't report `usage`**: **Non-fatal.** `_call_planner` defaults `usage` to `{}` when the subagent dispatch result lacks a `usage` key (older subagent versions, mocked tests). `node_propose` then sets `proposal["tokens"] = usage.get("total", 0) = 0`. The experiment proceeds normally — only the cost-tracking field is 0 for that iteration. Operators summing `tokens` across `experiment_history` will see 0 for those entries (underestimates cost but doesn't break the loop).
- **[v1.8 N10] `pre_extracted_metric` is None** (no metric in full output): `node_evaluate` falls through to the existing extraction-from-output path. When the truncated output ALSO has no metric (the typical case — if the full output had no metric, the truncated tail certainly doesn't either), `evaluate` returns `current_metric=0.0` + `status="failed"` + `error="metric ... not found"`. `node_decide` discards. The loop continues. The `pre_extracted_metric` field is explicitly cleared to `None` in parallel `run_experiment` (parallel evaluate doesn't read it) and on the single-path skip path (`status="failed"` from modify) to prevent stale-state leakage across iterations.
- **`_git_reset_hard` with no `project_root` or non-repo**: **[v1.3 P1-4]** `tracer.warning`, returns `False`, skips reset. Prevents resetting the agent's own working tree.
- **[v1.9 A1] Parallel loser that improved over outer current_best**: `_record_failure_memory` is gated on `not _is_improvement(metrics[i], current_best, direction)` — a loser that DID improve (but lost to the winner) is NOT recorded as a failure. Pre-v1.9, every loser got the call → procedural memory was poisoned with false failures → future runs would avoid a perfectly valid change.
- **[v1.9 A3] Parallel winner copy fails**: `_atomic_write` (tempfile + os.fsync + os.replace) is used — was: non-atomic `write_text`. SIGKILL/OOM mid-write left `target_file` empty/partial. The atomic write either fully succeeds or fully fails (tempfile is `os.unlink`'d on failure); readers never see a half-written file. The existing try/except wrapper still catches the failure and traces a warning.
- **[v1.9 B3] Git toplevel mismatch**: `_git_reset_hard` runs `git rev-parse --show-toplevel` and compares to `Path(project_root).resolve()`. If they don't match (possible symlink/junction to a different repo), the reset is refused + a tracer warning is emitted. Prevents nuking a different repo's working tree. A missing git binary or permission error also skips the reset (conservative).
- **[v1.9 B4] _call_planner catches only transient types**: `(RuntimeError, ConnectionError, TimeoutError, OSError, ValueError)` — was: bare `except Exception`. KeyboardInterrupt, SystemExit, ImportError, AttributeError (real bugs) propagate immediately instead of being retried 3×.
- **[v1.9 C1] Ledger write partial / interleaved**: The single path adds `f.flush()` + `os.fsync(f.fileno())` before close (crash-safety). The parallel path batches all N rows into a SINGLE `open("a")` call (atomic on POSIX for writes < PIPE_BUF=4096) — was: N separate calls that could interleave on Windows.
- **[v1.9 C4] seen_hashes cap**: `seen_hashes` is capped at 1000 entries (most recent kept). When the cap is hit, the oldest hash is evicted. This means an experiment tried >1000 iterations ago COULD be re-proposed — but that's a rare edge case (1000 iterations × ~30s/iter = ~8 hours of experiments).
- **[v1.9 D2] Log dir exceeds cap**: When `.autoresearch/logs/` exceeds `cfg.autoresearch_log_dir_max_mb` (default 1024 = 1GB), new log writes are SKIPPED + a tracer warning is emitted. We don't delete old logs (operators may want them); we just stop adding new ones. The experiment loop continues normally — only the per-iteration log file isn't written.
- **[v1.9 D5] iteration_count vs experiment_count**: `iteration_count` increments by 1 per iteration (counts iterations). `experiment_count` increments by N per iteration in parallel mode (counts experiments). `node_reflect` fires on `iteration_count % interval == 0`; `route_after_log`'s `max_iterations` check still uses `experiment_count` (the user spec says max_iterations is "experiments").
- **`GraphRecursionError`** (dispatcher): **[v1.3 P0-2]** **EXPECTED exit.** Caught explicitly and returned as `{"status": "success", "result": "Recursion limit reached — ..."}`. **[v1.4]** `route_after_log` may terminate the loop BEFORE recursion_limit is hit if a stopping condition is met.
- **Non-fatal failures** (branch creation, ledger init/append, git reset failure): `tracer.warning` and continue — in-memory `experiment_history` is the LLM's source of truth; `results.tsv` is the human audit trail (best-effort).

For AI-editing rules around these failure modes, see [INSTRUCTIONS.md](INSTRUCTIONS.md).

---

*Last updated: 2026-07-22 (v1.11). See [CHANGELOG.md](CHANGELOG.md) for version history.*
