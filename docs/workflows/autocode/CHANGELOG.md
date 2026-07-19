<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v3.5** | 2026-07-19 | **F1 — Parallel subagent debug.** 4th debug path in `node_systematic_debug`, inserted between the swarm path and the single-subagent path. Opt-in via `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` (default OFF). Pipeline: (1) call planner LLM with `PARALLEL_HYPOTHESES_SYSTEM` (new in `constants.py`) to emit `AUTOCODE_PARALLEL_SUBAGENT_COUNT` (default 3) distinct hypotheses as a JSON array `{hypothesis_id, root_cause, proposed_fix, confidence}`; (2) dispatch N subagents in parallel via `concurrent.futures.ThreadPoolExecutor(max_workers=N)` — each subagent gets `SUBAGENT_VALIDATE_SYSTEM` (new in `constants.py`) + the hypothesis + the original debug context and is asked to validate/refine it via `agent(action="subagent", role="executor", ...)`; (3) aggregate by picking the verdict with the highest `hypothesis_confidence`; (4) store ALL verdicts in `debug.parallel_verdicts` (new field on `DebugState`) for observability; (5) mirror the winner into `debug.subagent_verdict` so downstream readers see a unified shape. Falls through to single-LLM debug on hypothesis-generation failure OR all-subagents-failed. Mutually exclusive with `AUTOCODE_SWARM_DEBUG` and `AUTOCODE_SUBAGENT_DEBUG` (INSTRUCTIONS.md NEVER DO #40 updated). New config flags `cfg.autocode_parallel_subagent_debug` + `cfg.autocode_parallel_subagent_count` in `core/config_backend/execution.py`. New state field `parallel_verdicts: list[dict]` in `DebugState` + `_default_state()`. New `_parallel_subagent_debug()` function in `workflows/autocode_impl/nodes/debug.py`. New `tests/workflows/autocode/test_parallel_subagent.py` (3 test classes, 4 tests — disabled-by-default contract, config-flag reading, count-configurable env-var override, function-existence + aggregation-callable check). Closes F1 from the v3.5 roadmap. |
| **v3.4** | 2026-07-19 | **#38 — Human-in-the-Loop (HiTL) approval gate.** New `node_hitl_gate` between `node_report` and `node_commit` (TDD path) + HiTL check at the top of `node_create_skill` (create_skill path). Opt-in via `AUTOCODE_HITL_ENABLED=1` (default OFF — gate is a no-op). Uses the **async-checkpoint-resume pattern**: when the gate fires and `hitl_approved` is False, saves a checkpoint via `save_checkpoint(tid, "hitl", state)`, returns `{"status": "awaiting_approval"}`, and routes to END. Operator reviews the changes, then resumes with `run_workflow("autocode", goal="...", resume=True, hitl_approved=True)` — the gate sees `hitl_approved=True` and passes through. New config flag `cfg.autocode_hitl_enabled` in `core/config_backend/execution.py`. New state field `hitl_approved: bool` in `AutocodeState` + `_default_state()`. New `route_after_hitl_gate(state)` in `routes.py`. `tools/workflow_ops/actions/run.py` + `tools/workflow_ops/types/autocode.py` + `tools/workflow_ops/helpers.py` forward `hitl_approved` end-to-end. `workflows/base.py` merges `hitl_approved` from kwargs on resume. Graph: 29 → 30 nodes (26 active + 3 backward-compat wrappers + 1 hitl_gate). `WORKFLOW_METADATA["version"]` → `"3.4"`. 9 new tests in `test_hitl_gate.py` + updated `test_graph.py` (29 → 30 nodes, 28 → 29 metadata entries). Closes #38 (was P2 — chose async-checkpoint-resume over sync-pause to avoid holding worker threads). |
| **v3.3** | 2026-07-19 | **#58 + F4 — standardize status-check pattern + configurable architecture-question threshold.** 2 items: **(#58)** Extracted `_should_skip_node(state)` helper in `helpers.py` with canonical `_SKIP_STATUSES = frozenset({"needs_clarification", "failed", "error", "skipped"})`. Migrated all 11 nodes from inline `state.get("status") in (...)` checks (which had 4 different sets — some missing `"error"`, some missing `"skipped"`). **(F4)** `_ARCHITECTURE_QUESTION_THRESHOLD` is now configurable via `AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD` env var (default 3). Was hardcoded to 3 in `debug.py`. 14 new tests in `test_should_skip_node.py`. |
| **v3.2** | 2026-07-19 | **6-LLM collective review hardening.** 19 fixes shipped (5 P0 + 6 P1 + 8 P2): **(P0-1)** `plan.py` + `debug.py` — lazy `kgraph` import (was top-level, crashed the module if `tree_sitter_languages` missing). **(P0-2)** `swarm_fallback.py` HIGH path now appends a `phase="swarm_fallback"` entry to `debug_history` + clears `last_test_error` (was: debug LLM couldn't see the swarm verdict + stuck-detection short-circuited on the stale prior error). **(P0-3)** `verify_decision.py:72` — `automated_checks_passed` default `True` → `False` (was: false-positive "HALLUCINATION DETECTED" on malformed JSON). **(P0-4)** `llm_review.py:65` — handles `test_code` as `list[str]` (was: `[:1000]` on a list returned a list slice + `repr()` garbage in the prompt). **(P0-5)** `apply_patches.py` — `dry_run` path now runs validation (path traversal, protected file, exists) before returning (was: silently masked security-validation failures). **(P1-1)** `state.py` — `test_code` type annotation `str` → `list[str]`. **(P1-2)** `state.py` — removed dead `MemoryState.context` field (declared but never populated). **(P1-3)** `run_pytest.py` — `timeout=120` → `cfg.sandbox_timeout`. **(P1-4)** `create_skill.py` — removed `sys.path.insert` leak (was never cleaned up; `spec_from_file_location` doesn't need it). **(P1-5)** `vcs_ops.py` — `_git_commit` returns structured dict `{"committed": bool, "sha": str, "reason": str}` (was: `None` for both "nothing to commit" and "error"). **(P1-6)** `helpers.py` — removed unreachable `raise last_error` + fixed comment typo. **(P2-1)** Extracted `_blast_radius_warning()` helper from `plan.py` + `debug.py` (was duplicated logic). **(P2-2)** Wired `_cleanup_old_autocode_runs` to `invoke_with_timeout()` (was never called — disk leak). **(P2-3)** Added `threading.Lock` to `get_graph()` singleton (race condition on concurrent access). **(P2-4)** `apply_patches.py` — added `"error"` to status-check set (was missing; could re-apply stale patches). **(P2-5)** `graph.py` — replaced inline `swarm_fallback` lambda with named `route_after_swarm_fallback()` in `routes.py` (was untestable inline lambda). **(P2-6)** Removed dead state fields `target_file`, `error_log`, `branch_name` from TypedDicts (verified: no node writes them). **(P2-7)** Fixed `patch.py` + `symbol_offload.py` docstring paths (were wrong paths in module docstrings). **(P2-8)** NEW `test_swarm_fallback_fixes.py` — 4 tests for the P0 fixes. |
| **v3.1.3** | 2026-07-18 | **F8 — symbol offloading in `summarize_context`.** `summarize_context.py` now offloads full `debug_history` to a per-trace file via `core/symbol_offload.py` when > 5 entries. State gets `debug_history_ref` SymbolRef for drill-down. Complements chonkie (within-field) with cross-field context management. |
| **v3.1.2** | 2026-07-18 | **Doc-drift + roadmap cleanup batch.** 10 shipped items: **(P0)** Removed dead `/autocode/graph` endpoint in `core/gateway_backend/routes/metrics.py` (stale import to deleted `mermaid.py`). **(P1)** Wired `trace_id=tid` to all 8 `_call()` callers (`classify.py`, `brainstorm.py`, `plan.py`, `tests.py`, `execute.py`, `debug.py`, `llm_review.py`, `create_skill.py`) — retry-exhaustion errors used to be unattributed (`trace_id=""`); now attributed to the workflow's trace. **(P1)** Fixed `create_skill` empty-file bug — LLM returning content under wrong key (`skill_code` instead of `skill_file`) silently wrote an empty file + set `skill_created=True`; now tries fallback keys (`skill_file` → `skill_code` → `code`) and rejects truly-empty output. **(P1)** Fixed `test_create_skill.py` mock — was using wrong key names (`skill_code`, `skill_description`), silently passing despite the bug above. **(P2)** Fixed `analyze_impact.py` literal `"unknown"` trace_id → `""` (consistency with every other node). **(P2)** Removed 13 unused imports across 12 files (`json`, `os`, `tempfile`, `Any`, `Optional`, `re`, `field`, `get_dependencies`). **(P2)** Fixed `ast.Str` deprecation in 4 test files (`test_branch.py`, `test_facade.py`, `test_graph.py` × 2) — `ast.Str` deprecated in 3.8, removed in 3.14. **(#34)** Removed `run_autocode_agent()` backward-compat shim — no production callers, only test refs; use `run_workflow("autocode")` directly. **(#36)** `create_skill` smoke-test — after writing the file: (a) `importlib.util.spec_from_file_location` import test (catches missing deps that AST parse misses), (b) `_git_commit(message=f"skill(autocode): {skill_name}")` to commit the new skill. **(#40)** Adaptive timeout by task type — `create_skill`=120s, `audit`=300s, `feature`=900s, `fix`/`refactor`/`edit`=600s. Opt-in via `AUTOCODE_ADAPTIVE_TIMEOUT=1` (default OFF — falls back to `cfg.autocode_graph_timeout`). |
| **v3.1.1** | 2026-07-16 | **Fix: `node_swarm_fallback` didn't reset `tdd_iteration` (collective review).** The node reset `tdd_status = ""` (allowing re-entry to the debug loop) but left `tdd_iteration` at `max_retries + 1` (the value that triggered the fallback). The debug node checks `if current_iteration > max_retries: bail` — so even with the outgoing edge to `node_systematic_debug`, the debug node would immediately bail. Now resets `tdd_iteration = 0` to give one full debug cycle. |
| **v3.1** | 2026-07-14 | **Debug loop improvements.** 4 items: (1) #42 Goal sanitization — max 2000 chars + strip control chars in `validate.py`. (2) #41 AST pre-check — `ruff --select E999` before pytest in `run_pytest.py` (saves ~30s on syntax errors). (3) F3 `debug_summary` in verify chain — `llm_review.py` injects compressed summary when `debug_history` > 5. (4) #48 Swarm fallback — new `node_swarm_fallback` node: when debug retries exhausted + `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, escalates to swarm consensus. HIGH confidence → one more debug cycle; LOW → verify chain. New config flag `AUTOCODE_SWARM_DEBUG_FALLBACK` (default OFF). Graph: 28 → 29 nodes. **[swarm v1.1 #17]** Smoke tests for both swarm-integration paths (`AUTOCODE_SWARM_DEBUG` enable/disable + `node_swarm_fallback` HIGH/LOW/unavailable) added in `tests/workflows/autocode/test_swarm_integration.py` (2 classes, 5 tests). |
| **v3.0** | 2026-07-14 | **Flat-field removal — Track M1 ✅ COMPLETE.** Removed ~32 legacy flat-field mirrors from `AutocodeState` + `_default_state()`. All 8 accessors simplified to 4-line sub-state-only reads. 13 ephemeral flat fields explicitly declared. See [SUBSTATE.md](SUBSTATE.md). |
| **v2.2** | 2026-07-14 | **Track M1 Batch 3c — `plan` sub-state.** 🎉 ALL 8 ACCESSORS NOW SAFE. 4 writers + 5 readers migrated. Fixed pre-existing `"steps"` → `"plan"` key mismatch. |
| **v2.3** | 2026-07-14 | **Track M1 Batch 3b — `files` sub-state.** 4 writers + 9 readers migrated. P1.8 hardening preserved. |
| **v2.1** | 2026-07-14 | **Track M1 Batch 3a — `vcs` sub-state.** 4 writers (12 RMW paths) + 7 readers migrated. Removed the v2.0.5 split-brain band-aid in `commit.py`. |
| **v2.5 + v2.6** | 2026-07-14 | **Track M1 Batch 2 — `debug` + `verify` sub-states.** `node_systematic_debug` + `node_verify_decision` migrated to RMW. `conftest.py::base_state` rewritten to use `_default_state()`. |
| **v2.4 + v2.7** | 2026-07-14 | **Track M1 Batch 1 — `impact` + `memory` sub-states.** Pattern proven for non-`tdd` sub-states. |
| **v2.0.5** | 2026-07-14 | **Phase 4g review.** Split-brain sub-state bug (`_get_vcs` returning stale `""`). Schema gaps fixed (`verification_passed`, `plan_state` TypedDict). 2 P1 + 3 P2 + 4 P3. |
| **v2.0.4** | 2026-07-14 | **Subagent debug path integration fixes.** `subagent_verdict` field now populated. `WORKFLOW_METADATA["version"]` synced. `_DEBUG_JSON_SCHEMA` deduped. |
| **v2.0.3** | 2026-07-12 | **[Hardening] Subagent debug path hardened.** `json_schema` + `temperature=retry_temp` passed to subagent call. Warning on empty `extract_json`. |
| **v2.0.2** | 2026-07-12 | **Subagent debug path** (`AUTOCODE_SUBAGENT_DEBUG=1`, default OFF). Third debug path: single-LLM → swarm → subagent. |
| **v2.0.1** | 2026-07-11 | **Hardening pass — cross-LLM review (3 P0 + 7 P1 + 3 P2).** Sub-state clobbering RMW fixes; `invoke_with_timeout` surfaces graph exceptions; markdown-fenced JSON via `_parse_json`; interruptible retry backoff. |
| **v2.0** | 2026-07-11 | **2.0 GA — Phase 7** (Ponytail + dead code + doc consolidation). 7-rung Lazy Dev ladder; `ponytail:` convention. All 7 phases ✅ COMPLETE. |
| v2.0-rc3 | 2026-07-11 | **Phase 6 — State migration** (sub-states primary). `_default_state()` populates all 8 sub-states. |
| v2.0-rc2 | 2026-07-11 | **Phase 5 — VCS consolidation.** Unified `vcs_ops.py`. |
| v2.0-rc1 | 2026-07-11 | **Phase 4 — Debug loop refactor.** 4-phase `DEBUG_SYSTEM`. `node_summarize_context`. 27 → 28 nodes. |
| v2.0-beta | 2026-07-11 | **Phase 3 — Node decomposition.** 3 god nodes → 10 focused nodes. 17 → 27 nodes. |
| v2.0-alpha | 2026-07-11 | **Phases 1+2 — Foundation + state redesign.** `core/json_extract.py`; cancellation flag. 8 sub-state TypedDicts + 8 accessors. |
| v1.4 | 2026-07-11 | Pre-2.0 hardening + dead code cleanup. Cross-LLM review (4 LLMs) — 4 P0 + 7 P1 + 8 P2. Deleted `mermaid.py`, `test_mapper.py`, `test_runner.py`. |
| v1.3 | 2026-07-10 | GitHub + Swarm integration. `node_publish`. 6 new config flags (all default OFF). |
| v1.2 (legacy) | 2026-07-08 | JSON schema enforcement. `debug.py` passes `json_schema` via `_call()`. (Note: this is the ORIGINAL v1.2 from the pre-v2.0 era. The row dated 2026-07-18 above labeled `v3.1.2` is the doc-drift + roadmap cleanup batch — it is NOT a regression to v1.x; the earlier `v1.2` label was a naming mistake that was corrected in v3.2.) |
| v1.1.2 | 2026-07-06 | Small-fix batch: #39 stuck detection, #44 structured artifacts, #46 multi-file git-diff, #47 dry-run actually dry. |
| v1.1 | 2026-07-06 | Facade fix + `WORKFLOW_METADATA` + routing fixes. Facade was unreachable for 2 versions. |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items). |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items). |
| v1.0 | — | Released — 17-node LangGraph StateGraph. |

