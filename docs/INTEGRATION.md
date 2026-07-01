# Cross-Tool Integration Roadmap

## Tavily v1.1 → v1.2 Integration Checklist

### P0 — Block v1.2 Release
- [ ] **Fix coroutine reuse in `_run_async_with_resilience`**
  - Change signature to accept `coro_factory` callable, not coroutine object
  - Update call sites: `search.py`, `crawl.py`, `map.py` — pass `_call` not `_call()`
- [ ] **Fix empty hostname SSRF bypass in `core/net/security.py`**
  - Reject `hostname = ""` before `is_safe_network_address()` call
- [ ] **Fix IPv6 port stripping in `core/net/security.py`**
  - Change `"]:/"` to `"]:"` in hostname check (or use regex)
- [ ] **Restore facade params**: `max_depth`, `max_breadth`, `limit`
  - Add back to `tools/tavily.py` facade signature and `kwargs` dict
  - Document default changes: max_depth 2→3, limit 100→50
- [ ] **Restore `raw_content` stripping in `search.py`**
  - When `include_raw_content=False`, strip `raw_content` from each result
- [ ] **Fix `_close_client` race**
  - Acquire `_CLIENT_LOCK` before closing
  - Log exceptions instead of `pass`

### P1 — v1.2 Integration (Tavily)
- [ ] **Adopt `core/net/errors.py` in `bridge.py`**
  - Use `is_retryable_error()` for retry decisions (covers HTTP 429, ConnectError, etc.)
- [ ] **Add `error_code` field to `fail()` dicts**
  - Extend `core/contracts.py:fail()` with optional `error_code` parameter
  - Tavily returns: `CB_OPEN`, `RATE_LIMITED`, `AUTH_FAILED`, `TIMEOUT`, `SERVER_ERROR`
- [ ] **Add `get_retry_delay()` to `core/net/retry.py`**
  - Unified exponential backoff with jitter
  - Replace hardcoded `5 * (2 ** attempt)` in bridge.py

### P1 — v1.2 Integration (Web Ops — next time you edit these files)
- [ ] **Adopt `core/net/errors.py` in `web_ops/actions/scrape.py`**
  - Replace inline retry logic with `is_retryable_error()` + `get_retry_delay()`
  - Add `JSWallError` / `BOT_BLOCKED` detection for Cloudflare responses
- [ ] **Adopt `core/net/errors.py` in `web_ops/actions/search.py`**
  - Use `classify_http_error()` for consistent error messages
- [ ] **Adopt `core/net/security.py` in `web_ops/utils.py`**
  - Replace `_is_safe_url()` with `_assert_safe_urls()` tuple API
  - Remove duplicated SSRF logic

### P1 — v1.2 Integration (Browser — next time you edit these files)
- [ ] **Add `classify_browser_error()` to `core/net/errors.py`**
  - Map Playwright errors: `TimeoutError` → `TIMEOUT`, `SelectorNotFound` → `NOT_FOUND`
- [ ] **Use unified retry policy for browser navigation**
  - Apply `get_retry_delay()` for page reloads on transient failures

### P2 — v1.3 Shared Infrastructure
- [ ] **Implement automatic fallback chain**
  - Facade/router level: tavily(search) → web(search) when CB open / no key / rate limited
  - Use `error_code` to trigger fallback without parsing strings
- [ ] **Add `@cached` decorator**
  - LRU cache keyed by `(tool, action, normalized_params_hash)`
  - TTL: 300s for search, 1800s for extract/scrape
- [ ] **Add URL normalization to `core/net/url.py`**
  - Strip trailing slashes, sort query params, lowercase domain

### P3 — Cost Tracking / Budget Awareness
- [ ] **Add `core/net/budget.py`**
  - Counter per paid API (Tavily)
  - Configurable daily limit, auto-CB-open on exhaustion
  - Expose via `system_status` tool or tracer metrics
