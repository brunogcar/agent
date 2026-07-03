
← Back to [Tavily Overview](../TAVILY.md)

# 📝 API Reference

## Tool Signature

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
    max_depth: int = 3,           # v1.2: restored, default 3
    max_breadth: int = 10,        # v1.2: restored
    limit: int = 50,              # v1.2: restored, default 50
    trace_id: str = "",
) -> dict:
    """Tavily AI research tool -- atomic actions for search/extract/crawl/map."""
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | One of `search`, `extract`, `crawl`, `map` (auto-generated Literal by @meta_tool) |
| `query` | `str` | No | Search query. **Required** for `search`. Also accepted by `crawl`/`map` as contextual `instructions`. |
| `urls` | `list[str]` | No | URLs for `extract`. **Required** for `extract`. Max 10 items. |
| `url` | `str` | No | Starting URL for `crawl`/`map`. **Required** for `crawl`/`map`. |
| `max_results` | `int` | No | Results per search. Default: 5. Range: 1-20. **Capped at 3 in keyless mode.** |
| `search_depth` | `str` | No | `"basic"` or `"advanced"`. Default: `"basic"`. |
| `topic` | `str` | No | Topic filter for search: `"general"`, `"news"`, `"finance"`. Default: `"general"`. **v1.1** |
| `time_range` | `str` | No | Time range filter for search. |
| `include_domains` | `list[str]` | No | Whitelist domains for search. **v1.1**. **v1.3: validated as `list[str]`.** |
| `exclude_domains` | `list[str]` | No | Blacklist domains for search. **v1.1**. **v1.3: validated as `list[str]`.** |
| `include_answer` | `bool` | No | Include AI-generated answer in search. Default: `True`. |
| `include_raw_content` | `bool` | No | Include full page text in search results. Default: `False`. **Large!** |
| `include_images` | `bool` | No | Include images in search results. Default: `False`. **v1.1: Now passed to SDK.** |
| `extract_depth` | `str` | No | `"basic"` or `"advanced"`. Default: `"basic"`. Now also supported by `crawl`. |
| `format` | `str` | No | Output format for extract/crawl. `"markdown"` or `"text"`. Default: `"markdown"`. |
| `max_depth` | `int` | No | Max link depth for crawl/map. Default: **3**. **v1.2: restored.** |
| `max_breadth` | `int` | No | Max pages per level for crawl/map. Default: **10**. **v1.2: restored.** |
| `limit` | `int` | No | Max total pages for crawl/map. Default: **50**. **v1.2: restored.** |
| `trace_id` | `str` | No | Trace identifier for logging and result correlation. Threaded through all handlers. |

> **Note:** `input`, `model`, `citation_format`, `max_chars` params were removed from the facade. `citation_format` only existed for `research`, which is not exposed as a tool action. Call `run_research()` directly from workflows.

---

## ⚡ Actions

### `search` -- AI-ranked web search

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
- `max_results` validated to 1-20 range (fail fast on invalid values)

**v1.2 additions:**
- `raw_content` stripped from results when `include_raw_content=False` (restored v1.0 behavior)
- Facade accepts `max_depth`, `max_breadth`, `limit` again (was removed in v1.1)

**v1.3 additions:**
- `include_domains`/`exclude_domains` validated as `list[str]` -- rejected with `INVALID_PARAMS` if not
- `check_budget("tavily.search")` guard before execution
- `record_tool_call("tavily.search")` after success
- `SEARCH_MAX_RESULTS` imported from `core.net.default`

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
- Missing `query` -> `fail("action='search' requires query=")`
- `max_results` < 1 or > 20 -> `fail("max_results must be >= 1")` / `fail("max_results must be <= 20")`
- Keyless rate limit -> `fail("Tavily keyless rate limit reached...")` with `error_code="AUTH_FAILED"`
- Invalid API key -> `fail("Tavily API key is invalid...")` with `error_code="AUTH_FAILED"`
- Timeout -> `fail("Tavily request timed out...")` with `error_code="TIMEOUT"`
- Connection error -> `fail("Tavily connection failed...")` with `error_code="CONNECT_ERROR"`
- **v1.3:** Network error -> `fail("Tavily network error...")` with `error_code="NETWORK_ERROR"`
- **v1.4:** Read/Write/Protocol error -> `fail("Tavily read/write/protocol error...")` with `error_code="NETWORK_ERROR"`
- Circuit breaker OPEN -> `fail("Tavily circuit breaker is OPEN...")` with `error_code="CB_OPEN"`
- **v1.3:** Budget exhausted -> `fail("Tavily budget exhausted...")` with `error_code="QUOTA_EXHAUSTED"`

