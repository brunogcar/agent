<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v2.0-alpha | 2026-07-11 | **2.0 refactor — Phase 1 (Foundation) + Phase 2 (State redesign).** New `core/json_extract.py` (consolidated JSON extraction — single source of truth for all LLM JSON parsing). `helpers._parse_json` + `router._extract_first_json` now delegate to it. `analyze_impact._run_async` simplified to `asyncio.run(coro)` (was create/destroy event loop per call — resource-leak risk flagged by 3 LLMs in v1.4 cross-LLM review). `helpers.py` adds cancellation flag (`request_cancellation()` / `clear_cancellation()` / `is_cancellation_requested()`) — `_call()` checks flag before each retry, `invoke_with_timeout()` sets it on timeout and clears it at start. `state.py` introduces 8 sub-state TypedDicts (`PlanState`, `TDDState`, `FilesState`, `ImpactState`, `DebugState`, `VerifyState`, `VCSState`, `MemoryState`) + 8 backward-compat accessor functions (`_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`). New `debug_history` field in `TDDState` (for Phase 4 #37 context summarization). Legacy flat fields KEPT for backward compat (removed in Phase 6). `commit.py` migrated to use `_get_vcs(state, "branch", "main")` as proof-of-concept for accessor pattern. `graph.py` `WORKFLOW_METADATA` version bumped to `"2.0-alpha"`. **Graph structure unchanged — still 17 nodes (Phase 3 will split nodes).** All changes marked `[v2.0]` in source. |
| v1.4 | 2026-07-11 | **Pre-2.0 hardening + dead code cleanup.** Cross-LLM review (DeepSeek, Qwen, MiMo, Kimi) found 19 real issues. Fixed 4 P0 (constants field mismatch, verify empty pytest, path traversal, dead flag_reset node), 6 P1 (shape_artifacts branch, tracer.error sig, verify stuck, brainstorm KG, execute _parse_json, commit label), 4 P2 (ruff scope, branch uniqueness, _call retry, create_skill atomic). Deleted 5 dead code items (test_mapper, test_runner, mermaid, route_after_analyze_impact, node_brainstorm mapping). 17 nodes (was 18). All fixes marked `[Pre-2.0 Fix]`. |
| v1.3 | 2026-07-10 | **GitHub + Swarm integration:** New `node_publish` (push + PR create + optional auto-merge). New `github_ops.py` helper module. Swarm 2-run debug (consensus → vote, confidence HIGH/MEDIUM/LOW). 6 new config flags (all default OFF). 4 new state fields (`pushed`, `pr_number`, `pr_url`, `swarm_verdict`). Fix TypedDict drift (`branch` field). All operations graceful-skip if GitHub not configured — zero behavior change unless opted in. |
| v1.2 | 2026-07-08 | **JSON schema enforcement:** `debug.py` now passes `json_schema` via `_call()` helper. Schema: `{root_cause: str, defense_notes: str, fix: str}`. `_call()` helper updated to accept `json_schema` param. LM Studio enforces at generation time. Defensive JSON parsing stays as fallback. |
| v1.1.2 | 2026-07-06 | **Small-fix batch:** #39 (stuck detection — same error signature on consecutive iterations bails to verify), #44 (structured artifacts in return dict), #46 (multi-file git-diff input via `files={"all changed": ""}` + `git_diff=True`), #47 (dry-run guards on write_files/commit/branch). Also folded in v1.1.1: `TestPartialDictReturns` + changelog cleanup. |
| v1.1 | 2026-07-06 | **Facade fix + WORKFLOW_METADATA + routing fixes.** Fixed the broken facade (was unreachable for 2 versions due to 4 dead imports + double-compile + uncompiled-graph crash in base.py). Added `WORKFLOW_METADATA` (17 nodes, loops, branches, safety_features). Fixed `route_after_write_files` to include `audit`/`edit` (was skipping impact analysis). Made `distill_memory` non-fatal (`tracer.warning` not `tracer.error`). Added facade contract tests. Based on cross-LLM review (Gemini, DeepSeek, Mistral, Qwen, Kimi). |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items — see Completed) |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items — see Completed) |
| v1.0 | — | Released — 17-node LangGraph StateGraph |

