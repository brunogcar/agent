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
14. **Never import removed symbols in the facade** — [v1.1] The facade was broken for 2 versions because it imported `AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot` after they were removed from their source modules. When removing a symbol from `state.py`/`routes.py`/`git_ops.py`, grep the facade and remove the import + `__all__` entry too.
15. **Never call `.compile()` on an already-compiled graph** — [v1.1] `get_graph()` returns a `CompiledStateGraph` which has no `.compile()` method. Calling it crashes with `AttributeError`. Use `get_graph()` directly, or `build_graph().compile()` for a fresh compile.
16. **Never let `distill_memory` fail the workflow** — [v1.1] The code is already committed by the time distill_memory runs. A ChromaDB failure there must not flip a successful workflow to failed. Use `tracer.warning`, not `tracer.error`, and return `{}`.
17. **Never bypass `base.py`'s `run_workflow()` from the facade** — [v1.1] The facade delegates to `run_workflow("autocode")` for tracing, checkpointing, and timeout. Bypassing it (the old design) caused double trace creation and missing checkpoint support.

## ✅ ALWAYS DO

14. **Always return `dict` from nodes** — Not `AutocodeState`. Partial updates only.
15. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
16. **Always handle validation failure gracefully** — Invalid input should return error state, not crash.
17. **Always test `node_classify_task` with mode override** — Assert correct task_type regardless of LLM output.
18. **Always test `node_brainstorm` with KG files** — Assert merged files (currently broken).
19. **Always test `node_analyze_impact` with empty files_map** — Assert early return (currently broken).
20. **Always test `node_write_files` with patch** — Assert atomic write and no `.bak` files.
21. **Always test `node_run_tests` with missing test files** — Assert error state.
22. **Always test `node_verify` with missing ruff** — Assert `lint_passed=False` (currently `True`).
23. **Always test `node_git_commit` with no changes** — Assert skipped state.
24. **Always test `node_distill_memory` with missing hypothesis** — Assert graceful handling.
25. **Always test `node_create_skill` with invalid name** — Assert error state.
26. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
27. **Always use `defense_notes` (plural)** — The state field is `defense_notes`, not `defense_note`.
28. **Always use `asyncio.to_thread()` for CPU-bound work** — AST parsing and file I/O blocks the event loop.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `.bak` backup files were created on every file write (patch.py, write_files.py, helpers.py). This violated project rules and cluttered the repo with stale backups.
> - **Why it matters:** `.bak` files accumulate, confuse git status, and are unnecessary since git provides versioning. The project explicitly forbids `.bak` files.
> - **Fix:** Use atomic writes (tempfile.NamedTemporaryFile + os.replace) only. No `.bak` creation anywhere. Git is the backup.

> - **What happened:** `_git_snapshot()` called `git(action="snapshot")` which was removed from the git tool in the un-multiplex refactor. The call always failed silently.
> - **Why it matters:** The "pre-autocode snapshot" was supposed to be a safety net, but it never worked. Autocode ran without any snapshot protection.
> - **Fix:** Removed `_git_snapshot` entirely. The git branch itself is the safety net — if something goes wrong, `git checkout main` or `git revert` recovers. Future plan: add GitHub PR integration so autocode can create/fix PRs.

> - **What happened:** `files_map` was declared in `AutocodeState` and initialized to `{}`, but no node ever populated it. `node_analyze_impact` read it and found it empty, so impact analysis never ran.
> - **Why it matters:** Without impact analysis, autocode can't detect regressions or target specific tests. It always falls back to running the full test suite.
> - **Fix:** `node_write_files` now populates `files_map` with file snapshots (content_preview, md5, size) after writing files. `analyze_impact` will now actually run.

> - **What happened:** `node_analyze_impact` was declared `async def` but LangGraph `StateGraph.add_node` expects sync functions. The async node may fail silently or hang the graph.
> - **Why it matters:** Async-in-sync-graph is undefined behavior in LangGraph. The node may never execute, or may hang forever.
> - **Fix:** Converted to `def` (sync). Async calls (`parse_dependencies_from_string`, `get_targeted_tests`) are wrapped in `_run_async()` which creates a new event loop.

> - **What happened:** `node_brainstorm` merged `kg_files` into `files_update` but stored `state["files"]` (the original) instead of the merged result. Knowledge graph files were discarded.
> - **Why it matters:** KG context (relevant files from the dependency graph) was fetched but never made available to downstream nodes. The planner and executor never saw the KG files.
> - **Fix:** Store `files_update` (merged) instead of `state["files"]` (original).

> - **What happened:** `node_distill_memory` read `hypothesis` and `defense_note` (singular), but `node_systematic_debug` sets `root_cause` and `defense_notes` (plural). Both fields were always empty.
> - **Why it matters:** Procedural memory distillation never received root cause or defense notes — the most valuable debugging insights were discarded.
> - **Fix:** Changed to `root_cause` and `defense_notes` to match what debug.py actually sets. Same fix in `node_commit`.

> - **What happened:** The facade (`workflows/autocode.py`) was broken for 2 versions (v1.0.1 + v1.0.2). It imported 4 symbols (`AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot`) that were removed from their source modules during the v1.0.1/v1.0.2 refactors. No test caught it because all 106 tests imported directly from `autocode_impl/`, never from the facade.
> - **Why it matters:** `import workflows.autocode` raised `ImportError`. `run_workflow(workflow_type="autocode")` was also broken (the dispatcher imports from the facade). The entire autocode workflow was unreachable through its documented public API for 2 versions.
> - **Fix:** [v1.1] Removed the 4 dead imports. Added facade contract tests (`test_facade.py`) that import the facade and exercise `run_workflow("autocode")`. This guards against silent facade breakage in future refactors.

> - **What happened:** `base.py`'s autocode branch did `graph = build_graph(); result = graph.invoke(state)`. But `build_graph()` returns an uncompiled `StateGraph`, which has no `.invoke()` method. This would crash with `AttributeError`.
> - **Why it matters:** Even if the facade imported correctly, `run_workflow("autocode")` would still crash at the invoke step.
> - **Fix:** [v1.1] `base.py` now uses `invoke_with_timeout(initial_state)` which calls `get_graph()` (returns compiled) internally. Also wires `cfg.autocode_graph_timeout`.

> - **What happened:** `route_after_write_files` only routed `fix`/`fix_error`/`refactor`/`improve`/`feature` to `node_analyze_impact`. `audit` and `edit` fell through to `node_verify`, skipping impact analysis entirely.
> - **Why it matters:** For `audit` especially, impact analysis IS the audit — skipping it made the audit task type misleading. For `edit`, the docs say it's "heavier than fix" but it skipped TDD, which was inconsistent.
> - **Fix:** [v1.1] Added `audit` and `edit` to the impact-analysis path. Found by cross-LLM review (DeepSeek, Mistral).

---

*Last updated: 2026-07-06 (v1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
