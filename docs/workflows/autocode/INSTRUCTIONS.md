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
20. **Never add an integration flag that defaults ON** — All 7 GitHub/Swarm/Subagent flags default OFF. Backward compat — with all OFF, autocode behaves identically to v1.2 (legacy) / v3.1.2.
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
44. **Never skip the `ruff --select E999` pre-check in `node_run_pytest`** — [v3.1 #41] The pre-check runs BEFORE pytest to catch syntax errors (saves a ~30s pytest run). If a syntax error exists, pytest would fail anyway with a less clear message. Non-fatal if ruff is not installed — falls through to pytest. Do NOT add an early-return-before-ruff path or bypass the pre-check "for speed".
45. **Never disable the `MAX_TASK_LENGTH = 2000` check in `node_validate_input`** — [v3.1 #42] Goal sanitization is the entry gate. Tasks > 2000 chars are rejected to prevent LLM token waste + context confusion. If a task legitimately needs more, split it into multiple workflow runs.
46. **Never call `_call()` without `trace_id=tid`** — [v3.1.2 P1] `_call()` retry-exhaustion errors include `trace_id` in their `tracer.error(...)` call. If you forget `trace_id=tid`, the error is attributed to `trace_id=""` and is unattributed in the trace viewer — invisible when debugging "which workflow produced this LLM failure?". All 8 in-tree callers (`classify.py`, `brainstorm.py`, `plan.py`, `tests.py`, `execute.py`, `debug.py`, `llm_review.py`, `create_skill.py`) now pass `trace_id=tid`. New `_call()` callers MUST do the same. See ALWAYS DO #43. This was a silent observability regression from v1.1 → v3.1.2 (the v1.1 hardening pass added `trace_id` to `_call()` but the callers weren't updated until v3.1.2).
47. **Never write an empty skill file** — [v3.1.2 P1] `node_create_skill` previously wrote an empty file + set `skill_created=True` if the LLM returned content under the wrong JSON key (`skill_code` instead of `skill_file`). Now: tries fallback keys (`skill_file` → `skill_code` → `code`), then returns `{"status": "failed", "error": "LLM returned empty skill_file content"}` if all are empty. The smoke-test (ALWAYS DO #44) also catches this at import time. Tests must use the correct key (`skill_file`) in their mock fixtures — the old `test_create_skill.py` was silently passing because it mocked `skill_code` (wrong key), masking the production bug.
48. **Never use top-level `kgraph` imports in autocode nodes — use lazy imports** — [v3.2 P0-1] `plan.py` and `debug.py` previously had `from core.kgraph import get_callers, get_dependencies` at module top level. `core.kgraph` initializes `tree_sitter_languages` on import — if that package is missing (or fails to load a language grammar), the entire `plan.py` / `debug.py` module fails to import, taking down the whole autocode workflow graph (since `build_graph()` imports every node module). v3.2 moved the `kgraph` import INSIDE the function that uses it (`_blast_radius_warning()` in `helpers.py`). Lazy-importing `core.kgraph` (and any other `tree_sitter_languages`-dependent module) is now mandatory for ALL autocode node modules. If you need kgraph data, do `from core.kgraph import get_callers` inside the function body, not at module top.
49. **Never return `None` from `_git_commit` for errors — return a structured dict** — [v3.2 P1-5] `_git_commit(message, tid, project_root)` previously returned `None` for BOTH "nothing to commit" (graceful no-op) AND "error during commit" (failure). Callers couldn't distinguish the two cases — `node_create_skill` treated both as "commit failed" and traced a warning even on the graceful no-op path. v3.2 changed the return to a structured dict `{"committed": bool, "sha": str, "reason": str}`: `committed=False` + `reason="nothing to commit"` is the graceful no-op; `committed=False` + `reason="error: <detail>"` is the failure path; `committed=True` + `sha="<commit_sha>"` + `reason="committed"` is the success path. New callers MUST inspect `result["committed"]` (and optionally `result["reason"]`) — never branch on `is None`.

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
41. **Always strip control chars from task input — let `node_validate_input` clean it** — [v3.1 #42] The validate node strips `[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]` (control chars except `\n\t\r`) from `task` before downstream nodes see it. Don't bypass it by writing to `state["task"]` directly elsewhere; if you must write task input, run it through the same `re.sub` pattern (or call `node_validate_input`). The cleaned task is returned in the state update so LangGraph merges it.
42. **When wiring a debug-loop exit, prefer `node_swarm_fallback` over a hard `status="failed"` if `AUTOCODE_SWARM_DEBUG_FALLBACK=1`** — [v3.1 #48] The swarm fallback (default OFF) gives the graph one more chance via multi-model consensus before giving up. HIGH confidence → reset `tdd.status` to `""` (one more debug cycle); LOW/unavailable → set `status="failed"` (proceeds to verify chain). `route_after_run_tests` already handles this — do not duplicate the routing logic in a node.
43. **Always pass `trace_id=tid` to `_call()`** — [v3.1.2 P1] `_call(...)` accepts a `trace_id` kwarg; retry-exhaustion errors attribute themselves to that trace. The v1.1 hardening pass added the kwarg to `_call()` but didn't update the callers — retry-exhaustion errors were unattributed (`trace_id=""`) for v1.1 → v3.1.2 (a silent observability regression). v3.1.2 wired `trace_id=tid` in all 8 callers (`classify.py`, `brainstorm.py`, `plan.py`, `tests.py`, `execute.py`, `debug.py`, `llm_review.py`, `create_skill.py`). New `_call()` callers MUST follow this pattern: extract `tid = state.get("trace_id", "")` at the top of the node, then pass `trace_id=tid` to every `_call(...)`. See NEVER DO #46.
44. **Always smoke-test skill files with importlib after writing** — [v3.1.2 #36] `ast.parse(code)` only verifies SYNTAX — it does NOT verify that imports resolve. A skill file that imports a non-existent module (or a module that doesn't exist in the agent's environment) passes AST validation but crashes on first use. `node_create_skill` now runs `importlib.util.spec_from_file_location(...)` + `spec.loader.exec_module(...)` after writing the file. On import failure: delete the broken file + return `{"status": "failed", "error": "Skill file failed import smoke-test: ..."}`. This catches: (a) missing dependencies, (b) circular imports, (c) top-level code that raises (e.g., `assert` failures, env-var lookups). Use `spec_from_file_location` (not `importlib.import_module`) to bypass namespace-package conflicts when an existing `skills/` package is already cached in `sys.modules`.
45. **Always clear `last_test_error` when resetting the debug loop** — [v3.2 P0-2] When `node_swarm_fallback` decides to give the debug loop one more chance (HIGH-confidence verdict), it resets `tdd.status = ""` and injects the swarm's suggested fix into `tdd.source_code`. v3.2 also requires clearing `tdd.last_test_error = ""` in the same RMW. Without this, the next `node_run_tests` invocation sees a stale `last_test_error` from BEFORE the swarm verdict — the stuck-detection logic (`route_after_run_tests` checks if the same error signature recurs) would immediately short-circuit back to the verify chain, burning the swarm's fresh fix attempt in a single iteration. The swarm's verdict is the new context; the prior error is no longer relevant. Same rule applies to any other node that resets `tdd.status` for a fresh debug cycle: always RMW `last_test_error = ""` alongside the status reset.
46. **Always handle `test_code` as `list[str]` in consumers** — [v3.2 P0-4] `node_write_tests` writes `test_code` as `list[str]` (multiple test strings, one per test function). Consumers that pass `test_code` into LLM prompts MUST handle the list type — never assume it's a string. v3.2 P0-4 fixed `node_llm_review` which was doing `test_code[:1000]` on a list — that returns a list slice (the first 1000 elements, not the first 1000 chars) + then `repr()`-rendered the list slice into the prompt, producing garbage. The correct pattern: `tc = state.get("test_code", [])`; `if isinstance(tc, list): tc = "\n\n".join(tc)`; `tc_preview = tc[:1000]`. `node_persist_artifacts` already does this join correctly; `node_llm_review` was the only consumer that drifted.
47. **Always run validation in `dry_run` paths** — [v3.2 P0-5] When `node_apply_patches` (or any node with a `dry_run` early-return path) skips writes because `dry_run=True`, it MUST still run path validation (`_is_path_safe()`), protected-file checks, and exists-checks on the target paths. v3.2 P0-5 fixed `apply_patches.py` which was returning `{"status": "dry_run", ...}` BEFORE the per-patch validation loop — silently masking security-validation failures (path traversal, protected-file writes, missing-file apply attempts). In dry-run mode, the operator is using the run to validate the planned changes; if validation failures are hidden, the operator gets a false "looks good" signal and then the real (non-dry-run) run hits the failures unexpectedly. The `patch_errors` list MUST be populated even in dry-run mode so the operator sees what would have failed.
48. **Always use `cfg.sandbox_timeout` for subprocess timeouts, not hardcoded values** — [v3.2 P1-3] `node_run_pytest` previously hardcoded `subprocess.run(..., timeout=120)` for the pytest subprocess. v3.2 replaced `120` with `cfg.sandbox_timeout` (the configured sandbox-wide subprocess timeout). Hardcoded values bypass the operator's tuning of `cfg.sandbox_timeout` (e.g., on a slow CI runner, the operator bumps `cfg.sandbox_timeout` to 600s — but `node_run_pytest` would still time out at 120s). The same rule applies to `node_run_lint` (30s ruff timeout) and any other node that invokes `subprocess.run` with a timeout: read `cfg.sandbox_timeout` (or a per-task-type variant of it) instead of hardcoding. If a node needs a tighter timeout than `cfg.sandbox_timeout` (e.g., the ruff E999 syntax pre-check uses 10s), that's fine — but the default for the main subprocess call must come from config.

---

## 🚫 Anti-Patterns & Lessons Learned

> **[v3.0] Using `state.get()` for sub-state fields:** The legacy flat fields (`tdd_status`, `modified_files`, `branch`, `commit_sha`, `verification_passed`, `root_cause`, `defense_notes`, etc.) were removed. `state.get("tdd_status", "")` now returns `""` (the flat field doesn't exist) — silently wrong, not loudly wrong. **Fix:** Use accessors (`_get_tdd(state, "status", "")`, `_get_files(state, "modified_files", [])`, etc.). The accessor is the ONLY path. See [SUBSTATE.md](SUBSTATE.md).

> **[v3.0] Writing flat-field mirrors in node returns:** Returning `{"modified_files": [...]}` (a flat field) when you meant to update `files_state` is silent corruption — the flat field was a no-op since v3.0 removed it from `AutocodeState`. Downstream readers using `_get_files(state, "modified_files", [])` won't see your update. **Fix:** Always use RMW: `current_files = dict(state.get("files_state", {}))`, mutate, return `{"files_state": current_files}`. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern".

> **[v3.0] Assuming `input_files` exists in `files_state`:** `input_files` was a mirror of the core `files` flat field — both pointed to the same dict. v3.0 removed the mirror to eliminate split-brain. Code that did `_get_files(state, "input_files", {})` now returns `{}` (the sub-state key was removed), even when files were passed via the facade. **Fix:** `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly (the core flat field, set by the facade). See [SUBSTATE.md](SUBSTATE.md) § "Core Flat Fields".

> **[v3.0] Sub-state clobbering (no RMW):** LangGraph replaces dict values, doesn't deep-merge. Returning `{"tdd": {"debug_history": [...]}}` clobbers `iteration`, `status`, `source_code`, etc. — every other `tdd` field is lost. The v2.0.1 hardening P0 fix added RMW everywhere; v3.0 made it mandatory because there's no flat-field mirror to silently back you up. **Fix:** Always `current_tdd = dict(state.get("tdd", {}))`, mutate, return `{"tdd": current_tdd}`. See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern".

> **[v3.0] Reading from the wrong sub-state key:** The `plan` field is overloaded — `state["plan"]` is the flat `list[dict]` step list (kept flat for backward compat with route_after_* lookups), while the sub-state lives under `state["plan_state"]`. `_get_plan(state, key, default)` reads from `plan_state` (NOT `plan`). Don't confuse them. See [SUBSTATE.md](SUBSTATE.md) § "The 8 Sub-states". **[v3.1.2 doc fix]** The "kept flat for backward compat" claim is stale — v3.0 removed the flat mirror; `plan` is sub-state-only now.

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

> **[v3.1.2] `_call()` retry-exhaustion errors unattributed:** The v1.1 hardening pass added `trace_id` as a kwarg to `_call()` but didn't update the 8 callers — retry-exhaustion errors used `trace_id=""` and were invisible in the trace viewer. v3.1.2 wired `trace_id=tid` in all 8 callers. **Fix:** Always pass `trace_id=tid` to `_call()` (see NEVER DO #46 + ALWAYS DO #43).

> **[v3.1.2] `node_create_skill` silently wrote empty files:** If the LLM returned content under `skill_code` instead of `skill_file`, the node wrote an empty file + set `skill_created=True`. The test mock used the wrong key too, so the bug was invisible. **Fix:** Tries fallback keys (`skill_file` → `skill_code` → `code`), rejects truly-empty output, runs importlib smoke-test (see NEVER DO #47 + ALWAYS DO #44).

> **[v3.2] Top-level `kgraph` import crashed `plan.py` + `debug.py`:** Both nodes had `from core.kgraph import get_callers, get_dependencies` at module top. `core.kgraph` initializes `tree_sitter_languages` on import — if the package is missing (or fails to load a grammar), the entire module fails to import, taking down the whole graph. **Fix:** Moved the import inside the function body (lazy import); extracted the shared blast-radius logic into `_blast_radius_warning()` in `helpers.py` (see NEVER DO #48).

> **[v3.2] `_git_commit` returned `None` for both "nothing to commit" and "error":** Callers couldn't distinguish the two cases. `node_create_skill` traced a warning on the graceful no-op path. **Fix:** Returns structured dict `{"committed", "sha", "reason"}` (see NEVER DO #49).

> **[v3.2] `node_swarm_fallback` HIGH path didn't clear `last_test_error`:** The node reset `tdd.status=""` for one more debug cycle but left the prior `last_test_error` in place — the next `node_run_tests` invocation hit stuck-detection on the stale error and short-circuited the swarm's fresh fix attempt. **Fix:** RMW `tdd.last_test_error=""` alongside the status reset (see ALWAYS DO #45).

> **[v3.2] `verify_decision.py` false-positive "HALLUCINATION DETECTED":** `automated_checks_passed` defaulted to `True` in the verify LLM JSON schema — when the LLM returned malformed JSON (missing the `automated_checks_passed` key), the default `True` was used, but real `tests_passed` was `False`, so the hallucination guard fired on every malformed-JSON run. **Fix:** Default changed to `False` (P0-3).

> **[v3.2] `node_llm_review` `test_code[:1000]` on a list:** `test_code` is `list[str]` (multiple test strings); `[:1000]` on a list returns a list slice (first 1000 elements, not first 1000 chars) + then `repr()`-rendered the slice into the prompt. **Fix:** Type-check + `"\n\n".join(test_code)` before slicing (see ALWAYS DO #46).

> **[v3.2] `apply_patches.py` `dry_run` path skipped validation:** Returned `{"status": "dry_run", ...}` BEFORE the per-patch validation loop, silently masking path-traversal + protected-file + missing-file failures. Operators using dry-run to validate planned changes got a false "looks good" signal. **Fix:** Run validation BEFORE returning the dry-run status; populate `patch_errors` even in dry-run mode (see ALWAYS DO #47).

---

## 🔮 Deferred Roadmap Items (Detailed Design)

The following roadmap items are deferred beyond v3.2. They're documented here so future implementers have a starting point — including the design decisions that need to be made, the dependencies that need to land first, and the inspiration sources.

### #35 — `invoke_with_timeout` daemon-thread zombie risk

**Current state (v3.2):** `invoke_with_timeout()` in `workflows/autocode_impl/graph.py` runs `graph.invoke(initial_state)` in a daemon thread via `threading.Thread(target=_invoke, daemon=True).start(); thread.join(timeout=timeout)`. **[Hardening P0.3]** Graph exceptions inside the daemon thread are captured via `nonlocal _invoke_error` and surfaced as `status="Autocode graph crashed: <exception>"` (was swallowed and misreported as timeout). **[v3.2 P2-2]** `invoke_with_timeout()` now also calls `_cleanup_old_autocode_runs()` at start (was never invoked anywhere — silent disk leak).

**What's deferred:** Python's `threading.Thread` does NOT support `Thread.kill()`. When `thread.join(timeout=...)` returns False (timeout exceeded), the daemon thread is STILL running — `request_cancellation()` is the only signal, and it relies on `_call()` checking `is_cancellation_requested()` between retries. If the thread is stuck inside a non-`_call()` operation (e.g., a long `subprocess.run()` in `node_run_pytest` without a timeout, a `git` invocation, a ChromaDB query), it will run to completion in the background — a zombie. The next workflow run starts a NEW thread while the zombie is still consuming CPU/IO.

**Proposed fix (deferred):** Re-architect `invoke_with_timeout()` to use `multiprocessing.Process` instead of `threading.Thread`:
- `Process.terminate()` sends SIGTERM (catchable) — `Process.kill()` sends SIGKILL (uncatchable).
- State must be picklable across the process boundary — `AutocodeState` contains `list[AnyMessage]` (LangGraph messages are dataclasses, should pickle, but verify).
- Result dict must come back via a `multiprocessing.Queue` or `multiprocessing.Pipe`.
- Signal handling: install a SIGTERM handler in the child that calls `request_cancellation()` and lets `_call()` finish its current iteration cleanly.
- Caveat: `multiprocessing.Process` on Windows uses spawn (not fork) — the entire `workflows.autocode_impl` module + `core.config.cfg` must be import-safe at spawn time.

**Estimated complexity:** M (one function rewrite + cross-platform testing + careful signal handling). Risk: regression in the cancellation-flag interplay between `_call()` and the timeout.

**Workaround until shipped:** Operators should set `cfg.autocode_graph_timeout` (or `AUTOCODE_ADAPTIVE_TIMEOUT=1` per-task-type timeouts) tight enough that zombies don't accumulate. Long-running `_call()` operations already honor the cancellation flag — the residual zombie risk is in non-`_call()` subprocess calls.

---

### #38 — Human-in-the-Loop (HiTL) approval

**Current state:** The workflow runs end-to-end without pausing. `node_commit` commits changes; `node_create_skill` writes + commits a new skill file. There's no opportunity for a human to review and approve before these irreversible actions.

**What's deferred:** A pause-before-commit / pause-before-create_skill gate. Two competing designs:

1. **Sync-pause (simpler):** `node_commit` (or a new `node_await_approval` wired before it) blocks on a `threading.Event`. The MCP client receives a "approval needed" notification, the user responds, and the event is set. **Pros:** simple, no state serialization. **Cons:** holds the worker thread for the duration of the human review (could be minutes/hours) — doesn't scale if the agent runs many concurrent workflows.

2. **Async-checkpoint-resume (more complex but cleaner):** The workflow checkpoints state + returns a `status="awaiting_approval"` response. The MCP client displays the diff/skill content to the user. On approval, the client calls `run_workflow(workflow_type="autocode", goal=..., resume=True, approval="approved")` which restores from checkpoint and continues. **Pros:** no held threads; survives process restart; composes with the existing `resume=True` infrastructure in `base.py`. **Cons:** the workflow's `status` field needs a new value (`awaiting_approval`); `node_commit` needs to know it's resuming an approved workflow (not starting fresh); the checkpoint must include the diff/skill content for the client to display.

**Design decision needed:** Pick one. Recommended: **async-checkpoint-resume** — it composes with existing infra and scales. But it requires UI work on the MCP client side.

**Estimated complexity:** M (sync-pause) or L (async-checkpoint-resume).

---

### F1 — Parallel subagent debug

**Current state (v2.0.2):** `AUTOCODE_SUBAGENT_DEBUG=1` enables a SINGLE subagent dispatch per debug iteration. `node_systematic_debug` constructs curated context (failing test + error output + current source + truncated prior fix attempts) and calls `agent(action="subagent", role="planner")` with it. The subagent returns `{fix, root_cause, defense_notes}`. Falls back to single-LLM on subagent failure. Non-blocking — the fix is applied regardless.

**What's deferred:** Parallel subagents — one per hypothesis. When the debug LLM proposes multiple candidate root causes (e.g., "could be a race condition OR a stale cache OR an off-by-one"), spawn N subagents in parallel, each investigating one hypothesis with curated context. Aggregate the N verdicts with a voting layer (similar to swarm's HIGH/MEDIUM/LOW confidence).

**Design:**
- New node OR new branch inside `node_systematic_debug`: when `AUTOCODE_SUBAGENT_DEBUG=1` AND the debug LLM returned multiple hypotheses, spawn N subagents via a thread pool (`concurrent.futures.ThreadPoolExecutor`).
- Each subagent gets: the hypothesis it's investigating + the same curated context (failing test, error, source, prior attempts).
- Aggregation: majority vote on `fix` (or `root_cause` if fixes differ); confidence = agreement fraction (HIGH if unanimous, MEDIUM if majority, LOW if split).
- Output shape: `{fix, root_cause, defense_notes, confidence, agreement, hypotheses: [...]}` — same shape as `swarm_verdict` so downstream code (PR comment gating, etc.) works unchanged.
- Non-blocking: if all N subagents fail, fall back to single-LLM (same as v2.0.2).

**Dependency:** v2.0.2 action-level allowlist makes this safe (subagents can't escape the allowlist to do arbitrary work). Already unblocked.

**Estimated complexity:** M (thread pool + aggregation logic + new env flag).

**Inspiration:** obra/superpowers "parallel investigation" pattern.

---

### F7 — Lazy Dev full audit mode (MOST DETAILED)

**This is the most detailed design write-up in this section — the user specifically asked for thorough documentation of F7.**

#### Current state

The 7-rung Lazy Dev ladder (see ALWAYS DO #38) shipped in v2.0 — it's integrated into `CODER_SYSTEM` and `DEBUG_SYSTEM` Phase 4 ("fix"). The ladder is **per-task**: each workflow run applies the ladder to its own task. The `ponytail:` comment convention (ALWAYS DO #39) marks deliberate simplifications.

`task_type="audit"` exists in the classifier enum (`classify.py` line 23) and routes through the SAME TDD pipeline as `feature`:
- `route_after_classify` sends `audit` → `node_brainstorm` (same as `feature`).
- `route_after_write_files` sends `audit` → `node_analyze_impact` (correctly added in v1.1).
- `node_run_tests` runs the TDD tests on the audit's "implementation" — but for an audit, there IS no implementation. The audit produces a REPORT, not code changes.

So today, `task_type="audit"` is functionally `task_type="feature"` with a different brainstorm prompt. It does NOT do a whole-repo scan, does NOT produce an audit-specific report, and does NOT have audit-specific exit criteria.

#### What's missing

1. **Whole-repo scan node.** No node walks `project_root` to enumerate all Python files + their ASTs. `node_analyze_impact` only looks at `modified_files` (the files THIS workflow changed) — for an audit, there are no modified files (or shouldn't be).
2. **Audit-specific report.** `node_report` generates a "what I did" report — for an audit, the report IS the deliverable. It should summarize: dead code, unused imports, missing type hints, complexity hotspots, dependency-graph anomalies (cycles, orphaned modules).
3. **Audit-specific exit criteria.** A `feature` workflow exits when tests pass + lint passes + LLM review passes. An audit workflow should exit when the whole-repo scan is complete + the report is generated — no TDD pass/fail to check.
4. **kgraph coverage dependency.** `core.kgraph` provides `ast_parser` + `get_callers` + dependency-graph queries. If the project hasn't been indexed (no `.kgraph/` cache), `get_callers` returns empty — blast-radius analysis is meaningless. Audit mode needs either a pre-flight index step or a graceful "kgraph empty, falling back to AST-only scan" path.

#### Proposed design

**New nodes:**

1. **`node_audit_scan(state)` — Phase 9a (audit-only):** Walks `project_root` recursively (`.py` files only, respecting `.gitignore` via `pathspec`). For each file:
   - Parse AST via `core.kgraph.ast_parser`.
   - Extract: imports, definitions (functions/classes/modules), call sites, complexity (cyclomatic via `radon` if installed, else AST-approximation).
   - Batch through `kgraph` for cross-file queries: `get_callers(symbol)`, `get_callees(symbol)`.
   - Accumulate findings: dead code (defined but never called), unused imports, missing type hints (functions with no annotations), complexity hotspots (functions with cyclomatic > N), circular dependencies (via DFS on the import graph).
   - Output: `audit_findings: list[dict]` — each finding is `{category, file, line, symbol, severity, suggestion}`.

2. **`node_audit_report(state)` — Phase 13a (audit-only, replaces `node_report` for audit):** Reads `audit_findings` from the `audit` sub-state (NEW sub-state, see below) + generates a Markdown report grouped by category + severity. Optionally writes the report to `audit_report.md` in `autocode_run_path`.

**New sub-state:**

```python
class AuditState(TypedDict, total=False):
    findings: list[dict]            # from node_audit_scan
    report: str                     # from node_audit_report (Markdown)
    files_scanned: int              # for the verify chain / report
    kgraph_coverage: float          # fraction of files with kgraph data (0.0-1.0)
    skipped: list[str]              # files skipped (binary, too large, parse error)
```

**Routing changes:**

- `route_after_classify`: `audit` → `node_audit_scan` (NEW path, bypasses brainstorm/plan/execute/TDD entirely).
- After `node_audit_scan`: → `node_audit_report` (linear, no conditional).
- After `node_audit_report`: → `node_distill_memory` → END (skip the publish chain — an audit doesn't produce code changes to push/PR).

**New prompts:**

- `AUDIT_SCAN_SYSTEM` — instructs the LLM (if used) on how to categorize findings. Likely most of the scan is deterministic (AST + kgraph queries) — the LLM is only needed for "is this dead code or is it a public API?" judgment calls.
- `AUDIT_REPORT_SYSTEM` — instructs the LLM on how to structure the report (group by category, sort by severity, include code snippets, suggest fixes).

**Configuration:**

- `AUTOCODE_AUDIT_MAX_FILES` (default 1000) — cap on files to scan (prevent runaway on monorepos).
- `AUTOCODE_AUDIT_COMPLEXITY_THRESHOLD` (default 10) — cyclomatic complexity threshold for "hotspot" findings.
- `AUTOCODE_AUDIT_SKIP_DIRS` (default `[".git", "__pycache__", ".venv", "node_modules", "build", "dist"]`) — directories to skip.

#### Design decision needed: does audit skip TDD?

**Option A (current behavior): audit keeps TDD.** The audit "writes a test" that asserts the codebase has no dead code, then "implements" by removing dead code. This is contrived — the test is tautological (it passes once the dead code is removed) and the "implementation" is just deletion.

**Option B (proposed): audit bypasses TDD.** `route_after_classify` sends `audit` → `node_audit_scan` directly, skipping `node_brainstorm` → `node_write_plan` → `node_git_branch` → `node_write_tests` → `node_execute_step` → `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` → `node_analyze_impact` → `node_run_tests`. The audit's deliverable is a REPORT, not code changes — TDD doesn't apply.

**Recommendation: Option B.** TDD-for-audit is forced and doesn't add value. The audit pipeline should be a separate, simpler pipeline: `node_audit_scan` → `node_audit_report` → `node_distill_memory` → END. This is a significant routing change (a new conditional branch in `route_after_classify`) but produces a cleaner workflow.

If the user wants the audit to ALSO propose fixes (not just report), that's a follow-up: a second pass that takes each finding + generates a `feature` workflow for it. But that's out of scope for F7 v1.

#### Dependency: kgraph coverage

If `project_root` is not indexed by `core.kgraph`, `get_callers(symbol)` returns `[]` — dead-code detection will mark EVERY function as "never called" (false positives). Two options:

1. **Pre-flight index:** `node_audit_scan` calls `kgraph.index_project(project_root)` if the cache is stale or missing. Slow (could be minutes for large repos) but accurate.
2. **Graceful degradation:** `node_audit_scan` checks `kgraph.coverage(project_root)` — if < 50%, skip cross-file queries and rely on AST-only checks (unused imports, complexity, missing types). Log a warning that the audit is incomplete.

**Recommendation: Option 2 (graceful degradation) + a `tracer.warning` telling the user to run `kgraph.index_project` for a complete audit.** This keeps the audit fast by default and lets the user opt into the slow path.

#### Inspiration

The 7-rung Lazy Dev ladder is inspired by [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) — the "be lazy about the solution, never about reading" principle. The ladder is ALREADY shipped (v2.0) and applies per-task. F7 extends it from per-task to whole-repo: instead of asking "what's the minimum code to fix THIS bug?", the audit asks "what's the minimum code in THIS REPO, and what's dead/unused/complex?"

Ponytail's "lazy auditor" pattern: a tool that reads the codebase exhaustively (reading is not lazy) but is conservative about flagging things (only flag clear wins — dead code is a clear win, "could be refactored" is not). F7 should follow this: high-confidence findings (unused imports, dead code with zero callers) are flagged; low-confidence findings (this function is "too complex", this name is "bad") are reported separately as "suggestions" not "findings".

#### Estimated complexity

**L (large).** Breakdown:
- New `node_audit_scan` + `node_audit_report` nodes: M.
- New `AuditState` sub-state + accessor (`_get_audit`): S.
- Routing changes in `routes.py` + `graph.py`: S.
- New prompts in `constants.py`: S.
- kgraph coverage check + graceful degradation: M.
- Tests (mock kgraph, mock filesystem, test routing, test report generation): M.
- Documentation (this section + NODES.md + API.md + ARCHITECTURE.md updates): S.

Total: ~L. Recommend splitting into two PRs: (1) `AuditState` + `node_audit_scan` (AST-only, no kgraph) + routing + tests; (2) kgraph integration + cross-file queries + `node_audit_report` LLM-powered categorization.

#### Open questions

- Should the audit write its report to `autocode_run_path/audit_report.md` (file) or return it as `state["result"]` (string)? Both? (Recommendation: both — file for human reading, string for MCP client display.)
- Should the audit commit the report to git? (Recommendation: NO — audits are read-only. If the user wants to commit the report, they can do it manually. This avoids the "audit accidentally creates a branch + PR" footgun.)
- Should `node_distill_memory` store audit findings as procedural memory for future runs? (Recommendation: YES — patterns like "this repo has a lot of dead code in `tools/legacy/`" are useful for future audits.)

---

### #57 — Per-node dedicated test files

**Current state (v3.2):** The `tests/workflows/autocode/` directory follows a one-file-per-concern pattern, but 14 of the 29 nodes still lack a dedicated `test_<node_name>.py` file. They are exercised indirectly through integration tests (`test_routes.py`, `test_safety.py`, `test_verify.py`, `test_debug.py`) rather than focused unit tests. The 14 nodes missing dedicated unit-test files are:

- `node_swarm_fallback` — partially covered by `test_swarm_integration.py::TestSwarmFallbackIntegration` (3 tests) + `test_swarm_fallback_fixes.py` (4 tests added in v3.2 P2-8 for the P0 fixes); lacks coverage of the LOW-confidence + swarm-unavailable RMW paths.
- `node_verify_decision` — covered indirectly by `test_verify.py`; lacks coverage of the hallucination-guard + max_retries/stuck early-exit paths in isolation.
- `node_apply_patches` — covered indirectly by `test_helpers.py` (which tests `_is_path_safe()` separately); lacks coverage of the dry-run-with-validation path added in v3.2 P0-5 + the `"error"` status-check addition in v3.2 P2-4.
- `node_write_new_files` — covered indirectly by `test_execute.py`; lacks coverage of the `files_map` snapshot shape + `FileLock` retry-on-timeout path.
- `node_persist_artifacts` — covered indirectly; lacks coverage of the `test_code` list-join behavior + missing-debug-fields skip path.
- `node_summarize_context` — covered indirectly by `test_debug.py`; lacks coverage of the chonkie-fallback path + empty-history early return.
- `node_run_pytest` — covered indirectly; lacks coverage of the ruff E999 pre-check paths (success, syntax-error, ruff-missing, timeout, exception) + the `cfg.sandbox_timeout` wiring added in v3.2 P1-3.
- `node_run_lint` — covered indirectly; lacks coverage of the no-modified-files early return + ruff-unavailable path.
- `node_llm_review` — covered indirectly; lacks coverage of the `debug_summary` injection threshold + the `test_code` list-handling fix from v3.2 P0-4.
- `node_push` / `node_create_pr` / `node_merge_pr` — covered indirectly; lack coverage of the GitHub-not-configured graceful-skip path + the `_build_pr_body` helper.
- `node_git_branch` — covered by `test_branch.py` (this one DOES have a dedicated file — counted in the "missing" list in error; actually has coverage but the file is small).
- `node_distill_memory` — covered indirectly; lacks coverage of the ChromaDB-failure non-fatal path.
- `node_report` — covered indirectly; lacks coverage of the `_shape_artifacts` integration.

**What's deferred:** Add a `test_<node_name>.py` for each of the 14 nodes above, following the pattern established by `test_branch.py`, `test_create_skill.py`, `test_helpers.py`, `test_analyze_impact.py`. Each file should have:
- A `conftest.py`-style `base_state` fixture (already provided by the existing `conftest.py`).
- Focused unit tests for: (a) the happy path (returns the expected sub-state RMW + ephemeral flat fields); (b) every skip-condition (status / verify.passed / dry_run); (c) every error path (LLM failure, subprocess failure, missing fields); (d) the state-update shape (asserts the returned dict's keys + that RMW preserved sibling sub-state fields).
- Mock fixtures that patch `_call`, `_swarm_debug_consensus`, `subprocess.run`, `git`, `github` as appropriate — following the existing mock strategy documented in [ARCHITECTURE.md](ARCHITECTURE.md) § "Testing".

**Why deferred:** The integration tests already cover the critical paths; the per-node files would add focused coverage of edge cases + skip conditions that integration tests don't reach. Estimated complexity: **M** (14 files × ~5 tests each ≈ 70 new tests; each file follows the same template so the marginal cost per file is low). Recommend splitting across multiple PRs (e.g., one PR per 3-4 nodes).

**Inspiration:** The `test_create_skill.py` v3.1.2 mock-key fix showed that integration tests can silently pass when the underlying node has a bug — the integration test mocked the wrong key and the production code wrote an empty file. Per-node unit tests with focused mock fixtures catch this class of bug earlier.

**Tracking:** See [CHANGELOG.md](CHANGELOG.md) § "🔄 In Progress / Next Up" → #57.

---

49. **Always use `_should_skip_node(state)` for status checks** (v3.3 #58) — Never write inline `state.get("status") in (...)`. The canonical set is `{"needs_clarification", "failed", "error", "skipped"}`.

*Last updated: 2026-07-19 (v3.3 — #58 + F4).*
