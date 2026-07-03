<- Back to [NET Overview](../NET.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never use `socket.getaddrinfo(timeout=...)`** — It has no `timeout` kwarg. Use `ThreadPoolExecutor` + `future.result(timeout=)`.
2. **Never pass an already-created coroutine to `retry_async_factory()`** — Factory must return fresh coroutine each call.
3. **Never use `threading.Lock()` for nested calls** — Use `threading.RLock()` to prevent deadlock.
4. **Never forget to reset the budget tracker between tests** — `_budget_tracker._calls.clear()` + `_configs.clear()`.
5. **Never hardcode retry/backoff math** — Use `get_retry_delay()` from `core.net.errors`.
6. **Never duplicate SSRF logic** — Use `_assert_safe_urls()` from `core.net.security`.
7. **Never forget to register SDK exceptions** — Call `register_retryable_exception()` for new SDK wrappers.
8. **Never skip `check_budget()` before paid API calls** — Prevents quota overruns.
9. **Never skip `record_tool_call()` after paid API success** — Budget tracking requires it.
10. **Never use `2001:db8::1` as a public IPv6 test address** — It\'s reserved in Python\'s `ipaddress` module. Use `2001:4860:4860::8888` instead.
11. **Never call `on_failure()` before `is_retryable()`** — Non-retryable errors must NOT trip the circuit breaker. `retry_async_factory` handles this correctly; don\'t bypass it.
12. **Never forget `ip.is_unspecified` in IP checks** — `0.0.0.0` and `::` are NOT caught by `is_private`/`is_loopback`/`is_reserved`/`is_multicast`.

## ✅ ALWAYS DO

13. **Always import from `core.net` package** — `from core.net import ...` not `core.security` or `core.web_errors`.
14. **Always use `normalize_url()` for cache keys** — Deterministic, sortable, consistent.
15. **Always patch `allowed_internal_hosts` to empty in security tests** — Prevents environment config from interfering.
16. **Always reset circuit breakers between tests** — `_MY_CB.reset()` must be in a known state.
17. **Always use `AsyncMock` for async client methods in tests** — `_run_async_with_resilience` calls `asyncio.run(coro)`.
18. **Always include `error_code` in `fail()` calls** — Every error response must be programmatically consumable.
19. **Always check `can_execute()` before CB-protected operations** — Fail fast when circuit is open.
20. **Always fall through to HALF_OPEN check after OPEN→HALF_OPEN transition** — Don\'t return True immediately (v1.3 fix).
21. **Always verify `www.` strip boundary** — `www2.example.com` must NOT become `2.example.com`. Use `startswith("www.") and count(".") >= 2`.
22. **Always use raw strings for `</` → `<\/` replacement** — `.replace("</", r"<\/")` avoids invalid escape sequence SyntaxError under `-W error`.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for module details, [CHANGELOG.md](CHANGELOG.md) for version history.*
