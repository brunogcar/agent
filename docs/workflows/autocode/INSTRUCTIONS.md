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

*(Fill this section with relevant info from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
