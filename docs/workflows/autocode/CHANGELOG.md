<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| **v2.4 + v2.7** | 2026-07-14 | **Track M1 Batch 1 — impact + memory sub-state migration.** First sub-states migrated under the v2.x → v3.0 accessor-migration track (Track M1). **v2.4 (impact):** `node_analyze_impact` now writes to the `impact` sub-state via read-modify-write (RMW) alongside legacy flat-field mirrors (`impact_warnings`, `targeted_test_cmd`, `analyze_impact_failed`). All 3 return paths updated. `node_run_tests` reader switched from `state.get("targeted_test_cmd")` to `_get_impact(state, "targeted_test_cmd", None)` — reads sub-state first, falls back to flat. **v2.7 (memory):** `node_distill_memory` was returning `{}` — the `memory` sub-state and `memory_notes` flat field were both dead code (populated by `_default_state()` but never written to by any node). Now writes a distillation summary (`distill_status=..., stored=N, skipped=N` or `distill_failed: ...`) to the `memory` sub-state via RMW + flat mirror. **Tests:** `test_run_tests.py::test_targeted_cmd_passed_through` rewritten to use `_default_state()` instead of a minimal hand-built state (the v2.0.5 split-brain bug was invisible because tests built state without the sub-state — Track M1 learning #2). New `test_targeted_cmd_read_from_impact_substate` verifies the accessor reads the sub-state value when flat field is default. **Pattern proven:** the RMW + flat-mirror approach works for non-`tdd` sub-states. Next: v2.5 (debug) + v2.6 (verify) in Batch 2. |
| **v2.0.5** | 2026-07-14 | **Phase 4g review — split-brain sub-state bug + state schema gaps + migration docs (2 P1 + 3 P2 + 4 P3).** **P1-1:** `_get_vcs(state, "branch", "main")` in `commit.py` was broken — read stale sub-state default `""` instead of actual branch name (sub-state populated by `_default_state()` but never written to by nodes; `node_write_plan` writes the flat `branch` field). The accessor returned `""`, making commit messages say `Branch: ` (empty). Reverted to direct `state.get("branch") or state.get("branch_name") or "main"`. This is the split-brain bug Gemini predicted in Phase 3 — the only accessor call outside `_get_tdd`, now proven broken. **P1-2:** INSTRUCTIONS.md #33 told new code to use the 8 accessors — but 7 of 8 return stale defaults. Added warning: only `_get_tdd` is safe today (nodes write to `tdd` sub-state via RMW). Updated ALWAYS DO #44 to match. **P2-1:** `verification_passed` was undeclared in `AutocodeState` TypedDict + missing from `_default_state()` (route_after_verify + commit.py read it). Added both. **P2-2:** `plan_state` key was used by `_get_plan()` + `_default_state()` but undeclared in TypedDict (overloaded `plan` is the legacy `list[dict]` step list). Added `plan_state: PlanState` declaration. Fixed API.md accessor table (`state["plan"]` → `state["plan_state"]`). **P2-3:** AUTOCODE.md "When to Use" table had `report` workflow (report is a tool) + missing `autoresearch`. Fixed both. **P2-4:** ARCHITECTURE.md + NODES.md overstated migration completeness ("All 7 phases COMPLETE — sub-states are PRIMARY"). Only `tdd` is actively maintained by nodes. Added candid migration-status warnings. NODES.md commit node updated: accessor "proof-of-concept" reverted. **P3-1:** `_call()` tracer.error used empty trace_id — retry-exhaustion errors were unattributed. Added `trace_id=""` param. **P3-2:** `run_tests.py` mutated `debug_history` list + dict in-place before RMW. Added defensive copy (`[dict(e) for e in debug_history]`). **P3-3:** `llm_review.py` used raw `json.loads` (fails on markdown-fenced JSON) — inconsistent with apply_patches.py + write_new_files.py. Switched to `_parse_json`. **P3-4:** `_pytest_output` ephemeral field (set by run_pytest, read by llm_review + verify_decision) was undocumented. Added ephemeral-fields table to API.md. **P3-5:** ARCHITECTURE.md node count drift ("27 active + 1 wrapper" → "25 active + 3 wrappers"). Fixed. |
| **v2.0.4** | 2026-07-14 | **Phase 4g review — subagent debug path integration fixes (2 P1 + 2 P2 + 1 P3).** P1-1: `subagent_verdict` field was documented in API.md since v2.0.2 but NEVER set in code — now populated in `node_systematic_debug` return dict + added to `DebugState` TypedDict + `AutocodeState` flat field + `_default_state()`. P1-2 (autoresearch, see below). P2-1: `WORKFLOW_METADATA["version"]` was stale at `"2.0.1"` through v2.0.2 + v2.0.3 (CHANGELOG bumped, code string forgot) — synced to `"2.0.4"`. `test_graph.py` version assertion weakened to `assert "version" in WORKFLOW_METADATA` (was: hard-coded `"2.0.1"`). P2-3: `_DEBUG_JSON_SCHEMA` was duplicated inline in both the subagent path and single-LLM path (byte-identical) — deduped to a single module-level constant. P3-1: tracer message "Subagent unavailable" was misleading (fires for both LLM errors AND unparseable JSON) — reworded to "yielded no usable result". |
| **v2.0.3** | 2026-07-12 | **[Hardening] Subagent debug path hardened.** `json_schema=_DEBUG_JSON_SCHEMA` now passed to subagent call (was: no schema enforcement). `temperature=retry_temp` now passed (was: default). Warning logged on empty `extract_json` (was: silent fallback). |
| **v2.0.2** | 2026-07-12 | **Subagent debug path (`AUTOCODE_SUBAGENT_DEBUG=1`, default OFF).** Third debug path: single-LLM (default) → swarm → subagent. Non-blocking, falls back to single-LLM on failure. Subagent gets isolated curated context — it does NOT see autocode session state (superpowers pattern: "you construct exactly what they need"). Now 7 config flags (was 6). See INSTRUCTIONS.md NEVER DO #40 + ALWAYS DO #56. |
| **v2.0.1** | 2026-07-11 | **Hardening pass — cross-LLM review (3 P0 + 7 P1 + 3 P2).** Sub-state clobbering in `debug.py` + `summarize_context.py` + `run_tests.py` (read-modify-write to preserve sibling TDD fields); `graph.py::invoke_with_timeout` now surfaces graph exceptions (was swallowing them as timeouts); markdown-fenced JSON parsing in `apply_patches.py` + `write_new_files.py` via `_parse_json`; `routes.py` short-circuits to `node_run_pytest` when `status=="error"`; `classify.py` enforces JSON schema (`task_type` enum); interruptible retry backoff via `threading.Event` (`helpers.py`); `modified_files` propagation from `write_new_files.py`; `blast_radius_note` now precedes "Output JSON ONLY:" in `DEBUG_SYSTEM`; `brainstorm.py` replaces `dir()` check with unconditional init; dead `json.loads` fallback removed from `execute.py`; dead `fix_error`/`improve` task_type entries removed from `route_after_write_files`; `debug_summary` now wired into `node_systematic_debug` prompt when `debug_history` > 5 entries. All 13 fixes tagged `[Hardening P*]` in source. 121/121 autocode tests pass. |
| **v2.0** | 2026-07-11 | **2.0 GA — Phase 7 (Ponytail integration + dead code removal + doc consolidation).** `CODER_SYSTEM` now includes the 7-rung Lazy Dev minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code); `DEBUG_SYSTEM` Phase 4 also applies the ladder; new `ponytail:` comment convention for deliberate simplifications. `helpers._write_files()` DELETED (was dead code since v2.0-rc2). API.md split into API.md (facade + state accessors) + new NODES.md (per-node reference). `WORKFLOW_METADATA["version"]` → `"2.0"` (GA). Graph topology UNCHANGED (28 nodes, 27 metadata). **All 7 phases of the 2.0 refactor ✅ COMPLETE.** |
| v2.0-rc3 | 2026-07-11 | **Phase 6 — State migration (sub-states primary).** `_default_state()` populates all 8 sub-states; legacy flat fields kept as mirrors. `_get_plan` accessor reads `plan_state` (not `plan`). |
| v2.0-rc2 | 2026-07-11 | **Phase 5 — VCS consolidation + cleanup.** New unified `vcs_ops.py` merges `git_ops.py` + `github_ops.py` (both kept as thin re-export wrappers). `helpers._write_files()` marked DEPRECATED (dead code — never called). 3 backward-compat node wrappers KEPT for test compat. |
| v2.0-rc1 | 2026-07-11 | **Phase 4 — Debug loop refactor.** `DEBUG_SYSTEM` restructured to 4 phases (investigation → pattern → hypothesis → fix) inspired by obra/superpowers. `node_systematic_debug` accumulates `debug_history` across iterations (closes #37 prerequisite). New `node_summarize_context` node compresses `debug_history` before re-entering the loop. New architecture-question exit (3+ consecutive `tests_passed=False`). `WORKFLOW_METADATA["version"]` → `"2.0-rc1"`. Graph: 27 → 28 nodes. |
| v2.0-beta | 2026-07-11 | **Phase 3 — Node decomposition.** Three "god nodes" split into 10 focused nodes: `node_write_files` → `apply_patches` + `write_new_files` + `persist_artifacts`; `node_verify` → `run_pytest` + `run_lint` + `llm_review` + `verify_decision`; `node_publish` → `push` + `create_pr` + `merge_pr`. Originals kept as backward-compat wrappers (registered, NOT wired). Graph: 17 → 27 nodes. |
| v2.0-alpha | 2026-07-11 | **Phases 1+2 — Foundation + state redesign.** New `core/json_extract.py` (consolidated JSON extraction). `analyze_impact._run_async` simplified to `asyncio.run(coro)`. `helpers.py` cancellation flag (`request_cancellation()` / `clear_cancellation()` / `is_cancellation_requested()`) wired into `_call()` retry loop. 8 sub-state TypedDicts + 8 backward-compat accessor functions (`_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`). `node_git_commit` migrated to accessors (proof-of-concept). |
| v1.4 | 2026-07-11 | Pre-2.0 hardening + dead code cleanup. Cross-LLM review (DeepSeek, Qwen, MiMo, Kimi) found 19 real issues; 4 P0 + 7 P1 + 8 P2 fixed. Dead modules deleted (`mermaid.py`, `test_mapper.py`, `test_runner.py`). |
| v1.3 | 2026-07-10 | GitHub + Swarm integration. New `node_publish` (push + PR + auto-merge). `github_ops.py` helper module. Swarm 2-run debug (consensus → vote). 6 new config flags (all default OFF). |
| v1.2 | 2026-07-08 | JSON schema enforcement. `debug.py` passes `json_schema` via `_call()`. |
| v1.1.2 | 2026-07-06 | Small-fix batch: #39 stuck detection, #44 structured artifacts, #46 multi-file git-diff, #47 dry-run actually dry. |
| v1.1 | 2026-07-06 | Facade fix + `WORKFLOW_METADATA` + routing fixes. Facade was unreachable for 2 versions; fixed via 4 dead-import removals + double-compile fix + `invoke_with_timeout` wiring. |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items — see Completed). |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items — see Completed). |
| v1.0 | — | Released — 17-node LangGraph StateGraph. |

