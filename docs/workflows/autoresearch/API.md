<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 📝 API Reference

This file documents the autoresearch workflow **facade** + **graph overview** +
**output format** + **state fields** + **per-node reference** (all 7 nodes) +
**routes**. Autoresearch is simpler than autocode, so facade + nodes live in
one file (no separate NODES.md).

---

## 🚀 Facade — `run_workflow("autoresearch", ...)`

The autoresearch workflow is invoked through the shared `run_workflow()` facade
in `workflows/base.py`. There is no autoresearch-specific facade function —
callers use `run_workflow("autoresearch", ...)` directly (autoresearch is
simpler than autocode and doesn't need the extra indirection).

```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="autoresearch",
    goal="minimize val_bpb",            # what to optimize (required)
    target_file="train.py",              # file to modify (default: cfg.autoresearch_target_file)
    project_root="/path/to/repo",        # git repo root (default: cfg.workspace_root)
    metric_name="val_bpb",               # [v1.3 P2-2] forwarded (was: dropped)
    metric_direction="lower",            # [v1.3 P2-2] forwarded (was: dropped)
    time_budget=300,                     # [v1.3 P2-2] forwarded (was: dropped)
    branch="autoresearch/my-run",        # [v1.3 P2-2] forwarded (was: dropped)
    results_path="/path/to/results.tsv", # [v1.3 P2-2] forwarded (was: dropped)
    trace_id="autoresearch_001",         # trace correlation ID (auto-created if empty)
)
```

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `workflow_type` | `str` | (required) | Must be `"autoresearch"`. |
| `goal` | `str` | (required) | Natural-language description of what to optimize, e.g. `"minimize val_bpb"`. Injected verbatim into the LLM proposal prompt. |
| `target_file` | `str` | `cfg.autoresearch_target_file` (`"train.py"`) | File to modify each iteration. Relative to `project_root`. Must resolve INSIDE `project_root` (v1.3 P1-3 path traversal guard) and must NOT be on `cfg.is_protected()` list. |
| `project_root` | `str` | `cfg.workspace_root` | Git repo root. Experiments run with `cwd=project_root`. Must be a git repo for `_git_reset_hard` (v1.3 P1-4). |
| `metric_name` | `str` | `cfg.autoresearch_metric_name` (`"val_bpb"`) | Metric name to extract from experiment output. `evaluate` greps for `{metric_name}: <float>`. **[v1.3 P2-2]** Now actually forwarded to the workflow (was: silently dropped by `_execute_workflow`). |
| `metric_direction` | `str` | `cfg.autoresearch_metric_direction` (`"lower"`) | `"lower"` (lower is better) or `"higher"`. Used by `decide`. **[v1.3 P2-2]** Now forwarded. |
| `time_budget` | `int` | `cfg.autoresearch_time_budget` (`300`) | Per-experiment wall-clock seconds. `run_experiment` kills the subprocess after this elapses. **[v1.3 P2-2]** Now forwarded. |
| `branch` | `str` | `"autoresearch/{YYYYMMDD-HHMMSS}"` | Git branch for experiment commits. Setup creates it (or reuses if it exists). **[v1.3 P2-2]** Now forwarded. |
| `results_path` | `str` | `"{project_root}/results.tsv"` | Path to the results ledger. Setup writes the header if the file doesn't exist. **[v1.3 P2-2]** Now forwarded. |
| `trace_id` | `str` | (auto-created) | Trace correlation ID. |

**Return value:** `dict` — see [📤 Output](#-output) below.

**Dispatcher behavior:** The `autoresearch` branch in `run_workflow()` (in
`workflows/base.py`) initializes state via `_default_state()`, merges in
caller-supplied kwargs (caller values win over defaults), invokes the graph
with `config={"recursion_limit": 1000}`. **[v1.3 P0-2]** `GraphRecursionError`
(raised when the loop hits the limit) is caught explicitly and returned as
`{"status": "success"}` with the trace_id — pre-v1.3 it was caught by the
generic `except Exception` and returned `{"status": "failed"}` (state lost).

---

## 🗺️ Graph Overview

The autoresearch workflow is a **7-node LangGraph StateGraph** with one
direct back-edge creating the infinite experiment loop.

| # | Node | Type | Phase | Purpose |
|---|------|------|-------|---------|
| 1 | `node_setup` | tool (git + subprocess) | 1 | Create branch, init `results.tsv`, run baseline experiment, record baseline metric |
| 2 | `node_propose` | llm (planner) | 2 | LLM proposes next experiment (description + rationale + new_content) based on history + current best. 3× retry (v1.3 P1-2). |
| 3 | `node_modify` | tool (file) | 3 | Apply proposed `new_content` to `target_file` via atomic tempfile + `os.replace`. Path traversal + protected-file guards (v1.3 P1-3). |
| 4 | `node_run_experiment` | tool (subprocess) | 4 | Execute `target_file` as a time-boxed subprocess (`time_budget` seconds), capture stdout+stderr |
| 5 | `node_evaluate` | logic | 5 | Regex-extract metric from experiment output (`{metric_name}: <float>`), take the LAST occurrence |
| 6 | `node_decide` | tool (git) | 6 | Compare `current_metric` vs `current_best`; if improved → `git commit` (keep), else → `git reset --hard HEAD` (discard). **[v1.3 P0-1]** Resets `status="running"` for next iteration. **[v1.3 P1-1]** Empty SHA → discard. |
| 7 | `node_log` | logic | 7 | Append the annotated experiment (post-decide) to `results.tsv` (TSV: iteration, commit, metric, status, description) + update `experiment_history` (capped at 100, v1.3 P2-3). |

**Loop:**

- **`experiment_loop`** — `propose → modify → run_experiment → evaluate → decide → log → propose` (repeats). `exit_condition: "human interrupt"`. `max_iterations: "unlimited"` (LangGraph's `recursion_limit` is the only safety cap).

**[v1.3 P2-5] All edges after `run_experiment` are direct `add_edge` calls** (no conditionals). Pre-v1.3 had two "fake" conditionals: `route_after_evaluate` (always returned `"log"`) and `route_after_decide` (always returned `"propose"`). Both deleted — direct edges are clearer.

For the mermaid diagram + module tree, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 📤 Output

The workflow returns a `dict` (the final LangGraph state). The dispatcher
wraps the graph result with `trace_id` + `status` + `error` normalization.

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

> **Note:** The `experiment_count` and `current_best` in the recursion-limit
> response come from `ar_state` (the initial state), NOT from the final graph
> state — `GraphRecursionError` is raised BEFORE `graph.invoke()` returns, so
> the accumulated state is trapped inside the graph. Operators should inspect
> `results.tsv` for the actual experiment count + best metric. The in-memory
> `experiment_history` is also trapped; a future fix could capture it via a
> state-snapshot callback.

**Setup failure (baseline metric not found — the target_file doesn't print the metric):**

```json
{
  "status": "failed",
  "error": "baseline metric 'val_bpb' not found in target_file output",
  "result": "",
  "artifacts": [],
  "trace_id": "autoresearch_001"
}
```

| Field | Type | Default | When populated |
|-------|------|---------|----------------|
| `status` | `str` | `"success"` | `"success"` (recursion limit hit, v1.3 P0-2), `"failed"` (setup baseline missing), or `"running"` (mid-loop — never returned to caller). |
| `result` | `str` | `""` | Final summary. Set to `"Recursion limit reached — ..."` on normal exit (v1.3 P0-2). |
| `error` | `str` | `""` | Error message on setup baseline failure. |
| `artifacts` | `list[str]` | `[]` | `[results_path]` if the ledger was written. |
| `trace_id` | `str` | (auto) | Always present (dispatcher guarantee). |
| `workflow` | `str` | `"autoresearch"` | Set by `_default_state()`. |
| `experiment_count` | `int` | `0` | Incremented by `node_log` each iteration. NOTE: in the recursion-limit response this is the INITIAL state value (0) — see note above. |
| `baseline_metric` | `float` | `0.0` | Set by `node_setup`. The reference every proposal is compared against. |
| `current_best` | `float` | `0.0` | Updated by `node_decide` on each keep. NOTE: in the recursion-limit response this is the INITIAL state value (0.0). |
| `experiment_history` | `list[dict]` | `[]` | One entry per iteration: `{iteration, description, metric, status, commit}`. Capped at 100 (v1.3 P2-3). |

---

## 🗂️ State Fields (AutoresearchState)

The workflow state is a `TypedDict(total=False)` defined in
`workflows/autoresearch_impl/state.py`. It extends `WorkflowState` (the
shared dispatcher schema) and adds autoresearch-specific fields.

| Field | Type | Default | Source node | Purpose |
|-------|------|---------|-------------|---------|
| `workflow` | `str` | `"autoresearch"` | `_default_state()` | Workflow name (set once, never changed). |
| `goal` | `str` | `""` | `_default_state()` | What to optimize (e.g. `"minimize val_bpb"`). Read by `node_propose`. |
| `trace_id` | `str` | `""` | `_default_state()` | Trace correlation ID. |
| `project_root` | `str` | `cfg.workspace_root` | `_default_state()` | Git repo root. Experiments run with `cwd=project_root`. |
| `target_file` | `str` | `cfg.autoresearch_target_file` | `_default_state()` | File to modify each iteration. |
| `metric_name` | `str` | `cfg.autoresearch_metric_name` | `_default_state()` | Metric to extract from output. |
| `metric_direction` | `str` | `cfg.autoresearch_metric_direction` | `_default_state()` | `"lower"` or `"higher"`. |
| `time_budget` | `int` | `cfg.autoresearch_time_budget` | `_default_state()` | Per-experiment seconds. |
| `branch` | `str` | `"autoresearch/{YYYYMMDD-HHMMSS}"` | `node_setup` | Git branch for experiment commits. |
| `results_path` | `str` | `"{project_root}/results.tsv"` | `node_setup` | Path to the TSV ledger. |
| `experiment_count` | `int` | `0` | `node_log` | Total experiments completed (keep + discard). |
| `baseline_metric` | `float` | `0.0` | `node_setup` | Metric from the unmodified target_file. |
| `current_best` | `float` | `0.0` | `node_setup`, `node_decide` | Best metric seen so far. Updated only on keep. |
| `experiment_history` | `list[dict]` | `[]` | `node_log` | All experiments: `{iteration, description, metric, status, commit}`. Capped at 100 (v1.3 P2-3). Read by `node_propose` (last 20 entries formatted into the prompt). |
| `current_experiment` | `dict` | `{}` | `node_propose`, `node_decide`, `node_log` | The proposal being processed this iteration. Annotated by `decide` (status + commit + metric), then cleared by `log` after appending to history. |
| `experiment_output` | `str` | `""` | `node_setup`, `node_run_experiment` | Combined stdout+stderr from the last experiment (truncated to 50KB by `node_run_experiment`). |
| `current_metric` | `float` | `0.0` | `node_setup`, `node_evaluate` | Metric extracted from the last experiment. |
| `status` | `str` | `"running"` | all nodes | `"running"` / `"success"` / `"failed"`. **[v1.3 P0-1]** Reset to `"running"` by `node_decide` (was: by `node_log`). Read by `node_run_experiment`, `node_evaluate`, `node_decide` to short-circuit on prior failure. |
| `error` | `str` | `""` | all nodes | Error message on failure. **[v1.3 P0-1]** Cleared by `node_decide` (was: by `node_log`). |
| `result` | `str` | `""` | (not set in v1.0) | Final summary. Operators inspect `results.tsv` instead. |
| `artifacts` | `list[str]` | `[]` | (not set in v1.0) | Ledger path. |
| `messages` | `list[AnyMessage]` | `[]` | (not used in v1.0) | LangGraph message accumulator. Reserved for future chat-style proposals. |

---

## ⚡ Per-Node Reference

Nodes are listed in graph-execution order: `setup → propose → modify → run_experiment → evaluate → decide → log → propose (loop)`.

For the mermaid diagram + module tree, see [ARCHITECTURE.md](ARCHITECTURE.md).
For routes, see [Routes](#-routes) below.

### `node_setup(state)` — Phase 1: Branch + Ledger + Baseline

**Purpose:** Create the experiment git branch, initialize the results ledger, run the baseline experiment, and record the baseline metric (which becomes the initial `current_best`).

**Logic:**
1. Compute `branch = "autoresearch/{YYYYMMDD-HHMMSS}"` (or use `state["branch"]` if provided).
2. Create + checkout the branch via `git(action="checkout_new")` (falls back to `checkout_branch` if it already exists — supports resume). Non-fatal on failure (experiments can still proceed on the current branch).
3. Compute `results_path = "{project_root}/results.tsv"` (or use `state["results_path"]`).
4. Write the TSV header (`iteration\tcommit\tmetric\tstatus\tdescription\n`) IF the file doesn't already exist (resume case).
5. Run the baseline experiment: `python <target_file>` as a subprocess, time-boxed by `time_budget`. **[v1.3 P2-1]** Uses shared `helpers.run_target_subprocess` (was a local copy).
6. Extract the baseline metric via `_extract_metric_from_output()`. If not found, return `status="failed"` with a descriptive error (the operator needs to fix the target_file before re-running).

**Output:** Partial dict with `branch`, `results_path`, `experiment_count=0`, `baseline_metric`, `current_best=baseline_metric`, `experiment_output`, `current_metric=baseline_metric`, `status="running"` (or `status="failed"` + `error` on baseline failure).

**Source:** `workflows/autoresearch_impl/nodes/setup.py` (hosts `_git_create_branch`; `_run_experiment_subprocess` removed in v1.3 P2-1 — now in `helpers.run_target_subprocess`).

---

### `node_propose(state)` — Phase 2: LLM Proposes Next Experiment

**Purpose:** Call the planner LLM via `agent(action="subagent", role="planner")` with the goal, metric, current best, experiment history, and current target_file content. The subagent returns a JSON proposal describing the next change.

**Logic:**
1. Compute `iteration = experiment_count + 1`.
2. Read the current `target_file` content from disk (so the LLM sees the post-modify state from the previous iteration, not the original baseline).
3. **[v1.3 P1-5]** If `len(current_content) > cfg.autocode_max_file_chars` (default 6000), truncate to first half + last half with a `[TRUNCATED]` marker. Prevents context window overflow on long files.
4. Format `experiment_history` into a human-readable block (most recent first, capped at 20 entries).
5. Build the user prompt: goal, metric + direction, current_best, target_file path, history block, current file content.
6. Call `_call_planner(_PROPOSE_SYSTEM, user)` — uses `agent(action="subagent", role="planner")`. **[v1.3 P1-2]** Retries up to 3× with 2s/4s backoff on failure (was: single attempt). Raises `RuntimeError` after all 3 attempts fail.
7. Parse the JSON response via `core.json_extract.extract_json()`. Falls back to `{"description": "(unparseable proposal)", "new_content": ""}` on parse failure (the workflow still records the attempt).

**Output:** Partial dict with `current_experiment = {iteration, description, rationale, new_content}` and `status="running"` (or `status="failed"` + `error` on LLM call failure).

**Source:** `workflows/autoresearch_impl/nodes/propose.py` (hosts `_PROPOSE_SYSTEM`, `_format_history`, `_read_target_file`, `_call_planner`, `_parse_proposal`).

---

### `node_modify(state)` — Phase 3: Atomic Write to target_file

**Purpose:** Apply the proposed `new_content` to `target_file` via an atomic write (tempfile + `os.replace`). Atomic writes ensure the file is never left in a half-written state if the process is killed mid-write.

**Logic:**
1. Read `proposal = state["current_experiment"]` and `new_content = proposal["new_content"]`.
2. If `new_content` is empty (LLM parse failure, etc.): skip the write, set `status="failed"` so `node_decide` knows to discard.
3. Compute `target_path = Path(project_root) / target_file`.
4. **[v1.3 P1-3]** Path traversal guard: `target_path.resolve().relative_to(Path(project_root).resolve())` — refuses paths that escape `project_root` (e.g. `target_file="../../../etc/passwd"`). Returns `status="failed"` with `error="path traversal blocked: ..."`.
5. **[v1.3 P1-3]** Protected-file check: `cfg.is_protected(target_path)` — refuses paths on the protected-file list (same list used by the `file` tool: `.env`, `pyproject.toml`, agent source, etc.). Returns `status="failed"` with `error="protected file: ..."`.
6. Otherwise: `_atomic_write(target_path, new_content)` — `tempfile.mkstemp(dir=target_path.parent)` + `os.fdopen` + `f.write` + `f.flush` + `os.fsync` + `os.replace`. On exception, `os.unlink` the tempfile (no `.tmp` leaks) and re-raise.

**Output:** Partial dict with `status="running"` + `error=""` (or `status="failed"` + `error` on empty proposal / path traversal / protected file / write failure).

**Source:** `workflows/autoresearch_impl/nodes/modify.py` (hosts `_atomic_write`).

---

### `node_run_experiment(state)` — Phase 4: Time-Boxed Subprocess

**Purpose:** Execute the (now-modified) `target_file` as a subprocess, time-boxed by `time_budget`. Capture combined stdout+stderr.

**Logic:**
1. If `state["status"] == "failed"` (prior node failed): skip the run, return the existing `experiment_output` (decide will discard).
2. Build `cmd = [sys.executable, target_file]`.
3. **[v1.3 P2-1]** Call shared `helpers.run_target_subprocess(target_file, project_root, time_budget)` (was a local `_run_subprocess`).
4. On `TimeoutExpired`: concatenate partial stdout+stderr + append sentinel `"[autoresearch] experiment timed out after {time_budget}s\n"`. The evaluate node will still try to extract the metric from the partial output.
5. On `FileNotFoundError` (target_file missing): return `"[autoresearch] target_file not found: ...\n"`.
6. Truncate to last 50KB if larger (prevents state bloat; the metric is usually printed at the end).

**Output:** Partial dict with `experiment_output` (combined stdout+stderr string), `status="running"`, `error=""`.

**Source:** `workflows/autoresearch_impl/nodes/run_experiment.py` (`_run_subprocess` removed in v1.3 P2-1 — now in `helpers.run_target_subprocess`).

---

### `node_evaluate(state)` — Phase 5: Regex Metric Extraction

**Purpose:** Extract the metric from the experiment output. Training scripts often print the metric per epoch; we want the FINAL value (last occurrence).

**Logic:**
1. If `state["status"] == "failed"`: propagate the failure (return `current_metric=0.0`; decide will discard).
2. Build regex: `rf"{re.escape(metric_name)}\s*[:=]\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"`. Accepts `:`, `=`, or whitespace as separator. Escapes the metric name so special chars like `val/loss` work.
3. `re.findall()` all occurrences, take `matches[-1]` (the last one).
4. If no match: return `current_metric=0.0` + `status="failed"` + `error="metric '{metric_name}' not found in experiment output"`.

**Output:** Partial dict with `current_metric` (float) and `status="running"` (or `status="failed"` + `error` on missing metric).

**Source:** `workflows/autoresearch_impl/nodes/evaluate.py` (uses `helpers.extract_metric`).

---

### `node_decide(state)` — Phase 6: Keep (Commit) / Discard (Reset) + Status Reset

**Purpose:** Compare `current_metric` against `current_best` using the configured direction. If improved, commit the change and update `current_best`. If worse or equal, discard via `git reset --hard HEAD` + `git clean -fd` to restore the last-known-good state.

**[v1.3 P0-1]** This node now runs BEFORE `node_log` (was: AFTER). It annotates `current_experiment` with `status` + `commit` + `metric` so `log` writes the CORRECT status to the ledger. Also takes over the `status="running"` + `error=""` reset (was: `log`'s job).

**Logic:**
1. Read `current_metric`, `current_best`, `metric_direction`.
2. If `state["status"] == "failed"` (prior node failed): always discard. Reset `status="running"` + `error=""`.
3. Compute `improved = _is_improvement(current_metric, current_best, direction)`:
   - `direction="lower"` → `new < best` is an improvement.
   - `direction="higher"` → `new > best` is an improvement.
   - Equality is NOT an improvement (discourage no-op changes).
4. If NOT improved: `_git_reset_hard(project_root)` (`git reset --hard HEAD` + `git clean -fd`). Annotate `proposal["status"] = "discard"`, `proposal["commit"] = ""`. Reset `status="running"` + `error=""`.
5. If improved: `_git_commit(message, project_root)` (`git add <target_file>` + `git commit -m` + `git rev-parse --short HEAD`). **[v1.3 P1-1]** If `_git_commit` returns `""` (commit failed): treat as discard — run `_git_reset_hard`, set `status="discard"` + `commit=""`, do NOT update `current_best`. Otherwise: annotate `proposal["status"] = "keep"`, `proposal["commit"] = sha`. Update `current_best = current_metric`. Reset `status="running"` + `error=""`.

**Output:** Partial dict with `current_experiment` (annotated with `status` + `commit` + `metric`), `current_best` (updated if kept, unchanged if discarded), `status="running"`, `error=""`.

**Source:** `workflows/autoresearch_impl/nodes/decide.py` (hosts `_is_improvement`, `_git_commit`, `_git_reset_hard`).

---

### `node_log(state)` — Phase 7: Append to results.tsv + Update History

**Purpose:** Append a single TSV row to the results ledger and push a corresponding entry into `experiment_history` so the propose node can see the full context on the next iteration.

**[v1.3 P0-1]** This node now runs AFTER `decide` (was: BEFORE). Reads the ANNOTATED `current_experiment` (with `status` + `commit` set by `decide`) — the ledger now records the CORRECT status. Pre-v1.3 it always recorded "discard" because it read `proposal.get("status", "discard")` before `decide` had set it.

**Logic:**
1. Read `proposal = state["current_experiment"]` (annotated by `node_decide` with `status` + `commit` + `metric`).
2. Sanitize `description` — collapse whitespace + strip newlines/tabs so the row stays one line.
3. Append `f"{iteration}\t{commit}\t{metric}\t{status}\t{safe_desc}\n"` to `results_path`.
4. Append `{iteration, description, metric, status, commit}` to `experiment_history` (copy the list, don't mutate — LangGraph pattern).
5. **[v1.3 P2-3]** Cap `experiment_history` at 100 entries (most recent kept).
6. Increment `experiment_count`.
7. Clear `current_experiment` (ready for the next proposal).

**Output:** Partial dict with `experiment_history` (updated list), `experiment_count` (incremented), `current_experiment={}`. **[v1.3 P0-1]** No longer returns `status` / `error` — `decide` does the reset.

**Source:** `workflows/autoresearch_impl/nodes/log.py` (hosts `_append_to_ledger`).

---

## 🔀 Routes

`workflows/autoresearch_impl/routes.py` defines 1 routing function (v1.3 P2-5:
was 3, but 2 were "fake" conditionals → deleted). Only `route_after_setup`
is conditional — the experiment loop has no exit condition other than human
interruption (or LangGraph's `recursion_limit`).

### `route_after_setup(state) -> str`

**Returns:** `"propose"` on success, `"end"` on failure.

**Rationale:** v1.2.1 (P1-1) — if setup fails (baseline metric not extracted), the workflow used to spin infinitely. Now routes to END.

### [v1.3 P2-5] DELETED: `route_after_evaluate` + `route_after_decide`

Both were unconditional single-destination "fake" conditionals (always returned the same value). Replaced with direct `add_edge` calls in `graph.py`:
- `evaluate → decide` (was: `evaluate → log`)
- `decide → log` (was: `log → decide`)
- `log → propose` (was: `decide → propose`)

The graph order changed from `evaluate → log → decide` to `evaluate → decide → log` (v1.3 P0-1) — see `node_log` reference above for why.

---

## 🔒 Security

- **`subprocess.run` with list args (NOT `shell=True`)** — `node_run_experiment`, `node_decide._git_commit`, `node_decide._git_reset_hard` all use `subprocess.run(["git", "add", ...])` with explicit list args. No shell injection risk.
- **`re.escape(metric_name)`** — `node_evaluate` escapes the metric name before building the regex, so special characters like `val/loss` or `loss-1` don't break the pattern or inject regex metacharacters.
- **Atomic writes** — `node_modify._atomic_write` uses `tempfile.mkstemp(dir=target_path.parent)` + `os.fsync` + `os.replace`. The target file is never in a half-written state. The tempfile is created in the same directory (same-filesystem rename — atomic on POSIX + Windows).
- **[v1.3 P1-3] Path traversal guard** — `node_modify` checks `target_path.resolve().relative_to(Path(project_root).resolve())` and refuses paths that escape `project_root` (e.g. `target_file="../../../etc/passwd"`).
- **[v1.3 P1-3] Protected-file check** — `node_modify` checks `cfg.is_protected(target_path)` and refuses paths on the protected-file list (same list used by the `file` tool).
- **[v1.3 P1-4] git reset safety guard** — `_git_reset_hard` refuses to reset without an explicit `project_root` or when `project_root` isn't a git repo (`.git` directory missing).
- **Time-boxed subprocess** — `node_run_experiment` passes `timeout=time_budget` to `subprocess.run`. A hung experiment is killed after `time_budget` seconds; the partial output is still returned for metric extraction.
- **Output truncation** — `node_run_experiment` truncates output to the last 50KB if larger. Prevents state bloat (and ledger bloat if the description somehow included the output).
- **[v1.3 P1-5] Target file content cap** — `node_propose` caps `current_content` at `cfg.autocode_max_file_chars` (default 6000) before sending to the LLM. Prevents context window overflow on long files.

---

## 📝 Error Handling

| Failure mode | Where caught | Behavior |
|--------------|--------------|----------|
| Branch creation fails | `node_setup._git_create_branch` | Non-fatal — `tracer.warning`, continue on current branch. Experiments still run; the safety net (revert via branch) is gone. |
| Ledger init fails (disk full, permissions) | `node_setup` | Non-fatal — `tracer.warning`, continue without ledger. In-memory `experiment_history` is still the source of truth for the LLM. |
| Baseline metric not found | `node_setup` | FATAL — return `status="failed"` + descriptive error. Operator must fix `target_file` (it must print the metric) before re-running. |
| Ledger append fails | `node_log._append_to_ledger` | Non-fatal — `tracer.warning`, continue. In-memory history still updated. |
| LLM call fails (timeout, network) | `node_propose._call_planner` | **[v1.3 P1-2]** Retries 3× with 2s/4s backoff. After all 3 attempts fail, raises `RuntimeError`; `node_propose` catches it and returns `status="failed"` + `error`. `node_decide` discards the (empty) proposal. Loop continues. |
| LLM returns unparseable JSON | `node_propose._parse_proposal` | Falls back to `{"description": "(unparseable proposal)", "new_content": ""}`. `node_modify` skips the empty write. `node_decide` discards. Loop continues. |
| Empty proposal (`new_content == ""`) | `node_modify` | Skips write, sets `status="failed"`. `node_run_experiment` skips run. `node_evaluate` propagates failure. `node_decide` discards. Loop continues. |
| **[v1.3 P1-3]** Path traversal (`target_file` escapes `project_root`) | `node_modify` | Returns `status="failed"` + `error="path traversal blocked: ..."`. `node_decide` discards. Loop continues. |
| **[v1.3 P1-3]** Protected file (`target_file` on `cfg.is_protected()` list) | `node_modify` | Returns `status="failed"` + `error="protected file: ..."`. `node_decide` discards. Loop continues. |
| Atomic write fails (disk full, permissions) | `node_modify._atomic_write` | Tempfile is `os.unlink`'d (no `.tmp` leaks), exception re-raised, `node_modify` catches and returns `status="failed"`. `node_decide` discards. |
| Subprocess times out | `node_run_experiment` (`helpers.run_target_subprocess`) | Catches `TimeoutExpired`, returns partial output + sentinel. `node_evaluate` tries to extract metric from partial output; if missing, marks failed. `node_decide` discards. |
| Subprocess crashes / target_file missing | `node_run_experiment` (`helpers.run_target_subprocess`) | Catches `FileNotFoundError` + generic `Exception`, returns sentinel error string. `node_evaluate` marks failed. `node_decide` discards. |
| Metric not in output (experiment crashed) | `node_evaluate` | Returns `current_metric=0.0` + `status="failed"`. `node_decide` discards. |
| **[v1.3 P1-1]** `git commit` fails (nothing to commit, hook rejection, returns `""`) | `node_decide._git_commit` | **[v1.3 P1-1]** Treated as DISCARD — runs `_git_reset_hard`, sets `status="discard"` + `commit=""`, does NOT update `current_best`. Was: set `status="keep"` with empty commit (ambiguous ledger entry). |
| `git reset --hard` fails | `node_decide._git_reset_hard` | `tracer.warning`, returns `False`. Next iteration may start from a dirty tree — the LLM sees the residual changes via `_read_target_file`. Not catastrophic. |
| **[v1.3 P1-4]** `_git_reset_hard` with no `project_root` or non-repo `project_root` | `node_decide._git_reset_hard` | `tracer.warning`, returns `False`, skips reset. Prevents accidentally resetting the agent's own working tree. |
| **[v1.3 P0-2]** `GraphRecursionError` (loop hit `recursion_limit`) | `workflows/base.py` dispatcher (autoresearch branch) | EXPECTED exit. Caught explicitly and returned as `{"status": "success", "result": "Recursion limit reached — check results.tsv ..."}` with the trace_id. Pre-v1.3 it was caught by the generic `except Exception` and returned `status="failed"` (state lost). |

---

*Last updated: 2026-07-15 (v1.3.0 — hardening batch).*
