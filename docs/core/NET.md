
# 🔗 core/net/ — Shared Network Infrastructure

Unified HTTP error classification, SSRF protection, retry/backoff policies, API budget tracking, URL normalization, and shared default constants for all web-facing tools (tavily, web, browser) and workflows.

**Key characteristics:**
- **Thread-safe** — `RLock` for nested calls, `Lock` for simple cases
- **Singleton pattern** — Budget tracker is global singleton; reset in tests via `_calls.clear()`
- **Cross-tool adoption** — `core/net/__init__.py` re-exports all modules for `from core.net import ...`
- **Lazy SDK exception registration** — `register_retryable_exception()` for tool-specific retryable errors
- **DNS timeout safety** — `ThreadPoolExecutor` + `future.result(timeout=)` (socket.getaddrinfo has no `timeout` kwarg)
- **IPv6 aware** — Handles bracketed `[::1]:8080` and unbracketed `2001:db8::1` correctly
- **Daily budget reset** — Automatic date change detection in `record_call()`

---

## 📦 Package Structure

```text
core/net/
├── __init__.py    # v1.3 NEW: Public re-exports for cross-tool adoption
├── errors.py      # HTTP error classification, retryable detection, backoff calculation
├── security.py    # SSRF prevention, URL safety checks, IP validation
├── retry.py       # Synchronous and async retry wrappers with circuit breaker hooks
├── budget.py      # API cost tracking and budget enforcement
├── url.py         # URL normalization and domain extraction
└── default.py     # Shared default constants across all network tools
```

| Module | Purpose | Adopted By |
|--------|---------|------------|
| `errors` | Classify HTTP exceptions, detect retryable errors, calculate backoff delays | tavily ✅, web ⏳, browser ⏳ |
| `security` | Block private/loopback IPs, validate URL schemes, prevent DNS rebinding | tavily ✅, web ⏳, browser ⏳ |
| `retry` | Unified retry wrappers with exponential backoff and CB hooks | tavily ✅, web ⏳, browser ⏳ |
| `budget` | Track API call costs, enforce daily limits, auto-block on exhaustion | tavily ✅, web ⏳, browser ⏳ |
| `url` | Normalize URLs for cache keys, extract domains, compare domains | tavily ✅, web ⏳, browser ⏳ |
| `default` | Single source of truth for timeouts, retry counts, CB thresholds | tavily ✅, web ⏳, browser ⏳ |

---

## 🔌 Module APIs

### `core/net/errors.py`

```python
from core.net.errors import (
    classify_http_error,      # Exception -> canonical error category string
    is_retryable_error,      # Exception -> bool (should we retry?)
    get_retry_delay,         # (attempt, base_delay, max_delay, jitter) -> float
    register_retryable_exception,  # Register SDK-specific retryable exceptions
    RETRYABLE_STATUS_CODES,  # {408, 429, 500, 502, 503, 504}
    RETRYABLE_EXCEPTIONS,    # Tuple of httpx exception types
)
```

**Error categories:** `TIMEOUT`, `CONNECT_ERROR`, `RATE_LIMITED`, `SERVER_ERROR`, `CLIENT_ERROR`, `NETWORK_ERROR`, `BOT_BLOCKED`, `UNKNOWN`

