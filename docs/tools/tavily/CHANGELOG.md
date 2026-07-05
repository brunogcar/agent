<- Back to [Tavily Overview](../TAVILY.md)

# 🗺️ Tavi Changelog


## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2024-04-01 | `@meta_tool` refactor -- actions/ + roles/ directories, auto-discovery |
| v1.1 | 2024-04-15 | Hardening pass: bridge timeout, circuit breaker, `include_images`, `max_results` validation, `include_domains`/`exclude_domains`, `topic`, API key sanitization, shared `core/net/`, URL strictness |
| v1.2 | 2024-05-01 | Coroutine factory, shared `core/net/` infrastructure, structured error codes, API budget tracking, unified retry/backoff, IPv6 SSRF fixes, client lifecycle fixes, error truncation, sanitization v2, BOT_BLOCKED, default constants |
| v1.3 | 2024-05-15 | `extract`/`research` resilience fix, `CB_OPEN` error code, budget on all actions, `include_domains` validation, `citation_format` isolation, URL normalization, `core/net/__init__.py` re-exports, `retry_async_factory()`, `RLock`, daily reset, DNS timeout, HALF_OPEN fix, `NetworkError` classification, 408 fix, `www.` strip, state sync, `RateLimitError` registration |
| v1.4 | 2024-06-01 | `on_failure` only for retryable, HTTP 408 -> `RATE_LIMITED`, `httpx` network errors -> `NETWORK_ERROR`, `max_chars` removed, `research` block removed, `www.` boundary fix, `0.0.0.0`/`::` blocked |
| v1.5 | 2026-07-05 | Removed dead `citation_format` facade param (was never forwarded to any handler — `research` is workflow-only, not in DISPATCH). `core/net/retry.py` v1.5 fix inherited: CB no longer accumulates failure_count from successful-but-retried calls. |

---

## ⚠️ Breaking Changes

### v1.5

| Old | New | Migration |
|-----|-----|-----------|
| `citation_format: str = "numbered"` in `tavily()` facade signature | Removed | No migration — was dead param. v1.4 removed the `if action == "research": kwargs["citation_format"] = ...` block, so the param never reached any handler. `research` is workflow-only (not in `DISPATCH`, not LLM-accessible). `research.py` keeps its own `citation_format` kwarg with `"apa"` default. |
| CB `failure_count` accumulated per retry attempt on retryable errors | `on_failure()` fires only on final raise (retry exhaustion) | No migration — internal fix in `core/net/retry.py` v1.5. Existing callers see strictly fewer CB trips, never more. |

### v1.4

| Old | New | Migration |
|-----|-----|-----------|
| `on_failure()` fired on all errors | Only fires for retryable errors | No migration -- internal fix |
| HTTP 408 -> `CLIENT_ERROR` | HTTP 408 -> `RATE_LIMITED` | No migration -- internal fix |
| `httpx.ReadError`/`WriteError`/`RemoteProtocolError` fell to `UNKNOWN` | Now map to `NETWORK_ERROR` | No migration -- internal fix |
| `max_chars` in facade signature | Removed (no handler accepted it) | No migration -- was dead code |
| `research` action block in facade | Removed (never executed, not in DISPATCH) | No migration -- was dead code |
| `www.` strip via `removeprefix("www.")` | Boundary check: `www2.example.com` preserved | No migration -- internal fix |

### v1.3

| Old | New | Migration |
|-----|-----|-----------|
| `extract`/`research` bypassed `_run_async_with_resilience()` | Now uses it correctly (factory pattern) | No migration -- internal fix |
| `include_domains`/`exclude_domains` accepted any type | Must be `list[str]` | Pass lists, not strings or tuples |
| `citation_format` passed to all actions | Only passed to `research` | No migration -- internal fix |
| `core/net/security.py` IPv6 parsing broken | Fixed bracket + unbracketed IPv6 handling | No migration -- internal fix |
| `core/net/errors.py` `NetworkError` -> `CONNECT_ERROR` | Now correctly returns `NETWORK_ERROR` | No migration -- internal fix |
| `can_execute()` OPEN->HALF_OPEN didn't count against `half_open_max_calls` | Now counts correctly | No migration -- internal fix |
| `get_status()` returned `{}` when no budget config | Now returns tool info with `used` count | No migration -- internal fix |

### v1.2