---

### ✅ Completed Roadmap Items

| # | Feature | Shipped |
|---|---------|---------|
| ✅ F8 | **Mermaid symbol context offloading** | ✅ **Shipped in v3.1.3** — `summarize_context.py` now offloads full `debug_history` to a per-trace file via `core/symbol_offload.py` when > 5 entries. State gets `debug_history_ref` SymbolRef for drill-down. Complements chonkie (within-field) with cross-field context management. |
| ✅ #17 | **Swarm ↔ autocode smoke test** | ✅ **Shipped in swarm v1.1** — `tests/workflows/autocode/test_swarm_integration.py` (2 classes, 5 tests) covers: (a) `TestSwarmDebugIntegration` — `_swarm_debug_consensus` is called when `cfg.autocode_swarm_debug=True`, NOT called when `False`; (b) `TestSwarmFallbackIntegration` — `node_swarm_fallback` HIGH-confidence path (resets `tdd.status=""` for one more cycle + records `swarm_verdict`), LOW-confidence path (`status="failed"` + records `swarm_verdict`), and swarm-unavailable path (`status="failed"`, no verdict). Uses pytest-mock `mocker` fixture. Closes the long-standing gap noted in the swarm v1.0.2 P0-1 fix — the autocode swarm integration was non-functional from v1.3 → v1.0.2 because of interface bugs (wrong param names, wrong result keys); the smoke test now locks the contract. |
| ✅ #48 | **Swarm ↔ autocode debug loop integration** | ✅ **Shipped in v3.1** — `node_swarm_fallback` (gated on `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, default OFF). Escalates to swarm consensus when debug retries exhausted; HIGH confidence → one more debug cycle, LOW/unavailable → verify chain. |
| ✅ #41 | **AST/linter pre-check before pytest** | ✅ **Shipped in v3.1** — `ruff --select E999` syntax-only pre-check in `node_run_pytest` (saves ~30s on syntax errors). Non-fatal if ruff not installed. |
| ✅ #42 | **Goal sanitization** | ✅ **Shipped in v3.1** — `node_validate_input` now enforces max 2000 chars + strips control chars; returns cleaned task in state update. |
| ✅ F3 | **`debug_summary` consumption in verify chain** | ✅ **Shipped in v3.1** — `node_llm_review` injects `debug_summary` into the verify LLM prompt when `debug_history` > 5 entries. |
| ✅ #34 | **Remove `run_autocode_agent()` backward-compat shim** | ✅ **Shipped in v3.1.2** — no production callers, only test refs. External callers now use `run_workflow(workflow_type="autocode", goal="...", **kwargs)` directly. `_shape_artifacts(final_state)` is still exported from `workflows.autocode` for callers that want structured output. See API.md § "Facade". |
| ✅ #36 | **`create_skill` smoke-test import + git commit** | ✅ **Shipped in v3.1.2** — after writing the file: (a) `importlib.util.spec_from_file_location` import test (catches missing deps that `ast.parse` misses — `ast.parse` only verifies syntax, not that imports resolve); (b) `_git_commit(message=f"skill(autocode): {skill_name}")` so the workflow's git history captures the new skill. Import-failure path deletes the broken file + returns `status="failed"`. Git-commit failure is non-fatal (`tracer.warning`). |
| ✅ #40 | **Adaptive timeout by task type** | ✅ **Shipped in v3.1.2** — `invoke_with_timeout()` now consults `cfg.autocode_adaptive_timeout` (env: `AUTOCODE_ADAPTIVE_TIMEOUT=1`, default OFF). When ON, per-task-type timeout map overrides `cfg.autocode_graph_timeout`: `create_skill`=120s, `audit`=300s, `feature`=900s, `fix`/`refactor`/`edit`=600s. Unknown `task_type` falls back to `cfg.autocode_graph_timeout`. Default OFF preserves backward compat — opt-in only. See API.md § "Adaptive Timeout". |
| ✅ #38 | **Human-in-the-Loop (HiTL) approval gate** | ✅ **Shipped in v3.4** — New `node_hitl_gate` between `node_report` and `node_commit` (TDD path) + HiTL check at the top of `node_create_skill` (create_skill path). Opt-in via `AUTOCODE_HITL_ENABLED=1` (default OFF). Uses async-checkpoint-resume pattern (option b from the design notes) — chosen over sync-pause (option a) to avoid holding worker threads. See API.md § "HiTL Approval Gate" + INSTRUCTIONS.md NEVER DO #50 + ALWAYS DO #50. |

