
# 🔗 Integration Roadmap — Adopting core/net/ Across the Stack

How to migrate `web`, `browser`, and workflow tools to use the unified `core/net/` infrastructure.

**Reference doc:** `docs/core/NET.md` — full API reference, patterns, and AI instructions for `core/net/`.

---

## 🗺️ Adoption Status

| Tool | Status | Notes |
|------|--------|-------|
| **tavily** | ✅ **Complete v1.3** | Reference implementation. All 6 modules adopted. |
| **web** | ⏳ **Pending** | Needs `errors.py`, `security.py`, `retry.py`, `url.py`, `default.py` |
| **browser** | ⏳ **Pending** | Needs `errors.py`, `security.py`, `retry.py`, `url.py`, `default.py` |
| **workflows/research** | ⏳ **Pending** | Needs `errors.py`, `retry.py` for HTTP calls |
| **workflows/deep_research** | ⏳ **Pending** | Needs `errors.py`, `retry.py` for HTTP calls |

---

## 📋 Per-Tool Integration Tasks

### web

**What to do:**
- Replace `core/security.py` imports with `core/net/security.py`
- Replace `core/web_errors.py` imports with `core/net/errors.py`
- Replace hardcoded retry/backoff with `retry_sync()` + `get_retry_delay()`
- Replace hardcoded constants with `core.net.default` imports
- Add `register_retryable_exception()` for any SDK-specific errors
- Use `normalize_url()` for cache keys in `web_ops/actions/scrape.py`
- Add `_assert_safe_urls()` before any URL fetch in `web_ops/actions/*.py`

**What to check:**
- `web_ops` structure mirrors `tavily_ops` (thin facade + `actions/` subfolder)
- Verify `web_ops/actions/search.py` doesn't duplicate Tavily search logic
- Check if `web_ops` has its own SSRF logic that conflicts with `core/net/security.py`

**What to avoid:**
- Don't create a second `web_errors.py` — use `core/net/errors.py`
- Don't hardcode timeout values — import from `core.net.default`
- Don't skip `register_retryable_exception()` if wrapping a new SDK

### browser

**What to do:**
- Same as web: replace security, errors, retry imports with `core/net/` equivalents
- Use `classify_http_error()` for Playwright navigation errors
- Use `get_retry_delay()` for browser nav retries
- Use `normalize_url()` for page URL comparison

**What to check:**
- `browser_ops` structure mirrors `tavily_ops` (thin facade + `actions/` subfolder)
- Playwright errors may need custom `register_retryable_exception()` mapping
- Browser timeouts may differ from network timeouts — check `BROWSER_TIMEOUT` in `default.py`

**What to avoid:**
- Don't treat all Playwright errors as retryable — `TimeoutError` from page load is different from `ConnectError`
- Don't use `retry_sync()` for interactive operations (click, fill) — only for navigation/fetch

### workflows/research + workflows/deep_research

**What to do:**
- Replace inline HTTP error classification with `classify_http_error()`
- Use `is_retryable_error()` for workflow retry decisions
- Use `get_retry_delay()` for workflow backoff calculations
- Use `check_budget()` + `record_tool_call()` if workflows call paid APIs directly

**What to check:**
- Workflows may call `tavily(action="search")` facade — already uses `core/net/`
- `deep_research_impl/nodes/search.py` uses `tavily(search)` — verify it gets budget tracking
- Workflows may have their own retry logic — consolidate with `core/net/retry.py`

**What to avoid:**
- Don't bypass the Tavily facade to call `run_research()` directly unless intentional
- Don't duplicate budget tracking — if calling through facade, it's already tracked

---

## 🔄 Suggested Implementation Order

```text
Phase 1: web tool (highest impact, most shared code)
  → errors.py, security.py, retry.py, url.py, default.py
  → Update tests: patch imports, add conftest fixtures

Phase 2: browser tool
  → errors.py, security.py, retry.py, url.py, default.py
  → Playwright-specific exception registration
  → Update tests: patch imports, add conftest fixtures

Phase 3: workflows
  → errors.py, retry.py for workflow-level HTTP calls
  → Budget tracking if workflows call APIs directly
  → Verify deep_research uses tavily facade (already tracked)
```

---

## ⚠️ Common Pitfalls

| Pitfall | Why It Happens | Fix |
|---------|---------------|-----|
| `socket.getaddrinfo(timeout=...)` crash | socket has no timeout kwarg | Use `ThreadPoolExecutor` + `future.result(timeout=)` |
| Coroutine reuse crash | Passing `_call()` instead of `_call` to `retry_async_factory` | Pass factory callable, not coroutine object |
| Budget deadlock | Using `Lock()` instead of `RLock()` in nested calls | Use `threading.RLock()` |
| Test pollution | Budget tracker singleton not reset between tests | `_budget_tracker._calls.clear()` in conftest |
| IPv6 test failures | `2001:db8::1` is reserved in Python | Use `2001:4860:4860::8888` for public IPv6 tests |
| Mock coroutine errors | MagicMock returns MagicMock, not coroutine | Use `AsyncMock` for async methods |
| Keyless mode leaks | `_is_keyless_mode` not patched in tests | Patch `cfg.tavily_api_key` or module-level function |

---

## 📝 Notes for Future Sessions

- **web** and **browser** have the same structure as tavily (thin facade + `actions/` subfolder)
- Both need to integrate `core/net/` modules but may have tool-specific exceptions
- Workflows are different structure — focus on `errors.py` and `retry.py` integration
- Check `docs/core/NET.md` for full API details, patterns, and AI instructions
- The original `docs/INTEGRATION.md` had general suggestions — verify against actual source before implementing
- Tavily v1.3 is the **reference implementation** — copy patterns from `tools/tavily_ops/`

---

*Last updated: Tavily v1.3 / core/net v1.3*
