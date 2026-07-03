<- Back to [Research Overview](../RESEARCH.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove parallel scraping** — Sequential scraping would be too slow.
4. **Never skip citation tracking** — Attribution is important for trust.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`. Always pass `action="dispatch"` for LLM calls.
10. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).

## ✅ ALWAYS DO

11. **Always return `dict` from nodes** — Not `WorkflowState`. Partial updates only.
12. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
13. **Always handle search failure gracefully** — Empty results should route to END, not crash.
14. **Always test `route_after_search` with both paths** — Assert `"no_results"` and `"has_results"`.
15. **Always test `route_after_synthesize` with both paths** — Assert `"failed"` and `"success"`.
16. **Always test memory storage** — Assert semantic + procedural memory stored correctly.
17. **Always test notification** — Assert `notify()` called with correct message.
18. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
19. **Always use `!= "success"` not `not ... == "success"`** — The latter is always False due to operator precedence.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
