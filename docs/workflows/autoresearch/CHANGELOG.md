<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2.2 | 2026-07-14 | **Phase 4g review — subagent dispatch doc fixes + version sync.** P1-2: Removed incorrect `_call()` fallback claim (no fallback exists). P2-2: `WORKFLOW_METADATA["version"]` synced from `"1.2"` to `"1.2.2"`. P3-2: `propose.py` docstring updated for v1.1+ subagent dispatch. |
| v1.2.1 | 2026-07-14 | **Bugfix batch.** P1-1: `route_after_setup` conditional edge — setup failure routes to END (was infinite loop). P1-2: Extracted `_extract_metric` to `helpers.py`. P2-1/P2-2/P2-3/P3-1: tracer tid, KEPT message direction, version sync, `git add` scoping. |
| v1.2 | 2026-07-12 | **[Hardening] Propose node hardened.** `_PROPOSE_JSON_SCHEMA` enforcement added. Removed duplicate `history_str` from `context` param. |
| v1.1 | 2026-07-12 | **Subagent dispatch in `propose` node.** `propose` now calls `agent(action="subagent", role="planner")` for isolated curated-context dispatch. No `_call()` fallback. |
| v1.0 | 2026-07-12 | **Initial implementation.** 7-node LangGraph StateGraph. Evolutionary experiment-driven optimization. 4 config knobs. 22/22 tests pass. |

---

### ⚠️ Breaking Changes

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

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Parallel experiments** | Branch N proposals, run all N subprocesses in parallel, keep the best. Would multiply iteration throughput on multi-GPU boxes. | P2 |
| 2 | **Multi-metric optimization** | Add `metric_name: list[str]` + a Pareto-front decide node. | P3 |
| 3 | **Human-in-the-Loop (HiTL) checkpoints** | Pause the loop every N iterations for operator review. | P3 |
| 4 | **Parallel subagent dispatch for proposals** | Single-subagent dispatch is done (v1.1). Replace with PARALLEL subagents (one per hypothesis family). | P3 |
| 5 | **Cross-run learning** | Store procedural memory when a proposal type repeatedly fails. | P3 |
| 6 | **Adaptive `time_budget`** | Detect if experiments consistently time out and either raise `time_budget` or surface a warning. | P3 |

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

*Last updated: 2026-07-14 (v1.2.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
