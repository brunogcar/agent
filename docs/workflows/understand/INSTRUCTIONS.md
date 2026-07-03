<- Back to [Understand Overview](../UNDERSTAND.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove GraphStore** — Dependency graph is essential for impact analysis.
4. **Never remove incremental updates** — Full re-parse would be too slow.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never use hardcoded `tid` strings** — Always use `state.get("trace_id", "")` for trace correlation.
10. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).

## ✅ ALWAYS DO

11. **Always return `dict` from nodes** — Not `WorkflowState`. Partial updates only.
12. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
13. **Always handle file read errors gracefully** — Log and continue, don't crash.
14. **Always test `node_discover_files` with no Python files** — Assert empty `files_to_parse`.
15. **Always test `node_parse_and_store` with parse errors** — Assert `"completed_with_errors"` status.
16. **Always test `node_report` with empty results** — Assert graceful handling.
17. **Always test sync facade timeout** — Assert timeout handling.
18. **Always update this doc** when adding nodes, changing parsing logic, or modifying error handling.
19. **Always use `asyncio.to_thread()` for CPU-bound work** — AST parsing blocks the event loop.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node reference, [CHANGELOG.md](CHANGELOG.md) for version history.*
