# TAVILY

## Overview

The `tavily()` tool provides **AI-optimized web search and content extraction** via the [Tavily API](https://tavily.com). It complements the existing `web` tool with superior ranking, automatic citations, and bulk extraction capabilities.

**Key characteristics:**
- **AI-ranked results** — Tavily's relevance engine outperforms raw SearXNG for research queries
- **Automatic citations** — Every result includes URL, title, and confidence score
- **Bulk extraction** — `extract` action can process up to 10 URLs in one call
- **Keyless mode** — Works without API key for `search` and `extract` (rate-limited)
- **PARALLEL_SAFE** — Pure network I/O, no shared state

---

## Architecture

```
tools/tavily.py
├── tavily(action, ...)            # @tool facade — sync, action-dispatch
├── _do_search(...)               # AsyncTavilyClient.search()
├── _do_extract(...)              # AsyncTavilyClient.extract()
├── _do_crawl(...)                # AsyncTavilyClient.crawl() (API key required)
├── _do_map(...)                  # AsyncTavilyClient.map() (API key required)
├── _do_research(...)             # AsyncTavilyClient.research() (workflow-only)
├── _get_client()                 # Lazy AsyncTavilyClient (keyless or keyed)
├── _assert_safe_urls(...)        # SSRF guard via core/security.py
├── _handle_tavily_error(...)     # Exception → standardized fail()
└── _run_async(...)               # Async-to-sync bridge for MCP compatibility
```

---

## Tool Signature

```python
@tool
def tavily(
    action: str,                       # "search" | "extract" | "crawl" | "map"
    query: str = "",                   # search query (search, crawl, map)
    urls: Optional[list[str]] = None,  # URL list (extract)
    url: str = "",                     # single URL (crawl, map)
    max_results: int = 5,              # search results (1-10, capped at 3 keyless)
    search_depth: str = "basic",       # "basic" | "advanced"
    include_answer: bool = True,        # include AI-generated answer
    include_raw_content: bool = False,  # include full page text
    extract_depth: str = "basic",       # "basic" | "advanced"
    format: str = "markdown",           # "markdown" | "text"
    max_depth: int = 2,                # crawl/map link depth (1-3)
    max_breadth: int = 10,             # crawl/map pages per level
    limit: int = 100,                   # crawl/map total pages
    trace_id: str = "",                # trace identifier
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** `search` \| `extract` \| `crawl` \| `map` |
| `query` | `str` | `""` | Search query |
| `urls` | `list[str]` | `None` | URLs for `extract` (max 10) |
| `url` | `str` | `""` | Starting URL for `crawl` / `map` |
| `max_results` | `int` | `5` | Results per search (1–10; **3 in keyless**) |
| `search_depth` | `str` | `"basic"` | `"basic"` or `"advanced"` |
| `include_answer` | `bool` | `True` | Include AI-generated answer in search |
| `include_raw_content` | `bool` | `False` | Include full page text (large!) |
| `extract_depth` | `str` | `"basic"` | `"basic"` or `"advanced"` |
| `format` | `str` | `"markdown"` | Output format for extract |
| `max_depth` | `int` | `2` | Max link depth for crawl/map (1–3) |
| `max_breadth` | `int` | `10` | Max pages per level |
| `limit` | `int` | `100` | Max total pages for crawl/map |
| `trace_id` | `str` | `""` | Trace identifier |

---

## Actions

### `search` — AI-ranked web search

Returns AI-ranked results with titles, URLs, snippets, and an optional AI-generated answer.

**Keyless behavior:**
- `max_results` is silently capped to `3`
- Response includes `"keyless": true`
- Lower rate limits apply (~100 requests/day)

**Return:**
```json
{
  "status": "success",
  "data": {
    "results": [
      {"title": "...", "url": "https://...", "content": "...", "score": 0.95}
    ],
    "answer": "AI-generated summary...",
    "query": "...",
    "keyless": false
  }
}
```

**raw_content handling:**
- Stripped by default (prevents context window explosion)
- Included only if `include_raw_content=True`

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

### `crawl` — Deep site traversal

Follows links from a starting URL up to `max_depth` levels. **Requires API key.**

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

### `map` — Site structure discovery

Discovers site hierarchy without fetching full content. **Requires API key.**

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

---

## Security

### SSRF Guard

All URL parameters (`url`, `urls`) pass through `_assert_safe_urls()`:

```python
def _assert_safe_urls(urls: list[str]) -> Optional[str]:
    for url in urls:
        hostname = urlparse(url).hostname or ""
        if not is_safe_network_address(hostname):
            return f"Blocked: {url} resolves to a private/internal address"
```

Uses `core.security.is_safe_network_address` — same guard as `web.py`.

---

## Error Handling

| Exception | HTTP | Action | User Message |
|-----------|------|--------|--------------|
| `TavilyKeylessLimitError` | — | `fail()` | "Keyless rate limit reached. Set TAVILY_API_KEY." |
| `InvalidAPIKeyError` | 401 | `fail()` | "API key invalid. Check TAVILY_API_KEY." |
| `UsageLimitExceededError` | — | `fail()` | "Monthly quota exhausted." |
| `TavilyAPIError` (429) | 429 | `fail()` | "Rate limit exceeded. Retry failed." |
| `httpx.TimeoutException` | — | `fail()` | "Request timed out after {timeout}s." |
| `httpx.ConnectError` | — | `fail()` | "Failed to connect to Tavily API." |

---

## Configuration

```ini
# .env
TAVILY_API_KEY=tvly-...          # Optional — enables full functionality
TAVILY_TIMEOUT=60                # Request timeout (1-300 seconds)
```

```python
# core/config.py
self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
self.tavily_timeout = int(os.getenv("TAVILY_TIMEOUT", "60"))
```

---

## Output & Pruning

All responses pass through `prune_tool_dict()` from `core.memory_backend.pruner`:
- Large `raw_content` fields are truncated with artifact recovery
- Full reports saved to `workspace/.artifacts/`
- Structured citations always preserved

---

## Keyless Mode

```python
# No API key configured
cfg.tavily_api_key = ""

# Client initializes in keyless mode
client = AsyncTavilyClient(api_key=None)

# Supported actions: search, extract
# Unsupported: crawl, map, research (fail with clear message)
```

---

## Testing

```powershell
# Run tavily tests (fully mocked, no API calls)
python -m pytest tests/tools/tavily/ -v

# Integration smoke test (requires real API key)
python -m pytest tests/tools/tavily/ -m integration -v
```

**Mock strategy:**
- Patch `tools.tavily._get_client` to return `AsyncMock`
- No `tavily` package installation required for unit tests
- Test keyless mode by mocking `cfg.tavily_api_key = ""`

---

## When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick search | `web(search)` | Free, SearXNG, no API costs |
| AI-ranked search | `tavily(search)` | Better relevance, citations, AI answer |
| Single static page | `web(read)` | Fast, lightweight |
| Bulk URL extraction | `tavily(extract)` | Optimized batch, AI-powered |
| Site crawling | `tavily(crawl)` | Follows links, discovers pages |
| Site structure | `tavily(map)` | Discovers hierarchy |
| JS-rendered page | `browser(navigate+text_content)` | Renders JavaScript |
| Interactive forms | `browser(click, fill)` | Supports interaction |

---

## Future Roadmap

- **Phase 1 (Current):** `search` + `extract` exposed to LLM; `crawl` + `map` require API key
- **Phase 2 (Next):** Integrate `tavily(search)` as primary search in `workflows/research.py`
- **Phase 3 (Future):** Expose `_do_research()` via `workflows/deep_research.py` node (not as tool action)
- **Phase 4 (Future):** Add `tavily(search)` → `browser` fallback chain for JS-heavy results