---

## ⚠️ Breaking Changes

### v1.1 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| `run_autocode_agent()` now delegates to `run_workflow("autocode")` | Was calling `get_graph().compile().invoke()` directly (crashed). Now goes through base.py for tracing/checkpointing/timeout. | No migration — the public API signature is unchanged. Callers get checkpoint/resume for free. |
| Removed 4 dead imports from facade (`AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot`) | These were already removed from `state.py`/`routes.py`/`git_ops.py` in v1.0.1/v1.0.2 but the facade still imported them → `ImportError`. | No migration — the facade was unreachable before. |
| `route_after_write_files` now routes `audit`/`edit` to `node_analyze_impact` | Was skipping impact analysis for these task types. | No migration — impact analysis is the correct path for audit/edit. |
| `distill_memory` uses `tracer.warning` (was `tracer.error`) | Distillation failure no longer logged as error (it's non-fatal — code already committed). | No migration — semantic change only. |
| `base.py` autocode branch uses `invoke_with_timeout` (was `graph.invoke()` on uncompiled graph) | Was crashing with `AttributeError: 'StateGraph' has no attribute 'invoke'`. | No migration — was broken before. |
| Removed internal constants from `__all__` (`MAX_RETRIES`, `MAX_FILE_CHARS`, `DEBUG`, etc.) | These are implementation details, not public API. | If external code imported them from `workflows.autocode`, import from `workflows.autocode_impl.state` instead. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| **[v2.0] `core/json_extract.py`** | ✅ v2.0-alpha | New consolidated JSON extraction utility. 3 functions: `extract_json`, `extract_json_array`, `extract_first_json`. Single source of truth for all LLM JSON parsing. `helpers._parse_json` and `router._extract_first_json` now delegate to this module. Eliminates the historical split where `helpers.py` (markdown-fence strip + `json.loads`) and `router.py` (`json.JSONDecoder().raw_decode()`) each rolled their own. |
| **[v2.0] `analyze_impact._run_async` simplified** | ✅ v2.0-alpha | Was: `loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); loop.run_until_complete(coro); loop.close()` — created and destroyed a new event loop per call. Now: `asyncio.run(coro)`. Fixes the resource-leak risk flagged by 3 LLMs (DeepSeek, Kimi, MiMo) in the v1.4 cross-LLM review (see "Cross-LLM Review Findings (Pre-2.0)" § deferred-to-2.0). |
| **[v2.0] `helpers.py` cancellation flag** | ✅ v2.0-alpha | New module-level flag + 3 functions: `request_cancellation()`, `clear_cancellation()`, `is_cancellation_requested()`. `_call()` checks the flag before each retry — if cancellation was requested (e.g., `invoke_with_timeout` timed out), `_call()` aborts instead of sleeping through backoff. `invoke_with_timeout()` calls `clear_cancellation()` at start and `request_cancellation()` on timeout. Partial mitigation for #35 (daemon-thread zombie risk) — full process-level termination deferred to Phase 7. |
| **[v2.0] `state.py` sub-state TypedDicts + accessors** | ✅ v2.0-alpha | 8 new sub-state TypedDicts: `PlanState`, `TDDState`, `FilesState`, `ImpactState`, `DebugState`, `VerifyState`, `VCSState`, `MemoryState`. 8 backward-compat accessor functions: `_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`. Each accessor reads from the corresponding sub-state dict if present, else falls back to the legacy flat field (which is KEPT for backward compat — removed in Phase 6). New `debug_history` field in `TDDState` (placeholder for Phase 4 #37 context summarization — not yet populated by any node). |
| **[v2.0] `commit.py` migrated to `_get_vcs` accessor** | ✅ v2.0-alpha | `node_git_commit` now reads `state["branch"]` via `_get_vcs(state, "branch", "main")` instead of `state.get("branch", "main")`. Proof-of-concept for the accessor pattern — `commit.py` is the first node migrated. Other nodes continue to read legacy flat fields (will migrate in Phase 3 as they are split/refactored). No behavior change — accessor returns the same value as the legacy fallback path. |
| **[v2.0] `graph.py` version bump + cancellation wiring** | ✅ v2.0-alpha | `WORKFLOW_METADATA["version"]` bumped from `"1.4"` to `"2.0-alpha"`. `invoke_with_timeout()` (in `base.py`, called from the autocode facade) now calls `clear_cancellation()` at start and `request_cancellation()` on timeout so the in-flight `_call()` retries notice and abort. Graph structure unchanged — still 17 nodes (Phase 3 will split `node_write_files` and `node_verify` per the v1.4 2.0 Review Notes). |
| 17-node LangGraph StateGraph | ✅ v1.0 | classify → validate → brainstorm → plan → branch → tests → execute → write → impact → run tests → debug → retry → verify → report → commit → memory → skill |
| Mode-driven workflow | ✅ v1.0 | fix_error, improve, add_feature, create_skill, unclear |
| TDD-first | ✅ v1.0 | Tests generated before implementation |
| Iterative debug loop | ✅ v1.0 | Debug → retry → run tests until pass or max retries |
| Impact analysis | ✅ v1.0 | Blast radius analysis using dependency graph |
| Git integration | ✅ v1.0 | Branch creation and commit |
| Memory integration | ✅ v1.0 | Procedural memory storage |
| Report generation | ✅ v1.0 | Structured report with result and metadata |
| Filelock + atomic writes | ✅ v1.0 | Prevents race conditions and data corruption |
| Result compression | ✅ v1.0 | compress_result() prevents oversized responses |
| #1 `node_write_files` `run_dir` NameError | ✅ v1.0.1 | False positive — not a bug |
| #2 `node_report` type annotation | ✅ v1.0.2 | Changed `AutocodeState` → `dict` |
| #3 `node_create_skill` writes to agent_root | ✅ v1.0.2 | Now resolves via `project_root` |
| #4 Dead route functions removed | ✅ v1.0.2 | `route_after_brainstorm`, `route_after_debug` |
| #5 `mermaid.py` LangGraph internals | ✅ v1.0.2 | Added `getattr()` guards |
| #6 `test_runner.py` `_should_copy_file` arg | ✅ v1.0.2 | Now passes `cfg.protected_files` |
| #7 `node_verify` `lint_passed=True` when ruff missing | ✅ v1.0.2 | Changed to `None` |
| #8 `node_report` `modified_files` empty | ✅ v1.0.1 | Fixed via `files_map` population |
| #9 `node_write_files` no `status` on error | ✅ v1.0.2 | Returns `{"status": "error"}` on JSON parse failure |
| #10 `node_git_branch` no error handling | ✅ v1.0.2 | Checks return value, returns error status |
| #11 `node_validate_input` path traversal | ✅ v1.0.2 | Catches Windows absolute, URL-encoded, Unicode |
| #12 `node_write_plan` slug may be empty | ✅ v1.0.2 | Fallback to `"autocode"` |
| #13 `node_write_files` `FileLock` no retry | ✅ v1.0.2 | Added 1 retry on timeout |
| #14 `node_run_tests` test file may not exist | ✅ v1.0.2 | Filters missing files |
| #15 `node_create_skill` no filename validation | ✅ v1.0.2 | Added `_sanitize_skill_name()` |
| #16 `node_create_skill` no syntax check | ✅ v1.0.2 | Added `ast.parse()` validation |
| #17 `node_create_skill` `skill_created` never set | ✅ v1.0.2 | Now sets `skill_created: True` |
| #28 `node_distill_memory` `classification` dead code | ✅ v1.0.2 | Removed — field never set |
| #29 Test restructure | ✅ v1.0.2 | Per-node tests already exist |
| #30 Configurable timeout | ✅ v1.0.2 | `invoke_with_timeout()` using `cfg.autocode_graph_timeout` |
| #31 Remove `__all__` internal constants | ✅ v1.1 | Facade `__all__` now only exports public API |
| **Facade fix (4 dead imports)** | ✅ v1.1 | `AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot` removed |
| **Double-compile fix** | ✅ v1.1 | `base.py` uses `invoke_with_timeout` (was `graph.compile().invoke()` — crashed) |
| **`WORKFLOW_METADATA`** | ✅ v1.1 | 17 nodes, loops, branches, safety_features |
| **Facade contract tests** | ✅ v1.1 | `test_facade.py` — import + run_workflow + graph structure + routing |
| **`audit`/`edit` routing fix** | ✅ v1.1 | Now route to `analyze_impact` (was skipping it) |
| **`distill_memory` non-fatal** | ✅ v1.1 | `tracer.warning` not `tracer.error` (code already committed) |
| **#33 Partial-dict returns** | ✅ v1.1.1 | All 16 nodes already return partial dicts (done in v1.0.1/v1.0.2). Added `TestPartialDictReturns` to lock in the clean state. |
| **#2 Checkpoint/resume** | ✅ v1.1 | Facade delegates to `run_workflow("autocode")` which has checkpoint/resume infra. |
| **#39 Stuck detection in debug loop** | ✅ v1.1.2 | Same error signature on consecutive iterations → `tdd_status="stuck"` → routes to verify (skips doomed debug loop). `_error_signature()` normalizes stderr. |
| **#44 Structured artifacts** | ✅ v1.1.2 | `run_autocode_agent()` now returns an `artifacts` dict: `commit_sha`, `branch_name`, `modified_files`, `test_results`, `tdd_status`, `tdd_iteration`, `verification_passed`, `skill_created`, `skill_path`. |
| **#46 Multi-file git-diff input** | ✅ v1.1.2 | `files={"all changed": ""}` + `git_diff=True` resolves changed files via `git diff --name-only`. Merges with explicitly-passed files. |
| **#47 Dry-run actually dry** | ✅ v1.1.2 | `dry_run=True` now guards `node_write_files`, `node_commit`, `node_git_branch`. Guards run AFTER validation checks so dry_run still surfaces JSON/verification errors. |
| **#43 GitHub PR workflow** | ✅ v1.3 | New `node_publish` between `node_commit` and `node_distill_memory`. Push branch → create PR → optional auto-merge. Gated on `AUTOCODE_PUSH_ON_COMMIT` + `AUTOCODE_OPEN_PR` + `AUTOCODE_AUTO_MERGE` flags (all default OFF). Uses new `workflows/autocode_impl/github_ops.py` helper module. |
| **`node_publish`** | ✅ v1.3 | New node: push + PR create + optional auto-merge. All operations graceful-skip if GitHub not configured. PR body includes task, commit SHA, verification status, swarm verdict. |
| **`github_ops.py` helper** | ✅ v1.3 | New module mirroring `git_ops.py` pattern: `_github_push()`, `_github_pr_create()`, `_github_pr_comment()`, `_github_pr_merge()`, `_github_pull()`, `_swarm_debug_consensus()`. Lazy imports, tracer.step logging, structured returns. |
| **Swarm debug integration** | ✅ v1.3 | `node_systematic_debug` now optionally uses swarm (2-run pattern: consensus → vote). Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split). Non-blocking: fix always applies. LOW confidence → optional PR comment. Falls back to single-LLM if swarm off/unavailable. |
| **6 new config flags** | ✅ v1.3 | `AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`. All default OFF — v1.3 behaves identically to v1.2 unless explicitly opted in. |
| **4 new state fields** | ✅ v1.3 | `pushed: bool`, `pr_number: int`, `pr_url: str`, `swarm_verdict: dict`. Plus fix: `branch: str` added to TypedDict (was read by `branch.py` but not declared — TypedDict drift). |
| **Optional pull before branch** | ✅ v1.3 | `node_git_branch` now optionally pulls recent commits before creating the branch (`AUTOCODE_PULL_BEFORE_BRANCH=1`). Uses `github(action="pull")`. Non-blocking — pull failure doesn't stop the workflow. |
| **P0: constants.py field name mismatch** | ✅ v1.4 | `DEBUG_SYSTEM` prompt used `hypothesis`/`defense_note`; code read `root_cause`/`defense_notes`. Swarm debug root_cause was always "Unknown". Fixed. Found by: MiMo. |
| **P0: verify.py empty pytest args** | ✅ v1.4 | If no test files existed, `pytest` ran with no args → entire project test suite. Now skips pytest. Found by: DeepSeek. |
| **P0: path traversal in write_files** | ✅ v1.4 | LLM-generated paths not validated (only user input validated). Added `_is_path_safe()` using `Path.resolve().is_relative_to()`. Found by: Qwen. |
| **P0: dead node_write_files_with_flag_reset** | ✅ v1.4 | Registered but never wired. Reset `step_attempt` (non-existent field). Deleted. Found by: MiMo, Kimi. |
| **P1: _shape_artifacts reads branch_name** | ✅ v1.4 | `plan.py` writes `branch`, facade reads `branch_name` → always `""`. Fixed with fallback. Found by: MiMo, Kimi. |
| **P1: tracer.error signature mismatch** | ✅ v1.4 | `helpers.py` passed 2 args (trace_id missing). Fixed to 3 args. Found by: Qwen. |
| **P1: verify doesn't handle tdd_status="stuck"** | ✅ v1.4 | Stuck routed to verify but verify only checked max_retries_exceeded. Now handles both. Found by: DeepSeek. |
| **P1: brainstorm KG files not in LLM prompt** | ✅ v1.4 | KG files merged into state AFTER LLM call. Brainstorm never saw them. Fixed. Found by: MiMo. |
| **P1: execute.py uses raw json.loads** | ✅ v1.4 | Markdown-fenced output → modified_files=[]. Now uses `_parse_json`. Found by: MiMo. |
| **P1: commit.py label KeyError** | ✅ v1.4 | `s["label"]` → KeyError if step lacks label. Now `.get("label", "step")`. Found by: DeepSeek. |
| **P2: verify ruff on entire workspace** | ✅ v1.4 | Was: `ruff check workspace_root` (slow, false failures). Now scopes to `modified_files`. Found by: DeepSeek, Qwen, Kimi. |
| **P2: branch name collision across runs** | ✅ v1.4 | Same task → same branch → cross-contamination. Now appends trace_id suffix. Found by: MiMo, Kimi. |
| **P2: _call no retry** | ✅ v1.4 | Single LLM failure crashed workflow. Now retries 2× with exponential backoff. Found by: MiMo. |
| **P2: create_skill non-atomic write** | ✅ v1.4 | Direct `write_text` → crash corrupts file. Now: tempfile + os.replace. Found by: MiMo. |
| **Dead code: test_mapper.py** | ✅ v1.4 | Unused (analyze_impact imports from `core.kgraph.test_mapper`). Deleted. Found by: Kimi. |
| **Dead code: test_runner.py** | ✅ v1.4 | Unused (node_run_tests has its own). Deleted. Found by: Kimi. |
| **Dead code: mermaid.py** | ✅ v1.4 | Never called (WORKFLOW_METADATA serves same purpose). Deleted. Found by: Kimi. |
| **Dead code: route_after_analyze_impact** | ✅ v1.4 | Always returned "node_run_tests". Replaced with direct edge. Found by: MiMo. |
| **Dead code: "node_brainstorm" mapping** | ✅ v1.4 | route_after_classify never returns "node_brainstorm". Removed from graph mapping. Found by: MiMo. |

---

## 🔍 Cross-LLM Review Findings (Pre-2.0)

v1.4 is based on a cross-LLM code review where 4 LLMs (DeepSeek, Qwen, MiMo, Kimi)
reviewed the autocode workflow code independently. Here's what was real vs noise:

### Reviewers and scope
- **DeepSeek**: 28 findings (4 P0, 5 P1, 7 P2, 4 P3, testing gaps, architecture)
- **Qwen**: 10 findings (2 P0, 4 P1, 4 P2) — couldn't fetch all files, asked for more
- **MiMo**: 20 findings (2 P0, 5 P1, 8 P2, 5 P3) — most thorough, found the constants bug
- **Kimi**: 28 findings (6 P0, 7 P1, 10 P2, 7 P3, architecture, testing)

### What was REAL (19 items, all fixed in v1.4)
See the ✅ v1.4 entries above. Key findings:
- The `constants.py` field name mismatch (MiMo P0.1) was the most damaging — swarm debug's root_cause was always "Unknown"
- Path traversal for LLM-generated paths (Qwen P0.1) was a real security gap
- 3 LLMs independently flagged ruff on entire workspace (real P2)
- 3 LLMs independently flagged `_run_async` event loop pattern (real P2, deferred to 2.0)

### What was FALSE (verified as wrong)
- **Qwen P0.2** — `run_dir` NameError when test_code empty: FALSE (lines 200-202 are inside the `if state.get("test_code"):` block, properly guarded)
- **Kimi P0.3** — `json_schema` may crash LM Studio: FALSE (`_call` helper already has 400 fallback that strips json_schema, built in v1.2)
- **DeepSeek P1.5** — debug node doesn't pass `json_schema` to `_call`: FALSE (debug.py line 100 passes `json_schema=_DEBUG_JSON_SCHEMA`; DeepSeek said "file cuts off at L43" — didn't see full file)

