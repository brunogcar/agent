<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

Version history (newest first), completed roadmap items (1-line each), open roadmap, deferred items. For per-node reference see [NODES.md](NODES.md); for AI editing rules see [INSTRUCTIONS.md](INSTRUCTIONS.md).

---

## 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v3.11.1** | 2026-07-22 | **B2 regression fix — `route_after_hitl_gate` allow-list.** The v3.11 B2 fix introduced `status=hitl_checkpoint_failed` but the router (`routes.py:112-120`, unchanged by v3.11) only checked `status == "awaiting_approval"` → `hitl_checkpoint_failed` fell through to `return "node_commit"`, **bypassing HiTL entirely on a plain disk/IO hiccup** — strictly worse than the original bug B2 was meant to fix. Fixed with an allow-list approach: only `"running"`/`"success"`/empty/None proceed to `node_commit`; everything else (awaiting_approval, hitl_checkpoint_failed, failed, error, or any future new status) routes to END. This fails safe by default — any future status added to `node_hitl_gate` routes to END instead of silently committing. 5 new routing tests in `test_hitl_gate.py` (TestHitlRouting) covering the end-to-end path (node return → router decision) that v3.11 missed. Found by Claude post-commit review of `d59c736`. |
| **v3.11** | 2026-07-22 | **Claude review fixes — 3 P1 + 4 P2 + 1 P3.** **B1 (P1):** Adaptive timeout now propagated to `_remaining_timeout()` — `set_graph_start_time(timeout)` accepts the resolved per-run timeout + `_remaining_timeout` reads it instead of the static `cfg.autocode_graph_timeout`. Pre-v3.11, a feature task at 400s elapsed (real 900s adaptive budget) computed `remaining = 300 - 400 = -100 → 1`, giving pytest a spurious 1-second timeout. Affects 3 of 6 task types (feature=900s, fix/refactor/edit=600s vs 300s static). 2 new tests in `test_invoke_with_timeout.py` + 2 existing tests in `test_cancellation_aware.py` updated. **B2 (P1):** `node_hitl_gate` surfaces checkpoint-save failures (was: bare `except Exception: pass` → returned `awaiting_approval` as if the pause succeeded → on resume, no checkpoint found → full restart from `node_classify_task`, re-executing LLM code generation, potentially producing a different implementation than the human reviewed). Now returns `status=hitl_checkpoint_failed` + `error` so `route_after_hitl_gate` routes to END. 2 new tests in `test_hitl_gate.py`. **B3 (P1):** Audit mode no longer silently truncates to 200 files — `_walk_python_files` now walks ALL files first (up to `max_files_to_scan=2000`), THEN sorts by line count, THEN caps at 200. Pre-v3.11, the walk broke at 200 in directory-traversal order, so the subset was arbitrary + dead-code analysis ran against it (falsely flagging files whose importers lived in unscanned directories). New `truncated`/`files_scanned`/`files_total` fields in `scan_results`; dead-code import scan now uses the FULL scanned set. 3 new tests in `test_audit_mode.py`. **B4 (P2):** `WORKFLOW_METADATA["version"]` bumped 3.8 → 3.11 (was stale — CHANGELOG at v3.10; inline comment misattributed centralize-workflow-utils to v3.8 when it was actually v3.10; v3.8 is per-node test coverage #57). **B5 (P2):** `node_systematic_debug`'s 3 LLM-dispatch paths (swarm, parallel-subagent, single-subagent) now check `is_cancellation_requested()` before dispatching — was: no check, so in-flight `swarm()`/`agent()` calls outlived the graph deadline. The v3.6 "≤1s past graph deadline" claim only covered subprocess calls, not LLM dispatches. 3 new tests in `test_debug_b5.py`. **B6 (P2):** Future-dated docs (2026-07-25) fixed to actual commit date (2026-07-21 for v3.10) + all 5 autocode doc footers bumped to v3.11. **B7 (P2):** `git_ops.py` docstring clarified — was "backward-compat wrapper" (misleading; it's a name-only alias, NOT signature-compatible). Delegates to **git tool v1.3**. 4 new tests in `test_git_ops_b7.py`. **B8 (P3):** Orphaned `branch_name` removed from `_default_state()` vcs dict (VCSState TypedDict no longer declares it since v1.4 P2). 3 new tests in `test_state_b8.py`. 17 new tests across 5 test files. |
| **v3.10** | 2026-07-21 | **Centralize-workflow-utils refactor (Phases A + B + C).** (Phase A) `core/atomic_write.py` extracted from 4 duplicated implementations — autoresearch `modify.py::_atomic_write`, autocode `patch.py::apply_patch`/`apply_patches`, autocode `write_new_files.py` node, autocode `create_skill.py` node. All 4 call sites updated. (Phase B) `_git_commit` + `_git_create_branch` moved from `vcs_ops.py` to `tools/git_ops/workflow_helpers.py` (new module — `commit`, `create_branch`, `reset_hard`). `vcs_ops.py` now only contains github_* + swarm helpers. `git_ops.py` is a name-only alias re-exporting from `workflow_helpers` (aliases `_git_commit = commit`, `_git_create_branch = create_branch`). Signature change: `(project_root, message, target_file, tid)` (project_root FIRST). All callers updated: `commit.py`, `create_skill.py`, `branch.py`. (Phase C) `core/backoff_retry.py` extracted from autocode `_call()` + autoresearch `_call_planner()` retry loops. `_call` passes `cancellation_check=is_cancellation_requested`; `_call_planner` passes `cancellation_check=lambda: is_workflow_cancelled(tid)` (None when tid empty). Return types NOT unified (autocode str, autoresearch tuple). 26 new tests across `tests/core/test_atomic_write.py` (7), `tests/core/test_backoff_retry.py` (6), `tests/tools/git/test_workflow_helpers.py` (9), `tests/workflows/autoresearch/test_cancellation.py` (4). |
| **v3.9** | 2026-07-19 | **Minimax follow-up review — 6 fixes.** (Bug A) `_graph_start_time` module global → `threading.local()` — concurrent workflows no longer race on the start time. (Bug C) `parallel_verdicts` schema documented in SUBSTATE.md. (Bug E) Removed dead `execution_notes` field from state + execute.py. (Bug F) `sorted(set(callers))[:5]` for deterministic blast-radius ordering. (Bug G) Removed dead `_get_tdd` import from graph.py. (Doc) Documented debug chain priority order in INSTRUCTIONS.md. |
| **v3.8** | 2026-07-19 | **#57 — Per-node test coverage.** 4 new test files covering 14 previously-untested nodes (`test_nodes_pre_tdd.py` — 12 tests, `test_nodes_verify.py` — 16 tests, `test_nodes_publish.py` — 17 tests, `test_nodes_write.py` — 17 tests). 2 merges (`test_call_trace_id.py` → `test_helpers.py`, `test_swarm_fallback_fixes.py` → `test_swarm_integration.py`). Total: 186 → 248 tests (+62 new, 0 net from merges). |
| **v3.7** | 2026-07-19 | **F7 — Lazy Dev full audit mode.** `task_type="audit"` routes to a dedicated read-only pipeline bypassing TDD. Two new nodes: `node_audit_scan` (walks `project_root`, enumerates `.py` files, finds dead code via AST importer analysis, missing type hints, lazily queries kgraph for dependency maps) → `node_audit_report` (planner LLM with `AUDIT_REPORT_SYSTEM` produces structured report). `route_after_classify` routes `audit` → `node_audit_scan` (was: → `node_validate_input`). Graph: 30 → 32 nodes. New `AUDIT_REPORT_SYSTEM` prompt in `constants.py`. New `audit_scan: dict` field in `ImpactState`. 9 new tests in `test_audit_mode.py`. |
| **v3.6** | 2026-07-19 | **#35 — incremental zombie fix (cancellation-aware subprocess calls).** `run_pytest.py`, `run_lint.py`, `run_tests.py` wrap every `subprocess.run(...)` with: pre-check `is_cancellation_requested()`, deadline-aware timeout via `_remaining_timeout(default)`, post-check `is_cancellation_requested()`. New helpers in `helpers.py`: `set_graph_start_time()`, `_remaining_timeout(default)`, `_cancelled()`. Bounds daemon-thread zombie linger to ≤1s past the graph deadline. Full process-level termination still deferred (see roadmap § 35). New tests in `test_cancellation_aware.py`. |
| **v3.5** | 2026-07-19 | **F1 — Parallel subagent debug.** 4th debug path in `node_systematic_debug`, inserted between the swarm path and the single-subagent path. Opt-in via `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` (default OFF). Pipeline: planner LLM emits `AUTOCODE_PARALLEL_SUBAGENT_COUNT` (default 3) hypotheses via `PARALLEL_HYPOTHESES_SYSTEM` → `ThreadPoolExecutor(max_workers=N)` dispatches N `agent(action="subagent")` calls using `SUBAGENT_VALIDATE_SYSTEM` → aggregate by descending `hypothesis_confidence` → store ALL verdicts in `debug.parallel_verdicts`, mirror winner into `debug.subagent_verdict`. Falls through on hypothesis-generation failure OR all-subagents-failed. Mutually exclusive with `AUTOCODE_SWARM_DEBUG` and `AUTOCODE_SUBAGENT_DEBUG`. New config flags `cfg.autocode_parallel_subagent_debug` + `cfg.autocode_parallel_subagent_count`. New `_parallel_subagent_debug()` function in `nodes/debug.py`. New tests in `test_parallel_subagent.py`. |
| **v3.4** | 2026-07-19 | **#38 — Human-in-the-Loop (HiTL) approval gate.** New `node_hitl_gate` between `node_report` and `node_commit` (TDD path) + HiTL check at the top of `node_create_skill` (create_skill path). Opt-in via `AUTOCODE_HITL_ENABLED=1` (default OFF). Uses async-checkpoint-resume pattern: when the gate fires and `hitl_approved` is False, saves a checkpoint via `save_checkpoint(tid, "hitl", state)`, returns `{"status": "awaiting_approval"}`, routes to END. Operator resumes with `run_workflow("autocode", goal="...", resume=True, hitl_approved=True)`. New config flag `cfg.autocode_hitl_enabled`. New state field `hitl_approved: bool`. New `route_after_hitl_gate(state)` in `routes.py`. End-to-end param threading through `tools/workflow_ops/`. Graph: 29 → 30 nodes. 9 new tests in `test_hitl_gate.py`. |
| **v3.3** | 2026-07-19 | **#58 + F4 — standardize status-check pattern + configurable architecture-question threshold.** (#58) Extracted `_should_skip_node(state)` helper in `helpers.py` with canonical `_SKIP_STATUSES = frozenset({"needs_clarification", "failed", "error", "skipped"})`. Migrated all 11 nodes from inline `state.get("status") in (...)` checks (which had 4 different sets). (F4) `_ARCHITECTURE_QUESTION_THRESHOLD` is now configurable via `AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD` env var (default 3). 14 new tests in `test_should_skip_node.py`. |
| **v3.2** | 2026-07-19 | **6-LLM collective review hardening.** 19 fixes (5 P0 + 6 P1 + 8 P2). Highlights: (P0-1) `plan.py` + `debug.py` lazy `kgraph` import (was top-level, crashed the module if `tree_sitter_languages` missing). (P0-2) `swarm_fallback.py` HIGH path now appends `phase="swarm_fallback"` entry to `debug_history` + clears `last_test_error`. (P0-3) `verify_decision.py:72` — `automated_checks_passed` default `True` → `False` (false-positive "HALLUCINATION DETECTED"). (P0-4) `llm_review.py` handles `test_code` as `list[str]`. (P0-5) `apply_patches.py` `dry_run` path now runs validation. (P1-5) `vcs_ops.py` `_git_commit` returns structured dict `{"committed", "sha", "reason"}`. (P2-1) Extracted `_blast_radius_warning()` helper. (P2-2) Wired `_cleanup_old_autocode_runs` to `invoke_with_timeout()`. (P2-3) `threading.Lock` on `get_graph()` singleton. (P2-5) Named `route_after_swarm_fallback()` in `routes.py`. 14 other localized fixes — see git history. |
| **v3.1.3** | 2026-07-18 | **F8 — symbol offloading in `summarize_context`.** `summarize_context.py` now offloads full `debug_history` to a per-trace file via `core/symbol_offload.py` when > 5 entries. State gets `debug_history_ref` SymbolRef for drill-down. |
| **v3.1.2** | 2026-07-18 | **Doc-drift + roadmap cleanup batch.** 10 items: (P0) Removed dead `/autocode/graph` endpoint in `core/gateway_backend/routes/metrics.py`. (P1) Wired `trace_id=tid` to all 8 `_call()` callers. (P1) Fixed `create_skill` empty-file bug with fallback keys (`skill_file` → `skill_code` → `code`). (P1) Fixed `test_create_skill.py` mock key names. (P2) Fixed `analyze_impact.py` literal `"unknown"` trace_id → `""`. (P2) Removed 13 unused imports across 12 files. (P2) Fixed `ast.Str` deprecation in 4 test files. (#34) Removed `run_autocode_agent()` backward-compat shim. (#36) `create_skill` smoke-test: `importlib.util.spec_from_file_location` import test + `_git_commit(message=f"skill(autocode): {skill_name}")`. (#40) Adaptive timeout by task type — opt-in via `AUTOCODE_ADAPTIVE_TIMEOUT=1`. |
| **v3.1.1** | 2026-07-16 | **Fix: `node_swarm_fallback` didn't reset `tdd_iteration`.** Reset `tdd_status = ""` but left `tdd_iteration` at `max_retries + 1`. Now resets `tdd_iteration = 0` to give one full debug cycle. |
| **v3.1** | 2026-07-14 | **Debug loop improvements.** 4 items: (1) #42 Goal sanitization — max 2000 chars + strip control chars in `validate.py`. (2) #41 AST pre-check — `ruff --select E999` before pytest in `run_pytest.py` (saves ~30s on syntax errors). (3) F3 `debug_summary` in verify chain — `llm_review.py` injects compressed summary when `debug_history` > 5. (4) #48 Swarm fallback — new `node_swarm_fallback` node: when debug retries exhausted + `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, escalates to swarm consensus. New config flag (default OFF). Graph: 28 → 29 nodes. Smoke tests in `test_swarm_integration.py`. |
| **v3.0** | 2026-07-14 | **Flat-field removal — Track M1 ✅ COMPLETE.** Removed ~32 legacy flat-field mirrors from `AutocodeState` + `_default_state()`. All 8 accessors simplified to 4-line sub-state-only reads. 13 ephemeral flat fields explicitly declared. See [SUBSTATE.md](SUBSTATE.md). |
| **v2.7** | 2026-07-14 | **Track M1 Batch 1 — `memory` sub-state.** Pattern proven for non-`tdd` sub-states. |
| **v2.6** | 2026-07-14 | **Track M1 Batch 2 — `verify` sub-state.** `node_verify_decision` migrated to RMW. |
| **v2.5** | 2026-07-14 | **Track M1 Batch 2 — `debug` sub-state.** `node_systematic_debug` migrated to RMW. `conftest.py::base_state` rewritten to use `_default_state()`. |
| **v2.4** | 2026-07-14 | **Track M1 Batch 1 — `impact` sub-state.** |
| **v2.3** | 2026-07-14 | **Track M1 Batch 3b — `files` sub-state.** 4 writers + 9 readers migrated. P1.8 hardening preserved. |
| **v2.2** | 2026-07-14 | **Track M1 Batch 3c — `plan` sub-state.** 🎉 ALL 8 ACCESSORS NOW SAFE. 4 writers + 5 readers migrated. Fixed pre-existing `"steps"` → `"plan"` key mismatch. |
| **v2.1** | 2026-07-14 | **Track M1 Batch 3a — `vcs` sub-state.** 4 writers (12 RMW paths) + 7 readers migrated. Removed the v2.0.5 split-brain band-aid in `commit.py`. |
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
| v1.2 (legacy) | 2026-07-08 | JSON schema enforcement. `debug.py` passes `json_schema` via `_call()`. |
| v1.1.2 | 2026-07-06 | Small-fix batch: #39 stuck detection, #44 structured artifacts, #46 multi-file git-diff, #47 dry-run actually dry. |
| v1.1 | 2026-07-06 | Facade fix + `WORKFLOW_METADATA` + routing fixes. |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items). |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items). |
| v1.0 | — | Released — 17-node LangGraph StateGraph. |

