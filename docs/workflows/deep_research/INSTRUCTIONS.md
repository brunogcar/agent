<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove budget management** — Budget tracking prevents runaway costs.
4. **Never remove convergence detection** — Without it, the workflow would run indefinitely.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`. Always pass `action="dispatch"` for LLM calls.
10. **Never use `task` parameter for system prompts** — `task` is the user message. Use role's `system_prompt` or add `system` parameter to `agent()`.
11. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).

## ✅ ALWAYS DO

12. **Always return `dict` from nodes** — Not `WorkflowState`. Partial updates only.
13. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
14. **Always handle search failure gracefully** — Individual search failures should not fail the workflow.
15. **Always test `route_after_synthesize` with all paths** — Assert `"converged"`, `"budget_exhausted"`, and `"continue"`.
16. **Always test budget exhaustion** — Assert workflow stops when budget is exhausted.
17. **Always test convergence detection** — Assert workflow stops when knowledge converges.
18. **Always test multi-tool fallback** — Assert Tavily → web → browser fallback chain.
19. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
20. **Always use `llm.complete()` directly for custom system prompts** — `agent()` uses role's system prompt. Bypass for custom prompts.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