---

## 🏗️ 2.0 Refactor Progress

The 7-phase 2.0 refactor addressed all technical debt documented in v1.4 (see "Cross-LLM Review Findings (Pre-2.0)" below). All 7 phases ✅ COMPLETE. Git history has full per-phase details.

| Phase | Name | Status | Key changes |
|-------|------|--------|-------------|
| **1** | Foundation | ✅ v2.0 | `core/json_extract.py`; `analyze_impact._run_async` → `asyncio.run`; `helpers.py` cancellation flag wired into `_call()`; version bump → `2.0-alpha`. |
| **2** | State redesign (accessor layer) | ✅ v2.0 | 8 sub-state TypedDicts + 8 accessor functions; `_get_vcs`/`_get_plan`/`_get_tdd`/etc.; `node_git_commit` migrated as proof-of-concept. |
| **3** | Node splits | ✅ v2.0 | 3 "god nodes" → 10 focused nodes (3 + 4 + 3); originals kept as wrappers (registered, NOT wired). 17 → 27 nodes. |
| **4** | Debug history + context summarization | ✅ v2.0 | `DEBUG_SYSTEM` 4-phase structure (obra/superpowers); `debug_history` accumulation; new `node_summarize_context` node; architecture-question exit. 27 → 28 nodes. |
| **5** | VCS consolidation + cleanup | ✅ v2.0 | `git_ops.py` + `github_ops.py` → unified `vcs_ops.py` (originals as re-export wrappers); `_write_files()` deprecated; 3 wrappers KEPT for test compat. |
| **6** | State migration (sub-states primary) | ✅ v2.0 | `_default_state()` populates all 8 sub-states; sub-states are now PRIMARY storage; legacy flat fields kept as mirrors. |
| **7** | Ponytail + dead code + doc consolidation | ✅ v2.0 | 7-rung Lazy Dev ladder in `CODER_SYSTEM`; `ponytail:` comment convention; `helpers._write_files()` DELETED; API.md split → API.md + NODES.md; version → `"2.0"` (GA). |

