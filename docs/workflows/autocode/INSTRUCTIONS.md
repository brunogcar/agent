<- Back to [Autocode Overview](../AUTOCODE.md)

# 🛡️ AI Instructions

> **[v3.0]** Sub-state architecture is the ONLY storage. Accessors are the ONLY read path. See [SUBSTATE.md](SUBSTATE.md) for the full reference.

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove TDD-first** — Test generation ensures code quality.
4. **Never remove debug loop** — Iteration catches edge cases.
5. **Never remove impact analysis** — Blast radius analysis prevents unintended side effects.
6. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
7. **Never create `.bak` files** — forbidden by project rules.
8. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
9. **Never skip `compileall` before `pytest`** — catches syntax errors early.
10. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`. Always pass `action="dispatch"` for LLM calls.
11. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).
12. **Never use `files_context` field** — It doesn't exist in `AutocodeState`. Use `_files_context()` helper.
13. **Never store `files_map` as `dict[str, FileSnapshot]`** — No node populates it. Use `modified_files` instead.
14. **Never import removed symbols in the facade** — The facade was broken for 2 versions because it imported `AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot` after they'd been removed. Always run facade contract tests after refactor.
15. **Never call `.compile()` on an already-compiled graph** — `get_graph()` returns a `CompiledStateGraph`. Use `get_graph().invoke(state)` directly.
16. **Never let `distill_memory` fail the workflow** — Code is already committed by the time distill runs. A ChromaDB failure must not flip a successful workflow to failed. Use `tracer.warning` (not `tracer.error`).
17. **Never bypass `base.py`'s `run_workflow()` from the facade** — The facade delegates to `run_workflow("autocode")` for tracing, checkpointing, and timeout. Bypassing it crashes and skips safety infra.
18. **Never put push / PR / merge logic in `node_commit` — use `node_push` / `node_create_pr` / `node_merge_pr`** — `node_commit` is local-only. ALL remote operations live in the split publish nodes.
19. **Never call GitHub API actions without `is_configured()`** — Every `vcs_ops.py` helper MUST call `_github_is_configured()` before any GitHub API call.
20. **Never add an integration flag that defaults ON** — All 7 GitHub/Swarm/Subagent flags default OFF. Backward compat — with all OFF, autocode behaves identically to v1.2.
21. **Never block the debug loop on a swarm verdict** — Swarm debug is non-blocking by design. LOW confidence surfaces as a PR comment, not as a workflow block.
22. **Never call `vcs_ops.py` helpers from outside `nodes/`** — The helpers are private to autocode workflow nodes. External code MUST call the public `tools.github` / `tools.git` / `tools.swarm` facades.
23. **Never mix local and remote VCS helpers inappropriately** — `_git_*` = local (no network). `_github_*` = remote (requires `is_configured()`). Exception: `_swarm_debug_consensus()` may be called by `node_systematic_debug` directly.
24. **Never use raw `json.loads()` on LLM-generated output** — LLMs frequently wrap JSON in markdown fences. Always use `_parse_json()` (in `helpers.py`) which strips fences via `core.json_extract.extract_json`.
25. **Never write LLM-generated paths to disk without `_is_path_safe()`** — `node_validate_input` only covers USER-supplied paths. LLM-generated paths (`patches[].path`, `new_files{}` keys) MUST be validated via `_is_path_safe(base_path, rel_path)` (in `apply_patches.py`, imported by `write_new_files.py`).
26. **Never re-add `node_write_files_with_flag_reset`** — It was dead code: registered but never wired, and it reset a field that doesn't exist.
27. **Never re-add `route_after_analyze_impact`** — It was a conditional router that ALWAYS returned `"node_run_tests"`. Use a direct edge.
28. **Never re-add `mermaid.py`, `test_mapper.py`, or `test_runner.py`** — All three were unused. `WORKFLOW_METADATA` serves the mermaid purpose; `analyze_impact` imports from `core.kgraph.test_mapper`; `node_run_tests` has its own test execution logic.
29. **Never call `tracer.error()` with 2 args** — Signature is `tracer.error(trace_id, category, message)` (3 args).
30. **Never assume `state["branch_name"]` is populated** — `node_write_plan` writes to `state["branch"]` (not `branch_name`). Always use `branch`.
31. **Never use `s["label"]` on plan steps** — LLM-returned plans are not guaranteed to label every step. ALWAYS use `s.get("label", "step")`.
32. **Never re-add legacy flat-field mirrors** — [v3.0] All legacy flat fields were removed. Sub-states are the ONLY storage. Never re-add flat-field mirrors to node returns — write to sub-states via RMW only. Ephemeral flat fields (test_results, test_code, etc.) stay flat by design. See [SUBSTATE.md](SUBSTATE.md).
33. **Always use accessors for sub-state reads** — [v3.0] ALL 8 accessors are the ONLY way to read sub-state fields (`_get_tdd`, `_get_impact`, `_get_memory`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_files`, `_get_plan`). Direct `state.get("flat_field")` for sub-state fields returns `None`. For ephemeral flat fields, use `state.get(key, default)`. See [SUBSTATE.md](SUBSTATE.md).
34. **Never wire the backward-compat wrappers (`node_write_files`, `node_verify`, `node_publish`) into the graph** — These 3 wrappers are registered via `add_node(...)` for `import`-compatibility but NOT wired. The graph flow uses the split nodes directly.
35. **Never call `_call()` on the backward-compat wrappers in tests** — The LLM `_call(...)` invocation moved from `verify.py` to `llm_review.py` (Phase 3.2 split). Tests MUST patch `workflows.autocode_impl.nodes.llm_review._call`.
36. **Never repeat a failed debug approach — check `debug_history` first** — Last 5 entries are injected into the LLM user prompt under a `PRIOR DEBUG ATTEMPTS (do NOT repeat these)` block.
37. **Never wire `node_summarize_context` as a wrapper or skip it in the debug loop** — It is a FULLY-WIRED active node. Skipping it means the LLM sees unbounded `debug_history` in long-running debug loops.
38. **Never call `helpers._write_files()` — it is DELETED** — Use the split nodes: `node_apply_patches` + `node_write_new_files` + `node_persist_artifacts`.
39. **Never hand-roll what the stdlib ships — check rung 3 first** — The 7-rung Lazy Dev ladder (see ALWAYS DO #38) prefers stdlib over hand-rolled equivalents.
40. **Never enable `AUTOCODE_SWARM_DEBUG` and `AUTOCODE_SUBAGENT_DEBUG` simultaneously** — They're alternative debug paths. Pick ONE per workflow run.
41. **Never use `state.get()` for sub-state fields** — [v3.0] Sub-state fields live ONLY in sub-state dicts (`state["tdd"]`, `state["vcs"]`, etc.). The legacy flat fields were removed — `state.get("tdd_status")`, `state.get("modified_files")`, `state.get("branch")`, etc. will return `None`. Use accessors (`_get_tdd`, `_get_files`, `_get_vcs`, etc.) instead. See [SUBSTATE.md](SUBSTATE.md).
42. **Never write flat-field mirrors in node returns** — [v3.0] Node returns MUST write sub-state only via RMW. Do NOT include legacy flat fields like `{"modified_files": [...], "branch": "..."}` — write `{"files_state": current_files, "vcs": current_vcs}` instead. Ephemeral flat fields (`test_results`, `test_code`, etc.) are still flat by design. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern".
43. **Never assume `input_files` exists in `files_state`** — [v3.0] `input_files` was removed from `FilesState` — it was just a mirror of the core `files` flat field. `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly (core flat field). See [SUBSTATE.md](SUBSTATE.md) § "Core Flat Fields".

## ✅ ALWAYS DO

1. **Always return `dict` from nodes** — Not `AutocodeState`. Partial updates only.
2. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
3. **Always handle validation failure gracefully** — Invalid input should return error state, not crash.
4. **Always test `node_classify_task` with mode override** — Assert correct task_type regardless of LLM output.
5. **Always test `node_brainstorm` with KG files** — Assert merged files.
6. **Always test `node_analyze_impact` with empty files_map** — Assert early return.
7. **Always test `node_write_files` with patch** — Assert atomic write and no `.bak` files.
8. **Always test `node_run_tests` with missing test files** — Assert error state.
9. **Always test `node_verify` with missing ruff** — Assert `lint_passed=None` (was `True`).
10. **Always test `node_git_commit` with no changes** — Assert skipped state.
11. **Always test `node_distill_memory` with missing hypothesis** — Assert graceful handling.
12. **Always test `node_create_skill` with invalid name** — Assert error state.
13. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
14. **Always use `defense_notes` (plural)** — The state field is `defense_notes`, not `defense_note`.
15. **Always use `asyncio.to_thread()` for CPU-bound work** — AST parsing and file I/O blocks the event loop.
16. **Always wrap `vcs_ops.py` helper calls in the node's natural skip-conditions** — `node_push`/`node_create_pr`/`node_merge_pr` check `status`, `verification_passed`, `dry_run` BEFORE calling any helper.
17. **Always use `tracer.step()` (not `tracer.error()`) for graceful-skip events in `vcs_ops.py`** — `is_configured()` returning `False` is NOT an error — it's the documented opt-out path.
18. **Always lazy-import `tools.github` and `tools.swarm` inside the helper function** — `from tools.github import github` is INSIDE each `_github_*()` helper, not at module top.
19. **Always log the swarm verdict in `state.swarm_verdict`** — When `_swarm_debug_consensus()` returns a non-`None` result, `node_systematic_debug` MUST set `swarm_verdict` in its return dict (via the `debug` sub-state RMW in v3.0).
20. **Always gate `AUTOCODE_DEBUG_COMMENT_PR` on `state["pr_number"]`** — The PR-comment-on-LOW-confidence flow checks THREE conditions: `confidence == "LOW"` AND `cfg.autocode_debug_comment_pr` AND `_get_vcs(state, "pr_number", 0)` is set.
21. **Always use `_parse_json()` for LLM JSON output** — The helper in `helpers.py` strips markdown fences before calling `json.loads()`. Delegates to `core/json_extract.py`.
22. **Always validate LLM-generated paths with `_is_path_safe()`** — The helper in `nodes/apply_patches.py` uses `Path.resolve().is_relative_to()`. Imported by `write_new_files.py`.
23. **Always include `trace_id` suffix in branch names** — `node_write_plan` MUST format branches as `autocode/{slug}-{tid_suffix}` where `tid_suffix = tid.replace("-", "")[:8]`.
24. **Always use atomic writes (`tempfile` + `os.replace`) for skill files** — `node_create_skill` MUST write via `tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')` followed by `os.replace(tmp_path, final_path)`.
25. **Always handle `tdd_status="stuck"` in the verify chain** — `route_after_run_tests` routes `"stuck"` to the verify chain, skipping the doomed debug loop.
26. **Always skip `pytest` when no test files exist** — The verify chain MUST check `tests_dir.exists() or test_file.exists()` BEFORE invoking pytest.
27. **Always scope `ruff check` to `modified_files` only** — Pass modified file paths as explicit args. Running `ruff check workspace_root` is slow and surfaces false failures.
28. **Always align prompt field names with state field names** — When editing a SYSTEM prompt that asks the LLM to return JSON keys, the keys MUST match the `AutocodeState` TypedDict (e.g., `root_cause` + `defense_notes` plural — was `hypothesis` + `defense_note` singular, broke swarm debug).
29. **Always use accessor functions for sub-state reads** — [v3.0] ALL 8 accessors are safe and are the ONLY path: `_get_tdd`, `_get_impact`, `_get_memory`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_files`, `_get_plan`. No legacy fallback exists. For ephemeral flat fields (`test_results`, `test_code`, `_pytest_output`, `lint_output`, etc.), use `state.get(key, default)` directly. See [SUBSTATE.md](SUBSTATE.md).
30. **Always delegate LLM JSON parsing to `core/json_extract.py`** — Single source of truth for all LLM JSON parsing. Exposes 3 functions: `extract_json(text)`, `extract_json_array(text)`, `extract_first_json(text)`.
31. **New code MUST import the split nodes directly, not the wrappers** — Phase 3 split `node_write_files` / `node_verify` / `node_publish` into 10 focused nodes:
    - `from workflows.autocode_impl.nodes.apply_patches import node_apply_patches, _is_path_safe`
    - `from workflows.autocode_impl.nodes.write_new_files import node_write_new_files`
    - `from workflows.autocode_impl.nodes.persist_artifacts import node_persist_artifacts`
    - `from workflows.autocode_impl.nodes.run_pytest import node_run_pytest`
    - `from workflows.autocode_impl.nodes.run_lint import node_run_lint`
    - `from workflows.autocode_impl.nodes.llm_review import node_llm_review` (tests mock `workflows.autocode_impl.nodes.llm_review._call`)
    - `from workflows.autocode_impl.nodes.verify_decision import node_verify_decision`
    - `from workflows.autocode_impl.nodes.push import node_push`
    - `from workflows.autocode_impl.nodes.create_pr import node_create_pr, _build_pr_body`
    - `from workflows.autocode_impl.nodes.merge_pr import node_merge_pr`

    The wrappers are kept ONLY for backward compat; new code MUST NOT depend on them.
32. **`_build_pr_body(state)` lives in `create_pr.py`** — Moved from `publish.py` in Phase 3.3 (signature unchanged).
33. **`_is_path_safe(base_path, rel_path)` lives in `apply_patches.py`** — Moved from `write_files.py` in Phase 3.1.
34. **Use 4-phase debug structure (investigation → pattern → hypothesis → fix)** — `DEBUG_SYSTEM` is a 4-phase structured prompt inspired by obra/superpowers. The LLM must declare its current `phase` in the JSON output (enum enforced by `_DEBUG_JSON_SCHEMA`).
35. **Honor the architecture-question threshold (3+ consecutive failures)** — `nodes/debug.py` defines `_ARCHITECTURE_QUESTION_THRESHOLD = 3`. If `len(debug_history) >= 3` AND the last 3 entries all have `tests_passed=False`, bail with `tdd_status="max_retries_exceeded"` + procedural memory store. Different from #25 stuck detection — fires on DIFFERENT errors each iteration.
36. **`node_summarize_context` writes `debug_summary` to `TDDState`** — Wired between `node_systematic_debug` and `node_apply_patches`. Compresses `debug_history` via chonkie `SentenceChunker(chunk_size=512)` (soft dep) with JSON-of-last-3-entries fallback. **[Hardening P0.1]** MUST use read-modify-write to preserve sibling TDD fields. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern".
37. **Import VCS functions from `vcs_ops.py`, not `git_ops` / `github_ops`** — VCS consolidation merged the former into one unified `vcs_ops.py`:
    - `from workflows.autocode_impl.vcs_ops import _git_commit, _git_create_branch` (Local operations section)
    - `from workflows.autocode_impl.vcs_ops import _github_pull, _github_push, _github_pr_create, _github_pr_comment, _github_pr_merge` (Remote operations section)
    - `from workflows.autocode_impl.vcs_ops import _swarm_debug_consensus` (Swarm integration section)

    `git_ops.py` + `github_ops.py` are kept as thin re-export wrappers for backward compat.
38. **Follow the 7-rung Lazy Dev ladder before writing code** — Integrated into `CODER_SYSTEM` (inspired by [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)):
    1. **Does this need to exist at all?** (YAGNI — speculative need = skip it)
    2. **Already in this codebase?** (reuse — grep `workflows/autocode_impl/` + `core/` + `tools/` first)
    3. **Stdlib does it?** (use it — see NEVER DO #39)
    4. **Native platform feature?** (use it — prefer DB constraints, OS-level file locking, `tempfile` + `os.replace`)
    5. **Already-installed dependency solves it?** (use it — never `pip install` a new dep when an existing one covers the case)
    6. **Can it be one line?** (one line — the smallest change that works)
    7. **Only then: the minimum code that works.** (No speculative abstractions, no interface-with-one-impl)

    Core principle: **"lazy about the solution, never about reading"** — the ladder runs AFTER understanding the problem (read the spec, read the failing test, read the surrounding code). `DEBUG_SYSTEM` Phase 4 ("fix") also applies the ladder.
39. **Use the `ponytail:` comment convention for deliberate simplifications** — `# ponytail: <ceiling>, <upgrade path if ceiling hit>`. Examples:
    - `# ponytail: global lock, per-account locks if contention > N`
    - `# ponytail: in-memory cache, Redis if multi-process`
    - `# ponytail: hard-coded 7-day TTL, cfg.autocode_xxx_ttl if per-task overrides needed`

    Purposes: (1) signals DELIBERATE simplification (not a missed edge case); (2) names the CEILING that would force a rewrite; (3) names the UPGRADE PATH. NOT for tech debt — use `# TODO:` / `# FIXME:` for those.
40. **When `AUTOCODE_SUBAGENT_DEBUG=1`, the subagent gets isolated curated context** — The subagent does NOT see autocode session state. It receives only what `node_systematic_debug` constructs: failing test, error output, current source file, prior fix attempts (truncated). This is by design — superpowers pattern: "you construct exactly what they need". Never pass `state` wholesale to `agent(action="subagent")`.

---

## 🚫 Anti-Patterns & Lessons Learned

> **[v3.0] Using `state.get()` for sub-state fields:** The legacy flat fields (`tdd_status`, `modified_files`, `branch`, `commit_sha`, `verification_passed`, `root_cause`, `defense_notes`, etc.) were removed. `state.get("tdd_status", "")` now returns `""` (the flat field doesn't exist) — silently wrong, not loudly wrong. **Fix:** Use accessors (`_get_tdd(state, "status", "")`, `_get_files(state, "modified_files", [])`, etc.). The accessor is the ONLY path. See [SUBSTATE.md](SUBSTATE.md).

> **[v3.0] Writing flat-field mirrors in node returns:** Returning `{"modified_files": [...]}` (a flat field) when you meant to update `files_state` is silent corruption — the flat field was a no-op since v3.0 removed it from `AutocodeState`. Downstream readers using `_get_files(state, "modified_files", [])` won't see your update. **Fix:** Always use RMW: `current_files = dict(state.get("files_state", {}))`, mutate, return `{"files_state": current_files}`. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern".

> **[v3.0] Assuming `input_files` exists in `files_state`:** `input_files` was a mirror of the core `files` flat field — both pointed to the same dict. v3.0 removed the mirror to eliminate split-brain. Code that did `_get_files(state, "input_files", {})` now returns `{}` (the sub-state key was removed), even when files were passed via the facade. **Fix:** `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly (the core flat field, set by the facade). See [SUBSTATE.md](SUBSTATE.md) § "Core Flat Fields".

> **[v3.0] Sub-state clobbering (no RMW):** LangGraph replaces dict values, doesn't deep-merge. Returning `{"tdd": {"debug_history": [...]}}` clobbers `iteration`, `status`, `source_code`, etc. — every other `tdd` field is lost. The v2.0.1 hardening P0 fix added RMW everywhere; v3.0 made it mandatory because there's no flat-field mirror to silently back you up. **Fix:** Always `current_tdd = dict(state.get("tdd", {}))`, mutate, return `{"tdd": current_tdd}`. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern".

> **[v3.0] Reading from the wrong sub-state key:** The `plan` field is overloaded — `state["plan"]` is the flat `list[dict]` step list (kept flat for backward compat with route_after_* lookups), while the sub-state lives under `state["plan_state"]`. `_get_plan(state, key, default)` reads from `plan_state` (NOT `plan`). Don't confuse them. See [SUBSTATE.md](SUBSTATE.md) § "The 8 Sub-states".

> **`.bak` files:** `.bak` backup files were created on every file write, violating project rules and cluttering the repo. **Fix:** Use atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) only. Git is the backup.

> **`_git_snapshot()` dead code:** `_git_snapshot()` called `git(action="snapshot")` which was removed — always failed silently. **Fix:** Removed entirely. The git branch itself is the safety net — `git checkout main` or `git revert` recovers.

> **`files_map` never populated:** `files_map` was declared in `AutocodeState` but no node ever populated it. **Fix:** `node_write_new_files` now populates `files_map` with file snapshots after writing files.

> **`node_analyze_impact` async-in-sync-graph:** `node_analyze_impact` was declared `async def` but LangGraph `StateGraph.add_node` expects sync functions. **Fix:** Converted to `def` (sync). Async calls wrapped in `_run_async()` which uses `asyncio.run(coro)`.

> **`node_brainstorm` discarded KG files:** `node_brainstorm` merged `kg_files` into `files_update` but stored `state["files"]` (the original) instead of the merged result. **Fix:** Store `files_update` (merged). **[Hardening P1.10]** Now unconditionally initializes `files_update` before the KG block.

> **`node_distill_memory` field name mismatch:** Read `hypothesis` and `defense_note` (singular), but `node_systematic_debug` sets `root_cause` and `defense_notes` (plural). Both were always empty. **Fix:** Changed to `root_cause` and `defense_notes` to match.

> **Facade broken for 2 versions:** The facade imported 4 symbols after they'd been removed — `import workflows.autocode` raised `ImportError` for 2 versions. **Fix:** Removed dead imports; added facade contract tests (`test_facade.py`).

> **`base.py` double-compile crash:** `base.py` did `graph = build_graph(); result = graph.invoke(state)`. But `build_graph()` returns an uncompiled `StateGraph`, which has no `.invoke()` method. **Fix:** `base.py` now uses `invoke_with_timeout(initial_state)` which calls `get_graph()` (returns compiled) internally.

> **`route_after_write_files` skipped impact for audit/edit:** Only routed `fix`/`fix_error`/`refactor`/`improve`/`feature` to `node_analyze_impact`. `audit` and `edit` fell through. **Fix:** Added `audit` and `edit` to the impact-analysis path.

> **`branch` field TypedDict drift:** `branch: str` was read by `nodes/branch.py` and set by `nodes/plan.py` since v1.0, but was NOT declared in the `AutocodeState` TypedDict. **Fix:** Added `branch: str` declaration (now lives in `VCSState` sub-state since v2.1).

---

*Last updated: 2026-07-14 (v3.0 — flat-field removal, Track M1 ✅ COMPLETE, legacy-fallback branches removed from all 8 accessors, #32 + #33 + #41-#43 added for v3.0, ALWAYS DO renumbered 1-40; v2.2 — Track M1 Batch 3c: plan sub-state migration, ALL 8 ACCESSORS NOW SAFE; v2.0.5 — Phase 4g review: split-brain accessor warning (lifted in v3.0); v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