| Old | New | Migration |
|-----|-----|-----------|
| `_run_async_with_resilience(coro)` takes coroutine object | Takes **coroutine factory** callable | Pass `_call` not `_call()` at all action call sites |
| `core/security.py` + `core/web_errors.py` standalone | Moved to `core/net/` package | Update imports: `core.net.security` -> `core.net.security`, `core.net.retry` -> `core.net.errors` |
| `max_depth` default 2, `limit` default 100 | `max_depth` default 3, `limit` default 50 | No migration -- facade now accepts params again; defaults changed |
| `raw_content` always included in search results | Stripped when `include_raw_content=False` | No migration -- restored v1.0 behavior |
| Error messages plain strings | All errors include `error_code` field | Consumers can now check `error_code` instead of parsing strings |
| `_close_client()` swallows exceptions silently | Logs exceptions; acquires lock; closes old client on key change | No migration -- internal fix |
| API key sanitization exact string match | Regex-based + URL-encoded variants + header patterns | No migration -- internal fix |
| `5 * (2 ** attempt)` hardcoded backoff | `get_retry_delay()` from `core/net/retry.py` | No migration -- internal fix |

### v1.1

| Old | New | Migration |
|-----|-----|-----------|
| `crawl`/`map` accepted `query` as URL fallback | `url` is **strictly required** for `crawl`/`map` | Pass `url=` explicitly; `query` is now only for contextual `instructions` |
| `search` silently dropped `include_images` | `include_images` is now passed to SDK | No migration -- it just works now |
| `max_results` had no upper bound | `max_results` validated to 1-20 range | Values >20 now fail fast with clear error |
| `_close_client()` was a no-op | Actually closes `AsyncTavilyClient` connection pool | No migration -- internal fix |
| `_run_async()` timeout was decorative | Timeout now actually fires and returns control | No migration -- internal fix |

### v1.0