**Topology changes:** Phase 3 added 10 split nodes (17 → 27). Phase 4 added `node_summarize_context` (27 → 28). Phases 5-7 did NOT change topology. Graph: 28 nodes registered, 27 in `WORKFLOW_METADATA["nodes"]` (3 wrappers excluded).

**Deferred to post-2.0** (`# TODO(2.0-post):`):
- Legacy flat-field removal (sub-states are PRIMARY; flat fields remain as mirrors)
- 3 backward-compat wrapper removal (kept for test compat — tests import wrappers directly)
- Full process-level termination for #35 (Phase 1 cancellation flag is the production mitigation)

---

## 🔍 Cross-LLM Review Findings

### Pre-2.0 review (v1.4) — 4 LLMs (DeepSeek, Qwen, MiMo, Kimi)
19 real issues fixed in v1.4 (4 P0 + 7 P1 + 8 P2). Items deferred to 2.0 (`_run_async` event loop pattern, `node_write_files` does too much, `node_verify` god node, debug statelessness, state field bloat, `invoke_with_timeout` zombie risk) — **ALL addressed by the v2.0 7-phase refactor above.** See git history for per-item details.

### v2.0.1 hardening review — 13 fixes
Cross-LLM review of v2.0 GA found 3 P0 + 7 P1 + 3 P2 real issues. All fixed in v2.0.1 (see Version History v2.0.1 row above for the full list). Each fix tagged `[Hardening P*]` in source for audit traceability. Verified via 121/121 autocode test pass + targeted smoke tests.