### What was PARTIALLY TRUE
- **DeepSeek P0.2/P0.3** — error status not checked by routers: partially true. Routers don't check `status=="error"` but in practice the nodes set other fields that route correctly. Worth adding status checks in 2.0.
- **Kimi P0.6** — test_files paths wrong for workspace projects: partially true. The `startswith("autocode/")` check is fragile but works for current structure. P2 not P0. Deferred to 2.0.

### What was deferred to 2.0 (not fixed in v1.4)
- `_run_async` event loop pattern (3 LLMs flagged) — needs full async refactor, too big for pre-2.0
- `node_write_files` does too much (2 LLMs flagged) — architecture concern, 2.0 will split it
- `node_verify` is a "god node" (Kimi flagged) — architecture, 2.0 will split it
- Debug node statelessness (#37) — blocks context summarization, needs full refactor
- State field bloat (~35 fields) — 2.0 will consider nested sub-states
- `invoke_with_timeout` daemon thread zombie risk (#35) — needs process-level termination

> **[v2.0-alpha] Update:** The `_run_async` event loop pattern is now FIXED (Phase 1 — see ✅ v2.0-alpha entries above). State field bloat is being addressed by the sub-state TypedDicts + accessor pattern (Phase 2 — see ✅ entries). The remaining 4 items (`node_write_files` split, `node_verify` split, debug node statelessness, daemon thread zombie risk) are scheduled for Phase 3 / Phase 4 / Phase 7 — see the "2.0 Refactor Progress" section below.

---

## 🏗️ 2.0 Refactor Progress

The autocode workflow is undergoing a 7-phase refactor to address the technical debt
documented in v1.4 (see "Cross-LLM Review Findings (Pre-2.0)" § deferred-to-2.0 and
"2.0 Review Notes" above). Each phase is independently shippable — no phase breaks the
public API. All v2.0 work is marked `[v2.0]` in source code and `# TODO(2.0):` markers
point forward to later phases.

| Phase | Name | Status | Summary |
|-------|------|--------|---------|
| **1** | Foundation | ✅ v2.0-alpha | `core/json_extract.py` (consolidated JSON extraction); `analyze_impact._run_async` simplified to `asyncio.run(coro)`; `helpers.py` cancellation flag (`request_cancellation` / `clear_cancellation` / `is_cancellation_requested`) wired into `_call()` and `invoke_with_timeout()`. |
| **2** | State redesign (backward-compat layer) | ✅ v2.0-alpha | 8 sub-state TypedDicts (`PlanState`/`TDDState`/`FilesState`/`ImpactState`/`DebugState`/`VerifyState`/`VCSState`/`MemoryState`) + 8 backward-compat accessor functions (`_get_plan`/`_get_tdd`/`_get_files`/`_get_impact`/`_get_debug`/`_get_verify`/`_get_vcs`/`_get_memory`). New `debug_history` field in `TDDState` (Phase 4 placeholder). `commit.py` migrated to `_get_vcs` as proof-of-concept. Legacy flat fields KEPT (removed in Phase 6). `WORKFLOW_METADATA["version"]` → `"2.0-alpha"`. |
| **3** | Node splits | `# TODO(2.0):` pending | Split `node_write_files` (does too much per v1.4 review) and `node_verify` (god node per Kimi). Migrate each split node to use accessors instead of legacy flat fields. |
| **4** | Debug history + context summarization | `# TODO(2.0):` pending | Populate `debug_history` (already declared in `TDDState` in Phase 2). Wire `node_systematic_debug` to accumulate history across iterations. Add a `summarize_context` node before debug re-entry (closes #37 — see "In Progress / Next Up"). |
| **5** | Async refactor | `# TODO(2.0):` pending | Convert remaining async-in-sync-graph patterns. Full review of `_run_async` callers now that Phase 1 simplified the helper. |
| **6** | Legacy field removal | `# TODO(2.0):` pending | Remove legacy flat fields from `AutocodeState` AFTER all nodes have migrated to accessors (Phase 3). Remove accessor legacy-fallback branches. |
| **7** | Timeout hardening | `# TODO(2.0):` pending | Address #35 (`invoke_with_timeout` daemon-thread zombie risk) with process-level termination (`multiprocessing` or `concurrent.futures`). The Phase 1 cancellation flag is a partial mitigation; Phase 7 closes it out. |

**Phase 1 + Phase 2 = v2.0-alpha.** Graph structure unchanged (still 17 nodes) — Phase 3
will be the first phase to touch the graph topology. No public API changes in either
phase; backward compat is preserved by the accessor legacy-fallback layer.

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 32 | **IDE integration** | LSP or VS Code extension for autocode. | P3 |
| 34 | **Remove `run_autocode_agent()` backward-compat shim** | Once all callers use `run_workflow("autocode")` directly, remove the shim. Audit callers first. | P2 |
| 35 | **`invoke_with_timeout` daemon-thread zombie risk** | On timeout, daemon thread keeps running (Python can't kill threads). Consider `concurrent.futures` with cancellation or `multiprocessing`. | P2 |
| 36 | **`create_skill` smoke-test import + git commit** | Currently has AST syntax check (v1.0.2 #16) but no import test or git commit. Skills should be committed like all other code changes. | P2 |
| 37 | **Context summarization node** | Compress debug-loop history before it overflows the LLM context window. Add a `summarize_context` node before the debug loop re-enters. **v1.3 note:** Chonkie `SentenceChunker` is the right tool for this compression (reuses `_chunk_text()` from file tool v1.2). **Dependency:** Current `debug.py` is stateless per iteration (each debug call sees only current test output, no accumulated history). This item depends on autocode first being refactored to accumulate debug-loop history across iterations. See `docs/TOOLS.md` § "Chunking (chonkie)". **v1.3 note:** Swarm debug does NOT solve this — it only sees the current iteration's test output, not history. Still blocked on debug history accumulation. | P1 (depends on debug history accumulation) |
| 38 | **Human-in-the-Loop (HiTL) approval** | Pause graph before `commit` or `create_skill`. Send notification, wait for approve/reject via MCP. | P2 |
| 40 | **Adaptive timeout by task type** | `create_skill`=120s, `audit`=300s, `feature`=900s. Better than one global timeout. | P2 |
| 41 | **AST/linter pre-check before pytest** | Run `ruff`/`flake8` before `pytest`. Catch indentation errors instantly without booting the test runner. | P2 |
| 42 | **Goal sanitization** | Enforce max length + strip control chars on `goal`/`task` input. Defense in depth (path traversal, command injection, token budget). | P2 |
| 43 | **GitHub PR workflow** | ✅ Shipped in v1.3 — see Completed section above. | ~~P2~~ Done |
| 45 | **Streaming node transitions** | Stream `tracer.step` events to the client via WebSocket so the user sees progress instead of a 5-minute blank wait. Needs gateway integration. | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove TDD-first** | TDD ensures test coverage. | Skip |
| 2 | **Remove debug loop** | Single-pass code generation misses edge cases. | Skip |
| 3 | **Remove impact analysis** | Blast radius analysis prevents unintended side effects. | Skip |
| 4 | **Remove git integration** | Git branches and commits are essential. | Skip |
| 5 | **Remove memory integration** | Procedural memory improves future performance. | Skip |
| 6 | **Real-time collaboration** | Multi-user editing requires complex state sync. | Skip |
| 7 | **Support non-Python languages** | Workflow is designed for Python. Other languages need tree-sitter per-lang. | Skip |

---

## 🔍 2.0 Review Notes

This section documents known technical debt and design decisions in v1.3 that
should be reviewed during the 2.0 refactoring. All items are marked with
`# TODO(2.0):` in the source code.

### Architecture

| Item | Location | Notes |
|------|----------|-------|
| `git_ops.py` + `github_ops.py` split | `workflows/autocode_impl/` | v1.3 keeps them separate because git (local) and github (remote) are separate tools. In 2.0, consider merging into a unified `vcs_ops.py` module. |
| `node_publish` as single node | `nodes/publish.py` | Currently one node handling push + PR + merge. In 2.0, consider splitting into separate `node_push`, `node_pr_create`, `node_pr_merge` for finer-grained routing and retry. |
| Debug node statelessness | `nodes/debug.py` | Each debug call sees only current test output, no accumulated history. Blocks context summarization (#37). Swarm debug does NOT solve this. Must be refactored in 2.0. |
| Swarm verdict non-blocking | `nodes/debug.py` | Low-confidence swarm verdict applies fix anyway (non-blocking). In 2.0, consider `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag for stricter gating. |
| Config flags are global | `core/config.py` | All 6 v1.3 flags are global. In 2.0, consider per-task overrides (e.g., different PR strategy for different task types). |

### Integration

| Item | Location | Notes |
|------|----------|-------|
| `AUTOCODE_AUTO_MERGE` hardcoded to squash | `nodes/publish.py` | In 2.0, add `AUTOCODE_AUTO_MERGE_METHOD` config (squash/merge/rebase). |
| Pull failure is non-blocking | `nodes/branch.py` | Pull failure doesn't stop the workflow. In 2.0, consider making this configurable (fail-fast vs graceful-skip). |
| Swarm confidence thresholds | `github_ops.py` | Currently: unanimous=HIGH, majority=MEDIUM, split/disagreement=LOW. In 2.0, review thresholds — maybe MEDIUM should require ≥3 providers. |
| PR body is minimal | `nodes/publish.py` | Currently includes task, commit SHA, verification status, swarm verdict. In 2.0, add test results, diff summary, impact warnings. |
| No retry on push/PR failure | `nodes/publish.py` | Push or PR creation failure is terminal. In 2.0, add retry logic for transient failures. |

### Documentation

| Item | Location | Notes |
|------|----------|-------|
| Stale env vars in AUTOCODE.md | `docs/workflows/AUTOCODE.md` | Lists `AUTOCODE_PLANNER_TIMEOUT` etc. which don't exist (timeouts come from `model_registry`). Fixed in v1.3 — verify the fix is complete. |
| `pull` action rebase param | `tools/github_ops/actions/pull.py` | `git pull --rebase` not supported. In 2.0, consider adding `rebase: bool` param. |

---

*Last updated: 2026-07-11 (v2.0-alpha — 2.0 refactor Phase 1 + Phase 2: new `core/json_extract.py`; `analyze_impact._run_async` → `asyncio.run`; `helpers.py` cancellation flag; `state.py` sub-state TypedDicts + 8 accessor functions; `commit.py` migrated to `_get_vcs`; `WORKFLOW_METADATA["version"]` → `"2.0-alpha"`; graph structure unchanged — 17 nodes). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
