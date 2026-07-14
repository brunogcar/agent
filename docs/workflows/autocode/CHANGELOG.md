<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v3.0** | 2026-07-14 | **Flat-field removal — Track M1 ✅ COMPLETE.** Removed ~32 legacy flat-field mirrors from `AutocodeState` + `_default_state()`. All 8 accessors simplified to 4-line sub-state-only reads. 13 ephemeral flat fields explicitly declared. All node returns write sub-state only. See [SUBSTATE.md](SUBSTATE.md). |
| **v2.2** | 2026-07-14 | **Track M1 Batch 3c — `plan` sub-state.** 🎉 ALL 8 ACCESSORS NOW SAFE. 4 writers + 5 readers migrated. Fixed pre-existing `"steps"` → `"plan"` key mismatch in `_default_state()` plan_state. |
| **v2.3** | 2026-07-14 | **Track M1 Batch 3b — `files` sub-state.** 4 writers + 9 readers migrated. `apply_patches.py`, `execute.py`, `write_new_files.py`, `brainstorm.py` switched to RMW; `analyze_impact.py`, `debug.py`, `memory.py`, `plan.py`, `report.py`, `run_lint.py`, `validate.py` switched to `_get_files`. |
| **v2.1** | 2026-07-14 | **Track M1 Batch 3a — `vcs` sub-state.** 4 writers (12 RMW return paths) + 7 readers migrated. Removed the v2.0.5 split-brain band-aid in `commit.py` (`_get_vcs` is now safe). |
| **v2.5 + v2.6** | 2026-07-14 | **Track M1 Batch 2 — `debug` + `verify` sub-states.** `node_systematic_debug` + `node_verify_decision` migrated to RMW. 9 reader nodes switched. `_get_debug` gained `legacy_map = {"notes": "debug_notes"}`. `conftest.py::base_state` rewritten to use `_default_state()`. |
| **v2.4 + v2.7** | 2026-07-14 | **Track M1 Batch 1 — `impact` + `memory` sub-states.** `node_analyze_impact` (3 return paths) + `node_distill_memory` migrated to RMW. `node_run_tests` reader switched to `_get_impact`. Pattern proven for non-`tdd` sub-states. |
| **v2.0.5** | 2026-07-14 | **Phase 4g review.** Split-brain sub-state bug (`_get_vcs(state, "branch", "main")` returning stale `""` in `commit.py`) — reverted to direct read. Schema gaps fixed (`verification_passed`, `plan_state` TypedDict declaration). 2 P1 + 3 P2 + 4 P3. |
| **v2.0.4** | 2026-07-14 | **Subagent debug path integration fixes.** `subagent_verdict` field now actually populated. `WORKFLOW_METADATA["version"]` synced from stale `"2.0.1"` to `"2.0.4"`. `_DEBUG_JSON_SCHEMA` deduped to a single module-level constant. |
| **v2.0.3** | 2026-07-12 | **[Hardening] Subagent debug path hardened.** `json_schema=_DEBUG_JSON_SCHEMA` passed to subagent call. `temperature=retry_temp` passed. Warning logged on empty `extract_json`. |
| **v2.0.2** | 2026-07-12 | **Subagent debug path** (`AUTOCODE_SUBAGENT_DEBUG=1`, default OFF). Third debug path: single-LLM → swarm → subagent. Non-blocking, isolated curated context (no autocode session state). |
| **v2.0.1** | 2026-07-11 | **Hardening pass — cross-LLM review (3 P0 + 7 P1 + 3 P2).** Sub-state clobbering in `debug.py` + `summarize_context.py` + `run_tests.py` (RMW to preserve sibling TDD fields); `invoke_with_timeout` surfaces graph exceptions; markdown-fenced JSON via `_parse_json`; `routes.py` error short-circuit; `classify.py` JSON schema; interruptible retry backoff via `threading.Event`. 121/121 tests pass. |
| **v2.0** | 2026-07-11 | **2.0 GA — Phase 7** (Ponytail integration + dead code removal + doc consolidation). 7-rung Lazy Dev ladder in `CODER_SYSTEM`; `ponytail:` comment convention. `helpers._write_files()` DELETED. API.md split → API.md + NODES.md. All 7 phases of the 2.0 refactor ✅ COMPLETE. |
| v2.0-rc3 | 2026-07-11 | **Phase 6 — State migration** (sub-states primary). `_default_state()` populates all 8 sub-states; legacy flat fields kept as mirrors. |
| v2.0-rc2 | 2026-07-11 | **Phase 5 — VCS consolidation.** Unified `vcs_ops.py` merges `git_ops.py` + `github_ops.py` (originals as thin re-export wrappers). |
| v2.0-rc1 | 2026-07-11 | **Phase 4 — Debug loop refactor.** `DEBUG_SYSTEM` 4-phase structure (investigation → pattern → hypothesis → fix). `debug_history` accumulation. New `node_summarize_context` node. Architecture-question exit. 27 → 28 nodes. |
| v2.0-beta | 2026-07-11 | **Phase 3 — Node decomposition.** 3 "god nodes" split into 10 focused nodes (3 + 4 + 3); originals kept as backward-compat wrappers. 17 → 27 nodes. |
| v2.0-alpha | 2026-07-11 | **Phases 1+2 — Foundation + state redesign.** `core/json_extract.py`; `helpers.py` cancellation flag. 8 sub-state TypedDicts + 8 backward-compat accessor functions. |
| v1.4 | 2026-07-11 | Pre-2.0 hardening + dead code cleanup. Cross-LLM review (4 LLMs) — 4 P0 + 7 P1 + 8 P2 fixed. Deleted `mermaid.py`, `test_mapper.py`, `test_runner.py`. |
| v1.3 | 2026-07-10 | GitHub + Swarm integration. `node_publish` (push + PR + auto-merge). `github_ops.py`. Swarm 2-run debug. 6 new config flags (all default OFF). |
| v1.2 | 2026-07-08 | JSON schema enforcement. `debug.py` passes `json_schema` via `_call()`. |
| v1.1.2 | 2026-07-06 | Small-fix batch: #39 stuck detection, #44 structured artifacts, #46 multi-file git-diff, #47 dry-run actually dry. |
| v1.1 | 2026-07-06 | Facade fix + `WORKFLOW_METADATA` + routing fixes. Facade was unreachable for 2 versions; fixed via dead-import removal + double-compile fix. |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items). |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items). |
| v1.0 | — | Released — 17-node LangGraph StateGraph. |