| Priority | Count | Examples |
|----------|-------|----------|
| **P0** | 3 | Sub-state clobbering in `debug.py` + `summarize_context.py` (lost sibling TDD fields); `run_tests.py` not marking `debug_history[].tests_passed=True`; `graph.py::invoke_with_timeout` swallowing graph exceptions as timeouts. |
| **P1** | 7 | Markdown-fenced JSON parsing (`apply_patches` + `write_new_files`); `routes.py` error short-circuit; `classify.py` JSON schema; interruptible retry backoff (`threading.Event`); `modified_files` propagation; `blast_radius_note` prompt position; `brainstorm.py` `dir()` check removal. |
| **P2** | 3 | Dead `json.loads` fallback in `execute.py`; dead `fix_error`/`improve` task_type entries in `route_after_write_files`; `debug_summary` now consumed by `node_systematic_debug` prompt (was written but never read). |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 32 | IDE integration | LSP or VS Code extension for autocode. | P3 |
| 34 | Remove `run_autocode_agent()` backward-compat shim | Once all callers use `run_workflow("autocode")` directly. | P2 |
| 35 | `invoke_with_timeout` daemon-thread zombie risk | **[Hardening P0.3]** v2.0.1 surfaces graph crashes (was misreported as timeout). Full process-level termination (`concurrent.futures` / `multiprocessing`) still deferred. | P2 |
| 36 | `create_skill` smoke-test import + git commit | Currently has AST syntax check; no import test or git commit. | P2 |
| 37 | Context summarization node | ✅ Shipped in v2.0 (`node_summarize_context`). | ~~P2~~ Done |
| 38 | Human-in-the-Loop (HiTL) approval | Pause graph before `commit` or `create_skill`. | P2 |
| 40 | Adaptive timeout by task type | `create_skill`=120s, `audit`=300s, `feature`=900s. | P2 |
| 41 | AST/linter pre-check before pytest | Run `ruff`/`flake8` before `pytest` to catch indentation errors early. | P2 |
| 42 | Goal sanitization | Max length + strip control chars on `goal`/`task` input. | P2 |
| 43 | GitHub PR workflow | ✅ Shipped in v1.3. | ~~P2~~ Done |
| 45 | Streaming node transitions | Stream `tracer.step` events to MCP client via WebSocket. | P2 |
| 46 | **[v2.x → v3.0] Complete sub-state migration** | Migrate 7 remaining sub-states (plan, files, impact, debug, verify, vcs, memory) from flat-field writes to RMW sub-state writes. See Future Track M1 below for full scope + learnings from the `tdd` migration. | P1 |
| 47 | **[v3.0] Remove legacy flat fields** | After all nodes write to sub-states, remove the flat field mirrors from `AutocodeState` TypedDict + `_default_state()`. Prerequisite: #46 complete. | P1 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | Remove TDD-first | TDD ensures test coverage. | Skip |
| 2 | Remove debug loop | Single-pass code generation misses edge cases. | Skip |
| 3 | Remove impact analysis | Blast radius analysis prevents unintended side effects. | Skip |
| 4 | Remove git integration | Git branches and commits are essential. | Skip |
| 5 | Remove memory integration | Procedural memory improves future performance. | Skip |
| 6 | Real-time collaboration | Multi-user editing requires complex state sync. | Skip |
| 7 | Support non-Python languages | Workflow is designed for Python. Other languages need tree-sitter per-lang. | Skip |