| Old | New | Migration |
|-----|-----|-----------|
| Monolithic `tools/tavily.py` (~526 lines) | Atomic `tools/tavily_ops/actions/*.py` (5 files) + thin facade | No migration needed -- same API |
| Manual `if action == "search": ... elif ...` dispatch in facade | `@register_action` auto-discovery + `@meta_tool` | No migration needed -- same API |
| Manual docstring in `tavily()` | `@meta_tool` auto-generated from `help_text` + `examples` | No migration needed -- same API |
| `crawl()`/`map()` passed `query=` to SDK | Now translates to `instructions=` (SDK 0.7.26) | No migration needed -- facade param name unchanged |
| `crawl()` missing `extract_depth`/`format` | Now exposed (SDK 0.7.26) | New optional params, no breaking change |
| `research()` not validated | Now validates `citation_format` against SDK Literal | Internal-only, no breaking change |
| `trace_id` hardcoded `""` in actions | Now threaded through `ok()`/`fail()`/`prune_tool_dict()` | No migration needed -- already a facade param |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 4 exposed actions (`search`, `extract`, `crawl`, `map`) | v1.0 | `research` is workflow-only |
| Async-to-sync bridge | ✅ v1.0 | `_run_async()` handles nested loops + ThreadPoolExecutor fallback |
| Lazy client with key caching |✅ v1.0 | `_get_singleton_client()` re-creates only on API key change, thread-safe lock |
| Keyless mode | ✅ v1.0 | `search`/`extract` work without API key; `crawl`/`map`/`research` reject |
| SSRF guard | ✅ v1.0 | `_assert_safe_urls()` on `extract`/`crawl`/`map` |
| Raw content stripping | ✅ v1.0 | `_action_search` strips `raw_content` unless `include_raw_content=True` |
| Comprehensive error handling | ✅ v1.0 | `_handle_tavily_error()` covers 8+ exception types with lazy imports |
| `prune_tool_dict` integration | ✅ v1.0 | All action outputs piped through pruner |
| `PARALLEL_SAFE` | ✅ v1.0 | Pure network I/O, no shared state |
| `max_results` keyless cap | ✅ v1.0 | Silently clamps to 3 in keyless mode |
| URL count validation | ✅ v1.0 | `extract` rejects > 10 URLs |
| `crawl`/`map` url/query fallback | v1.0 | Accepts either `url` or `query` param |
| `@meta_tool` facade | ✅ v1.0 | Auto-generated Literal + docstring from DISPATCH metadata |
| Un-multiplex to `tavily_ops/` | ✅ v1.0 | Atomic action files with auto-discovery |
| `trace_id` propagation | ✅ v1.0 | Threaded through all handlers |
| SDK 0.7.26 compatibility | ✅ v1.0 | `instructions` translation, `extract_depth`/`format` for crawl |
| State ownership bug guard | ✅ v1.0 | `test_tavily_state.py` regression test |
| Non-dict handler guard | ✅ v1.0 | Facade checks `isinstance(result, dict)` |
| **Bridge timeout actually works** | ✅ v1.1 | `shutdown(wait=False)` prevents blocking; timeout fires correctly |
| **Circuit breaker + rate-limit retry** | ✅ v1.1 | `_run_async_with_resilience()` in `bridge.py` |
| **`include_images` passed to SDK** | ✅ v1.1 | Was silently dropped in `search` |
| **`max_results` validated (1-20)** | ✅ v1.1 | Fail fast instead of confusing SDK error |
| **`include_domains`/`exclude_domains`** | ✅ v1.1 | Domain-scoped research |
| **`topic` parameter surfaced** | ✅ v1.1 | News/current-events filtering |
| **API key sanitization** | ✅ v1.1 | Key stripped from all error messages |
| **`_assert_safe_urls` in `core/net/security.py`** | ✅ v1.1 | Cross-tool shared SSRF guard |
| **`core/net/retry.py` shared module** | ✅ v1.1 | `classify_http_error()`, `is_retryable_error()` for web + tavily |
| **`_close_client()` actually closes** | ✅ v1.1 | Properly awaits `client.close()` via bridge |
| **`crawl`/`map` URL strictly required** | ✅ v1.1 | Removed misleading `url or query` fallback |
| **Coroutine factory pattern** | ✅ v1.2 | Prevents coroutine reuse crash on retry; `_call` not `_call()` |
| **Shared `core/net/` infrastructure** | ✅ v1.2 | errors, security, retry, budget, url, default modules |
| **Structured error codes** | ✅ v1.2 | `error_code` in all `fail()` responses via `core/contracts.py` |
| **API budget tracking** | ✅ v1.2 | `APICostTracker` with daily limits, warnings, thread safety |
| **Unified retry/backoff** | ✅ v1.2 | `get_retry_delay()` + `retry_sync()` in `core/net/retry.py` |
| **IPv6 SSRF fixes** | ✅ v1.2 | Port stripping, empty hostname rejection, scheme validation |
| **Client lifecycle fixes** | ✅ v1.2 | Lock on close, old client cleanup on key change, `api_key or None` |
| **Error message truncation** | ✅ v1.2 | 500 char cap to prevent context window bloat |
| **API key sanitization v2** | ✅ v1.2 | Regex, URL-encoded, header, and query param patterns |
| **BOT_BLOCKED classification** | ✅ v1.2 | Cloudflare/cf-ray detection in `core/net/errors.py` |
| **Default constants** | ✅ v1.2 | `core/net/default.py` -- shared across tavily, web_ops, browser |
| **`extract`/`research` use `_run_async_with_resilience()`** | ✅ v1.3 | Was bypassing all resilience (coroutine reuse bug) |
| **`CB_OPEN` error code** | ✅ v1.3 | Properly returned when circuit breaker is OPEN |
| **Budget tracking wired to all 5 actions** | ✅ v1.3 | `check_budget()` + `record_tool_call()` on every action |
| **`include_domains`/`exclude_domains` validation** | ✅ v1.3 | Must be `list[str]` -- rejected with `INVALID_PARAMS` |
| **`citation_format` only for `research`** | ✅ v1.3 | No longer leaked to other actions |
| **`normalize_url()` in `extract`/`crawl`** | ✅ v1.3 | URLs normalized before extraction/crawl |
| **`core/net/__init__.py` re-exports** | ✅ v1.3 | `from core.net import ...` for cross-tool adoption |
| **`retry_async_factory()` in `core/net/retry.py`** | ✅ v1.3 | Async coroutine retry with CB hooks for web_ops/browser reuse |
| **`RLock` in budget tracker** | ✅ v1.3 | Prevents deadlock in nested `get_status()` calls |
| **Daily reset in budget tracker** | ✅ v1.3 | Date change detection in `record_call()` |
| **`_is_private_or_localhost()` restored** | ✅ v1.3 | Cross-tool IP check for web_ops/browser adoption |
| **DNS timeout via ThreadPoolExecutor** | ✅ v1.3 | `socket.getaddrinfo` has no `timeout` kwarg |
| **`can_execute()` HALF_OPEN fix** | ✅ v1.3 | OPEN->HALF_OPEN transition counts against `half_open_max_calls` |
| **`NetworkError` -> `NETWORK_ERROR`** | ✅ v1.3 | Fixed classification in `core/net/errors.py` |
| **408 -> `RATE_LIMITED`** | ✅ v1.3 | HTTP 408 is in `RETRYABLE_STATUS_CODES` |
| **`is_same_domain` strips `www.`** | ✅ v1.3 | `www.example.com` and `example.com` match |
| **`state._KEYLESS_WARNED` sync** | ✅ v1.3 | `client.py` uses `state._KEYLESS_WARNED` for proper reset |
| **`RateLimitError` registered as retryable** | ✅ v1.3 | Tavily SDK exception auto-registered |
| **`on_failure` only for retryable errors** | ✅ v1.4 | CB no longer tripped by validation/4xx failures |
| **HTTP 408 -> `RATE_LIMITED`** | ✅ v1.4 | Aligns with `classify_http_error()` in `core/net/errors.py` |
| **`httpx` network error handlers** | ✅ v1.4 | ReadError/WriteError/RemoteProtocolError/NetworkError -> `NETWORK_ERROR` |
| **`max_chars` removed** | ✅ v1.4 | Dead param, no handler accepted it |
| **`research` block removed** | ✅ v1.4 | Dead code, not in DISPATCH |
| **`www.` strip boundary fix** | ✅ v1.4 | `www2.example.com` no longer stripped |
| **`0.0.0.0`/`::` blocked** | ✅ v1.4 | `is_unspecified` check in `core/net/security.py` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Wire `run_research()` into `workflows/deep_research_impl/nodes/search.py` | Trigger: "when iteration > 3 and completeness < 50" as accelerator | P1 |
| Adopt `core/net/` in `web_ops` | Use `core/net/errors.py`, `core/net/security.py`, `core/net/retry.py` in `web_ops/actions/scrape.py` and `search.py` | P1 |
| Adopt `core/net/` in `browser` tool | Use `classify_http_error()` for Playwright errors; `get_retry_delay()` for nav retries | P1 |
| `tavily(search)` -> `web(search)` fallback chain | Automatic fallback when CB open / no key / rate limited, using `error_code` | P2 |
| `tavily(search)` as primary search in research workflow | Replace `web(search)` with `tavily(search)` in `workflows/research.py` when API key present | P2 |
| Add `@cached` decorator | LRU cache for search/extract results (TTL 300s/1800s) | P2 |
| URL normalization module | `core/net/url.py` -- strip slashes, sort params, lowercase domain | P2 |
| Remove backward-compat wrappers | Delete `core/net/security.py` and `core/net/retry.py` re-exports once web_ops/browser migrate | P3 |
| Search result deduplication | Similar to `web(search_and_read)`, deduplicate identical URLs across Tavily result pages | P3 |
| Response caching | Cache Tavily responses (TTL-based) to avoid redundant API calls | P3 |
| Client-side batching for `extract` | Split >10 URLs into batches of 10, execute concurrently, merge results | P2 |
| Persistent event loop in `bridge.py` | Background thread with dedicated loop to save ~1ms per call | P3 |
| Surface `include_images`/`include_image_descriptions` in `search` | SDK supports it; facade needs param | P2 |
| Surface `search_depth`/`topic`/`time_range` validation | Client-side enum validation instead of SDK error | P2 |
| Tavily as `web` tool fallback | When SearXNG fails, fall back to `tavily(search)` | P3 |
| Composite `deep_research` action | Search + extract + LLM synthesis in one call | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Expose `research` as tool action** | `run_research()` is intentionally workflow-only. Exposing it as a tool action would bypass the research workflow's planning, routing, and memory integration. | Skip |
| 2 | **Streaming responses** | MCP stdio transport doesn't support streaming. Would require gateway-only mode. | Skip |
| 3 | **Synchronous client** | `AsyncTavilyClient` is the only official client. A sync wrapper would be redundant given `_run_async()`. | Skip |
| 4 | **Custom HTTP adapter** | `httpx` handles retries and connection pooling well. No need for a custom adapter. | Skip |
| 5 | **Result pagination** | Tavily API returns all results in one call. No pagination API exists. | Skip |
| 6 | **Configurable keyless `max_results`** | Hardcoded cap of 3 is Tavily API-imposed, not arbitrary. Making it configurable invites users to hit rate limits. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
