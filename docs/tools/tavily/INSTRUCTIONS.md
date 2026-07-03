<- Back to [Tavily Overview](../TAVILY.md)

# 🛡️ AI Instructions

## NEVER DO

1. **Never expose `run_research()` as a tool action** -- it is workflow-only by design.
2. **Never bypass `_assert_safe_urls()`** -- SSRF protection must run before every URL-touching action.
3. **Never remove the keyless check from `crawl`/`map`** -- these require an API key. Keyless mode is search/extract only.
4. **Never hardcode timeout values** -- Always use `cfg.tavily_timeout`. The `.env` is the single source of truth.
5. **Never skip `_handle_tavily_error()`** -- Always route exceptions through the centralized handler for consistent error messages.
6. **Never create `.bak` files** -- forbidden by project rules.
7. **Never rewrite the entire file** -- surgical edits only. Preserve existing code exactly.
8. **Never add `**kwargs` to the `@tool` facade** -- FastMCP schema breaks.
9. **Never print to stdout** -- MCP stdio corruption. Return dicts only.
10. **Never skip `compileall` before `pytest`** -- catches syntax errors early.
11. **Never use `from tools.tavily_ops.state import _TAVILY_CLIENT`** -- use `import tools.tavily_ops.state as state` and `state._TAVILY_CLIENT` directly. Prevents name-binding divergence bug.
12. **Never call `asyncio.run()` directly from action handlers** -- Always use `_run_async()` or `_run_async_with_resilience()` from `bridge.py`.
13. **Never leak the API key in error messages** -- `_handle_tavily_error()` sanitizes automatically; don't bypass it.
14. **Never pass `_call()` to `_run_async_with_resilience()`** -- Always pass `_call` (the factory). Passing `_call()` creates a single coroutine that cannot be reused on retry.
15. **Never hardcode backoff math** -- Use `core/net/retry.py:get_retry_delay()` for all retry timing.
16. **Never skip `error_code` in `fail()` calls** -- Every error response must include a structured `error_code` for programmatic consumers.
17. **Never forget to call `record_tool_call()` after paid API success** -- Budget tracking requires it.
18. **Never forget to call `check_budget()` before paid API execution** -- Prevents quota overruns.
19. **Never call `on_failure()` before `is_retryable()`** -- Non-retryable errors must NOT trip the circuit breaker. `retry_async_factory` handles this correctly; don't bypass it.
20. **Never forget `ip.is_unspecified` in IP checks** -- `0.0.0.0` and `::` are NOT caught by `is_private`/`is_loopback`/`is_reserved`/`is_multicast`.
21. **Never use `removeprefix("www.")` without boundary check** -- `www2.example.com` becomes `2.example.com`. Use `startswith("www.") and count(".") >= 2`.
22. **Never use non-raw strings for </ → <\/ replacement — .replace("</", r"<\/") avoids invalid escape sequence SyntaxError under -W error.

## ALWAYS DO

23. **Always pass `trace_id` to `ok()` and `fail()`** — Threaded from facade through all action handlers.
24. **Always use `_run_async_with_resilience()` for Tavily client calls** — Handles circuit breaker, rate-limit retry, and nested event loops.
25. **Always strip `raw_content` by default** — `_action_search` must pop `raw_content` from results unless `include_raw_content=True`.
26. **Always test keyless and keyed modes** — Patch `cfg.tavily_api_key` to `""` and `"tvly-test"` respectively.
27. **Always test error paths with both real and mocked exceptions** — `_handle_tavily_error()` uses both `isinstance` and name matching.
28. **Always update this doc when adding actions, changing return shapes, or modifying the client lifecycle.**
29. **Always add the non-dict handler return fallback in the facade** — `if not isinstance(result, dict): return fail(...)`.
30. **Always reset the circuit breaker between tests** — `tools.tavily_ops.client._TAVILY_CB.reset()` must be in a known state.
31. **Always use `core/net/` imports** — `core.net.security`, `core.net.errors`, `core.net.retry`, `core.net.budget`. Not the backward-compat wrappers.
32. **Always register SDK exceptions** — If a tool wraps a new SDK, call `register_retryable_exception()` for its retryable exception types.
33. **Always record paid API calls** — After every successful Tavily call, call `record_tool_call("tavily.search")` (or appropriate tool name).
34. **Always reset the budget tracker between tests** — `core.net.budget._budget_tracker._calls.clear()` prevents singleton pollution.
35. **Always use `AsyncMock` for async client methods in tests** — `_run_async_with_resilience` calls `asyncio.run(coro)`, so mock methods must return coroutines.

---

## 🚫 Anti-Patterns & Lessons Learned

> **Placeholder:** This section is reserved for documenting hard-won lessons from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:
> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*(No entries yet. Add lessons here as they are learned.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
