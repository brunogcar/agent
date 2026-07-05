<- Back to [NET Overview](../NET.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.5 | 2026-07-05 | `on_failure()` fires only on final raise (retry exhaustion), not per attempt — prevents CB opening on successful-but-retried calls. Preserves v1.4 retryable-only semantics. |
| v1.4 | — | `0.0.0.0`/`::` blocked, `on_failure()` retryable-only, `www.` strip boundary, Tavily error handler alignment |
| v1.3 | — | `RLock`, daily reset, IPv6 bracket parsing, unbracketed IPv6, `get_status()` no-config fallback, `__init__.py` re-exports |
| v1.2 | — | Initial package structure, test suite |
| v1.1 | — | — |
| v1.0 | — | — |

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

### v1.5

| Change | Impact |
|--------|--------|
| `on_failure()` per-attempt → final-raise only | `retry_async_factory` no longer calls `on_failure()` on each retry attempt that is later retried. It fires exactly once on retry exhaustion (still retryable-only). CB `failure_count` no longer accumulates transient noise from successful-but-retried calls. No migration — internal fix; existing callers see strictly fewer CB trips, never more. |

### v1.4

| Change | Impact |
|--------|--------|
| `0.0.0.0` and `::` blocked | `is_safe_network_address()` now rejects unspecified addresses. Previously bypassed all IP checks. |
| `on_failure()` retryable-only | `retry_async_factory` only calls `on_failure()` for retryable errors. Non-retryable errors (validation, 4xx) raise immediately without CB trip. |
| `www.` strip boundary | `is_same_domain()` no longer strips `www2.` → `2.`. Only strips when `startswith("www.") and count(".") >= 2`. |
| Tavily error handler alignment | `ReadError`/`WriteError`/`RemoteProtocolError`/`NetworkError` explicitly handled. HTTP 408 mapped to `RATE_LIMITED`. |

### v1.3

| Change | Impact |
|--------|--------|
| `threading.Lock()` → `RLock()` | Prevents deadlock in nested `get_status()` calls. |
| Daily reset | Automatic date change detection in `record_call()`. |
| IPv6 bracket parsing | `[::1]:8080` now handled correctly. |
| Unbracketed IPv6 | `2001:db8::1` bypasses DNS, uses `ipaddress` directly. |
| `get_status()` no-config fallback | Returns info even when no explicit budget config is set. |
| `__init__.py` re-exports | `from core.net import ...` now works for all public modules. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 6 modules (`errors`, `security`, `retry`, `budget`, `url`, `default`) | ✅ v1.2 | Package structure |
| HTTP error classification | ✅ v1.2 | `classify_http_error()`, 8 categories |
| Retryable detection | ✅ v1.2 | `is_retryable_error()`, status code + exception checks |
| Exponential backoff | ✅ v1.2 | `get_retry_delay()` with jitter |
| SDK exception registration | ✅ v1.2 | `register_retryable_exception()` |
| SSRF protection | ✅ v1.2 | `is_safe_network_address()`, IPv4 + IPv6 |
| Budget tracking | ✅ v1.3 | `APICostTracker`, `RLock`, daily reset |
| URL normalization | ✅ v1.3 | `normalize_url()`, `is_same_domain()` |
| Cross-tool re-exports | ✅ v1.3 | `core/net/__init__.py` |
| `0.0.0.0`/`::` block | ✅ v1.4 | `ip.is_unspecified` |
| `on_failure()` retryable-only | ✅ v1.4 | CB protection from non-retryable errors |
| `www.` boundary check | ✅ v1.4 | `startswith("www.") and count(".") >= 2` |
| Tavily error alignment | ✅ v1.4 | Explicit `NetworkError` subclass handling |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Replace inline HTTP error checks in `web` | Use `classify_http_error()` in `web/actions/*.py` | P1 |
| Replace hardcoded backoff in `web` | Use `get_retry_delay()` instead of `time.sleep(2 ** attempt)` | P1 |
| Replace duplicated SSRF logic in `web` | Use `_assert_safe_urls()` in `web/utils.py` | P1 |
| ~~Replace inline HTTP error checks in `browser`~~ | ✅ N/A — browser doesn't make HTTP calls directly (Playwright handles internally). Only `navigate.py` uses backoff, now via `get_retry_delay()`. | ✅ Done |
| ~~Replace duplicated SSRF logic in `browser`~~ | ✅ Already uses `core/net/security.is_safe_network_address()` | ✅ Done |
| Add `check_budget()` + `record_tool_call()` for paid APIs in `web` | If web tool ever calls paid APIs | P2 |
| Use `normalize_url()` for cache keys in `research`/`deep_research` | Any tool with response caching | P2 |
| ~~Import constants from `core.net.default` in `web`/`browser`~~ | ✅ Both now import from `core/net/default.py` | ✅ Done |
| Update `web`/`browser` tests to use `tests/core/net/conftest.py` fixtures | Shared fixtures — low priority, current tests work fine | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Proxy / SOCKS5 support** | Not needed for current deployment. Can be added via `httpx` proxy config if required. | Skip |
| 2 | **HTTP/2 support** | `httpx` supports HTTP/2 but not required for current tools. | Skip |
| 3 | **Connection pooling optimization** | `httpx.Client` already handles pooling. No action needed. | Skip |
| 4 | **Response compression** | `httpx` already handles gzip/brotli transparently. | Skip |
| 5 | **Custom DNS resolver** | `socket.getaddrinfo` is sufficient. Custom resolver adds complexity. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for module details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