---

### ⚠️ Breaking Changes

#### v3.1.2 — 2026-07-18

| Change | Impact | Migration |
|--------|--------|-----------|
| `run_autocode_agent()` shim removed from `workflows/autocode.py` | External callers that imported `run_autocode_agent` now `ImportError`. The module now exports `build_graph`, `get_graph`, `WORKFLOW_METADATA`, `AutocodeState`, `_default_state` only. | Call `run_workflow(workflow_type="autocode", goal="...", **kwargs)` from `workflows/base.py` instead. For structured artifacts, call `_shape_artifacts(final_state)` (still exported from `autocode.py`) on the returned dict. |
| `/autocode/graph` endpoint removed from `core/gateway_backend/routes/metrics.py` | The HTTP endpoint that returned the mermaid diagram (via the deleted `mermaid.py`) is gone. Any MCP/HTTP client hitting `/autocode/graph` now gets a 404. | Use `WORKFLOW_METADATA` (exported from `workflows.autocode`) — it carries the same node/edge info that the endpoint used to return. |
| `_call()` now requires `trace_id=tid` from every caller | Functionally backward-compatible (`trace_id` was already an optional kwarg defaulting to `""`), but observability expectations changed: retry-exhaustion errors are now attributed to the workflow's trace. Nodes that forget `trace_id=tid` will produce unattributed tracer errors (regression in observability, not correctness). | All 8 in-tree callers updated. New `_call()` callers MUST pass `trace_id=tid` (see INSTRUCTIONS.md NEVER DO #46 + ALWAYS DO #43). |
| `node_create_skill` rejects empty `skill_file` content | Was: silently wrote empty file + set `skill_created=True`. Now: tries fallback keys (`skill_file` → `skill_code` → `code`), then returns `{"status": "failed", "error": "LLM returned empty skill_file content"}`. | Tests that mocked `data = {"skill_code": "..."}` (wrong key) now FAIL — they must use `skill_file`. Update mock fixtures. |