**v1.3 fixes:**
- `NetworkError` now correctly returns `NETWORK_ERROR` (was incorrectly grouped with `CONNECT_ERROR`)
- `ReadError`/`WriteError`/`RemoteProtocolError` return `NETWORK_ERROR` (checked before `NetworkError` since they subclass it)
- HTTP 408 returns `RATE_LIMITED` (it's in `RETRYABLE_STATUS_CODES`)

**SDK registration:**
```python
from core.net.errors import register_retryable_exception
from tavily.errors import RateLimitError
register_retryable_exception(RateLimitError)
```

### `core/net/security.py`

```python
from core.net.security import (
    is_safe_network_address,  # hostname -> bool (public = True)
    _assert_safe_urls,        # [urls] -> (bool, error_msg)
    _is_private_or_localhost, # hostname -> bool (private = True)
    _resolve_safe,            # hostname -> [(family, type, proto, canonname, sockaddr)]
)
```

**v1.3 fixes:**
- Fixed IPv6 bracket parsing (`[::1]:8080` now handled correctly)
- Unbracketed IPv6 literals (`2001:db8::1`) bypass DNS and use `ipaddress` module directly
- DNS timeout uses `ThreadPoolExecutor` + `future.result(timeout=)` (socket.getaddrinfo has no `timeout` kwarg)

**Important:** `2001:db8::/32` is **reserved** in Python's `ipaddress` module (RFC 3849 documentation range). Use `2001:4860:4860::8888` (Google DNS) or `2606:4700:4700::1111` (Cloudflare) for truly public IPv6 test addresses.

### `core/net/retry.py`

```python
from core.net.retry import (
    retry_sync,           # (fn, max_retries=3, ...) -> result
    retry_async_factory,  # (coro_factory, run_async, max_retries=3, ...) -> result
)
```

**`retry_async_factory` signature:**
```python
def retry_async_factory(
    coro_factory: Callable,           # Returns fresh coroutine each call
    *,
    run_async: Callable,              # Runs coroutine (e.g., bridge._run_async)
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 10.0,
    jitter: bool = True,
    is_retryable: Callable = is_retryable_error,
    on_success: Optional[Callable] = None,   # e.g., CB.record_success
    on_failure: Optional[Callable] = None,   # e.g., CB.record_failure
)
```

**Critical rule:** The factory must create a **fresh coroutine** on each call. Never pass an already-created coroutine.

```python
# CORRECT
factory = lambda: client.search(query="...")  # fresh coroutine each call

# WRONG — coroutine reuse crash
coro = client.search(query="...")
factory = lambda: coro  # same coroutine — cannot be awaited twice
```

### `core/net/budget.py`

```python
from core.net.budget import (
    APICostTracker,      # Thread-safe singleton (usually use helpers below)
    BudgetConfig,        # dataclass: daily_limit, warning_threshold, auto_block
    record_tool_call,    # (tool, cost=1) -> None
    check_budget,        # (tool) -> bool
    get_budget_status,   # (tool="") -> dict
    set_tool_budget,     # (tool, daily_limit=0, warning_threshold=0.8) -> None
)
```

**v1.3 fixes:**
- `threading.Lock()` → `threading.RLock()` (prevents deadlock in nested `get_status()` calls)
- Added automatic daily reset (date change detection in `record_call()`)
- `get_status()` returns info even when no explicit budget config is set

**Status dict shape:**
```python
{
    "tavily.search": {
        "used": 42,
        "limit": 100,
        "remaining": 58,
        "warning": False,   # True when used >= limit * threshold
        "blocked": False,   # True when used >= limit
    }
}
```

**Test reset:**
```python
from core.net.budget import _budget_tracker
_budget_tracker._calls.clear()
_budget_tracker._configs.clear()
_budget_tracker._last_reset_date = datetime.date.today()
```

### `core/net/url.py`

```python
from core.net.url import (
    normalize_url,    # url -> normalized_url (lowercase, strip slash, sort params)
    extract_domain,   # url -> hostname
    is_same_domain,   # (url1, url2) -> bool (strips www. prefix)
)
```

**v1.3:** `is_same_domain` now considers `www.example.com` and `example.com` as the same domain.

### `core/net/default.py`

```python
from core.net.default import (
    SEARCH_MAX_RESULTS,   # 5
    SEARCH_TIMEOUT,       # 30
    CRAWL_MAX_DEPTH,      # 3
    CRAWL_MAX_BREADTH,    # 10
    CRAWL_LIMIT,          # 50
    EXTRACT_MAX_URLS,     # 10
    EXTRACT_DEPTH,        # "basic"
    SCRAPE_TIMEOUT,       # 30
    SCRAPE_MAX_RETRIES,   # 3
    BROWSER_TIMEOUT,      # 30
    BROWSER_NAV_RETRIES,  # 2
    RETRY_MAX_ATTEMPTS,   # 3
    RETRY_BASE_DELAY,     # 2.0
    RETRY_MAX_DELAY,      # 30.0
    RETRY_JITTER,         # True
    CB_FAILURE_THRESHOLD,      # 5
    CB_RECOVERY_TIMEOUT,       # 60.0
    CB_HALF_OPEN_MAX_CALLS,    # 1
)
```

---

## ⚡ Circuit Breaker Integration Pattern

```python
from core.llm_backend.circuit_breaker import CircuitBreaker
from core.net.retry import retry_async_factory

_MY_CB = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)

def _run_with_resilience(coro_factory):
    if not _MY_CB.can_execute():
        raise CircuitBreakerOpen("Service unavailable")
    
    return retry_async_factory(
        coro_factory,
        run_async=_run_async,
        on_success=_MY_CB.record_success,
        on_failure=_MY_CB.record_failure,
    )
```

**Key rules:**
- Call `can_execute()` before every protected operation
- Call `record_success()` only on final success (retry handles intermediate failures)
- Call `record_failure()` on every retryable failure (retry_async_factory calls this automatically)
- Reset CB in tests with `_MY_CB.reset()`
- **v1.3 FIX:** OPEN→HALF_OPEN transition counts against `half_open_max_calls` (was allowing 1 extra call)

---

## 💰 Budget Tracking Integration Pattern

```python
from core.net.budget import check_budget, record_tool_call, set_tool_budget

# Optional: set limits at startup
set_tool_budget("my_tool.search", daily_limit=100, warning_threshold=0.8)

def my_action():
    if not check_budget("my_tool.search"):
        return fail("Budget exhausted", error_code="QUOTA_EXHAUSTED")
    
    result = call_api()
    record_tool_call("my_tool.search")
    return ok(result)
```

**v1.3 behavior:**
- Daily reset happens automatically when date changes (checked on every `record_call`)
- `threading.RLock()` allows nested calls (e.g., `get_status()` inside `record_call()`)
- `auto_block` flag (future) will auto-open circuit breaker on budget exhaustion

---

## 🌐 URL Normalization Usage

```python
from core.net.url import normalize_url, is_same_domain

# Cache key consistency
key = normalize_url("https://Example.COM:443/PATH/?Z=1&A=2")
# -> "https://example.com/PATH?A=2&Z=1"

# Domain comparison
is_same_domain("https://www.example.com/a", "https://example.com/b")
# -> True (www. stripped)
```

---

## ✅ Cross-Tool Adoption Checklist

| Step | Action | Files to Touch |
|------|--------|----------------|
| 1 | Replace inline HTTP error checks with `classify_http_error()` | `web/actions/*.py`, `browser/actions/*.py` |
| 2 | Replace hardcoded backoff with `get_retry_delay()` | Any file with `time.sleep(2 ** attempt)` |
| 3 | Replace duplicated SSRF logic with `_assert_safe_urls()` | `web/utils.py`, `browser/actions/*.py` |
| 4 | Add `register_retryable_exception()` for SDK-specific errors | SDK wrapper files |
| 5 | Add `check_budget()` + `record_tool_call()` for paid APIs | Any tool calling paid APIs |
| 6 | Use `normalize_url()` for cache keys | Any tool with response caching |
| 7 | Import constants from `core.net.default` instead of hardcoding | All web tool action files |
| 8 | Update tests to use `tests/core/net/conftest.py` fixtures | Test files |

---

## 🗺️ Migration Guide

### `core/security.py` → `core/net/security.py`

```python
# BEFORE
from core.security import is_safe_url

# AFTER
from core.net.security import is_safe_network_address, _assert_safe_urls
```

### `core/web_errors.py` → `core/net/errors.py`

```python
# BEFORE
from core.web_errors import is_retryable

# AFTER
from core.net.errors import is_retryable_error, classify_http_error
```

### Per-tool constants → `core/net/default.py`

```python
# BEFORE (in tavily_ops/actions/search.py)
MAX_RESULTS = 5

# AFTER
from core.net.default import SEARCH_MAX_RESULTS
```

---

## 📋 Error Code Reference

| Code | Source | Meaning | Retry? |
|------|--------|---------|--------|
| `TIMEOUT` | errors.py | Request timed out | Yes |
| `CONNECT_ERROR` | errors.py | Could not establish connection | Yes |
| `RATE_LIMITED` | errors.py | HTTP 429 or 408 | Yes |
| `SERVER_ERROR` | errors.py | HTTP 5xx | Yes |
| `CLIENT_ERROR` | errors.py | HTTP 4xx (not 429/408) | No |
| `NETWORK_ERROR` | errors.py | Read/write/protocol error | Yes |
| `BOT_BLOCKED` | errors.py | Cloudflare/cf-ray detected | No |
| `UNKNOWN` | errors.py | Unrecognized exception | No |
| `CB_OPEN` | bridge.py | Circuit breaker is OPEN | No |
| `QUOTA_EXHAUSTED` | budget.py | Daily budget limit reached | No |
| `AUTH_FAILED` | errors.py | Invalid API key or keyless limit | No |

---

## 🧪 Testing Integration

### Shared test fixtures

```python
# tests/core/net/conftest.py
import pytest
from core.net.budget import _budget_tracker

@pytest.fixture(autouse=True)
def reset_budget_tracker():
    """Reset budget tracker before each test."""
    _budget_tracker._calls.clear()
    _budget_tracker._configs.clear()
    _budget_tracker._last_reset_date = datetime.date.today()
    yield
```

### Security test isolation

```python
# In any test file that tests security
@pytest.fixture(autouse=True)
def patch_allowed_hosts(monkeypatch):
    from core.net import security
    monkeypatch.setattr(security.cfg, "allowed_internal_hosts", frozenset())
```

### Async resource warning suppression

```python
# In tavily/browser test conftest.py
import warnings

@pytest.fixture(autouse=True)
def filter_resource_warnings():
    warnings.filterwarnings("ignore", category=ResourceWarning)
    yield
```

---

## 🛡️ AI Agent Instructions

### NEVER DO
1. **Never use `socket.getaddrinfo(timeout=...)`** — It has no `timeout` kwarg. Use `ThreadPoolExecutor` + `future.result(timeout=)`.
2. **Never pass an already-created coroutine to `retry_async_factory()`** — Factory must return fresh coroutine each call.
3. **Never use `threading.Lock()` for nested calls** — Use `threading.RLock()` to prevent deadlock.
4. **Never forget to reset the budget tracker between tests** — `_budget_tracker._calls.clear()` + `_configs.clear()`.
5. **Never hardcode retry/backoff math** — Use `get_retry_delay()` from `core.net.errors`.
6. **Never duplicate SSRF logic** — Use `_assert_safe_urls()` from `core.net.security`.
7. **Never forget to register SDK exceptions** — Call `register_retryable_exception()` for new SDK wrappers.
8. **Never skip `check_budget()` before paid API calls** — Prevents quota overruns.
9. **Never skip `record_tool_call()` after paid API success** — Budget tracking requires it.
10. **Never use `2001:db8::1` as a public IPv6 test address** — It's reserved in Python's `ipaddress` module. Use `2001:4860:4860::8888` instead.

### ALWAYS DO
11. **Always import from `core.net` package** — `from core.net import ...` not `core.security` or `core.web_errors`.
12. **Always use `normalize_url()` for cache keys** — Deterministic, sortable, consistent.
13. **Always patch `allowed_internal_hosts` to empty in security tests** — Prevents environment config from interfering.
14. **Always reset circuit breakers between tests** — `_MY_CB.reset()` must be in a known state.
15. **Always use `AsyncMock` for async client methods in tests** — `_run_async_with_resilience` calls `asyncio.run(coro)`.
16. **Always include `error_code` in `fail()` calls** — Every error response must be programmatically consumable.
17. **Always check `can_execute()` before CB-protected operations** — Fail fast when circuit is open.
18. **Always fall through to HALF_OPEN check after OPEN→HALF_OPEN transition** — Don't return True immediately (v1.3 fix).

---

*Architecture: unified error classification + SSRF guard + retry/backoff + budget tracking + URL normalization + shared defaults, all thread-safe with RLock and singleton patterns.*
