# 🔗 NET

The `core/net/` package provides shared network infrastructure for all web-facing tools and workflows. Unified HTTP error classification, SSRF protection, retry/backoff policies, API budget tracking, URL normalization, and shared default constants.

**Key characteristics:**
- **Thread-safe** — `RLock` for nested calls, `Lock` for simple cases
- **Singleton pattern** — Budget tracker is global singleton; reset in tests via `_calls.clear()`
- **Cross-tool adoption** — `core/net/__init__.py` re-exports all modules for `from core.net import ...`
- **Lazy SDK exception registration** — `register_retryable_exception()` for tool-specific retryable errors
- **DNS timeout safety** — `ThreadPoolExecutor` + `future.result(timeout=)` (socket.getaddrinfo has no `timeout` kwarg)
- **IPv6 aware** — Handles bracketed `[::1]:8080` and unbracketed `2001:db8::1` correctly
- **Daily budget reset** — Automatic date change detection in `record_call()`
- **v1.4: `0.0.0.0` and `::` blocked** — `is_unspecified` check added to all IP validation paths

---

## 🚀 Quick Start

```python
from core.net import classify_http_error, is_retryable_error, is_safe_network_address
from core.net import retry_sync, normalize_url, record_tool_call, check_budget
```

*(Fill this section with relevant info from edits and refactors. Add quick-start examples as they are learned.)*

---

## 🔄 When to Use vs Alternatives

| Need | Use | Why |
|------|-----|-----|
| HTTP error classification | `core/net/errors.py` | Unified categories, retryable detection, SDK registration |
| SSRF protection | `core/net/security.py` | Cross-tool, IPv6-aware, DNS timeout-safe |
| Retry/backoff | `core/net/retry.py` | Exponential backoff, jitter, circuit breaker hooks |
| API budget tracking | `core/net/budget.py` | Thread-safe, daily reset, auto-block |
| URL normalization | `core/net/url.py` | Deterministic cache keys, domain comparison |
| Shared constants | `core/net/default.py` | Single source of truth for timeouts, retries, thresholds |

---

## ⚙️ Configuration

```ini
# No direct .env variables for core/net/ — constants live in default.py
# Tools that adopt core/net/ use their own .env keys:
SEARXNG_URL=http://localhost:8080        # Used by web tool (via cfg)
TAVILY_API_KEY=tvly-...                  # Used by tavily tool (via cfg)
```

*(Fill this section with relevant info from edits and refactors. Add configuration details as they are learned.)*

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](net/ARCHITECTURE.md) | Module tree, design decisions, test coverage, source code reference, cross-tool adoption status |
| [API.md](net/API.md) | Module APIs, function signatures, error codes, security rules, return formats |
| [CHANGELOG.md](net/CHANGELOG.md) | Version history, breaking changes, completed milestones, adoption roadmap |
| [INSTRUCTIONS.md](net/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

## ✅ Cross-Tool Adoption Status

| Tool | Status | Notes |
|------|--------|-------|
| `tavily` | ✅ Adopted | errors, security, retry, budget, url, default |
| `web` | ⏳ Pending | Replace inline error checks, SSRF logic, hardcoded backoff |
| `browser` | ⏳ Pending | Replace inline error checks, SSRF logic |
| `workflows/research` | ⏳ Pending | Use `normalize_url()` for cache keys, `default.py` constants |
| `workflows/deep_research` | ⏳ Pending | Use `normalize_url()` for cache keys, `default.py` constants |

---

## 🔧 v1.6 Fix (2026-07-18)

**`core/net/retry.py`** — `_sleep = time.sleep` module-level reference. `retry_sync()` + `retry_async_factory()` now call `_sleep(delay)` instead of `time.sleep(delay)`. Tests patch `core.net.retry._sleep` (scoped to `retry.py`) instead of `core.net.retry.time.sleep` (global — `time` is a singleton module, so the old patch caught stray `time.sleep()` calls from background threads like the browser reaper `sleep(60)` and watchdog, causing `assert_called_once()` to fail with 35004 stray calls in `test_scrape_retry_on_503`). See [net/CHANGELOG.md](net/CHANGELOG.md) for details.

*Last updated: 2026-07-18 (v1.6 _sleep fix). See subfiles for detailed documentation.*