#### v3.0 — 2026-07-14

| Change | Impact | Migration |
|--------|--------|-----------|
| ~32 legacy flat-field mirrors removed from `AutocodeState` + `_default_state()` | Direct `state.get("tdd_status")`, `state.get("branch")`, `state.get("modified_files")`, etc. now return `None` — the flat fields no longer exist. | Use accessors (`_get_tdd`, `_get_vcs`, `_get_files`, etc.) for all sub-state reads. See [SUBSTATE.md](SUBSTATE.md). |
| All 8 accessor functions simplified to 4-line sub-state-only reads | Legacy-fallback branches removed. Accessors now ONLY read from sub-states. | No migration if already using accessors. If calling `_get_vcs(state, "branch", "main")` expecting flat fallback — it now returns the sub-state value or `default` only. |
| `test_results` removed from `TDDState` | Stays flat-only (ephemeral). | Read via `state.get("test_results", {})` — no accessor. |
| `input_files` removed from `FilesState` | Was just a mirror of the core `files` flat field. | `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly. |
| Node returns must write sub-state only via RMW | Flat-field mirrors in node returns (e.g., `{"modified_files": [...]}`) are no longer valid. | Write `{"files_state": current_files}` instead of `{"modified_files": [...]}`. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern". |

#### v2.0 — 2026-07-11

| Change | Impact | Migration |
|--------|--------|-----------|
| `helpers._write_files()` DELETED | Dead code (never called by any node). | Use `node_apply_patches` + `node_write_new_files` + `node_persist_artifacts`. |
| API.md split → API.md + NODES.md | API.md was too large. | NODES.md is now the per-node reference; API.md is facade + state accessors. |
| `WORKFLOW_METADATA["version"]` → `"2.0"` (GA) | Version bump. | No migration. |

#### v2.0-beta — 2026-07-11

| Change | Impact | Migration |
|--------|--------|-----------|
| 3 "god nodes" split into 10 focused nodes | `node_write_files`, `node_verify`, `node_publish` are now backward-compat wrappers (registered, NOT wired). | Import split nodes directly. See INSTRUCTIONS.md #47. |

#### v1.4 — 2026-07-11

| Change | Impact | Migration |
|--------|--------|-----------|
| Deleted `mermaid.py`, `test_mapper.py`, `test_runner.py` | All three were unused. | No migration — `WORKFLOW_METADATA` serves the mermaid purpose; `analyze_impact` imports from `core.kgraph.test_mapper`; `node_run_tests` has its own test execution. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 35 | `invoke_with_timeout` daemon-thread zombie risk | v2.0.1 surfaces graph crashes (P0.3). The daemon thread still can't be killed — Python's `threading` doesn't support `Thread.kill()`. Full process-level termination needs `multiprocessing.Process` (terminate-able) — deferred because it requires re-architecting the invocation path (pickling state across process boundary, IPC for the result dict, signal handling for SIGTERM). | P2 |
| ~~#38~~ | ✅ v3.4 — `node_hitl_gate` + `route_after_hitl_gate` + `AUTOCODE_HITL_ENABLED=1` + `hitl_approved` state field + checkpoint-resume. | ✅ Done |
| ~~F1~~ | ✅ v3.5 — Parallel subagent debug (`AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`) + `AUTOCODE_PARALLEL_SUBAGENT_COUNT` env var (default 3) + `PARALLEL_HYPOTHESES_SYSTEM` / `SUBAGENT_VALIDATE_SYSTEM` prompts + `_parallel_subagent_debug()` function + `parallel_verdicts` state field + `ThreadPoolExecutor`-based dispatch + confidence-weighted aggregation. | ✅ Done |
| F7 | **Lazy Dev full audit mode** (`task_type="audit"` whole-repo scan) | **DEFERRED — needs detailed design (see INSTRUCTIONS.md § "Deferred Roadmap Items" for full design notes).** The 7-rung Lazy Dev ladder shipped in v2.0 (per-task), but `task_type="audit"` currently routes through the SAME TDD pipeline as `feature` — it doesn't do a whole-repo scan. Full audit mode needs: (1) a new `node_audit_scan` node that walks `project_root` and batches files through `core.kgraph.ast_parser`; (2) a `node_audit_report` node that summarizes findings (dead code, unused imports, missing types, complexity hotspots); (3) routing changes — `route_after_classify` sends `audit` to the audit pipeline instead of `node_brainstorm`; (4) audit-specific prompts; (5) **design decision**: does audit skip TDD? (current keeps TDD; a full-scan would bypass TDD because there's no single "feature under test"); (6) **dependency**: kgraph coverage — if the project isn't indexed, `get_callers` returns empty and blast-radius is meaningless. Inspiration: [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) — the 7-rung ladder is already shipped (v2.0); full audit mode extends it from per-task to whole-repo. Estimated complexity: **L** (new nodes + routing + prompts + design decision + kgraph coverage check). See INSTRUCTIONS.md § "🔮 Deferred Roadmap Items → F7 Lazy Dev full audit mode" for the full design write-up. | P2 |
| ~~#58~~ | ✅ v3.3 — `_should_skip_node(state)` helper + all 11 nodes migrated. | ✅ Done |
| ~~F4~~ | ✅ v3.3 — `AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD` env var (default 3). | ✅ Done |
| #57 | **Per-node dedicated test files** | **Added in v3.2 (collective review).** 14 nodes still lack dedicated per-node test files. The pattern in `tests/workflows/autocode/` is one file per concern; new nodes added in v2.0–v3.2 (e.g., `swarm_fallback.py`, `verify_decision.py`, `apply_patches.py`, `write_new_files.py`, `persist_artifacts.py`, `summarize_context.py`, `run_pytest.py`, `run_lint.py`, `llm_review.py`, `push.py`, `create_pr.py`, `merge_pr.py`, `branch.py`, `memory.py`) are tested via integration tests (`test_routes.py`, `test_safety.py`, `test_verify.py`) rather than per-node unit tests. Goal: each node has a `test_<node_name>.py` with focused unit tests for its skip-conditions, error paths, and state-update shape. | P2 |
| #58 | **Standardize status-check pattern** | **Added in v3.2 (collective review).** The `status in {needs_clarification, failed, skipped, error}` skip-condition pattern is duplicated across `node_apply_patches`, `node_write_new_files`, `node_persist_artifacts`, `node_run_pytest`, `node_run_lint`, `node_llm_review`, `node_verify_decision`, `node_push`, `node_create_pr`, `node_merge_pr`, `node_create_skill`. v3.2 P2-4 added `"error"` to `apply_patches.py`'s set; the remaining nodes may have the same drift. Extract a `_should_skip_node(state) -> bool` helper or formalize the canonical set in `helpers.py`. | P2 |
| 32 | IDE integration | LSP or VS Code extension for autocode. | P3 |
| 56 | v3.x cleanup: remove backward-compat wrappers | `node_write_files`, `node_verify`, `node_publish` (registered but NOT wired). Blocked by tests importing them directly. | P3 |
| F2 | Autoresearch pre-flight before plan | Wire a `node_autoresearch_preflight` before `node_brainstorm`. | P3 |
| F4 | Adaptive `_ARCHITECTURE_QUESTION_THRESHOLD` | Currently hardcoded to 3. Make configurable per task type (`create_skill`=1, `feature`=5). | P3 |
| F5 | Procedural memory recall before debug | Cross-run recall (read past failures before debug) still pending. | P3 |
| F6 | Stream `phase` transitions to MCP client | The `phase` field is currently internal. Stream it to the MCP client so the user sees debug progress. | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | Remove TDD-first | TDD ensures test coverage. | Skip |
| 2 | Remove debug loop | Single-pass code generation misses edge cases. | Skip |
| 3 | Remove impact analysis | Blast radius analysis prevents unintended side effects. | Skip |
| 4 | Remove git integration | Git branches and commits are essential. | Skip |
| 5 | Remove memory integration | Procedural memory improves future performance. | Skip |
| 6 | Real-time collaboration | Multi-user editing requires complex state sync. | Skip |
| 7 | Support non-Python languages | Workflow is designed for Python. Other languages need tree-sitter per-lang. | Skip |
| 8 | Swarm verdict non-blocking flag | `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag deferred. | P3 |
| 9 | Per-task config flag overrides | Config flags are global; per-task overrides deferred. | P3 |
| 10 | `AUTOCODE_AUTO_MERGE_METHOD` config | Currently hardcoded to squash. | P3 |
| 11 | Pull failure fail-fast config | Currently non-blocking; fail-fast vs graceful-skip config deferred. | P3 |
| 12 | Richer PR body | Test results, diff summary, impact warnings — deferred. | P3 |
| 13 | Push/PR transient-failure retry | Currently no retry on push/PR failure. | P3 |
| 14 | `git pull --rebase` | Not supported. | P3 |

---

*Last updated: 2026-07-19 (v3.5 — F1 parallel subagent debug).*
