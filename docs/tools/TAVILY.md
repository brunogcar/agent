# 🔬 Tavily Tool

The `tavily()` tool provides **AI-optimized web search and content extraction** via the [Tavily API](https://tavily.com). It complements the existing `web` tool with superior ranking, automatic citations, and bulk extraction capabilities.

**Key characteristics:**
- **AI-ranked results** — Tavily's relevance engine outperforms raw SearXNG for research queries
- **Automatic citations** — Every result includes URL, title, and confidence score
- **Bulk extraction** — `extract` action can process up to 10 URLs in one call
- **Keyless mode** — Works without API key for `search` and `extract` (rate-limited)
- **Async client, sync facade** — `AsyncTavilyClient` wrapped in `_run_async()` bridge for MCP compatibility
- **Lazy client loading** — `AsyncTavilyClient` imported and instantiated only on first use
- **PARALLEL_SAFE** — Pure network I/O, no shared state
- **Circuit breaker** — Automatic fail-fast after 5 consecutive failures, recovers after 60s
- **Rate-limit retry** — Exponential backoff on retryable errors via `core/net/retry.py` (2s base, unified across tools)
- **Structured error codes** — Every error response includes `error_code` for programmatic fallback decisions
- **API budget tracking** — Per-tool cost counter with configurable limits and auto-block
- **Shared network infrastructure** — `core/net/` modules used by tavily, web_ops, browser

---

## ⚠️ Breaking Changes

### v1.2

| Old | New | Migration |
|-----|-----|-----------|
| `_run_async_with_resilience(coro)` takes coroutine object | Takes **coroutine factory** callable | Pass `_call` not `_call()` at all action call sites |
| `core/security.py` + `core/web_errors.py` standalone | Moved to `core/net/` package | Update imports: `core.security` → `core.net.security`, `core.web_errors` → `core.net.errors` |
| `max_depth` default 2, `limit` default 100 | `max_depth` default 3, `limit` default 50 | No migration — facade now accepts params again; defaults changed |
| `raw_content` always included in search results | Stripped when `include_raw_content=False` | No migration — restored v1.0 behavior |
| Error messages plain strings | All errors include `error_code` field | Consumers can now check `error_code` instead of parsing strings |
| `_close_client()` swallows exceptions silently | Logs exceptions; acquires lock; closes old client on key change | No migration — internal fix |
| API key sanitization exact string match | Regex-based + URL-encoded variants + header patterns | No migration — internal fix |
| `5 * (2 ** attempt)` hardcoded backoff | `get_retry_delay()` from `core/net/retry.py` | No migration — internal fix |

### v1.1

| Old | New | Migration |
|-----|-----|-----------|
| `crawl`/`map` accepted `query` as URL fallback | `url` is **strictly required** for `crawl`/`map` | Pass `url=` explicitly; `query` is now only for contextual `instructions` |
| `search` silently dropped `include_images` | `include_images` is now passed to SDK | No migration — it just works now |
| `max_results` had no upper bound | `max_results` validated to 1–20 range | Values >20 now fail fast with clear error |
| `_close_client()` was a no-op | Actually closes `AsyncTavilyClient` connection pool | No migration — internal fix |
| `_run_async()` timeout was decorative | Timeout now actually fires and returns control | No migration — internal fix |

### v1.0

| Old | New | Migration |
|-----|-----|-----------|
| Monolithic `tools/tavily.py` (~526 lines) | Atomic `tools/tavily_ops/actions/*.py` (5 files) + thin facade | No migration needed — same API |
| Manual `if action == "search": ... elif ...` dispatch in facade | `@register_action` auto-discovery + `@meta_tool` | No migration needed — same API |
| Manual docstring in `tavily()` | `@meta_tool` auto-generated from `help_text` + `examples` | No migration needed — same API |
| `crawl()`/`map()` passed `query=` to SDK | Now translates to `instructions=` (SDK 0.7.26) | No migration needed — facade param name unchanged |
| `crawl()` missing `extract_depth`/`format` | Now exposed (SDK 0.7.26) | New optional params, no breaking change |
| `research()` not validated | Now validates `citation_format` against SDK Literal | Internal-only, no breaking change |
| `trace_id` hardcoded `""` in actions | Now threaded through `ok()`/`fail()`/`prune_tool_dict()` | No migration needed — already a facade param |

---

## 🚀 Quick Start

```python
# AI-ranked search
result = tavily(action="search", query="FastMCP python tutorial", max_results=5)

# Bulk URL extraction
result = tavily(action="extract", urls=["https://docs.python.org/3/library/pathlib.html", "https://..."])

# Deep site crawl (requires API key)
result = tavily(action="crawl", url="https://example.com", max_depth=2, max_breadth=10)

# Site structure map (requires API key)
result = tavily(action="map", url="https://example.com", max_depth=2)

# Keyless mode — works without API key for search/extract
result = tavily(action="search", query="Python async patterns")
# → {"status": "success", "data": {"keyless": true, ...}}

# Domain-scoped search (v1.1)
result = tavily(
    action="search",
    query="Python asyncio",
    include_domains=["github.com", "docs.python.org"],
    exclude_domains=["pinterest.com", "quora.com"]
)

# News-scoped search (v1.1)
result = tavily(action="search", query="AI regulation", topic="news")
```

---

## 🏗️ Architecture

```text
tools/tavily.py              # @tool + @meta_tool facade — thin dispatch only
tools/tavily_ops/
├── __init__.py              # Auto-discovery: imports _registry, glob actions/*.py
├── _registry.py             # DISPATCH dict + @register_action decorator
├── state.py                 # _TAVILY_CLIENT, _CLIENT_LOCK, _KEYLESS_WARNED, reset_state()
├── client.py                # _get_singleton_client(), _close_client(), _TAVILY_CB
│                            # v1.2: closes old client on key change, lock on close
├── bridge.py                # _run_async() + _run_async_with_resilience() (CB + retry)
│                            # v1.2: accepts coroutine factory, uses core/net/retry.py
├── errors.py                # _handle_tavily_error(), error_code, API key sanitization
│                            # v1.2: regex sanitization, 500-char truncation
└── actions/
    ├── search.py            # @register_action("tavily", "search", ...)
    ├── extract.py           # @register_action("tavily", "extract", ...)
    ├── crawl.py             # @register_action("tavily", "crawl", ...)
    ├── map.py               # @register_action("tavily", "map", ...)
    └── research.py          # PLAIN function, NO @register_action (workflow-only)

core/net/                    # v1.2: Shared network infrastructure
├── __init__.py              # Package init
├── errors.py                # classify_http_error(), is_retryable_error(), get_retry_delay(), BOT_BLOCKED
├── security.py              # is_safe_network_address(), _assert_safe_urls() — SSRF guard
├── retry.py                 # retry_sync() — unified retry with backoff
├── budget.py                # APICostTracker — cost tracking per tool
├── url.py                   # normalize_url(), extract_domain(), is_same_domain()
└── default.py               # Shared defaults: SEARCH_MAX_RESULTS, CRAWL_MAX_DEPTH, RETRY_BASE_DELAY, etc.

core/security.py             # BACKWARD COMPAT: re-exports from core.net.security (remove after migration)
core/web_errors.py           # BACKWARD COMPAT: re-exports from core.net.errors (remove after migration)

EDIT: 
- files deleted
- need to check for missing imports
```

### Dispatch Flow

```mermaid
graph TD
    A["tavily(action, ...)"] --> B{"action?"}
    B -->|search| C["_action_search → _run_async_with_resilience → prune_tool_dict"]
    B -->|extract| D["Validate urls (≤10) → _assert_safe_urls → _action_extract → _run_async_with_resilience → prune_tool_dict"]
    B -->|crawl| E["Validate url → _assert_safe_urls → keyless check → _action_crawl → _run_async_with_resilience → prune_tool_dict"]
    B -->|map| F["Validate url → _assert_safe_urls → keyless check → _action_map → _run_async_with_resilience → prune_tool_dict"]
    B -->|unknown| G["Return fail('Unknown action ...')"]
    C --> H["Return ok({results, answer, query, keyless})"]
    D --> I["Return ok({results, keyless})"]
    E --> J["Return ok({results, keyless: false})"]
    F --> K["Return ok({results, keyless: false})"]
```

**Key design decisions:**
- **Async-to-sync bridge** — `_run_async()` handles two cases: (1) no running loop → `asyncio.run(coro)`; (2) running loop (e.g., inside MCP) → spawns a `ThreadPoolExecutor(max_workers=1)` and runs `asyncio.run` in a fresh thread. Timeout: `cfg.tavily_timeout + 10` seconds. Deliberately uses per-call ThreadPoolExecutor instead of a persistent background loop — Tavily calls are short network requests, not long Playwright sessions.
- **v1.2: _run_async_with_resilience()** — Wraps `_run_async()` with circuit breaker (`_TAVILY_CB`) and automatic retry on all retryable errors (3 attempts, exponential backoff via `core/net/retry.py:get_retry_delay()`). **Accepts a coroutine factory (callable), not a coroutine object** — ensures fresh coroutine per retry attempt. Centralized in `bridge.py` so every action gets resilience without per-action edits.
- **Lazy client with key caching** — `_get_singleton_client()` caches the `AsyncTavilyClient` instance and re-creates it only if the API key changes. Thread-safe via `_CLIENT_LOCK` (double-checked locking). Keyless mode uses `api_key=None`.
- **v1.2: Client lifecycle** — `_get_singleton_client()` closes the old client before creating a new one when the API key changes. `_close_client()` acquires `_CLIENT_LOCK` and logs exceptions instead of silently swallowing.
- **State ownership** — `state.py` owns `_TAVILY_CLIENT`, `_CLIENT_LOCK`, `_KEYLESS_WARNED`. `client.py` does `import tools.tavily_ops.state as state` and reads/writes `state._TAVILY_CLIENT` directly. This prevents the name-binding divergence bug that broke `web_ops`'s `reset_state()`.
- **Keyless warning once** — `_warn_keyless_once()` logs a single `logger.warning` on first keyless invocation to avoid log spam. `state.reset_state()` clears `_KEYLESS_WARNED` for test isolation.
- **SSRF at action level** — `_assert_safe_urls()` is called inside `_action_extract`, `_action_crawl`, and `_action_map` (not at the facade level). `search` does not need SSRF since it doesn't fetch arbitrary URLs. v1.2: `_assert_safe_urls` moved to `core/net/security.py` with scheme validation, empty hostname rejection, and IPv6 port stripping.
- **Raw content stripping** — `_action_search` strips `raw_content` from all results unless `include_raw_content=True`. Prevents context window explosion.
- **v1.2: Error type detection + sanitization** — `_handle_tavily_error()` uses both `isinstance` checks (with lazy tavily imports) and `type(e).__name__` string fallback. API key is stripped via regex (exact match, URL-encoded, Authorization header, query param) from all error messages before returning to the LLM. Error messages truncated to 500 chars to prevent context window bloat.
- **v1.2: Error codes** — `core/contracts.py:fail()` accepts an `error_code` parameter. Tavily returns standardized codes: `CB_OPEN`, `RATE_LIMITED`, `AUTH_FAILED`, `QUOTA_EXHAUSTED`, `TIMEOUT`, `CONNECT_ERROR`, `SERVER_ERROR`, `CLIENT_ERROR`, `API_ERROR`, `UNKNOWN`.
- **`research` is workflow-only** — `run_research()` in `actions/research.py` exists but is NOT exposed in the `@tool` facade. Not registered in `DISPATCH`. Reserved for `workflows/deep_research_impl/nodes/search.py`.
- **All outputs pruned** — Every action result passes through `prune_tool_dict()` from `core.memory_backend.pruner` before return.
- **trace_id propagation** — `trace_id` is threaded from facade through `ok()` / `fail()` / `prune_tool_dict()` in all action handlers.
- **Non-dict handler guard** — Facade checks `isinstance(result, dict)` after handler call. Returns `fail()` if handler returns non-dict (regression guard from prior refactors).
- **v1.2: Coroutine factory pattern** — `_run_async_with_resilience()` accepts a callable that produces a fresh coroutine (`_call`), not an already-instantiated coroutine (`_call()`). This prevents `RuntimeError: cannot reuse already awaited coroutine` on retry attempts.
- **v1.2: Unified network infrastructure** — All HTTP error classification, retry logic, SSRF guards, and budget tracking live in `core/net/`. Adopted by tavily_ops; web_ops and browser adoption scheduled.

---

## 📝 Tool Signature

```python
@tool
@meta_tool(DISPATCH.get("tavily", {}), doc_sections=[...])
def tavily(
    action: str,
    query: str = "",
    urls: Optional[list[str]] = None,
    url: str = "",
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    time_range: str = "",
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    include_answer: bool = True,
    include_raw_content: bool = False,
    include_images: bool = False,
    extract_depth: str = "basic",
    format: str = "markdown",
    max_depth: int = 3,          # v1.2: restored, default 3
    max_breadth: int = 10,       # v1.2: restored
    limit: int = 50,             # v1.2: restored, default 50
    trace_id: str = "",
) -> dict:
    """Tavily AI research tool — atomic actions for search/extract/crawl/map."""
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | One of `search`, `extract`, `crawl`, `map` (auto-generated Literal by @meta_tool) |
| `query` | `str` | No | Search query. **Required** for `search`. Also accepted by `crawl`/`map` as contextual `instructions`. |
| `urls` | `list[str]` | No | URLs for `extract`. **Required** for `extract`. Max 10 items. |
| `url` | `str` | No | Starting URL for `crawl`/`map`. **Required** for `crawl`/`map`. |
| `max_results` | `int` | No | Results per search. Default: 5. Range: 1–20. **Capped at 3 in keyless mode.** |
| `search_depth` | `str` | No | `"basic"` or `"advanced"`. Default: `"basic"`. |
| `topic` | `str` | No | Topic filter for search: `"general"`, `"news"`, `"finance"`. Default: `"general"`. **v1.1** |
| `time_range` | `str` | No | Time range filter for search. |
| `include_domains` | `list[str]` | No | Whitelist domains for search. **v1.1** |
| `exclude_domains` | `list[str]` | No | Blacklist domains for search. **v1.1** |
| `include_answer` | `bool` | No | Include AI-generated answer in search. Default: `True`. |
| `include_raw_content` | `bool` | No | Include full page text in search results. Default: `False`. **Large!** |
| `include_images` | `bool` | No | Include images in search results. Default: `False`. **v1.1: Now passed to SDK.** |
| `extract_depth` | `str` | No | `"basic"` or `"advanced"`. Default: `"basic"`. Now also supported by `crawl`. |
| `format` | `str` | No | Output format for extract/crawl. `"markdown"` or `"text"`. Default: `"markdown"`. |
| `max_depth` | `int` | No | Max link depth for crawl/map. Default: **3**. **v1.2: restored.** |
| `max_breadth` | `int` | No | Max pages per level for crawl/map. Default: **10**. **v1.2: restored.** |
| `limit` | `int` | No | Max total pages for crawl/map. Default: **50**. **v1.2: restored.** |
| `trace_id` | `str` | No | Trace identifier for logging and result correlation. Threaded through all handlers. |

> **Note:** `input`, `model`, `citation_format` params were removed from the facade. They only existed for `research`, which is not exposed as a tool action. Call `run_research()` directly from workflows.

---

## ⚡ Actions

### `search` — AI-ranked web search

Queries Tavily and returns AI-ranked results with titles, URLs, snippets, and an optional AI-generated answer.

**Keyless behavior:**
- `max_results` is silently capped to `3`
- Response includes `"keyless": true`
- Lower rate limits apply (~100 requests/day)
- Single `logger.warning` on first keyless use

**v1.1 additions:**
- `include_images` is now passed to the SDK (was silently dropped before)
- `include_domains`/`exclude_domains` for domain-scoped research
- `topic` parameter for news/current-events filtering
- `max_results` validated to 1–20 range (fail fast on invalid values)

**v1.2 additions:**
- `raw_content` stripped from results when `include_raw_content=False` (restored v1.0 behavior)
- Facade accepts `max_depth`, `max_breadth`, `limit` again (was removed in v1.1)

**Return:**
```json
{
  "status": "success",
  "data": {
    "results": [
      {"title": "...", "url": "https://...", "content": "...", "score": 0.95}
    ],
    "answer": "AI-generated summary...",
    "query": "FastMCP python tutorial",
    "keyless": false
  }
}
```

**Raw content handling:**
- Stripped from all results by default (prevents context window explosion)
- Included only if `include_raw_content=True`

**Error cases:**
- Missing `query` → `fail("action='search' requires query=")`
- `max_results` < 1 or > 20 → `fail("max_results must be >= 1")` / `fail("max_results must be <= 20")`
- Keyless rate limit → `fail("Tavily keyless rate limit reached...")` with `error_code="AUTH_FAILED"`
- Invalid API key → `fail("Tavily API key is invalid...")` with `error_code="AUTH_FAILED"`
- Timeout → `fail("Tavily request timed out...")` with `error_code="TIMEOUT"`
- Connection error → `fail("Tavily connection failed...")` with `error_code="CONNECT_ERROR"`
- Circuit breaker OPEN → `fail("Tavily circuit breaker is OPEN...")` with `error_code="CB_OPEN"`

### `extract` — Bulk URL content extraction

Accepts up to 10 URLs and returns extracted content with citations for each.

**Return:**
```json
{
  "status": "success",
  "data": {
    "results": [
      {"url": "https://...", "text": "Extracted markdown...", "images": []}
    ],
    "keyless": false
  }
}
```

**Validation:**
- Missing `urls` → `fail("urls is required for extract action")`
- More than 10 URLs → `fail("urls cannot exceed 10 items")`
- Unsafe URLs → `fail("Blocked: {url} resolves to a private/internal address")`

### `crawl` — Deep site traversal

Follows links from a starting URL up to `max_depth` levels. **Requires API key.**

**SDK note:** Tavily SDK 0.7.26 uses `instructions=` internally. The facade keeps `query` as the parameter name for backward compatibility but translates it automatically: `client.crawl(url=..., instructions=query, ...)`.

**v1.1 breaking change:** `url` is now **strictly required**. The old `url or query` fallback (where `query` would be used as the target URL) has been removed because it produced misleading SSRF errors when users passed search strings instead of URLs.

**v1.2:** Facade accepts `max_depth`, `max_breadth`, `limit` again.

**Return:**
```json
{
  "status": "success",
  "data": {
    "results": [{"url": "...", "title": "...", "content": "..."}],
    "keyless": false
  }
}
```

**Validation:**
- Missing `url` → `fail("action='crawl' requires url=")`
- Keyless mode → `fail("action='crawl' requires a Tavily API key...")`
- Unsafe URL → `fail("Blocked: {url} resolves to a private/internal address")`

### `map` — Site structure discovery

Discovers site hierarchy without fetching full content. **Requires API key.**

**SDK note:** Same `instructions=` translation as `crawl`.

**v1.1 breaking change:** Same as `crawl` — `url` is strictly required, `query` is only for contextual instructions.

**v1.2:** Facade accepts `max_depth`, `max_breadth`, `limit` again.

**Return:**
```json
{
  "status": "success",
  "data": {
    "results": [{"url": "...", "title": "..."}],
    "keyless": false
  }
}
```

**Validation:** Same as `crawl`.

### `research` — End-to-end deep research (workflow-only)

**NOT exposed as a tool action.** Call directly from workflows:

```python
from tools.tavily_ops.actions.research import run_research

result = run_research(
    input="Research topic",
    model=None,
    citation_format="apa",  # "numbered" | "mla" | "apa" | "chicago"
    trace_id="...",
)
```

Requires API key. Validates `citation_format` against SDK Literal type (`"numbered" | "mla" | "apa" | "chicago"`).

---

## 🔒 Security

### SSRF Guard (`_assert_safe_urls`)

All URL parameters (`url`, `urls`) pass through `_assert_safe_urls()` inside the action handlers:

```python
def _assert_safe_urls(urls: list[str]) -> tuple[bool, str]:
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Blocked: {url} — only http/https schemes allowed"
        if not parsed.hostname:
            return False, f"Blocked: {url} — no valid hostname"
        if not is_safe_network_address(parsed.hostname):
            return False, f"Blocked: {url} — resolves to private/internal address"
    return True, ""
```

Uses `core.net.security.is_safe_network_address` — same guard as `web.py`. v1.2: `_assert_safe_urls` moved to `core/net/security.py` with scheme validation, empty hostname rejection, and IPv6 port stripping. Cross-tool shared — adopted by tavily_ops; web_ops and browser adoption scheduled.

**Note:** `search` does not call `_assert_safe_urls()` because it does not fetch arbitrary URLs — it queries the Tavily API with a search string.

### API Key Sanitization (v1.2)

All error messages from `_handle_tavily_error()` strip the Tavily API key before returning to the LLM:

```python
api_key = getattr(cfg, "tavily_api_key", None)
if api_key and len(api_key) > 4:
    escaped_key = re.escape(api_key)
    raw_msg = re.sub(escaped_key, "***", raw_msg)
    raw_msg = re.sub(re.escape(api_key.replace("-", "%2D")), "***", raw_msg)
    raw_msg = re.sub(r"Authorization:\s*Bearer\s+[^\s]+", "Authorization: Bearer ***", raw_msg)
    raw_msg = re.sub(r"[?&]api_key=[^&\s]+", "api_key=***", raw_msg)
raw_msg = raw_msg[:500]  # Truncate to prevent token waste
```

This prevents accidental key leakage into logs, traces, or LLM context windows. v1.2 adds regex, URL-encoded, header, and query param patterns plus 500-char truncation.

---

## ⚠️ Error Handling

`_handle_tavily_error()` maps exceptions to standardized `fail()` responses:

| Condition | Detection | error_code | User Message |
|-----------|-----------|------------|--------------|
| Keyless rate limit | `TavilyKeylessLimitError` | `AUTH_FAILED` | `"Tavily keyless rate limit reached. Set TAVILY_API_KEY..."` |
| Invalid API key | `InvalidAPIKeyError` | `AUTH_FAILED` | `"Tavily API key is invalid. Check TAVILY_API_KEY..."` |
| Monthly quota | `UsageLimitExceededError` | `QUOTA_EXHAUSTED` | `"Tavily monthly quota exhausted. Upgrade..."` |
| Tavily API error (429) | `APIError` with status 429 | `RATE_LIMITED` | `"Tavily rate limit (HTTP 429): ..."` |
| Tavily API error (5xx) | `APIError` with status >= 500 | `SERVER_ERROR` | `"Tavily server error (HTTP {status}): ..."` |
| Tavily API error (other) | `APIError` | `API_ERROR` | `"Tavily API error: ..."` |
| HTTP timeout | `httpx.TimeoutException` | `TIMEOUT` | `"Tavily request timed out: ..."` |
| HTTP connection error | `httpx.ConnectError` | `CONNECT_ERROR` | `"Tavily connection failed: ..."` |
| HTTP 401/403 | `httpx.HTTPStatusError` | `AUTH_FAILED` | `"Tavily authentication failed..."` |
| HTTP other 4xx | `httpx.HTTPStatusError` | `CLIENT_ERROR` | `"Tavily HTTP error (HTTP {status}): ..."` |
| Circuit breaker OPEN | `_TAVILY_CB.can_execute()` | `CB_OPEN` | `"Tavily circuit breaker is OPEN..."` |
| Generic | Any other exception | `UNKNOWN` | `"Tavily error: ..."` |

**Detection strategy:** Uses `isinstance` checks with lazy tavily imports, falling back to `type(e).__name__` string matching. This handles both installed and mocked tavily packages.

**v1.2: Circuit breaker integration:**
- After **5** consecutive failures, the circuit breaker opens and all Tavily calls fail fast with: `"Tavily circuit breaker is OPEN. Service temporarily unavailable. Try again later or use web(search) as fallback."` (error_code: `CB_OPEN`)
- After 60 seconds, the circuit enters HALF_OPEN and allows 1 test call.
- Success → CLOSED; failure → OPEN again.

**v1.2: Retry policy:**
- All retryable errors (HTTP 429, 408, 5xx, timeouts, connection errors, network errors, and registered SDK exceptions) trigger up to 3 retry attempts with exponential backoff via `core/net/retry.py:get_retry_delay()` (2s base, 30s max, 0-25% jitter).
- Non-retryable errors (4xx client errors, auth failures) trip the circuit breaker immediately.

---

## ⚙️ Configuration

```ini
# .env
TAVILY_API_KEY=tvly-...       # Optional — enables full functionality (crawl, map, research)
TAVILY_TIMEOUT=60             # Request timeout in seconds (1-300, default 60)
```

```python
# core/config.py
self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
self.tavily_timeout = int(os.getenv("TAVILY_TIMEOUT", "60"))
```

**Requirements:**
```
tavily-python>=0.7.0,<0.8.0   # Locked to SDK version this refactor is built against
```

**Keyless mode:** When `TAVILY_API_KEY` is empty, `AsyncTavilyClient(api_key=None)` supports `search` and `extract` with lower limits. `crawl`, `map`, and `research` fail with a clear message.

---

## 📤 Output & Pruning

All responses pass through `prune_tool_dict()` from `core.memory_backend.pruner`:
- Large `raw_content` / `text` fields are truncated with artifact recovery
- Full content saved to `workspace/.artifacts/`
- Structured citations always preserved
- `trace_id` is threaded through `ok()` / `fail()` / `prune_tool_dict()` for observability

---

## 🧪 Testing

```powershell
# Run all tavily tests (fully mocked, no API calls)
D:\mcp\agent\venv\Scripts\pytest.exe tests/tools/tavily/ -W error --tb=short -v

# Run all core/net tests
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/net/ -W error --tb=short -v
```

**Test coverage:**

| File | Tests | Coverage |
|------|-------|----------|
| `conftest.py` | — | Shared fixtures: reset_state, mock_cfg, mock_tavily_client |
| `test_search.py` | 8 | Search action, result parsing, keyless capping, trace_id propagation, **raw_content stripping, facade params** |
| `test_extract.py` | 5 | Extract action, URL validation, batch processing, format handling, SSRF |
| `test_crawl.py` | 9 | Crawl action, keyless rejection, URL requirement, extract_depth/format, SDK translation, **facade params, coroutine factory** |
| `test_map.py` | 7 | Map action, keyless rejection, URL requirement, SDK translation, **facade params** |
| `test_tavily_error_handling.py` | 14 | All error types + non-dict handler guard, **sanitization, truncation, error_code** |
| `test_tavily_keyless_mode.py` | 5 | Keyless search/extract, keyless crawl/map rejection, warning once |
| `test_tavily_ssrf.py` | 4 | `_assert_safe_urls` blocking across extract/crawl/map, search exempt |
| `test_tavily_client.py` | 3 | Lazy client creation, key change detection, thread safety |
| `test_tavily_state.py` | 2 | State ownership regression guard (web bug), keyless warning reset |
| `test_facade.py` | 5 | `@meta_tool` metadata, action Literal, unknown action, trace_id |
| `test_registry.py` | 6 | Duplicate guard, research not in DISPATCH, all actions registered |
| `test_bridge_timeout.py` | 2 | Timeout actually fires |
| `test_circuit_breaker.py` | 7 | **v1.2:** State transitions, half_open_max_calls, reset, record_success noop |
| `test_bridge_resilience.py` | 6 | **v1.2:** Coroutine factory, retry, CB integration, unified backoff |
| `test_client.py` | 5 | **v1.2:** Singleton, key change, close logging, old client cleanup |

**Core/net tests (`tests/core/net/`):**

| File | Tests | Coverage |
|------|-------|----------|
| `test_security.py` | 12 | SSRF guard, IPv6, empty hostname, scheme validation |
| `test_web_errors.py` | 12 | Classification, BOT_BLOCKED, 408, SDK duck-typing, retry delay |
| `test_retry.py` | 6 | Success, retry, exhaust, non-retryable, custom predicate, backoff |
| `test_budget.py` | 6 | Record, afford, warning, status, thread safety |
| `test_url.py` | 7 | Normalize, domain extract, same domain |
| `test_path_validation.py` | — | Existing (moved from tests/core/) |
| `test_ssrf_edge_cases.py` | — | Existing (moved from tests/core/) |
| `test_ssrf_protection.py` | — | Existing (moved from tests/core/) |

**Mock strategy:**
- Patch `tools.tavily_ops.client._get_singleton_client` to return `MagicMock` with `side_effect=_async_return(...)` (no `tavily` package installation required for unit tests)
- Patch `tools.tavily_ops.client.cfg.tavily_api_key` to `""` for keyless mode tests
- Patch `tools.tavily_ops.client.cfg.tavily_api_key` to `"tvly-test"` for keyed mode tests
- Patch `core.net.security.is_safe_network_address` for SSRF tests (or mock `_assert_safe_urls` directly)
- Mock `AsyncTavilyClient.search()` / `.extract()` / `.crawl()` / `.map()` / `.research()` to return deterministic responses
- Test `_handle_tavily_error()` with both real and mocked exception types
- Reset state via `tools.tavily_ops.state.reset_state()` (not direct module var poking)
- Reset circuit breaker via `tools.tavily_ops.client._TAVILY_CB.reset()` between tests
- Reset `_KEYLESS_WARNED` via `tools.tavily_ops.client._KEYLESS_WARNED = False` before keyless warning tests

**Current test layout:**
```text
tests/tools/tavily/
├── conftest.py
├── test_search.py
├── test_extract.py
├── test_crawl.py
├── test_map.py
├── test_tavily_error_handling.py
├── test_tavily_keyless_mode.py
├── test_tavily_ssrf.py
├── test_tavily_client.py
├── test_tavily_state.py
├── test_facade.py
├── test_registry.py
├── test_bridge_timeout.py
├── test_circuit_breaker.py
├── test_bridge_resilience.py    # v1.2
└── test_client.py               # v1.2

tests/core/net/                   # v1.2
├── test_security.py
├── test_web_errors.py
├── test_retry.py
├── test_budget.py
├── test_url.py
├── test_path_validation.py
├── test_ssrf_edge_cases.py
└── test_ssrf_protection.py
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick search (free) | `web(search)` | SearXNG, no API costs |
| AI-ranked search | `tavily(search)` | Better relevance, citations, AI answer |
| Domain-scoped search | `tavily(search, include_domains=...)` | **v1.1** — Research precision |
| News/current events | `tavily(search, topic="news")` | **v1.1** — Time-relevant results |
| Single static page (free) | `web(read)` | Fast, lightweight, no API costs |
| Bulk URL extraction | `tavily(extract)` | Optimized batch, AI-powered, up to 10 URLs |
| Site crawling | `tavily(crawl)` | Follows links, discovers pages (API key required) |
| Site structure | `tavily(map)` | Discovers hierarchy without fetching content (API key required) |
| Deep research | `workflows/deep_research.py` | Uses `run_research()` internally (not exposed as tool action) |
| JS-rendered page | `browser(navigate+text_content)` | Renders JavaScript |
| Interactive forms | `browser(click, fill)` | Supports interaction |

---

## 🗺️ Roadmap

### ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 4 exposed actions (`search`, `extract`, `crawl`, `map`) | ✅ v1.0 | `research` is workflow-only |
| Async-to-sync bridge | ✅ v1.0 | `_run_async()` handles nested loops + ThreadPoolExecutor fallback |
| Lazy client with key caching | ✅ v1.0 | `_get_singleton_client()` re-creates only on API key change, thread-safe lock |
| Keyless mode | ✅ v1.0 | `search`/`extract` work without API key; `crawl`/`map`/`research` reject |
| SSRF guard | ✅ v1.0 | `_assert_safe_urls()` on `extract`/`crawl`/`map` |
| Raw content stripping | ✅ v1.0 | `_action_search` strips `raw_content` unless `include_raw_content=True` |
| Comprehensive error handling | ✅ v1.0 | `_handle_tavily_error()` covers 8+ exception types with lazy imports |
| `prune_tool_dict` integration | ✅ v1.0 | All action outputs piped through pruner |
| `PARALLEL_SAFE` | ✅ v1.0 | Pure network I/O, no shared state |
| `max_results` keyless cap | ✅ v1.0 | Silently clamps to 3 in keyless mode |
| URL count validation | ✅ v1.0 | `extract` rejects > 10 URLs |
| `crawl`/`map` url/query fallback | ✅ v1.0 | Accepts either `url` or `query` param |
| `@meta_tool` facade | ✅ v1.0 | Auto-generated Literal + docstring from DISPATCH metadata |
| Un-multiplex to `tavily_ops/` | ✅ v1.0 | Atomic action files with auto-discovery |
| `trace_id` propagation | ✅ v1.0 | Threaded through all handlers |
| SDK 0.7.26 compatibility | ✅ v1.0 | `instructions` translation, `extract_depth`/`format` for crawl |
| State ownership bug guard | ✅ v1.0 | `test_tavily_state.py` regression test |
| Non-dict handler guard | ✅ v1.0 | Facade checks `isinstance(result, dict)` |
| **Bridge timeout actually works** | ✅ **v1.1** | `shutdown(wait=False)` prevents blocking; timeout fires correctly |
| **Circuit breaker + rate-limit retry** | ✅ **v1.1** | `_run_async_with_resilience()` in `bridge.py` |
| **`include_images` passed to SDK** | ✅ **v1.1** | Was silently dropped in `search` |
| **`max_results` validated (1–20)** | ✅ **v1.1** | Fail fast instead of confusing SDK error |
| **`include_domains`/`exclude_domains`** | ✅ **v1.1** | Domain-scoped research |
| **`topic` parameter surfaced** | ✅ **v1.1** | News/current-events filtering |
| **API key sanitization** | ✅ **v1.1** | Key stripped from all error messages |
| **`_assert_safe_urls` in `core/security.py`** | ✅ **v1.1** | Cross-tool shared SSRF guard |
| **`core/web_errors.py` shared module** | ✅ **v1.1** | `classify_http_error()`, `is_retryable_error()` for web + tavily |
| **`_close_client()` actually closes** | ✅ **v1.1** | Properly awaits `client.close()` via bridge |
| **`crawl`/`map` URL strictly required** | ✅ **v1.1** | Removed misleading `url or query` fallback |
| **Coroutine factory pattern** | ✅ **v1.2** | Prevents coroutine reuse crash on retry; `_call` not `_call()` |
| **Shared `core/net/` infrastructure** | ✅ **v1.2** | errors, security, retry, budget, url, default modules |
| **Structured error codes** | ✅ **v1.2** | `error_code` in all `fail()` responses via `core/contracts.py` |
| **API budget tracking** | ✅ **v1.2** | `APICostTracker` with daily limits, warnings, thread safety |
| **Unified retry/backoff** | ✅ **v1.2** | `get_retry_delay()` + `retry_sync()` in `core/net/retry.py` |
| **IPv6 SSRF fixes** | ✅ **v1.2** | Port stripping, empty hostname rejection, scheme validation |
| **Client lifecycle fixes** | ✅ **v1.2** | Lock on close, old client cleanup on key change, `api_key or None` |
| **Error message truncation** | ✅ **v1.2** | 500 char cap to prevent context window bloat |
| **API key sanitization v2** | ✅ **v1.2** | Regex, URL-encoded, header, and query param patterns |
| **BOT_BLOCKED classification** | ✅ **v1.2** | Cloudflare/cf-ray detection in `core/net/errors.py` |
| **Default constants** | ✅ **v1.2** | `core/net/default.py` — shared across tavily, web_ops, browser |

### 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Wire `run_research()` into `workflows/deep_research_impl/nodes/search.py` | Trigger: "when iteration > 3 and completeness < 50" as accelerator | P1 |
| Adopt `core/net/` in `web_ops` | Use `core/net/errors.py`, `core/net/security.py`, `core/net/retry.py` in `web_ops/actions/scrape.py` and `search.py` | P1 |
| Adopt `core/net/` in `browser` tool | Use `classify_http_error()` for Playwright errors; `get_retry_delay()` for nav retries | P1 |
| `tavily(search)` → `web(search)` fallback chain | Automatic fallback when CB open / no key / rate limited, using `error_code` | P2 |
| `tavily(search)` as primary search in research workflow | Replace `web(search)` with `tavily(search)` in `workflows/research.py` when API key present | P2 |
| Add `@cached` decorator | LRU cache for search/extract results (TTL 300s/1800s) | P2 |
| URL normalization module | `core/net/url.py` — strip slashes, sort params, lowercase domain | P2 |
| Remove backward-compat wrappers | Delete `core/security.py` and `core/web_errors.py` re-exports once web_ops/browser migrate | P3 |
| Search result deduplication | Similar to `web(search_and_read)`, deduplicate identical URLs across Tavily result pages | P3 |
| Response caching | Cache Tavily responses (TTL-based) to avoid redundant API calls | P3 |
| Client-side batching for `extract` | Split >10 URLs into batches of 10, execute concurrently, merge results | P2 |
| Persistent event loop in `bridge.py` | Background thread with dedicated loop to save ~1ms per call | P3 |
| Surface `include_images`/`include_image_descriptions` in `search` | SDK supports it; facade needs param | P2 |
| Surface `search_depth`/`topic`/`time_range` validation | Client-side enum validation instead of SDK error | P2 |
| Tavily as `web` tool fallback | When SearXNG fails, fall back to `tavily(search)` | P3 |
| Composite `deep_research` action | Search + extract + LLM synthesis in one call | P3 |

### 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Expose `research` as tool action** | `run_research()` is intentionally workflow-only. Exposing it as a tool action would bypass the research workflow's planning, routing, and memory integration. | Skip |
| 2 | **Streaming responses** | MCP stdio transport doesn't support streaming. Would require gateway-only mode. | Skip |
| 3 | **Synchronous client** | `AsyncTavilyClient` is the only official client. A sync wrapper would be redundant given `_run_async()`. | Skip |
| 4 | **Custom HTTP adapter** | `httpx` handles retries and connection pooling well. No need for a custom adapter. | Skip |
| 5 | **Result pagination** | Tavily API returns all results in one call. No pagination API exists. | Skip |
| 6 | **Configurable keyless `max_results`** | Hardcoded cap of 3 is Tavily API-imposed, not arbitrary. Making it configurable invites users to hit rate limits. | Skip |

---

## 🛡️ AI Agent Instructions

### NEVER DO
1. **Never expose `run_research()` as a tool action** — it is workflow-only by design.
2. **Never bypass `_assert_safe_urls()`** — SSRF protection must run before every URL-touching action.
3. **Never remove the keyless check from `crawl`/`map`** — these require an API key. Keyless mode is search/extract only.
4. **Never hardcode timeout values** — Always use `cfg.tavily_timeout`. The `.env` is the single source of truth.
5. **Never skip `_handle_tavily_error()`** — Always route exceptions through the centralized handler for consistent error messages.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never skip `compileall` before `pytest`** — catches syntax errors early.
11. **Never use `from tools.tavily_ops.state import _TAVILY_CLIENT`** — use `import tools.tavily_ops.state as state` and `state._TAVILY_CLIENT` directly. Prevents name-binding divergence bug.
12. **Never call `asyncio.run()` directly from action handlers** — Always use `_run_async()` or `_run_async_with_resilience()` from `bridge.py`.
13. **Never leak the API key in error messages** — `_handle_tavily_error()` sanitizes automatically; don't bypass it.
14. **Never pass `_call()` to `_run_async_with_resilience()`** — Always pass `_call` (the factory). Passing `_call()` creates a single coroutine that cannot be reused on retry.
15. **Never hardcode backoff math** — Use `core/net/retry.py:get_retry_delay()` for all retry timing.
16. **Never skip `error_code` in `fail()` calls** — Every error response must include a structured `error_code` for programmatic consumers.

### ALWAYS DO
17. **Always pass `trace_id` to `ok()` and `fail()`** — Threaded from facade through all action handlers.
18. **Always use `_run_async_with_resilience()` for Tavily client calls** — Handles circuit breaker, rate-limit retry, and nested event loops.
19. **Always strip `raw_content` by default** — `_action_search` must pop `raw_content` from results unless `include_raw_content=True`.
20. **Always test keyless and keyed modes** — Patch `cfg.tavily_api_key` to `""` and `"tvly-test"` respectively.
21. **Always test error paths with both real and mocked exceptions** — `_handle_tavily_error()` uses both `isinstance` and name matching.
22. **Always update this doc** when adding actions, changing return shapes, or modifying the client lifecycle.
23. **Always add the non-dict handler return fallback** in the facade — `if not isinstance(result, dict): return fail(...)`.
24. **Always reset the circuit breaker between tests** — `tools.tavily_ops.client._TAVILY_CB.reset()` must be in a known state.
25. **Always use `core/net/` imports** — `core.net.security`, `core.net.errors`, `core.net.retry`, `core.net.budget`. Not the backward-compat wrappers.
26. **Always register SDK exceptions** — If a tool wraps a new SDK, call `register_retryable_exception()` for its retryable exception types.
27. **Always record paid API calls** — After every successful Tavily call, call `record_tool_call("tavily.search")` (or appropriate tool name).

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/tavily.py` | `@tool` + `@meta_tool` facade: action dispatch, validation |
| `tools/tavily_ops/__init__.py` | Auto-discovery: glob actions/*.py, importlib import |
| `tools/tavily_ops/_registry.py` | `DISPATCH` dict + `@register_action` decorator with duplicate guard |
| `tools/tavily_ops/state.py` | `_TAVILY_CLIENT`, `_CLIENT_LOCK`, `_KEYLESS_WARNED`, `reset_state()` |
| `tools/tavily_ops/client.py` | `_get_singleton_client()`, `_close_client()`, `_TAVILY_CB`, `_is_keyless()`, `_warn_keyless_once()` |
| `tools/tavily_ops/bridge.py` | `_run_async()`, `_run_async_with_resilience()` — async-to-sync bridge with CB + retry |
| `tools/tavily_ops/errors.py` | `_handle_tavily_error()`, API key sanitization, `error_code` classification |
| `tools/tavily_ops/actions/search.py` | `@register_action("tavily", "search")` handler |
| `tools/tavily_ops/actions/extract.py` | `@register_action("tavily", "extract")` handler |
| `tools/tavily_ops/actions/crawl.py` | `@register_action("tavily", "crawl")` handler |
| `tools/tavily_ops/actions/map.py` | `@register_action("tavily", "map")` handler |
| `tools/tavily_ops/actions/research.py` | `run_research()` — workflow-only, NOT registered |
| `core/net/security.py` | `is_safe_network_address()`, `_assert_safe_urls()` — cross-tool SSRF protection |
| `core/net/errors.py` | `classify_http_error()`, `is_retryable_error()`, `get_retry_delay()`, `register_retryable_exception()` — shared HTTP error classification |
| `core/net/retry.py` | `retry_sync()` — unified retry with exponential backoff |
| `core/net/budget.py` | `APICostTracker`, `record_tool_call()`, `check_budget()` — cost tracking |
| `core/net/url.py` | `normalize_url()`, `extract_domain()`, `is_same_domain()` — URL utilities |
| `core/net/default.py` | `SEARCH_MAX_RESULTS`, `CRAWL_MAX_DEPTH`, `RETRY_BASE_DELAY`, `CB_FAILURE_THRESHOLD` — shared defaults |
| `core/security.py` | BACKWARD COMPAT — re-exports from `core.net.security` (remove after migration) |
| `core/web_errors.py` | BACKWARD COMPAT — re-exports from `core.net.errors` (remove after migration) |
| `core/contracts.py` | `ok()` / `fail()` — standardized return dicts with `trace_id` + `error_code` injection |
| `core/config.py` | `cfg.tavily_api_key`, `cfg.tavily_timeout` |
| `core/memory_backend/pruner.py` | `prune_tool_dict()` — head+tail truncation, artifact storage |
| `core/llm_backend/circuit_breaker.py` | `CircuitBreaker` class — thread-safe state machine |
| `tests/tools/tavily/conftest.py` | Shared fixtures |
| `tests/tools/tavily/test_search.py` | Search action tests |
| `tests/tools/tavily/test_extract.py` | Extract action tests |
| `tests/tools/tavily/test_crawl.py` | Crawl action tests |
| `tests/tools/tavily/test_map.py` | Map action tests |
| `tests/tools/tavily/test_tavily_error_handling.py` | Error handler tests |
| `tests/tools/tavily/test_tavily_keyless_mode.py` | Keyless mode tests |
| `tests/tools/tavily/test_tavily_ssrf.py` | SSRF guard tests |
| `tests/tools/tavily/test_tavily_client.py` | Client lifecycle tests |
| `tests/tools/tavily/test_tavily_state.py` | State ownership regression guard |
| `tests/tools/tavily/test_facade.py` | `@meta_tool` facade tests |
| `tests/tools/tavily/test_registry.py` | `DISPATCH` auto-discovery + duplicate guard |
| `tests/tools/tavily/test_bridge_timeout.py` | Timeout regression tests |
| `tests/tools/tavily/test_circuit_breaker.py` | Circuit breaker state tests |
| `tests/tools/tavily/test_bridge_resilience.py` | **v1.2** — Coroutine factory + retry integration tests |
| `tests/tools/tavily/test_client.py` | **v1.2** — Client lifecycle, key change, close logging tests |
| `tests/core/net/test_security.py` | **v1.2** — SSRF guard tests (moved from `tests/core/`) |
| `tests/core/net/test_web_errors.py` | **v1.2** — Error classification tests (moved from `tests/core/`) |
| `tests/core/net/test_retry.py` | **v1.2** — Retry/backoff tests |
| `tests/core/net/test_budget.py` | **v1.2** — Budget tracking tests |
| `tests/core/net/test_url.py` | **v1.2** — URL normalization tests |
| `workflows/deep_research_impl/nodes/search.py` | Uses `tavily(action="search")` facade |

---

*Architecture: thin @tool + @meta_tool facade + @register_action auto-discovery + lazy AsyncTavilyClient with key caching + double-checked locking + async-to-sync bridge with circuit breaker + rate-limit retry + SSRF guard + comprehensive error handler with API key sanitization + prune_tool_dict truncation + keyless mode with warning + trace_id propagation + non-dict handler guard + coroutine factory pattern + structured error codes + unified network infrastructure + budget tracking.*