---

## 🏗️ 2.0 Refactor Progress

The 7-phase 2.0 refactor addressed all technical debt documented in v1.4. All 7 phases ✅ COMPLETE.

| Phase | Name | Status | Key changes |
|-------|------|--------|-------------|
| 1 | Foundation | ✅ v2.0 | `core/json_extract.py`; `analyze_impact._run_async` → `asyncio.run`; cancellation flag wired into `_call()`. |
| 2 | State redesign (accessor layer) | ✅ v2.0 | 8 sub-state TypedDicts + 8 accessor functions; `node_git_commit` migrated as proof-of-concept. |
| 3 | Node splits | ✅ v2.0 | 3 "god nodes" → 10 focused nodes. 17 → 27 nodes. |
| 4 | Debug history + context summarization | ✅ v2.0 | `DEBUG_SYSTEM` 4-phase structure; `debug_history` accumulation; new `node_summarize_context`. 27 → 28 nodes. |
| 5 | VCS consolidation + cleanup | ✅ v2.0 | `git_ops.py` + `github_ops.py` → unified `vcs_ops.py`; `_write_files()` deprecated. |
| 6 | State migration (sub-states primary) | ✅ v2.0 | `_default_state()` populates all 8 sub-states; legacy flat fields kept as mirrors. |
| 7 | Ponytail + dead code + doc consolidation | ✅ v2.0 | 7-rung Lazy Dev ladder; `ponytail:` convention; `helpers._write_files()` DELETED; API.md split → API.md + NODES.md. |

**Topology:** Phase 3 added 10 split nodes (17 → 27). Phase 4 added `node_summarize_context` (27 → 28). Phases 5–7 did NOT change topology. Graph: 28 nodes registered, 27 in `WORKFLOW_METADATA["nodes"]` (3 wrappers excluded).

**Deferred to post-2.0** (`# TODO(2.0-post):`):
- ~~Legacy flat-field removal~~ ✅ Shipped in v3.0 (Track M1 complete — see below).
- 3 backward-compat wrapper removal — tracked as roadmap #56.
- Full process-level termination for #35 (Phase 1 cancellation flag is the production mitigation).

---

## 🔍 Cross-LLM Review Findings

### Pre-2.0 review (v1.4) — 4 LLMs (DeepSeek, Qwen, MiMo, Kimi)
19 real issues fixed in v1.4 (4 P0 + 7 P1 + 8 P2). Items deferred to 2.0 (`_run_async` event loop pattern, `node_write_files` does too much, `node_verify` god node, debug statelessness, state field bloat, `invoke_with_timeout` zombie risk) — **ALL addressed by the v2.0 7-phase refactor above.**

