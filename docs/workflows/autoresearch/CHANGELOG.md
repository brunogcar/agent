<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.6 | 2026-07-21 | **Parallel experiments (batch mode).** When `parallel_count > 1`, each iteration proposes N experiments in parallel via ThreadPoolExecutor(max_workers=N) — each with the SAME prompt (the LLM produces different proposals via sampling temperature). Per-call LLM failures are recorded as failed-proposal placeholders so the batch isn't aborted. `node_modify` writes each proposal to its own temp dir under `{project_root}/.autoresearch/parallel/{i}/{target_file}` (the real `target_file` is only touched by `node_decide`). `node_run_experiment` runs N subprocesses concurrently in their own temp dirs as cwd. `node_evaluate` extracts N metrics. `node_decide` picks the best, copies the winner's content to the real `target_file`, git commits it, discards the rest, and cleans up the temp dir. `node_log` writes N ledger rows + N history entries (experiment_count increments by N). When `parallel_count == 1` (default), all nodes behave exactly as v1.5 (single-experiment). New env var: `AUTORESEARCH_PARALLEL_COUNT`. 4 new state fields: `parallel_count`, `current_experiments`, `experiment_outputs`, `current_metrics` (singular fields kept for v1.5 backward compat). |
| v1.5 | 2026-07-21 | **Reflect node (N1) + cross-run learning (N4).** New `node_reflect` between `log` and `route_after_log` — every `autoresearch_reflect_interval` iterations (default 5; 0=disabled) calls the planner LLM with the full experiment history + `REFLECT_SYSTEM` prompt and stores the reflection in `state["reflect_notes"]`. `node_propose` surfaces the reflection in its prompt (when non-empty) so the LLM has strategic context, not just raw history. No-op on non-reflect iterations (returns `{}`). New env var: `AUTORESEARCH_REFLECT_INTERVAL`. Cross-run learning (N4): `node_decide` records a procedural memory via `memory.store_procedural()` on every discard path (prior failure + no-improvement); `node_propose` recalls procedural memories before generating the next proposal so the LLM avoids re-proposing known dead-ends. Failures non-fatal (memory may be unavailable — try/except wraps all calls). Graph bumps to 8 nodes. |
| v1.4 | 2026-07-20 | **Loop control + dedup.** `max_iterations` param (caller-set hard cap; 0=unlimited). `route_after_log` conditional edge replaces the v1.3 direct `log → propose` edge — checks 3 stopping conditions: (1) max_iterations reached, (2) convergence: last N all discarded, (3) stuck: last N metrics all within ε of current_best. All default OFF → v1.4 preserves v1.3 "loop forever" behavior unless caller opts in. Experiment deduplication (N8): `node_modify` md5-hashes `new_content` and skips duplicates from `experiment_history`; `content_hash` stored on each history entry by `node_log`. 3 new env vars: `AUTORESEARCH_MAX_ITERATIONS`, `AUTORESEARCH_CONVERGENCE_WINDOW`, `AUTORESEARCH_CONVERGENCE_EPSILON`. |
| v1.3.0 | 2026-07-15 | **Hardening batch (5-reviewer collective audit).** P0-1: graph order swapped `evaluate → log → decide` → `evaluate → decide → log` (log was reading pre-decide status → ledger ALWAYS said "discard"). P0-2: `GraphRecursionError` caught explicitly (was: generic `except Exception` → `status="failed"` + state lost). P1-1: empty SHA → discard (was: `status="keep"` with empty commit). P1-2: `_call_planner` retries 3× with 2s/4s backoff. P1-3: path traversal + protected-file guard in `node_modify`. P1-4: `_git_reset_hard` safety guard (refuses no-root / non-repo). P1-5: target-file content capped at `cfg.autocode_max_file_chars` (6000). P2-1: shared `run_target_subprocess` in helpers.py (was duplicated). P2-2: forward ALL params (metric_name, metric_direction, time_budget, branch, results_path) through type handler. P2-3: `experiment_history` capped at 100. P2-4: removed 4 dead conftest fixtures. P2-5: fake conditional edges (`route_after_evaluate` / `route_after_decide`) replaced with direct edges; both routers deleted. |
| v1.2.2 | 2026-07-14 | **Phase 4g review — subagent dispatch doc fixes + version sync.** P1-2: Removed incorrect `_call()` fallback claim (no fallback exists). P2-2: `WORKFLOW_METADATA["version"]` synced from `"1.2"` to `"1.2.2"`. P3-2: `propose.py` docstring updated for v1.1+ subagent dispatch. |
| v1.2.1 | 2026-07-14 | **Bugfix batch.** P1-1: `route_after_setup` conditional edge — setup failure routes to END (was infinite loop). P1-2: Extracted `_extract_metric` to `helpers.py`. P2-1/P2-2/P2-3/P3-1: tracer tid, KEPT message direction, version sync, `git add` scoping. |
| v1.2 | 2026-07-12 | **[Hardening] Propose node hardened.** `_PROPOSE_JSON_SCHEMA` enforcement added. Removed duplicate `history_str` from `context` param. |
| v1.1 | 2026-07-12 | **Subagent dispatch in `propose` node.** `propose` now calls `agent(action="subagent", role="planner")` for isolated curated-context dispatch. No `_call()` fallback. |
| v1.0 | 2026-07-12 | **Initial implementation.** 7-node LangGraph StateGraph. Evolutionary experiment-driven optimization. 4 config knobs. 22/22 tests pass. |