---

## 🔍 2.0 Review Notes

Items documented as known technical debt during v1.3, marked `# TODO(2.0):` in source. All Architecture + Integration items resolved by v2.0 GA + v2.0.1 hardening; Documentation items are ongoing.

### Architecture

| Item | Status | Resolution |
|------|--------|------------|
| `git_ops.py` + `github_ops.py` split | ✅ RESOLVED (v2.0 Phase 5) | Merged into unified `vcs_ops.py` (originals kept as re-export wrappers). |
| `node_publish` as single node | ✅ RESOLVED (v2.0 Phase 3.3) | Split into `node_push` / `node_create_pr` / `node_merge_pr`. |
| Debug node statelessness | ✅ RESOLVED (v2.0 Phase 4) | `node_systematic_debug` now accumulates `debug_history`; `node_summarize_context` compresses it. |
| Swarm verdict non-blocking | OPEN | `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag still deferred. `# TODO(2.0-post):`. |
| Config flags are global | OPEN | Per-task overrides still deferred. `# TODO(2.0-post):`. |

### Integration

| Item | Status | Resolution |
|------|--------|------------|
| `AUTOCODE_AUTO_MERGE` hardcoded to squash | OPEN | `AUTOCODE_AUTO_MERGE_METHOD` config still deferred. `# TODO(2.0-post):`. |
| Pull failure is non-blocking | OPEN | Fail-fast vs graceful-skip config still deferred. `# TODO(2.0-post):`. |
| Swarm confidence thresholds | OPEN | MEDIUM requiring ≥3 providers still under review. `# TODO(2.0-post):`. |
| PR body is minimal | OPEN | Richer PR body (test results, diff summary, impact warnings) still deferred. `# TODO(2.0-post):`. |
| No retry on push/PR failure | OPEN | Transient-failure retry logic still deferred. `# TODO(2.0-post):`. |

### Documentation

