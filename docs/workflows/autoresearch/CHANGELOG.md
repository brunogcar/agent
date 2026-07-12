<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| **v1.2** | 2026-07-12 | **[Hardening] Propose node hardened.** `_PROPOSE_JSON_SCHEMA` enforcement added (was: prompt-only). Removed duplicate `history_str` from `context` param (was in both `user` and `context` — wasted tokens). |
| **v1.1** | 2026-07-12 | **Subagent dispatch in `propose` node.** `propose` now calls `agent(action="subagent", role="planner")` for isolated curated-context LLM dispatch. Was: `autocode_impl.helpers._call()`. Subagent gets only experiment history + target file content — no session history (superpowers pattern: "you construct exactly what they need"). Non-blocking: falls back to `_call()` on subagent failure. |
| **v1.0** | 2026-07-12 | **Initial implementation.** 7-node LangGraph StateGraph (`setup → propose → modify → run_experiment → evaluate → log → decide → propose (loop)`). Evolutionary experiment-driven optimization: modify target file → run time-boxed subprocess → extract metric → keep (git commit) / discard (git reset). `AutoresearchState` TypedDict extends `WorkflowState`. `WORKFLOW_METADATA` mirrors autocode's schema. 4 config knobs (`AUTORESEARCH_TIME_BUDGET`, `AUTORESEARCH_TARGET_FILE`, `AUTORESEARCH_METRIC_NAME`, `AUTORESEARCH_METRIC_DIRECTION`). 22/22 tests pass with `-W error`. |

---

## 🏗️ Breaking Changes

None. v1.0 is a new workflow — there is no prior version to break.

The v1.0 release touched 4 existing files to wire the workflow into the dispatcher:

| File | Change |
|------|--------|
| `tools/workflow.py` | Added `"autoresearch"` to `VALID_WORKFLOWS`, `WorkflowType` Literal, docstring, dispatch kwargs (forwards `target_file` + `project_root`). |
| `workflows/base.py` | Added `elif wf_type == "autoresearch":` dispatch case in `run_workflow()`. Initializes state via `_default_state()`, invokes graph with `recursion_limit=1000` (LangGraph default of 25 is too low for the infinite loop). |
| `core/config.py` | Added 4 config knobs (see AUTORESEARCH.md § Configuration). All have sane defaults; no migration required. |
| `tests/workflows/base/test_dispatcher.py` | Added `"autoresearch"` to the list of workflow types the unknown-type error message must mention. |

No other workflows were touched. No existing tests were broken.

---

## ✅ Completed (v1.0)

