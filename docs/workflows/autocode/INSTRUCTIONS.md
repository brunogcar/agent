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

---

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