| Item | Status | Resolution |
|------|--------|------------|
| Stale env vars in AUTOCODE.md | ✅ RESOLVED (v1.3) | `AUTOCODE_PLANNER_TIMEOUT` etc. confirmed not to exist; `AUTOCODE_GRAPH_TIMEOUT` is the only autocode timeout. |
| `pull` action rebase param | OPEN | `git pull --rebase` not supported. `# TODO(2.0-post):`. |

---

## 🚀 Future Tracks (Post-2.0)

Tracks that emerged from the v2.0 refactor + obra/superpowers + autoresearch design discussions. Explicitly OUT OF SCOPE for the 7-phase 2.0 refactor — ship after 2.0 GA. Each item marked `# TODO(2.0-post):` in source where relevant.

| # | Track | Inspiration | Notes |
|---|-------|-------------|-------|
| F1 | Subagent dispatch for parallel debug | obra/superpowers; agent dispatch roadmap | **PARTIALLY IMPLEMENTED** — single subagent dispatch available via `AUTOCODE_SUBAGENT_DEBUG=1` (v2.0.2). Parallel subagents (one per hypothesis) still future. |
| F2 | Autoresearch pre-flight before plan | autoresearch design discussion | Wire a `node_autoresearch_preflight` (optional, gated on `AUTOCODE_AUTORESEARCH_PREFLIGHT=1`) before `node_brainstorm` to fetch web context for tasks that need external research. |
| F3 | `debug_summary` consumption in verify chain | obra/superpowers Phase 4.5 | **[Hardening P2]** v2.0.1 wired `debug_summary` into `node_systematic_debug` prompt (when `debug_history` > 5 entries). Verify-chain consumption still deferred. |
| F4 | Adaptive `_ARCHITECTURE_QUESTION_THRESHOLD` | obra/superpowers | Currently hardcoded to 3. Make it configurable per task type (`create_skill`=1, `feature`=5). |
| F5 | Procedural memory recall before debug | obra/superpowers | Phase 4.2 stores a procedural memory when the architecture-question exit fires; cross-run recall (read past failures before debug) still pending. |
| F6 | Streaming `phase` transitions to MCP client | v2.0 Phase 4.1 `phase` field; #45 | The new `phase` field (investigation / pattern / hypothesis / fix) is currently internal. Stream it to the MCP client so the user sees debug progress. |
| F7 | Lazy Dev (YAGNI Ladder) — **PARTIALLY IMPLEMENTED** | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | **[v2.0 GA]** 7-rung ladder in `CODER_SYSTEM` + Lazy Dev rule in `DEBUG_SYSTEM` Phase 4 + `ponytail:` comment convention all shipped. Full audit mode (`task_type="audit"` whole-repo scan for over-engineering) still deferred. |
| F8 | Mermaid symbol context offloading | [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | Instead of chonkie-compressing `debug_history`, offload symbol context (function/class signatures, call graph) to a mermaid diagram that the LLM can reference on demand. |

### Track M1 — Sub-state migration (v2.x → v3.0)

**Goal:** Complete the v2.0 accessor-layer migration. Today only `tdd` is fully migrated (nodes write to the `tdd` sub-state via read-modify-write). The other 7 sub-states hold stale defaults because nodes still write to flat fields. This causes split-brain bugs: `_get_vcs(state, "branch", "main")` returns `""` (stale sub-state default), not the actual branch name (which lives in the flat `branch` field). See v2.0.5 P1-1 for the proof.

**Why gradual:** The `tdd` migration took 4 phases (v2.0-alpha → v2.0-rc1 → v2.0-rc3 → v2.0.1) and still produced 3 P0 RMW-clobbering bugs (fixed in v2.0.1 hardening). Scaling that to 7 more sub-states in one release is too risky. The 2.x line will migrate them one sub-state at a time, building on what was learned from `tdd`.

**Learnings from the `tdd` migration (apply to every future sub-state):**

1. **Read-modify-write is mandatory.** LangGraph replaces dict values, doesn't deep-merge. Returning `{"tdd": {"debug_history": [...]}}` clobbers every other `tdd` field. Always do: `current_tdd = dict(state.get("tdd", {}))`, mutate, return `current_tdd`. This was P0.1 in v2.0.1.
2. **Tests must use `_default_state()`, not minimal hand-built state.** The split-brain bug (P1-1) was invisible to tests because tests built `state = {"branch": "fix-bug", ...}` without the `vcs` sub-state — so `_get_vcs` fell through to the flat field and returned the correct value. The bug only manifested when `_default_state()` was used (which populates the sub-state with `""`).
3. **Copy before mutating.** `run_tests.py` mutated `debug_history[-1]["tests_passed"] = True` in-place. Works today, but unsafe if LangGraph ever snapshots state between nodes. Pattern: `debug_history = [dict(e) for e in debug_history]` before mutating. (v2.0.5 P3-2.)
4. **Migrate the writer first, then the reader.** If a node writes flat (`state["branch"] = ...`) and a reader uses the accessor (`_get_vcs(state, "branch")`), the accessor returns the stale sub-state default. Either migrate the writer to RMW sub-state writes BEFORE any reader uses the accessor, or don't use the accessor at all. The `tdd` migration worked because BOTH the writers (debug.py, summarize_context.py, run_tests.py) AND the readers (debug.py) use `_get_tdd` + RMW.
5. **The accessor layer is the trap.** 6 of 8 accessors are dead code today (zero callers). If anyone follows INSTRUCTIONS.md #33 (old version) and uses them, they'll hit split-brain. INSTRUCTIONS.md #33 has been updated (v2.0.5) to warn: only `_get_tdd` is safe. The 6 dead accessors must either be deleted or made safe (via writer migration) before v3.0.

**Migration order (proposed — lowest-risk first):**

| Sub-state | Writer nodes | Risk | Why this order |
|-----------|-------------|------|----------------|
| `tdd` | debug.py, summarize_context.py, run_tests.py | ✅ DONE | Already migrated (v2.0 → v2.0.1) |
| `vcs` | commit.py, branch.py, plan.py, push.py, create_pr.py, merge_pr.py | **v2.1** | Most callers (6 nodes) but all writes are simple flat→sub-state. P1-1 already proved the trap; fix it properly. |
| `plan` | brainstorm.py, plan.py, execute.py | **v2.2** | `plan` key is overloaded (legacy `list[dict]` step list vs `PlanState` dict). Migrate to `plan_state` as primary, keep `plan` as the step-list alias. |
| `files` | apply_patches.py, write_new_files.py, persist_artifacts.py | **v2.3** | `files_map` + `modified_files` propagation — the P1.8 hardening showed how easy it is to lose writes here. |
| `impact` | analyze_impact.py | **v2.4** | Single writer — lowest risk. |
| `debug` | debug.py (flat writes for root_cause/defense_notes) | **v2.5** | Partially overlaps with `tdd` (debug_history). Consolidate. |
| `verify` | run_pytest.py, run_lint.py, llm_review.py, verify_decision.py | **v2.6** | 4 nodes in the verify chain. `_pytest_output` ephemeral field needs a home (see v2.0.5 P3-4). |
| `memory` | memory.py (distill) | **v2.7** | Single writer — lowest risk, but last because it's the least-read sub-state. |

**After all 7 are migrated (v3.0):**
- Remove the 6 dead accessors that were never safe (`_get_plan`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`) — they'll be redundant once all nodes use `_get_*` + RMW.
- Remove the legacy flat fields from `AutocodeState` TypedDict + `_default_state()`.
- Update all 13 test files to assert on sub-state reads instead of flat fields.
- Update INSTRUCTIONS.md #33 to remove the warning (all accessors safe again).

**Estimated scope:** ~15 nodes (RMW rewrites) + 4 route functions (switch to accessors) + 13 test files. Each sub-state = 1 minor release (v2.1 → v2.7). v3.0 = flat-field removal + accessor cleanup.

---

*Last updated: 2026-07-14 (v2.0.5 — Phase 4g review: split-brain sub-state fix + state schema gaps + migration docs + v2.x→v3.0 roadmap; v2.0.4 subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