### v2.0.1 hardening review — 13 fixes
Cross-LLM review of v2.0 GA found 3 P0 + 7 P1 + 3 P2 real issues. All fixed in v2.0.1. Each fix tagged `[Hardening P*]` in source for audit traceability. Verified via 121/121 autocode test pass.

| Priority | Count | Examples |
|----------|-------|----------|
| **P0** | 3 | Sub-state clobbering in `debug.py` + `summarize_context.py`; `run_tests.py` not marking `debug_history[].tests_passed=True`; `invoke_with_timeout` swallowing graph exceptions. |
| **P1** | 7 | Markdown-fenced JSON parsing; `routes.py` error short-circuit; `classify.py` JSON schema; interruptible retry backoff; `modified_files` propagation; `blast_radius_note` prompt position; `brainstorm.py` `dir()` check removal. |
| **P2** | 3 | Dead `json.loads` fallback in `execute.py`; dead `fix_error`/`improve` task_type entries; `debug_summary` consumption. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 32 | IDE integration | LSP or VS Code extension for autocode. | P3 |
| 34 | Remove `run_autocode_agent()` backward-compat shim | Once all callers use `run_workflow("autocode")` directly. | P2 |
| 35 | `invoke_with_timeout` daemon-thread zombie risk | **[Hardening P0.3]** v2.0.1 surfaces graph crashes. Full process-level termination still deferred. | P2 |
| 36 | `create_skill` smoke-test import + git commit | Currently has AST syntax check; no import test or git commit. | P2 |
| 37 | Context summarization node | ✅ Shipped in v2.0 (`node_summarize_context`). | ~~P2~~ Done |
| 38 | Human-in-the-Loop (HiTL) approval | Pause graph before `commit` or `create_skill`. | P2 |
| 40 | Adaptive timeout by task type | `create_skill`=120s, `audit`=300s, `feature`=900s. | P2 |
| 41 | AST/linter pre-check before pytest | Run `ruff`/`flake8` before `pytest` to catch indentation errors early. | P2 |
| 42 | Goal sanitization | Max length + strip control chars on `goal`/`task` input. | P2 |
| 43 | GitHub PR workflow | ✅ Shipped in v1.3. | ~~P2~~ Done |
| 45 | Streaming node transitions | Stream `tracer.step` events to MCP client via WebSocket. | P2 |
| 46 | **[v2.x → v3.0] Complete sub-state migration** | ✅ **Shipped across v2.1–v2.7.** All 7 remaining sub-states migrated to RMW sub-state writes. ALL 8 ACCESSORS NOW SAFE. See Track M1 below. | ~~P1~~ Done |
| 47 | **[v3.0] Remove legacy flat fields** | ✅ **Shipped in v3.0.** Removed ~32 legacy flat-field mirrors. All 8 accessors simplified. 13 ephemeral flat fields explicitly declared. Track M1 complete. See [SUBSTATE.md](SUBSTATE.md). | ~~P1~~ Done |
| 48 | Swarm ↔ autocode debug loop integration | Wire swarm verdict feedback into the autocode debug loop. | P1 |
| 49 | Swarm ↔ router vote-based routing | When router confidence is low, fall back to `swarm(vote)` for routing decision. | P1 |
| 50 | Memory tool: group-aware delete by `source_doc_id` | Allow deleting all chunks belonging to one source doc. | P1 |
| 51 | Browser fallback in web `search_and_read` | JS-rendered pages don't yield content via plain HTTP fetch. Add Playwright fallback. | P1 |
| 52 | Native `json_schema` for Claude | Anthropic tool-use conversion (current path is prompt-injected JSON). | P2 |
| 53 | Native `json_schema` for Gemini | `responseSchema` conversion (current path is prompt-injected JSON). | P2 |
| 54 | Autoresearch parallel experiments | Multiple branches/GPUs running experiments in parallel. Currently sequential. | P2 |
| 55 | TencentDB layered memory L0→L1→L2→L3 | Hot/warm/cold/archival memory tiers. | P2 |
| 56 | v3.x cleanup: remove backward-compat wrappers | `node_write_files`, `node_verify`, `node_publish` (registered but NOT wired). Blocked by tests importing them directly. | P3 |

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
| `git_ops.py` + `github_ops.py` split | ✅ RESOLVED (v2.0 Phase 5) | Merged into unified `vcs_ops.py`. |
| `node_publish` as single node | ✅ RESOLVED (v2.0 Phase 3.3) | Split into `node_push` / `node_create_pr` / `node_merge_pr`. |
| Debug node statelessness | ✅ RESOLVED (v2.0 Phase 4) | `node_systematic_debug` accumulates `debug_history`; `node_summarize_context` compresses it. |
| Swarm verdict non-blocking | OPEN | `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag deferred. |
| Config flags are global | OPEN | Per-task overrides deferred. |

### Integration

| Item | Status | Resolution |
|------|--------|------------|
| `AUTOCODE_AUTO_MERGE` hardcoded to squash | OPEN | `AUTOCODE_AUTO_MERGE_METHOD` config deferred. |
| Pull failure is non-blocking | OPEN | Fail-fast vs graceful-skip config deferred. |
| Swarm confidence thresholds | OPEN | MEDIUM requiring ≥3 providers under review. |
| PR body is minimal | OPEN | Richer PR body (test results, diff summary, impact warnings) deferred. |
| No retry on push/PR failure | OPEN | Transient-failure retry logic deferred. |

### Documentation

| Item | Status | Resolution |
|------|--------|------------|
| Stale env vars in AUTOCODE.md | ✅ RESOLVED (v1.3) | `AUTOCODE_PLANNER_TIMEOUT` etc. confirmed not to exist; `AUTOCODE_GRAPH_TIMEOUT` is the only autocode timeout. |
| `pull` action rebase param | OPEN | `git pull --rebase` not supported. |

---

## 🚀 Future Tracks (Post-2.0)

Tracks that emerged from the v2.0 refactor + obra/superpowers + autoresearch design discussions. Explicitly OUT OF SCOPE for the 7-phase 2.0 refactor — ship after 2.0 GA.

| # | Track | Inspiration | Notes |
|---|-------|-------------|-------|
| F1 | Subagent dispatch for parallel debug | obra/superpowers | **PARTIALLY IMPLEMENTED** — single subagent via `AUTOCODE_SUBAGENT_DEBUG=1` (v2.0.2). Parallel subagents still future. |
| F2 | Autoresearch pre-flight before plan | autoresearch design | Wire a `node_autoresearch_preflight` (gated on `AUTOCODE_AUTORESEARCH_PREFLIGHT=1`) before `node_brainstorm`. |
| F3 | `debug_summary` consumption in verify chain | obra/superpowers Phase 4.5 | **[Hardening P2]** v2.0.1 wired `debug_summary` into `node_systematic_debug` prompt. Verify-chain consumption still deferred. |
| F4 | Adaptive `_ARCHITECTURE_QUESTION_THRESHOLD` | obra/superpowers | Currently hardcoded to 3. Make it configurable per task type. |
| F5 | Procedural memory recall before debug | obra/superpowers | Cross-run recall (read past failures before debug) still pending. |
| F6 | Streaming `phase` transitions to MCP client | v2.0 Phase 4.1; #45 | The new `phase` field is currently internal. Stream it to the MCP client. |
| F7 | Lazy Dev (YAGNI Ladder) | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | **PARTIALLY IMPLEMENTED** — 7-rung ladder in `CODER_SYSTEM` + `ponytail:` convention shipped. Full audit mode still deferred. |
| F8 | Mermaid symbol context offloading | [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | Offload symbol context to a mermaid diagram instead of chonkie-compressing `debug_history`. |

### Track M1 — Sub-state migration (v2.x → v3.0) ✅ COMPLETE

**Status:** ✅ COMPLETE — shipped across v2.1–v2.7 + v3.0. All 8 accessors are safe (no split-brain). Legacy flat-field mirrors removed. The v2.0.5 split-brain warning is lifted.

For the full migration narrative + per-version details, see [SUBSTATE.md](SUBSTATE.md) § "Migration History". Summary:
- 7 sub-states migrated: `vcs` (v2.1), `plan` (v2.2), `files` (v2.3), `impact` (v2.4), `debug` (v2.5), `verify` (v2.6), `memory` (v2.7). `tdd` was already migrated in v2.0 → v2.0.1.
- v3.0 cleanup: ~32 legacy flat-field mirrors removed; 8 accessor functions simplified to 4-line sub-state-only reads; 13 ephemeral flat fields explicitly declared; 16 node files + 9 test files updated.
- Total scope: ~15 nodes (RMW rewrites) + 4 route functions + 9 test files + 1 state.py rewrite.

---

*Last updated: 2026-07-14 (v3.0 — flat-field removal, Track M1 ✅ COMPLETE; v2.7 — memory sub-state; v2.6 — verify sub-state; v2.5 — debug sub-state; v2.4 — impact sub-state; v2.3 — files sub-state; v2.2 — plan sub-state; v2.1 — vcs sub-state; v2.0.5 — Phase 4g review; v2.0.4 subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