---

## ⚠️ Breaking Changes

### v3.1.2 — 2026-07-18

| Change | Impact | Migration |
|--------|--------|-----------|
| `run_autocode_agent()` shim removed | Importers `ImportError`. | Use `run_workflow("autocode")`. |
| `/autocode/graph` endpoint removed | 404 on HTTP clients. | Use `WORKFLOW_METADATA` (exported from `workflows.autocode`). |
| `_call()` requires `trace_id=tid` | Observability regression if omitted. | All 8 in-tree callers updated. New callers MUST pass `trace_id=tid`. |
| `node_create_skill` rejects empty `skill_file` content | Tests mocking `skill_code` (wrong key) now FAIL. | Use `skill_file` in mock fixtures. |

### v3.0 — 2026-07-14

| Change | Impact | Migration |
|--------|--------|-----------|
| ~32 legacy flat-field mirrors removed | Direct `state.get("tdd_status")` etc. return `None`. | Use accessors (`_get_tdd`, `_get_vcs`, `_get_files`). See [SUBSTATE.md](SUBSTATE.md). |
| Accessor fallback branches removed | Accessors now ONLY read sub-states. | No migration if already using accessors. |
| `test_results` removed from `TDDState` | Stays flat-only (ephemeral). | Read via `state.get("test_results", {})`. |
| `input_files` removed from `FilesState` | Was mirror of core `files` flat field. | Read `state.get("files", {})` directly. |
| Node returns must write sub-state only via RMW | Flat-field mirrors in node returns no longer valid. | Write `{"files_state": current_files}` instead of `{"modified_files": [...]}`. |

