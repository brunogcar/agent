<- Back to [NET Overview](../NET.md)

# 📝 API Reference

## 🔧 Module Overview

`core/net/` is not a single `@tool` facade. It is a shared library of 6 modules consumed by tools and workflows. Each module exports a focused API.

---

## ⚡ Module Reference

### `core/net/errors.py`

```python
from core.net.errors import (
    classify_http_error,       # Exception -> canonical error category string
    is_retryable_error,        # Exception -> bool (should we retry?)
    get_retry_delay,           # (attempt, base_delay, max_delay, jitter) -> float
    register_retryable_exception,  # Register SDK-specific retryable exceptions
    RETRYABLE_STATUS_CODES,    # {408, 429, 500, 502, 503, 504}
    RETRYABLE_EXCEPTIONS,      # Tuple of httpx exception types
)
```

**Error categories:** `TIMEOUT`, `CONNECT_ERROR`, `RATE_LIMITED`, `SERVER_ERROR`, `CLIENT_ERROR`, `NETWORK_ERROR`, `BOT_BLOCKED`, `UNKNOWN`

**v1.3 fixes:**
- `NetworkError` now correctly returns `NETWORK_ERROR` (was incorrectly grouped with `CONNECT_ERROR`)
- `ReadError`/`WriteError`/`RemoteProtocolError` return `NETWORK_ERROR` (checked before `NetworkError` since they subclass it)
- HTTP 408 returns `RATE_LIMITED` (it\'s in `RETRYABLE_STATUS_CODES`)

**v1.4 fixes:**
- `ReadError`/`WriteError`/`RemoteProtocolError`/`NetworkError` explicitly handled in Tavily error handler (`tools/tavily_ops/errors.py`)
- HTTP 408 mapped to `RATE_LIMITED` in Tavily handler to align with `classify_http_error()`

**SDK registration:**
```python
from core.net.errors import register_retryable_exception
from tavily.errors import RateLimitError
register_retryable_exception(RateLimitError)
```

---

### `core/net/security.py`

```python
from core.net.security import (
    is_safe_network_address,   # hostname -> bool (public = True)
    _assert_safe_urls,         # [urls] -> (bool, error_msg)
    _is_private_or_localhost,  # hostname -> bool (private = True)
    _resolve_safe,             # hostname -> [(family, type, proto, canonname, sockaddr)]
)
```

**v1.3 fixes:**
- Fixed IPv6 bracket parsing (`[::1]:8080` now handled correctly)
- Unbracketed IPv6 literals (`2001:db8::1`) bypass DNS and use `ipaddress` module directly
- DNS timeout uses `ThreadPoolExecutor` + `future.result(timeout=)` (socket.getaddrinfo has no `timeout` kwarg)

**v1.4 fixes:**
- Added `ip.is_unspecified` check to all 4 IP validation blocks (IPv6 bracket, IPv6 no-bracket, IPv4 literal, DNS resolution loop)
- Blocks `0.0.0.0` and `::` which previously bypassed the guard (none of `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast` catch these)

**Important:** `2001:db8::/32` is **reserved** in Python\'s `ipaddress` module (RFC 3849 documentation range). Use `2001:4860:4860::8888` (Google DNS) or `2606:4700:4700::1111` (Cloudflare) for truly public IPv6 test addresses.

---

### `core/net/retry.py`

```python
from core.net.retry import (
    retry_sync,              # (fn, max_retries=3, ...) -> result
    retry_async_factory,     # (coro_factory, run_async, max_retries=3, ...) -> result
)
```

**`retry_async_factory` signature:**
```python
def retry_async_factory(
    coro_factory: Callable,  # Returns fresh coroutine each call
    *,
    run_async: Callable,     # Runs coroutine (e.g., bridge._run_async)
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 10.0,
    jitter: bool = True,
    is_retryable: Callable = is_retryable_error,
    on_success: Optional[Callable] = None,  # e.g., CB.record_success
    on_failure: Optional[Callable] = None,  # e.g., CB.record_failure
)
```

**v1.4 fixes:**
- `on_failure()` only fires for **retryable** errors. Previously it fired on EVERY exception, including validation errors and 4xx client errors, causing the circuit breaker to trip on non-retryable failures.
- Removed unreachable `raise last_exception` after the for loop (every path returns or raises inside the loop).

**Critical rule:** The factory must create a **fresh coroutine** on each call. Never pass an already-created coroutine.

```python
# CORRECT
factory = lambda: client.search(query="...")  # fresh coroutine each call

# WRONG — coroutine reuse crash
coro = client.search(query="...")
factory = lambda: coro  # same coroutine — cannot be awaited twice
```

---

### `core/net/budget.py`

```python
from core.net.budget import (
    APICostTracker,          # Thread-safe singleton (usually use helpers below)
    BudgetConfig,            # dataclass: daily_limit, warning_threshold, auto_block
    record_tool_call,        # (tool, cost=1) -> None
    check_budget,            # (tool) -> bool
    get_budget_status,       # (tool="") -> dict
    set_tool_budget,         # (tool, daily_limit=0, warning_threshold=0.8) -> None
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

---

### `core/net/url.py`

```python
from core.net.url import (
    normalize_url,           # url -> normalized_url (lowercase, strip slash, sort params)
    extract_domain,          # url -> hostname
    is_same_domain,          # (url1, url2) -> bool (strips www. prefix)
)
```

**v1.3:** `is_same_domain` now considers `www.example.com` and `example.com` as the same domain.

**v1.4 fix:** Boundary check on `www.` strip. `www2.example.com` no longer becomes `2.example.com`. Only strips when `d.startswith("www.") and d.count(".") >= 2`.

---

### `core/net/default.py`

```python
from core.net.default import (
    SEARCH_MAX_RESULTS,      # 5
    SEARCH_TIMEOUT,          # 30
    CRAWL_MAX_DEPTH,         # 3
    CRAWL_MAX_BREADTH,       # 10
    CRAWL_LIMIT,             # 50
    EXTRACT_MAX_URLS,        # 10
    EXTRACT_DEPTH,           # "basic"
    SCRAPE_TIMEOUT,          # 30
    SCRAPE_MAX_RETRIES,      # 3
    BROWSER_TIMEOUT,         # 30
    BROWSER_NAV_RETRIES,     # 2
    RETRY_MAX_ATTEMPTS,      # 3
    RETRY_BASE_DELAY,        # 2.0
    RETRY_MAX_DELAY,         # 30.0
    RETRY_JITTER,            # True
    CB_FAILURE_THRESHOLD,    # 5
    CB_RECOVERY_TIMEOUT,     # 60.0
    CB_HALF_OPEN_MAX_CALLS,  # 1
)
```

---

## 🔒 Security

### 🛡️ SSRF Guard (`is_safe_network_address`)

All URL parameters pass through `is_safe_network_address()` before any HTTP request:

```python
def is_safe_network_address(hostname: str) -> bool:
    # 1. IPv6 bracket parsing: [::1]:8080
    # 2. Unbracketed IPv6: 2001:db8::1
    # 3. IPv4 literal: 192.168.1.1
    # 4. DNS resolution with timeout
    # All paths check: is_private, is_loopback, is_link_local, is_reserved, is_multicast, is_unspecified
```

**Blocks:**
- Non-HTTP schemes (`file://`, `ftp://`, `javascript://`, etc.) — enforced by callers
- Private IP ranges (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`)
- Loopback (`127.0.0.1`, `localhost`, `::1`)
- Link-local (`169.254.x.x`)
- Unspecified (`0.0.0.0`, `::`)
- IPv6 loopback (`::1`)
- Malformed URLs (empty hostname)

**Applied to:**
- SearXNG URL in `web(search)` (via `web_ops/utils.py`)
- Target URLs in `web(scrape)` / `web(read)`
- All URLs in `web(search_and_read)` (via internal `_action_scrape`)
- Tavily API endpoint and extracted URLs

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

## 📤 Output & Return Shapes

All modules return standard Python types or `ok()`/`fail()` dicts from `core/contracts.py`.

**Budget status dict:**
```python
{
    "tool_name": {
        "used": int,
        "limit": int,
        "remaining": int,
        "warning": bool,
        "blocked": bool,
    }
}
```

**URL normalization:**
```python
normalize_url("https://Example.COM:443/PATH/?Z=1&A=2")
# -> "https://example.com/PATH?A=2&Z=1"
```

**Domain comparison:**
```python
is_same_domain("https://www.example.com/a", "https://example.com/b")
# -> True (www. stripped)

is_same_domain("https://www2.example.com/a", "https://example.com/b")
# -> False (www2. NOT stripped, v1.4)
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
- **v1.4 CRITICAL:** `retry_async_factory` only calls `on_failure()` for retryable errors. Non-retryable errors (validation, 4xx) raise immediately without touching the CB.
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

# v1.4: Boundary check
is_same_domain("https://www2.example.com/a", "https://example.com/b")
# -> False (www2. NOT stripped)
```

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