---

### `extract` -- Bulk URL content extraction

Accepts up to 10 URLs and returns extracted content with citations for each.

**v1.3 additions:**
- Now uses `_run_async_with_resilience()` (was bypassing all resilience in v1.2)
- URLs normalized via `normalize_url()` before extraction
- `EXTRACT_MAX_URLS`/`EXTRACT_DEPTH` imported from `core.net.default`
- Budget tracking wired

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
- Missing `urls` -> `fail("urls is required for extract action")`
- More than 10 URLs -> `fail("urls cannot exceed 10 items")`
- Unsafe URLs -> `fail("Blocked: {url} resolves to a private/internal address")`

---

### `crawl` -- Deep site traversal

Follows links from a starting URL up to `max_depth` levels. **Requires API key.**

**SDK note:** Tavily SDK 0.7.26 uses `instructions=` internally. The facade keeps `query` as the parameter name for backward compatibility but translates it automatically: `client.crawl(url=..., instructions=query, ...)`.

**v1.1 breaking change:** `url` is now **strictly required**. The old `url or query` fallback (where `query` would be used as the target URL) has been removed because it produced misleading SSRF errors when users passed search strings instead of URLs.

**v1.2:** Facade accepts `max_depth`, `max_breadth`, `limit` again.

**v1.3 additions:**
- URL normalized via `normalize_url()` before crawl
- `CRAWL_*` constants imported from `core.net.default`
- Budget tracking wired

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
- Missing `url` -> `fail("action='crawl' requires url=")`
- Keyless mode -> `fail("action='crawl' requires a Tavily API key...")`
- Unsafe URL -> `fail("Blocked: {url} resolves to a private/internal address")`

---

### `map` -- Site structure discovery

Discovers site hierarchy without fetching full content. **Requires API key.**

**SDK note:** Same `instructions=` translation as `crawl`.

**v1.1 breaking change:** Same as `crawl` -- `url` is strictly required, `query` is only for contextual instructions.

**v1.2:** Facade accepts `max_depth`, `max_breadth`, `limit` again.

**v1.3 additions:**
- `CRAWL_*` constants imported from `core.net.default`
- Budget tracking wired

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

---

### `research` -- End-to-end deep research (workflow-only)

**NOT exposed as a tool action.** Call directly from workflows:

```python
from tools.tavily_ops.actions.research import run_research

result = run_research(
    input="Research topic",
    model=None,
    citation_format="apa",    # "numbered" | "mla" | "apa" | "chicago"
    trace_id="...",
)
```

Requires API key. Validates `citation_format` against SDK Literal type (`"numbered" | "mla" | "apa" | "chicago"`).

**v1.3 additions:**
- Now uses `_run_async_with_resilience()` (was bypassing all resilience in v1.2)
- Budget tracking wired
- `citation_format` is **only** passed to `research` action (not leaked to others)

---

## 🔒 Security

### SSRF Guard (`_assert_safe_urls`)

All URL parameters (`url`, `urls`) pass through `_assert_safe_urls()` inside the action handlers:

```python
def _assert_safe_urls(urls: list[str]) -> tuple[bool, str]:
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Blocked: {url} -- only http/https schemes allowed"
        if not parsed.hostname:
            return False, f"Blocked: {url} -- no valid hostname"
        if not is_safe_network_address(parsed.hostname):
            return False, f"Blocked: {url} -- resolves to private/internal address"
    return True, ""
```

