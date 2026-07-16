<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
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
| v1.2 | 2026-07-08 | JSON schema enforcement. `debug.py` passes `json_schema` via `_call()`. |
| v1.1.2 | 2026-07-06 | Small-fix batch: #39 stuck detection, #44 structured artifacts, #46 multi-file git-diff, #47 dry-run actually dry. |
| v1.1 | 2026-07-06 | Facade fix + `WORKFLOW_METADATA` + routing fixes. Facade was unreachable for 2 versions. |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items). |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items). |
| v1.0 | — | Released — 17-node LangGraph StateGraph. |

---

### ⚠️ Breaking Changes

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
| ✅ #17 | **Swarm ↔ autocode smoke test** | ✅ **Shipped in swarm v1.1** — `tests/workflows/autocode/test_swarm_integration.py` (2 classes, 5 tests) covers: (a) `TestSwarmDebugIntegration` — `_swarm_debug_consensus` is called when `cfg.autocode_swarm_debug=True`, NOT called when `False`; (b) `TestSwarmFallbackIntegration` — `node_swarm_fallback` HIGH-confidence path (resets `tdd.status=""` for one more cycle + records `swarm_verdict`), LOW-confidence path (`status="failed"` + records `swarm_verdict`), and swarm-unavailable path (`status="failed"`, no verdict). Uses pytest-mock `mocker` fixture. Closes the long-standing gap noted in the swarm v1.0.2 P0-1 fix — the autocode swarm integration was non-functional from v1.3 → v1.0.2 because of interface bugs (wrong param names, wrong result keys); the smoke test now locks the contract. |
| ✅ #48 | **Swarm ↔ autocode debug loop integration** | ✅ **Shipped in v3.1** — `node_swarm_fallback` (gated on `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, default OFF). Escalates to swarm consensus when debug retries exhausted; HIGH confidence → one more debug cycle, LOW/unavailable → verify chain. |
| ✅ #41 | **AST/linter pre-check before pytest** | ✅ **Shipped in v3.1** — `ruff --select E999` syntax-only pre-check in `node_run_pytest` (saves ~30s on syntax errors). Non-fatal if ruff not installed. |
| ✅ #42 | **Goal sanitization** | ✅ **Shipped in v3.1** — `node_validate_input` now enforces max 2000 chars + strips control chars; returns cleaned task in state update. |
| ✅ F3 | **`debug_summary` consumption in verify chain** | ✅ **Shipped in v3.1** — `node_llm_review` injects `debug_summary` into the verify LLM prompt when `debug_history` > 5 entries. |
| 34 | Remove `run_autocode_agent()` backward-compat shim | Once all callers use `run_workflow("autocode")` directly. | P2 |
| 35 | `invoke_with_timeout` daemon-thread zombie risk | v2.0.1 surfaces graph crashes. Full process-level termination still deferred. | P2 |
| 36 | `create_skill` smoke-test import + git commit | Currently has AST syntax check; no import test or git commit. | P2 |
| 38 | Human-in-the-Loop (HiTL) approval | Pause graph before `commit` or `create_skill`. | P2 |
| 40 | Adaptive timeout by task type | `create_skill`=120s, `audit`=300s, `feature`=900s. | P2 |
| F1 | Parallel subagent debug | Single subagent via `AUTOCODE_SUBAGENT_DEBUG=1` (v2.0.2). Parallel subagents (one per hypothesis) still future. Now unblocked — v2.0.2 action-level allowlist makes this safe. | P2 |
| F7 | Lazy Dev full audit mode | 7-rung ladder + `ponytail:` convention shipped (v2.0). Full audit mode (`task_type="audit"` whole-repo scan) still deferred. | P2 |
| 32 | IDE integration | LSP or VS Code extension for autocode. | P3 |
| 56 | v3.x cleanup: remove backward-compat wrappers | `node_write_files`, `node_verify`, `node_publish` (registered but NOT wired). Blocked by tests importing them directly. | P3 |
| F2 | Autoresearch pre-flight before plan | Wire a `node_autoresearch_preflight` before `node_brainstorm`. | P3 |
| F4 | Adaptive `_ARCHITECTURE_QUESTION_THRESHOLD` | Currently hardcoded to 3. Make configurable per task type (`create_skill`=1, `feature`=5). | P3 |
| F5 | Procedural memory recall before debug | Cross-run recall (read past failures before debug) still pending. | P3 |
| F6 | Stream `phase` transitions to MCP client | The `phase` field is currently internal. Stream it to the MCP client so the user sees debug progress. | P3 |
| F8 | Mermaid symbol context offloading | Offload symbol context to a mermaid diagram instead of chonkie-compressing `debug_history`. TencentDB-inspired. | P3 |

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

*Last updated: 2026-07-14 (v3.1 — debug loop improvements: #42 goal sanitization, #41 AST pre-check, F3 debug_summary in verify chain, #48 swarm fallback; swarm v1.1 #17 smoke test for both swarm-integration paths in `tests/workflows/autocode/test_swarm_integration.py`). See [SUBSTATE.md](SUBSTATE.md) for the v3.0 sub-state architecture, [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for state accessors, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