### v2.0 — 2026-07-11

| Change | Impact | Migration |
|--------|--------|-----------|
| `helpers._write_files()` DELETED | Dead code. | Use `node_apply_patches` + `node_write_new_files` + `node_persist_artifacts`. |
| `WORKFLOW_METADATA["version"]` → `"2.0"` (GA) | Version bump. | No migration. |

### v2.0-beta — 2026-07-11

| Change | Impact | Migration |
|--------|--------|-----------|
| 3 "god nodes" split into 10 focused nodes | `node_write_files`, `node_verify`, `node_publish` are now backward-compat wrappers (registered, NOT wired). | Import split nodes directly. |

### v1.4 — 2026-07-11

| Change | Impact | Migration |
|--------|--------|-----------|
| Deleted `mermaid.py`, `test_mapper.py`, `test_runner.py` | All three were unused. | No migration — `WORKFLOW_METADATA` serves the mermaid purpose. |

---

## ✅ Completed Roadmap Items

1-line each — for the full description see the Version History row above.

| # | Feature | Shipped |
|---|---------|---------|
| #57 | Per-node dedicated test files (14 nodes) | ✅ v3.8 — 4 new test files, +62 tests |
| F7 | Lazy Dev full audit mode (whole-repo scan) | ✅ v3.7 — `node_audit_scan` + `node_audit_report` |
| #35 (incremental) | Cancellation-aware subprocess calls | ✅ v3.6 — pre-check + `_remaining_timeout()` + post-check |
| F1 | Parallel subagent debug (4th debug path) | ✅ v3.5 — `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` |
| #38 | Human-in-the-Loop (HiTL) approval gate | ✅ v3.4 — `node_hitl_gate` + `AUTOCODE_HITL_ENABLED=1` |
| #58 | Standardize status-check pattern (`_should_skip_node`) | ✅ v3.3 — canonical `_SKIP_STATUSES` set |
| F4 | Configurable architecture-question threshold | ✅ v3.3 — `AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD` env var |
| F8 | Mermaid symbol context offloading | ✅ v3.1.3 — `summarize_context.py` offloads `debug_history` via `core/symbol_offload.py` |
| #34 | Remove `run_autocode_agent()` backward-compat shim | ✅ v3.1.2 — use `run_workflow("autocode")` directly |
| #36 | `create_skill` smoke-test import + git commit | ✅ v3.1.2 — `importlib.util.spec_from_file_location` + `_git_commit` |
| #40 | Adaptive timeout by task type | ✅ v3.1.2 — `AUTOCODE_ADAPTIVE_TIMEOUT=1` (default OFF) |
| #17 | Swarm ↔ autocode smoke test | ✅ swarm v1.1 — `test_swarm_integration.py` (2 classes, 5 tests) |
| #48 | Swarm ↔ autocode debug loop integration | ✅ v3.1 — `node_swarm_fallback` gated on `AUTOCODE_SWARM_DEBUG_FALLBACK=1` |
| #41 | AST/linter pre-check before pytest | ✅ v3.1 — `ruff --select E999` in `node_run_pytest` |
| #42 | Goal sanitization | ✅ v3.1 — `node_validate_input` max 2000 chars + strip control chars |
| F3 | `debug_summary` consumption in verify chain | ✅ v3.1 — `node_llm_review` injects `debug_summary` when `debug_history` > 5 |

---

## 🔄 In Progress / Open Roadmap

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 35 (full) | `invoke_with_timeout` process-level termination | **✅ v3.6 (incremental)** — bounds zombie linger to ≤1s past deadline. FULL process-level termination still deferred — requires re-architecting `invoke_with_timeout()` to use `multiprocessing.Process` (pickling state across process boundary, IPC for result dict, SIGTERM handling, `spawn`-safe imports on Windows). | P2 |
| 32 | IDE integration | LSP or VS Code extension for autocode. | P3 |
| 56 | v3.x cleanup: remove backward-compat wrappers | `node_write_files`, `node_verify`, `node_publish` (registered but NOT wired). Blocked by tests importing them directly. | P3 |
| F2 | Autoresearch pre-flight before plan | Wire a `node_autoresearch_preflight` before `node_brainstorm`. | P3 |
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

*Last updated: 2026-07-22 (v3.11.1 — B2 regression fix).*
