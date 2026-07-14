<- Back to [Autocode Overview](../AUTOCODE.md)

# 🛡️ AI Instructions

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
14. **Never import removed symbols in the facade** — The facade was broken for 2 versions because it imported `AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot` after they'd been removed from `state.py`/`routes.py`/`git_ops.py`. Always run facade contract tests after refactor.
15. **Never call `.compile()` on an already-compiled graph** — `get_graph()` returns a `CompiledStateGraph` which has no `.compile()` method. Calling it crashes with `AttributeError`. Use `get_graph().invoke(state)` directly.
16. **Never let `distill_memory` fail the workflow** — The code is already committed by the time distill_memory runs. A ChromaDB failure there must not flip a successful workflow to failed. Use `tracer.warning` (not `tracer.error`).
17. **Never bypass `base.py`'s `run_workflow()` from the facade** — The facade delegates to `run_workflow("autocode")` for tracing, checkpointing, and timeout. Bypassing it (the old design) crashed and skipped safety infra.
18. **Never put push / PR / merge logic in `node_commit` — use `node_push` / `node_create_pr` / `node_merge_pr`** — `node_commit` is local-only (calls `git(action="commit")` via `vcs_ops.py`). ALL remote operations live in the split publish nodes.
19. **Never call GitHub API actions without `is_configured()`** — Every helper in `vcs_ops.py` MUST call `_github_is_configured()` (wraps `tools.github_ops.client.is_configured()`) before any GitHub API call.
20. **Never add an integration flag that defaults ON** — All 7 GitHub/Swarm/Subagent flags (`AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`, `AUTOCODE_SUBAGENT_DEBUG`) default OFF. Backward compat — with all OFF, autocode behaves identically to v1.2.
21. **Never block the debug loop on a swarm verdict** — Swarm debug (`AUTOCODE_SWARM_DEBUG=1`) is non-blocking by design. The fix is ALWAYS applied, regardless of confidence (HIGH/MEDIUM/LOW). LOW confidence surfaces as a PR comment (if `AUTOCODE_DEBUG_COMMENT_PR=1`), not as a workflow block.
22. **Never call `vcs_ops.py` helpers from outside `nodes/`** — The helpers (`_github_pull`, `_github_push`, `_github_pr_create`, `_github_pr_comment`, `_github_pr_merge`, `_swarm_debug_consensus`, `_git_commit`, `_git_create_branch`) are private to the autocode workflow nodes. External code MUST call the public `tools.github` / `tools.git` / `tools.swarm` facades.
23. **Never mix local and remote VCS helpers inappropriately** — `_git_*` helpers = local git (no network, no auth). `_github_*` helpers = remote GitHub (requires `is_configured()`). Exception: `_swarm_debug_consensus()` may be called by `node_systematic_debug` directly.
24. **Never use raw `json.loads()` on LLM-generated output** — LLMs frequently wrap JSON in markdown fences (```` ```json\n{...}\n``` ````). Raw `json.loads()` raises `JSONDecodeError`. Always use `_parse_json()` (in `helpers.py`) which strips fences via `core.json_extract.extract_json`.
25. **Never write LLM-generated paths to disk without `_is_path_safe()`** — `node_validate_input` path traversal check only covers USER-supplied paths. LLM-generated paths (`patches[].path`, `new_files{}` keys) MUST be validated via `_is_path_safe(base_path, rel_path)` (in `apply_patches.py`, imported by `write_new_files.py`).
26. **Never re-add `node_write_files_with_flag_reset`** — It was dead code: registered in the graph but never wired, and it reset `step_attempt` (a field that doesn't exist in `AutocodeState`).
27. **Never re-add `route_after_analyze_impact`** — It was a conditional router that ALWAYS returned `"node_run_tests"`. Use a direct edge (`workflow.add_edge("node_analyze_impact", "node_run_tests")`).
28. **Never re-add `mermaid.py`, `test_mapper.py`, or `test_runner.py` to `workflows/autocode_impl/`** — All three were unused. `WORKFLOW_METADATA` serves the mermaid purpose; `analyze_impact` imports from `core.kgraph.test_mapper`; `node_run_tests` has its own test execution logic.
29. **Never call `tracer.error()` with 2 args** — The signature is `tracer.error(trace_id, category, message)` (3 args). Passing only 2 args misattributed trace data.
30. **Never assume `state["branch_name"]` is populated** — `node_write_plan` writes to `state["branch"]` (not `branch_name`). The facade's `_shape_artifacts()` was reading `branch_name` → always `""`. Always use `branch`.
31. **Never use `s["label"]` on plan steps** — LLM-returned plans are not guaranteed to label every step. ALWAYS use `s.get("label", "step")` (or another sensible default) to avoid `KeyError`.
32. **Never remove legacy flat fields from `AutocodeState` yet** — Sub-states are PRIMARY storage, but legacy flat fields are KEPT as mirrors for backward compat with unmigrated nodes + tests. Removal is `# TODO(2.0-post):`.
33. **Never bypass the accessor layer when writing NEW code that reads sub-state fields** — New nodes (and edits to existing nodes) MUST read sub-state via their accessors (`_get_tdd`, `_get_impact`, `_get_memory`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_files`, `_get_plan`) so the eventual legacy-flat-field removal is a mechanical diff. **[v2.2] 🎉 ALL 8 ACCESSORS ARE NOW SAFE.** The Track M1 migration (v2.1–v2.7) is complete — every sub-state has writers that use RMW + flat mirrors, and every reader uses the accessor. The v2.0.5 split-brain warning is lifted. **v3.0 next step:** remove the legacy flat fields from `AutocodeState` TypedDict + `_default_state()`, remove the accessor legacy-fallback branches, update test files to assert on sub-state reads. See CHANGELOG Future Tracks, Track M1 for the v3.0 cleanup checklist.
34. **Never wire the backward-compat wrappers (`node_write_files`, `node_verify`, `node_publish`) into the graph** — These 3 wrappers are registered via `add_node(...)` for `import`-compatibility but NOT wired (no edges in or out). The graph flow uses the split nodes directly.
35. **Never call `_call()` on the backward-compat wrappers in tests** — The LLM `_call(...)` invocation moved from `verify.py` to `llm_review.py` (Phase 3.2 split). Tests that need to mock `_call` MUST patch `workflows.autocode_impl.nodes.llm_review._call`, not `…verify._call`.
36. **Never repeat a failed debug approach — check `debug_history` first** — `node_systematic_debug` accumulates `debug_history` across iterations; the last 5 entries are injected into the LLM user prompt under a `PRIOR DEBUG ATTEMPTS (do NOT repeat these)` block. If you bypass this, the LLM will re-suggest the same failed hypothesis.
37. **Never wire `node_summarize_context` as a wrapper or skip it in the debug loop** — It is a FULLY-WIRED active node between `node_systematic_debug` and `node_apply_patches`. Skipping it means the LLM sees unbounded `debug_history` in long-running debug loops.
38. **Never call `helpers._write_files()` — it is DELETED** — `helpers._write_files()` was DELETED in v2.0 GA after a dead-code audit found it was never called by any node. Code that imports it will now `ImportError`. Use the split nodes: `node_apply_patches` + `node_write_new_files` + `node_persist_artifacts`.
39. **Never hand-roll what the stdlib ships — check rung 3 first** — The 7-rung Lazy Dev ladder (see ALWAYS DO #54) prefers stdlib (`collections.defaultdict`, `itertools.chain`, `pathlib.Path.read_text`, `dataclasses.asdict`, `functools.lru_cache`, `subprocess.run`) over hand-rolled equivalents.
40. **Never enable `AUTOCODE_SWARM_DEBUG` and `AUTOCODE_SUBAGENT_DEBUG` simultaneously** — They're alternative debug paths. Swarm = multi-provider consensus (2 runs, vote); Subagent = single isolated dispatch (curated context, no session state). Pick ONE per workflow run.

## ✅ ALWAYS DO

14. **Always return `dict` from nodes** — Not `AutocodeState`. Partial updates only.
15. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
16. **Always handle validation failure gracefully** — Invalid input should return error state, not crash.
17. **Always test `node_classify_task` with mode override** — Assert correct task_type regardless of LLM output.
18. **Always test `node_brainstorm` with KG files** — Assert merged files.
19. **Always test `node_analyze_impact` with empty files_map** — Assert early return.
20. **Always test `node_write_files` with patch** — Assert atomic write and no `.bak` files.
21. **Always test `node_run_tests` with missing test files** — Assert error state.
22. **Always test `node_verify` with missing ruff** — Assert `lint_passed=None` (was `True`).
23. **Always test `node_git_commit` with no changes** — Assert skipped state.
24. **Always test `node_distill_memory` with missing hypothesis** — Assert graceful handling.
25. **Always test `node_create_skill` with invalid name** — Assert error state.
26. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
27. **Always use `defense_notes` (plural)** — The state field is `defense_notes`, not `defense_note`.
28. **Always use `asyncio.to_thread()` for CPU-bound work** — AST parsing and file I/O blocks the event loop.
29. **Always wrap `vcs_ops.py` helper calls in the node's natural skip-conditions** — `node_push`/`node_create_pr`/`node_merge_pr` check `status in {needs_clarification, failed, skipped}`, `verification_passed`, `dry_run` BEFORE calling any helper.
30. **Always use `tracer.step()` (not `tracer.error()`) for graceful-skip events in `vcs_ops.py`** — `is_configured()` returning `False` is NOT an error — it's the documented opt-out path.
31. **Always lazy-import `tools.github` and `tools.swarm` inside the helper function** — `vcs_ops.py` mirrors the `git_ops.py` pattern: `from tools.github import github` is INSIDE each `_github_*()` helper, not at module top.
32. **Always log the swarm verdict in `state.swarm_verdict`** — When `_swarm_debug_consensus()` returns a non-`None` result, `node_systematic_debug` MUST set `swarm_verdict` in its return dict for downstream inspection.
33. **Always gate `AUTOCODE_DEBUG_COMMENT_PR` on `state["pr_number"]`** — The PR-comment-on-LOW-confidence flow checks THREE conditions: `confidence == "LOW"` AND `cfg.autocode_debug_comment_pr` AND `state["pr_number"]` is set.
36. **Always use `_parse_json()` for LLM JSON output** — The helper in `helpers.py` strips markdown fences before calling `json.loads()`. Delegates to `core/json_extract.py` (single source of truth).
37. **Always validate LLM-generated paths with `_is_path_safe()`** — The helper in `nodes/apply_patches.py` uses `Path.resolve().is_relative_to()` to verify the resolved target stays inside `base_path`. Imported by `write_new_files.py`.
38. **Always include `trace_id` suffix in branch names** — `node_write_plan` MUST format branches as `autocode/{slug}-{tid_suffix}` where `tid_suffix = tid.replace("-", "")[:8]`. Without this, same task → same branch → cross-contamination.
39. **Always use atomic writes (`tempfile` + `os.replace`) for skill files** — `node_create_skill` MUST write via `tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')` followed by `os.replace(tmp_path, final_path)`.
40. **Always handle `tdd_status="stuck"` in the verify chain** — `route_after_run_tests` routes `"stuck"` (same error signature on consecutive iterations) to the verify chain, skipping the doomed debug loop.
41. **Always skip `pytest` when no test files exist** — The verify chain MUST check `tests_dir.exists() or test_file.exists()` BEFORE invoking pytest. Running `pytest` with no args executes the entire project test suite.
42. **Always scope `ruff check` to `modified_files` only** — The verify chain MUST pass the modified file paths as explicit args to `ruff check` (e.g., `ruff check path1 path2 ...`). Running `ruff check workspace_root` is slow and surfaces false failures from unrelated files.
43. **Always align prompt field names with state field names** — When editing a SYSTEM prompt in `constants.py` that asks the LLM to return JSON keys, the keys MUST match the `AutocodeState` TypedDict (e.g., `root_cause` + `defense_notes` plural — was `hypothesis` + `defense_note` singular, broke swarm debug root_cause).
44. **Always use the accessor functions for sub-state reads in new code** — **[v2.2] 🎉 ALL 8 accessors are now safe:** `_get_tdd`, `_get_impact`, `_get_memory`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_files`, `_get_plan`. Every sub-state has writers that use RMW + flat mirrors, and every reader uses the accessor. The Track M1 migration (v2.1–v2.7) is complete. For state fields that are NOT in a sub-state (core task fields, ephemeral fields like `_pytest_output`), use `state.get(key, default)` directly. v3.0 will remove the legacy flat fields + accessor fallback branches.
46. **Always delegate LLM JSON parsing to `core/json_extract.py`** — The module is the single source of truth for all LLM JSON parsing. It exposes 3 functions: `extract_json(text)`, `extract_json_array(text)`, `extract_first_json(text)`.
47. **New code MUST import the split nodes directly, not the wrappers** — Phase 3 split `node_write_files` / `node_verify` / `node_publish` into 10 focused nodes. Import paths:
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

    The wrappers are kept ONLY for backward compat with existing external callers + tests; new code MUST NOT depend on them.
48. **`_build_pr_body(state)` lives in `create_pr.py`** — Moved from `publish.py` in Phase 3.3 (signature unchanged). New code that needs the PR body builder imports from `create_pr.py`.
49. **`_is_path_safe(base_path, rel_path)` lives in `apply_patches.py`** — Moved from `write_files.py` in Phase 3.1. New code that needs the path-traversal guard imports from `apply_patches.py`.
50. **Use 4-phase debug structure (investigation → pattern → hypothesis → fix)** — `DEBUG_SYSTEM` in `constants.py` is a 4-phase structured prompt inspired by obra/superpowers `systematic-debugging`. The LLM must declare its current `phase` in the JSON output (enum enforced by `_DEBUG_JSON_SCHEMA`).
51. **Honor the architecture-question threshold (3+ consecutive failures)** — `nodes/debug.py` defines `_ARCHITECTURE_QUESTION_THRESHOLD = 3`. If `len(debug_history) >= 3` AND the last 3 entries all have `tests_passed=False`, bail with `tdd_status="max_retries_exceeded"` + procedural memory store. Different from #39 stuck detection — fires on DIFFERENT errors each iteration, suggesting architectural bug.
52. **`node_summarize_context` writes `debug_summary` to `TDDState`** — Wired between `node_systematic_debug` and `node_apply_patches` in the debug loop. Compresses `debug_history` via chonkie `SentenceChunker(chunk_size=512)` (soft dep) with JSON-of-last-3-entries fallback. **[Hardening P0.1]** MUST use read-modify-write to preserve sibling TDD fields.
53. **Import VCS functions from `vcs_ops.py`, not `git_ops` / `github_ops`** — VCS consolidation merged the former `git_ops.py` (local operations) + `github_ops.py` (remote operations) into one unified `vcs_ops.py`. Import paths:
    - `from workflows.autocode_impl.vcs_ops import _git_commit, _git_create_branch` (Local operations section)
    - `from workflows.autocode_impl.vcs_ops import _github_pull, _github_push, _github_pr_create, _github_pr_comment, _github_pr_merge` (Remote operations section)
    - `from workflows.autocode_impl.vcs_ops import _swarm_debug_consensus` (Swarm integration section)

    `git_ops.py` + `github_ops.py` are kept as thin re-export wrappers for backward compat.
54. **Follow the 7-rung Lazy Dev ladder before writing code** — Integrated into `CODER_SYSTEM` (inspired by [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)):
    1. **Does this need to exist at all?** (YAGNI — speculative need = skip it)
    2. **Already in this codebase?** (reuse — grep `workflows/autocode_impl/` + `core/` + `tools/` first)
    3. **Stdlib does it?** (use it — see NEVER DO #39)
    4. **Native platform feature?** (use it — prefer DB constraints, OS-level file locking, `tempfile` + `os.replace`)
    5. **Already-installed dependency solves it?** (use it — never `pip install` a new dep when an existing one covers the case)
    6. **Can it be one line?** (one line — the smallest change that works)
    7. **Only then: the minimum code that works.** (No speculative abstractions, no interface-with-one-impl)

    Core principle: **"lazy about the solution, never about reading"** — the ladder runs AFTER understanding the problem (read the spec, read the failing test, read the surrounding code). `DEBUG_SYSTEM` Phase 4 ("fix") also applies the ladder.
55. **Use the `ponytail:` comment convention for deliberate simplifications** — `# ponytail: <ceiling>, <upgrade path if ceiling hit>`. Examples:
    - `# ponytail: global lock, per-account locks if contention > N`
    - `# ponytail: in-memory cache, Redis if multi-process`
    - `# ponytail: hard-coded 7-day TTL, cfg.autocode_xxx_ttl if per-task overrides needed`
    - `# ponytail: single-file write, atomic-batch-write if >1 file ever needed`

    Purposes: (1) signals DELIBERATE simplification (not a missed edge case); (2) names the CEILING that would force a rewrite; (3) names the UPGRADE PATH. NOT for tech debt — use `# TODO:` / `# FIXME:` for those.
56. **When `AUTOCODE_SUBAGENT_DEBUG=1`, the subagent gets isolated curated context** — The subagent does NOT see autocode session state (no `debug_history`, no `tdd_state`, no `plan_state`). It receives only what `node_systematic_debug` constructs: failing test, error output, current source file, prior fix attempts (truncated). This is by design — superpowers pattern: "you construct exactly what they need". Never pass `state` wholesale to `agent(action="subagent")`; always build a focused context dict.

---

## 🚫 Anti-Patterns & Lessons Learned

> **`.bak` files:** `.bak` backup files were created on every file write (patch.py, write_files.py, helpers.py), violating project rules and cluttering the repo. **Fix:** Use atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) only. Git is the backup.

> **`_git_snapshot()` dead code:** `_git_snapshot()` called `git(action="snapshot")` which was removed from the git tool — always failed silently. **Fix:** Removed entirely. The git branch itself is the safety net — `git checkout main` or `git revert` recovers.

> **`files_map` never populated:** `files_map` was declared in `AutocodeState` and initialized to `{}`, but no node ever populated it. `node_analyze_impact` read it and found it empty. **Fix:** `node_write_new_files` now populates `files_map` with file snapshots (content_preview, md5, size) after writing files.

> **`node_analyze_impact` async-in-sync-graph:** `node_analyze_impact` was declared `async def` but LangGraph `StateGraph.add_node` expects sync functions. **Fix:** Converted to `def` (sync). Async calls wrapped in `_run_async()` which uses `asyncio.run(coro)`.

> **`node_brainstorm` discarded KG files:** `node_brainstorm` merged `kg_files` into `files_update` but stored `state["files"]` (the original) instead of the merged result. **Fix:** Store `files_update` (merged) instead of `state["files"]` (original). **[Hardening P1.10]** Now unconditionally initializes `files_update` before the KG block (was using brittle `dir()` check).

> **`node_distill_memory` field name mismatch:** Read `hypothesis` and `defense_note` (singular), but `node_systematic_debug` sets `root_cause` and `defense_notes` (plural). Both fields were always empty. **Fix:** Changed to `root_cause` and `defense_notes` to match.

> **Facade broken for 2 versions:** The facade (`workflows/autocode.py`) imported 4 symbols (`AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot`) after they'd been removed — `import workflows.autocode` raised `ImportError` for 2 versions. **Fix:** Removed dead imports; added facade contract tests (`test_facade.py`).

> **`base.py` double-compile crash:** `base.py`'s autocode branch did `graph = build_graph(); result = graph.invoke(state)`. But `build_graph()` returns an uncompiled `StateGraph`, which has no `.invoke()` method. **Fix:** `base.py` now uses `invoke_with_timeout(initial_state)` which calls `get_graph()` (returns compiled) internally.

> **`route_after_write_files` skipped impact for audit/edit:** Only routed `fix`/`fix_error`/`refactor`/`improve`/`feature` to `node_analyze_impact`. `audit` and `edit` fell through, skipping impact analysis. **Fix:** Added `audit` and `edit` to the impact-analysis path.

> **`branch` field TypedDict drift:** `branch: str` was read by `nodes/branch.py` and set by `nodes/plan.py` since v1.0, but was NOT declared in the `AutocodeState` TypedDict. **Fix:** Added `branch: str` declaration to `AutocodeState`.

---

*Last updated: 2026-07-14 (v2.2 — Track M1 Batch 3c: plan sub-state migration, 🎉 ALL 8 ACCESSORS NOW SAFE — Track M1 complete; v2.3 — Batch 3b: files; v2.1 — Batch 3a: vcs; v2.5 + v2.6 — Batch 2: debug + verify; v2.4 + v2.7 — Batch 1: impact + memory; v2.0.5 — Phase 4g review: split-brain accessor warning (#33 + #44); v2.0.4 subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