Uses `core.net.security.is_safe_network_address` -- same guard as `web.py`. v1.2: `_assert_safe_urls` moved to `core/net/security.py` with scheme validation, empty hostname rejection, and IPv6 port stripping. v1.3: Fixed IPv6 bracket parsing (`[::1]:8080`, `2001:db8::1`). v1.4: Blocks `0.0.0.0` and `::` via `is_unspecified` check.

**Note:** `search` does not call `_assert_safe_urls()` because it does not fetch arbitrary URLs -- it queries the Tavily API with a search string.

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
raw_msg = raw_msg[:500]   # Truncate to prevent token waste
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
| **v1.4: HTTP read error** | **`httpx.ReadError`** | **`NETWORK_ERROR`** | **`"Tavily read error: ..."`** |
| **v1.4: HTTP write error** | **`httpx.WriteError`** | **`NETWORK_ERROR`** | **`"Tavily write error: ..."`** |
| **v1.4: HTTP protocol error** | **`httpx.RemoteProtocolError`** | **`NETWORK_ERROR`** | **`"Tavily protocol error: ..."`** |
| **v1.4: HTTP network error** | **`httpx.NetworkError`** | **`NETWORK_ERROR`** | **`"Tavily network error: ..."`** |
| HTTP 401/403 | `httpx.HTTPStatusError` | `AUTH_FAILED` | `"Tavily authentication failed..."` |
| HTTP 408 | `httpx.HTTPStatusError` status 408 | `RATE_LIMITED` | `"Tavily rate limit (HTTP 408): ..."` |
| HTTP other 4xx | `httpx.HTTPStatusError` | `CLIENT_ERROR` | `"Tavily HTTP error (HTTP {status}): ..."` |
| Circuit breaker OPEN | `_TAVILY_CB.can_execute()` | `CB_OPEN` | `"Tavily circuit breaker is OPEN..."` |
| Generic | Any other exception | `UNKNOWN` | `"Tavily error: ..."` |

**Detection strategy:** Uses `isinstance` checks with lazy tavily imports, falling back to `type(e).__name__` string matching. This handles both installed and mocked tavily packages.

**v1.2: Circuit breaker integration:**
- After **5** consecutive failures, the circuit breaker opens and all Tavily calls fail fast with: `"Tavily circuit breaker is OPEN. Service temporarily unavailable. Try again later or use web(search) as fallback."` (error_code: `CB_OPEN`)
- After 60 seconds, the circuit enters HALF_OPEN and allows 1 test call.
- Success -> CLOSED; failure -> OPEN again.
- **v1.3 FIX: OPEN->HALF_OPEN transition now counts against `half_open_max_calls` (was allowing 1 extra call).**

**v1.2: Retry policy:**
- All retryable errors (HTTP 429, 408, 5xx, timeouts, connection errors, network errors, and registered SDK exceptions) trigger up to 3 retry attempts with exponential backoff via `core/net/retry.py:get_retry_delay()` (2s base, 30s max, 0-25% jitter).
- Non-retryable errors (4xx client errors, auth failures) do NOT trip the circuit breaker.
- **v1.4 CRITICAL:** `retry_async_factory()` only calls `on_failure()` for retryable errors. A validation bug or 400 Bad Request from Tavily raises immediately without touching the CB.

**v1.3: Budget tracking integration:**
- Each action calls `check_budget("tavily.{action}")` before execution.
- On budget exhaustion: returns `QUOTA_EXHAUSTED` error immediately.
- Each action calls `record_tool_call("tavily.{action}")` after success.
- Daily limit auto-resets at midnight (date change detection in `record_call()`).

---

## 📤 Output & Pruning

All responses pass through `prune_tool_dict()` from `core.memory_backend.pruner`:
- Large `raw_content` / `text` fields are truncated with artifact recovery
- Full content saved to `workspace/.artifacts/`
- Structured citations always preserved
- `trace_id` is threaded through `ok()` / `fail()` / `prune_tool_dict()` for observability

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
