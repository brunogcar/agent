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
21. **Always decrement API budget only for paid APIs** — `decrement_api_calls()` is for Tavily only. Web (SearXNG) and browser searches are free and must NOT consume API budget.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `decrement_api_calls()` was called for ALL successful searches, including web (SearXNG) searches. Web searches are free — only Tavily is a paid API.
> - **Why it matters:** The API budget was exhausted prematurely. A 20-call Tavily budget would be consumed by web searches, leaving no room for actual Tavily queries.
> - **Fix:** Guard the decrement with `if actual_tool == "tavily":` — only paid API calls consume budget.

> - **What happened:** Both `agent()` calls in `node_synthesize` (synthesize + evaluate) were missing `action="dispatch"`. The agent facade requires it — without it, every call returned "Unknown action" error.
> - **Why it matters:** Synthesis fell back to `prev_knowledge` (always `""` on first iteration), and evaluate always returned `score=0.0`. The knowledge base never advanced and completeness was permanently 0.
> - **Fix:** Add `action="dispatch"` as the first keyword argument to every `agent()` call.

> - **What happened:** A dead `completeness_threshold = state.get("completeness_threshold", 0.85)` local was read but never used. The real threshold comparison lives in `routes.py` (default `85.0` on 0-100 scale).
> - **Why it matters:** The `0.85` (0-1 scale) was misleading — it looked like a scale mismatch but was actually dead code. Real comparison uses `85.0` (0-100 scale), matching `_parse_score()` output.
> - **Fix:** Removed the dead local. Added explanatory comment to prevent re-introduction.

---

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