---

### ⚠️ Breaking Changes

#### v1.6 — 2026-07-21

| Change | Impact | Migration |
|--------|--------|------------|
| New `parallel_count` state field + 3 plural state fields (`current_experiments`, `experiment_outputs`, `current_metrics`) | `AutoresearchState` gained 4 new fields. Defaults: `parallel_count=1`, the lists `[]`. When `parallel_count == 1`, all nodes use the v1.5 singular fields only — the plural fields are unused (additive, no behavior change). When `parallel_count > 1`, all nodes use the plural fields; the singular fields mirror the first list element for v1.5 backward compat. | None — additive change. Code reading state by key keeps working. |
| New env var `AUTORESEARCH_PARALLEL_COUNT` | `cfg.autoresearch_parallel_count` (default 1) controls how many parallel experiments run per iteration. | Set `AUTORESEARCH_PARALLEL_COUNT=N` (N > 1) to enable batch mode. Default 1 = v1.5 behavior. |
| `node_modify` in parallel mode writes to `{project_root}/.autoresearch/parallel/{i}/{target_file}` (NOT the real `target_file`) | The real `target_file` is only modified by `node_decide` (which copies the winner's content back). Pre-v1.6 modify wrote directly to `target_file`. | None — in `parallel_count == 1` mode (default), modify still writes directly to `target_file` exactly as v1.5. |
| `node_decide` in parallel mode picks the best of N experiments, copies winner's content, commits, cleans up temp dir | Operators see one git commit per iteration (same as v1.5) even though N experiments ran. The commit message includes `[parallel best of N]` marker. | None — additive change. |
| `node_log` in parallel mode appends N rows to `results.tsv` + N entries to `experiment_history` + increments `experiment_count` by N | Pre-v1.6 incremented `experiment_count` by 1 per iteration. With `parallel_count=N`, it now increments by N. | Operators tailing `results.tsv` will see N rows per iteration when batch mode is on. |

#### v1.5 — 2026-07-21

| Change | Impact | Migration |
|--------|--------|------------|
| New `reflect` node inserted between `log` and `route_after_log` | The graph now has 8 nodes (was 7). `route_after_log` is now invoked from `reflect` (was from `log`). The conditional edge `log → propose (type=loop)` is replaced by `log → reflect` (linear) + `reflect → propose (type=loop, conditional)`. | Code that imports `WORKFLOW_METADATA` and asserts `len(nodes) == 7` must update to 8. Code reading edges must handle the new `log → reflect` + `reflect → propose` pair. |
| New `reflect_notes` state field | `AutoresearchState` gained a new `str` field. Defaults to `""`. | None — additive change. Code reading state by key keeps working. |
| `node_decide` now calls `memory.store_procedural()` on discard | Discard paths now invoke `core.memory_engine.memory.store_procedural()` (wrapped in try/except — non-fatal). If chromadb is unavailable, the call silently no-ops. | None — additive change. Operators without chromabd see no behavior change. |

#### v1.4 — 2026-07-20

| Change | Impact | Migration |
|--------|--------|------------|
| `log → propose` back-edge changed from direct edge to conditional edge (`route_after_log`) | The loop now checks stopping conditions (max_iterations / convergence / stuck) after each `node_log`. All 3 default OFF → v1.3 "loop forever" behavior preserved unless caller opts in. | Callers wanting the v1.3 indefinite-loop behavior: do nothing (defaults). Callers wanting auto-stop: pass `max_iterations=N` or set `AUTORESEARCH_MAX_ITERATIONS=N` env var. |
| `experiment_history` entries now include `content_hash` field | History entries gained a new key (md5 of `new_content`). No existing key removed. | None — additive change. Code reading history by key keeps working. |
| `node_modify` now md5-hashes `new_content` and skips duplicates | A proposal whose `new_content` matches a prior experiment's hash now returns `status="failed"` with a "duplicate" error (was: re-wrote the same content + re-ran the experiment). | None — duplicates were wasted iterations pre-v1.4. |

#### v1.3 — 2026-07-15

| Change | Impact | Migration |
|--------|--------|-----------|
| Graph order changed: `evaluate → log → decide` → `evaluate → decide → log` | `log` now reads `current_experiment.status` AFTER `decide` annotates it — ledger records correct `keep`/`discard`. Pre-v1.3 ledgers always said "discard" (silent bug). | Operators: ledger will now show mixed `keep`/`discard`. Pre-v1.3 ledgers should be re-checked against `git log autoresearch/{branch}`. |
| `route_after_evaluate` + `route_after_decide` deleted from `routes.py` | Both were unconditional "fake" conditionals. Replaced with direct `add_edge` calls. | Code that imported these must remove the import (none found — only `graph.py` imported them). |
| `_run_experiment_subprocess` (setup.py) + `_run_subprocess` (run_experiment.py) deleted | Consolidated into `helpers.run_target_subprocess`. | Code importing these private helpers must switch (none found — private). |
| Conftest fixtures `base_state`, `mock_subprocess`, `mock_git`, `tmp_project` removed | Dead code — defined but never used. | None. |
| `node_log` no longer returns `status`/`error` reset | Reset moved to `node_decide` (runs first in new order). | Internal — no caller-facing impact. |

#### v1.1 — 2026-07-12

| Change | Impact | Migration |
|--------|--------|-----------|
| `propose` node switched to subagent dispatch | Was: `autocode_impl.helpers._call()`. Now: `agent(action="subagent", role="planner")`. | No migration — the subagent gets isolated curated context (no session history). On failure, the iteration halts with `status="failed"` (no `_call()` fallback). |

#### v1.0 — 2026-07-12

| Change | Impact | Migration |
|--------|--------|-----------|
| New workflow — no prior version to break | Wired into dispatcher: `tools/workflow.py`, `workflows/base.py`, `core/config.py`, `tests/workflows/base/test_dispatcher.py`. | No migration — new workflow. |

---

## 🔄 In Progress / Next Up

Items N1–N10 are from the post-v1.3 collective review; items 1–7 are from earlier roadmap planning. Higher priority (P2) items N1, N2, N4, N8 are done (v1.4 + v1.5).

| # | Feature | Priority | Notes |
|---|---------|----------|-------|
| N1 | ~~**Reflect node between log and propose**~~ | ~~P2~~ | ✅ **Done in v1.5** — `node_reflect` between `log` and `route_after_log` calls planner LLM every `autoresearch_reflect_interval` iterations (default 5). Reflection stored in `state["reflect_notes"]` and surfaced to `node_propose`. |
| N2 | ~~**Stuck detector**~~ | ~~P2~~ | ✅ **Done in v1.4** — `route_after_log` checks metric plateau (last N within ε of best). |
| N3 | **Resume support** | P2 | Accept `branch` from caller, skip baseline, reload `experiment_history` from `results.tsv`. |
| N4 | ~~**Cross-run learning** (merged with prior item 5)~~ | ~~P2~~ | ✅ **Done in v1.5** — `node_decide` stores procedural memory on every discard; `node_propose` recalls procedural memories before proposing. |
| N5 | **Experiment output logging** | P3 | Per-iteration `{results_path}.d/{iteration}.log` with full stdout+stderr (not just 50KB tail). |
| N6 | **Cost/token tracking** | P3 | Per-iteration `tokens_in` / `tokens_out` / `cost_usd` in `experiment_history` entries. |
| N7 | **Checkpoint on every keep** | P3 | Save checkpoint after every keep so resume picks up from last-known-good. |
| N8 | ~~**Experiment deduplication**~~ | ~~P3~~ | ✅ **Done in v1.4** — `node_modify` md5-hashes `new_content`; duplicates skipped with `status="failed"`. Semantic dedup still deferred (cross-run learning in v1.5 N4 catches repeated failures but does not byte-similar dedup). |
| N9 | **Sandbox experiment subprocess** | P3 | Restricted filesystem for untrusted experiment code. |
| N10 | **Output truncation improvement** | P3 | Extract metric BEFORE truncation, or increase cap to 200KB. |
| 1 | ~~**Parallel experiments**~~ | ~~P2~~ | ✅ **Done in v1.6** — `parallel_count` param + node-internal N-way parallelism (propose / modify / run_experiment / evaluate / decide / log). Each iteration generates N proposals, runs N subprocesses concurrently, picks the best, commits it. Multi-GPU throughput. Default 1 = v1.5 single-experiment mode. |
| 2 | **Multi-metric optimization** | P3 | `metric_name: list[str]` + a Pareto-front decide node. |
| 3 | **Human-in-the-Loop (HiTL) checkpoints** | P3 | Pause the loop every N iterations for operator review. |
| 4 | **Parallel subagent dispatch for proposals** | P3 | PARALLEL subagents (one per hypothesis family); single-subagent dispatch done in v1.1. |
| 6 | **Adaptive `time_budget`** | P3 | Detect consistent timeouts → raise `time_budget` or surface a warning. |
| 7 | **Integration tests for `_call_planner` retry (P1-2)** | P3 | The 3× retry loop is unit-tested via mock but not exercised by integration tests. |

> Prior item 5 ("Cross-run learning", P3) merged into N4 above (promoted to P2 after the collective review).

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **Remove the indefinite loop** | The whole point — the loop runs until a human is satisfied. | Skip |
| 2 | **Skip the ledger** | `results.tsv` is the human audit trail; operators `tail -f` it. | Skip |
| 3 | **Modify `target_file` outside `node_modify`** | Atomic-write invariant — every modification goes through `tempfile + os.replace`. | Skip |
| 4 | **Auto-stop on convergence** | ✅ **Done in v1.4** — `route_after_log` checks last-N-discarded (convergence) AND last-N-within-ε (stuck). Was deferred as "no clean convergence signal"; v1.4 adds an OPT-IN detector (all defaults OFF → legacy behavior preserved). | ✅ Done |
| 5 | **Use the `git` tool for `decide`** | Adds tracing + compression noise. `subprocess.run` direct git calls are deliberately chosen. | Skip |
| 6 | **Multi-file modifications** | `target_file` is a single file (matches karpathy/autoresearch scope). | P3 future |
| 7 | **Non-Python target files** | `run_experiment` runs `python <target_file>`. Other runtimes would need a `runner` config field. | P3 future |

---

*Last updated: 2026-07-21 (v1.6). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