| # | Feature | Notes |
|---|---------|-------|
| 1 | Thin facade (`workflows/autoresearch.py`) | Re-exports `build_autoresearch_graph` + `WORKFLOW_METADATA`. Matches research / autocode / deep_research / understand / data pattern. |
| 2 | `autoresearch_impl/` subpackage | `__init__.py` + `state.py` + `routes.py` + `graph.py` + `nodes/` (7 per-node modules). |
| 3 | `AutoresearchState` TypedDict | Extends `WorkflowState` (total=False). Unique fields: `target_file`, `metric_name`, `metric_direction`, `time_budget`, `experiment_count`, `baseline_metric`, `current_best`, `experiment_history`, `current_experiment`, `experiment_output`, `current_metric`. Plus shared dispatcher fields (`workflow`, `trace_id`, `status`, `error`, `result`, `artifacts`). |
| 4 | `_default_state()` factory | Pulls sane defaults from `cfg` (4 autoresearch knobs + `workspace_root`). |
| 5 | `node_setup` | Creates git branch `autoresearch/{YYYYMMDD-HHMMSS}`, initializes `results.tsv` with header, runs baseline experiment, extracts baseline metric (becomes initial `current_best`). |
| 6 | `node_propose` | Calls planner LLM (via `autocode_impl.helpers._call()` for retry + cancellation). Parses JSON proposal `{description, rationale, new_content}`. |
| 7 | `node_modify` | Atomic write (`tempfile.mkstemp` + `os.fsync` + `os.replace`). Skips on empty proposal. |
| 8 | `node_run_experiment` | `subprocess.run` time-boxed by `time_budget`. Captures stdout+stderr, truncates to 50KB to prevent state bloat. |
| 9 | `node_evaluate` | Regex extracts LAST occurrence of `{metric_name}: <float>` from output. Returns `0.0` + `status="failed"` if missing. |
| 10 | `node_decide` | Compares `current_metric` vs `current_best` using `metric_direction`. If improved → `git add -A` + `git commit` + `git rev-parse --short HEAD`. If worse → `git reset --hard HEAD` + `git clean -fd`. |
| 11 | `node_log` | Appends TSV row to `results.tsv` (iteration, commit, metric, status, description). Updates `experiment_history` + `experiment_count`. Clears `current_experiment`. |
| 12 | `routes.py` | `route_after_evaluate` (always → log) + `route_after_decide` (always → propose — the infinite loop back-edge). |
| 13 | `WORKFLOW_METADATA` | Mirrors autocode's schema: `name`, `version`, `description`, `entry_point`, 7 `nodes` (with type/role/description), 7 `edges` (with conditions + `type="loop"` flag), 1 `loop` (`experiment_loop`), `branches=[]`, 5 `safety_features`. |
| 14 | 4 config knobs | `AUTORESEARCH_TIME_BUDGET` (300s), `AUTORESEARCH_TARGET_FILE` ("train.py"), `AUTORESEARCH_METRIC_NAME` ("val_bpb"), `AUTORESEARCH_METRIC_DIRECTION` ("lower"). |
| 15 | Dispatcher integration | `tools/workflow.py` + `workflows/base.py` + `core/config.py` updated. `recursion_limit=1000` (≈160 experiments overnight). |
| 16 | Tests | 14 graph-topology + metadata tests + 8 integration tests (loop ordering, decide keep/discard, evaluate last-occurrence extraction, modify atomic write + skip, log ledger append). 22/22 pass with `-W error`. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | Parallel experiments | Currently the loop runs one experiment at a time. Branch N proposals, run all N subprocesses in parallel, keep the best. Would multiply iteration throughput on multi-GPU boxes. | **P2** |
| 2 | Multi-metric optimization | Currently a single `metric_name` is optimized. Add `metric_name: list[str]` + a Pareto-front decide node so the loop keeps experiments that improve one metric without regressing others. | **P3** |
| 3 | Human-in-the-Loop (HiTL) checkpoints | Pause the loop every N iterations and surface the current_best + experiment_history for operator review. Operator can adjust the goal, prune the history, or stop. | **P3** |
| 4 | Subagent dispatch for proposals | Replace the single-LLM sequential `propose` node with parallel subagents (one per hypothesis family) — autocode Future Track F1 pattern. | **P3** |
| 5 | Cross-run learning | Store procedural memory when a proposal type repeatedly fails (e.g. "increasing LR past 1e-3 always crashes"), so future runs skip it. | **P3** |
| 6 | Adaptive `time_budget` | Detect if experiments consistently time out (the metric is never extracted) and either raise `time_budget` or surface a warning. | **P3** |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | Remove the indefinite loop | The whole point — the loop runs until a human is satisfied. | Skip |
| 2 | Skip the ledger | `results.tsv` is the human audit trail; operators `tail -f` it while the loop runs. | Skip |
| 3 | Modify `target_file` outside `node_modify` | Atomic-write invariant — every modification goes through `tempfile + os.replace` so the file is never half-written. | Skip |
| 4 | Auto-stop on convergence | No clean convergence signal (unlike `deep_research` cosine similarity). Metric can plateau then jump. Human judgment required. | Skip |
| 5 | Use the `git` tool for `decide` | Adds tracing + compression noise to the tight experiment loop. `subprocess.run` direct git calls are deliberately chosen. | Skip |
| 6 | Multi-file modifications | `target_file` is a single file (matches karpathy/autoresearch scope). Multi-file would require a patch format — see `autocode` `node_apply_patches` for the pattern. | P3 future |
| 7 | Non-Python target files | `run_experiment` runs `python <target_file>`. Other runtimes (shell, make, docker) would need a `runner` config field. | P3 future |

---

*Last updated: 2026-07-12 (v1.1 — `propose` node switched to subagent dispatch for isolated curated context).*
