# WEB

## Overview

The `web()` tool provides web search and content extraction via **SearXNG** (self-hosted metasearch) and **BeautifulSoup4** (HTML parsing). It is the agent's primary tool for discovering URLs and reading static HTML pages.

**Key characteristics:**
- **Free / self-hosted** — requires only a running SearXNG instance (no API keys)
- **Static HTML only** — JavaScript-rendered pages may return empty/short text
- **Parallel** — `search_and_read` uses `ThreadPoolExecutor` for concurrent scraping
- **Lightweight** — pure Python (httpx + BS4), no browser overhead

---

## Architecture

```
tools/web.py
├── web(action, ...)               # @tool facade — sync, action-dispatch
├── _do_search(...)              # SearXNG query via httpx
├── _do_read(...)                # Fetch + BS4 clean
├── _do_scrape(...)              # Structured scrape with metadata
├── _do_search_and_read(...)     # Parallel search + scrape + LLM summarize
├── _fetch_html(...)             # httpx GET with SSRF guard
├── _is_safe_url(...)            # SSRF: blocks private IPs
└── _clean_html(...)             # BS4 extraction → title + text
```

---

## Tool Signature

```python
@tool
def web(
    action: str,                       # "search" | "read" | "scrape" | "search_and_read"
    query: str = "",                   # search query
    url: str = "",                     # target URL for read/scrape
    trace_id: str = "",                # trace identifier
    max_results: int = 10,              # search results cap (1-50)
    max_chars: int = 8000,             # per-page text cap
    include_raw: bool = False,          # include raw HTML in output
    summarize: bool = True,             # LLM summarize in search_and_read
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** One of `search`, `read`, `scrape`, `search_and_read` |
| `query` | `str` | `""` | Search query (required for `search`, `search_and_read`) |
| `url` | `str` | `""` | Target URL (required for `read`, `scrape`) |
| `trace_id` | `str` | `""` | Trace identifier for logging/artifacts |
| `max_results` | `int` | `10` | Max search results (1–50) |
| `max_chars` | `int` | `8000` | Max characters per scraped page |
| `include_raw` | `bool` | `False` | Include raw HTML in response |
| `summarize` | `bool` | `True` | Run LLM summarization in `search_and_read` |

---

## Actions

### `search` — Find URLs via SearXNG

Queries the configured SearXNG instance and returns ranked results with titles, URLs, and snippets.

**Config:**
```
SEARXNG_URL=http://localhost:8080
WEB_MAX_SEARCH_RESULTS=10
WEB_SNIPPET_CHARS=300
```

**Return:**
```json
{
  "status": "success",
  "data": {
    "results": [
      {"title": "...", "url": "https://...", "snippet": "...", "score": 1.0}
    ],
    "query": "...",
    "total": 5
  }
}
```

### `read` — Read a single static page

Fetches HTML via httpx, parses with BeautifulSoup4, and returns clean text + metadata.

**Return:**
```json
{
  "status": "success",
  "data": {
    "url": "https://...",
    "title": "Page Title",
    "text": "Clean extracted text...",
    "word_count": 1500
  }
}
```

**JS limitation:** If the page requires JavaScript (React, Angular, etc.), `text` may be empty or very short (`< 300 chars`). Use `browser` tool as fallback.

### `scrape` — Structured extraction

Same as `read` but returns additional metadata: headers, links, images, and optional raw HTML.

**Return:**
```json
{
  "status": "success",
  "data": {
    "url": "...",
    "title": "...",
    "text": "...",
    "headers": ["H1", "H2"],
    "links": ["https://..."],
    "images": ["https://..."],
    "raw_html": "..."  // only if include_raw=True
  }
}
```

### `search_and_read` — Parallel search + scrape + summarize

**Most powerful action.** Runs `search`, then fans out to `read` each result in parallel via `ThreadPoolExecutor`, then optionally runs an LLM summarization per page.

**Flow:**
```
search(query) → [url1, url2, url3]
  ├─ ThreadPoolExecutor(max_workers=cfg.max_concurrent_workers)
  │   ├─ Worker 1: read(url1) → summarize(LLM) → result1
  │   ├─ Worker 2: read(url2) → summarize(LLM) → result2
  │   └─ Worker 3: read(url3) → summarize(LLM) → result3
  └─ Merge + return
```

**Return:**
```json
{
  "status": "success",
  "data": {
    "query": "...",
    "pages": [
      {"url": "...", "title": "...", "summary": "LLM summary...", "text": "..."}
    ]
  }
}
```

---

## Security

### SSRF Guard (`_is_safe_url`)

All URL parameters pass through `_is_safe_url()` before any HTTP request:

```python
def _is_safe_url(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return is_safe_network_address(hostname)  # from core/security.py
```

**Blocks:**
- Private IP ranges (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`)
- Loopback (`127.0.0.1`, `localhost`)
- Link-local (`169.254.x.x`)
- IPv6 loopback (`::1`)

### HTTP Client

Uses `httpx.Client` with:
- `follow_redirects=True` (up to 10 hops)
- `timeout=30s`
- `headers` with realistic User-Agent

---

## Output & Pruning

All actions return `ok()/fail()` dicts from `core/contracts.py`.

Large outputs (`text > max_chars`) are piped through `prune_tool_dict()` from `core.memory_backend.pruner`:
- Head + tail truncation with `[TRUNCATED: ...]` marker
- Full content saved to `workspace/.artifacts/`
- Recovery hint included in response

---

## Testing

```powershell
# Run web tool tests
python -m pytest tests/tools/web/ -v

# Run with full output
python -m pytest tests/tools/web/test_web.py -v -s
```

**Test patterns:**
- Mock `httpx.Client` at module level
- Mock `cfg` with explicit integers (no MagicMock comparison errors)
- Test SSRF blocking with `192.168.1.1`
- Test timeout and connection error handling
- Test action dispatch (`search`, `read`, `scrape`, `search_and_read`)

---

## When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick search | `web(search)` | Free, SearXNG, no API costs |
| Static page text | `web(read)` | Fast, lightweight, no overhead |
| Bulk scrape + summarize | `web(search_and_read)` | Parallel, automated LLM summaries |
| AI-ranked search | `tavily(search)` | Better relevance, citations, AI answer |
| JS-rendered page | `browser(navigate+text_content)` | Renders JavaScript |
| Bulk URL extraction | `tavily(extract)` | Optimized batch extraction |

---

## Future Roadmap

- **Phase 1 (Current):** `web` as primary free-tier tool
- **Phase 2 (Next):** Add browser fallback detection in `search_and_read` — when `web(read)` returns `< 300` chars, retry with `browser`
- **Phase 3 (Future):** Deprecate `search_and_read` in favor of `tavily(research)` for deep research workflows
- **Phase 4 (Future):** Add `web(cached_read)` — read from local cache before fetching
