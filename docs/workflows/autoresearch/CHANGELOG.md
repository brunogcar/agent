<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.3.0 | 2026-07-15 | **Hardening batch (5-reviewer collective audit).** P0-1: graph order swapped `evaluate → log → decide` → `evaluate → decide → log` (log was reading pre-decide status → ledger ALWAYS said "discard"). P0-2: `GraphRecursionError` caught explicitly (was: generic `except Exception` → `status="failed"` + state lost). P1-1: empty SHA → discard (was: `status="keep"` with empty commit). P1-2: `_call_planner` retries 3× with 2s/4s backoff. P1-3: path traversal + protected-file guard in `node_modify`. P1-4: `_git_reset_hard` safety guard (refuses no-root / non-repo). P1-5: target-file content capped at `cfg.autocode_max_file_chars` (6000). P2-1: shared `run_target_subprocess` in helpers.py (was duplicated). P2-2: forward ALL params (metric_name, metric_direction, time_budget, branch, results_path) through type handler. P2-3: `experiment_history` capped at 100. P2-4: removed 4 dead conftest fixtures. P2-5: fake conditional edges (`route_after_evaluate` / `route_after_decide`) replaced with direct edges; both routers deleted. |
| v1.2.2 | 2026-07-14 | **Phase 4g review — subagent dispatch doc fixes + version sync.** P1-2: Removed incorrect `_call()` fallback claim (no fallback exists). P2-2: `WORKFLOW_METADATA["version"]` synced from `"1.2"` to `"1.2.2"`. P3-2: `propose.py` docstring updated for v1.1+ subagent dispatch. |
| v1.2.1 | 2026-07-14 | **Bugfix batch.** P1-1: `route_after_setup` conditional edge — setup failure routes to END (was infinite loop). P1-2: Extracted `_extract_metric` to `helpers.py`. P2-1/P2-2/P2-3/P3-1: tracer tid, KEPT message direction, version sync, `git add` scoping. |
| v1.2 | 2026-07-12 | **[Hardening] Propose node hardened.** `_PROPOSE_JSON_SCHEMA` enforcement added. Removed duplicate `history_str` from `context` param. |
| v1.1 | 2026-07-12 | **Subagent dispatch in `propose` node.** `propose` now calls `agent(action="subagent", role="planner")` for isolated curated-context dispatch. No `_call()` fallback. |
| v1.0 | 2026-07-12 | **Initial implementation.** 7-node LangGraph StateGraph. Evolutionary experiment-driven optimization. 4 config knobs. 22/22 tests pass. |

---

### ⚠️ Breaking Changes

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

Items N1–N10 are from the post-v1.3 collective review; items 1–7 are from earlier roadmap planning. Higher priority (P2) items are scheduled for v1.4.

| # | Feature | Priority | Notes |
|---|---------|----------|-------|
| N1 | **Reflect node between log and propose** | P2 | LLM looks at full history + adapts strategy before next proposal. |
| N2 | **Stuck detector** | P2 | If last N experiments all discarded within ε, surface warning (doesn't auto-exit). |
| N3 | **Resume support** | P2 | Accept `branch` from caller, skip baseline, reload `experiment_history` from `results.tsv`. |
| N4 | **Cross-run learning** (merged with prior item 5) | P2 | Store procedural memory when a proposal type repeatedly fails. Persistent cache keyed by `{goal, target_file_hash, proposal_description_hash}`. |
| N5 | **Experiment output logging** | P3 | Per-iteration `{results_path}.d/{iteration}.log` with full stdout+stderr (not just 50KB tail). |
| N6 | **Cost/token tracking** | P3 | Per-iteration `tokens_in` / `tokens_out` / `cost_usd` in `experiment_history` entries. |
| N7 | **Checkpoint on every keep** | P3 | Save checkpoint after every keep so resume picks up from last-known-good. |
| N8 | **Experiment deduplication** | P3 | Hash check on `new_content` to skip duplicate proposals (semantic dedup deferred). |
| N9 | **Sandbox experiment subprocess** | P3 | Restricted filesystem for untrusted experiment code. |
| N10 | **Output truncation improvement** | P3 | Extract metric BEFORE truncation, or increase cap to 200KB. |
| 1 | **Parallel experiments** | P2 | Branch N proposals, run all N subprocesses in parallel, keep the best. Multi-GPU throughput. |
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
| 4 | **Auto-stop on convergence** | No clean convergence signal (unlike `deep_research` cosine similarity). Human judgment required. | Skip |
| 5 | **Use the `git` tool for `decide`** | Adds tracing + compression noise. `subprocess.run` direct git calls are deliberately chosen. | Skip |
| 6 | **Multi-file modifications** | `target_file` is a single file (matches karpathy/autoresearch scope). | P3 future |
| 7 | **Non-Python target files** | `run_experiment` runs `python <target_file>`. Other runtimes would need a `runner` config field. | P3 future |

---

*Last updated: 2026-07-20 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
