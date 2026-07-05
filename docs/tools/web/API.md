<- Back to [Web Overview](../WEB.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(DISPATCH["web"], doc_sections=[...])
def web(
    action: str,       # Literal["search", "scrape", "read", "search_and_read"]
    query: str = "",
    url: str = "",
    max_results: int = 5,
    max_chars: Optional[int] = None,  # None = use cfg.web_max_text_chars (resolved in handlers)
    trace_id: str = "",
) -> dict:
    '''Web meta-tool — atomic actions for search and scraping.'''
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | One of `search`, `scrape`, `read`, `search_and_read` |
| `query` | `str` | No | Search query. **Required** for `search` and `search_and_read`. |
| `url` | `str` | No | Target URL. **Required** for `scrape` and `read`. |
| `max_results` | `int` | No | Max search results. Default: 5. Upper bound: `cfg.web_max_search_results`. |
| `max_chars` | `Optional[int]` | No | Max characters per scraped page. Default: `None` (resolved to `cfg.web_max_text_chars` in handlers). |
| `trace_id` | `str` | No | Trace identifier for logging and pruning artifacts. |

> **Note:** There is no `summarize` or `include_raw` parameter. The old doc incorrectly listed these. `search_and_read` returns raw scraped text, not LLM summaries. Raw HTML is never included in responses.

---

## ⚡ Actions

### 🔍 `search` — Find URLs via SearXNG

Queries the configured SearXNG instance and returns ranked results with titles, URLs, snippets, and source engines.

**Config:**
```ini
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
      {"url": "https://...", "title": "...", "snippet": "...", "engine": "google"}
    ],
    "count": 5,
    "query": "FastMCP python tutorial"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | Result URL |
| `title` | `str` | Page title from SearXNG |
| `snippet` | `str` | Content snippet, truncated to `cfg.web_snippet_chars` |
| `engine` | `str` | Source search engine (e.g., `google`, `bing`, `duckduckgo`) |

**Error cases:**
- Missing query → `fail("action='search' requires query=")`
- SSRF blocked SearXNG URL → `fail("SSRF blocked: SearXNG URL ...")`
- SearXNG timeout → `fail("SearXNG timeout at {url}")`
- SearXNG unreachable → `fail("Cannot reach SearXNG at {url}")`
- General failure → `fail("Search failed: {exception}")`

---

### 📄 `scrape` — Read a single static page (raw)

Fetches HTML via `httpx`, parses with BeautifulSoup4, and returns clean text + metadata. **No pruning** — returns the full text up to `max_chars`.

**Guards applied:**
- SSRF: URL validated before request
- Scheme: only `http://` and `https://` allowed
- PDF pre-flight: URLs ending in `.pdf` rejected before HTTP request
- Content-type: `application/pdf` and `image/*` rejected after headers arrive
- Size: `Content-Length > 10 MB` rejected before reading body
- Retry: uses `retry_sync()` from `core/net/retry.py` with `is_retryable_error()` classification. Constants from `core/net/default.py` (`SCRAPE_MAX_RETRIES=3`, `SCRAPE_TIMEOUT=30`)

**Return:**
```json
{
  "status": "success",
  "data": {
    "url": "https://...",
    "title": "Page Title",
    "text": "Clean extracted text...",
    "word_count": 1500,
    "truncated": false
  }
}
```

**JS limitation:** If the page requires JavaScript (React, Angular, etc.), `text` may be empty or very short (`< 300 chars`). Use the `browser` tool as fallback.

---

### 📖 `read` — Read a single static page (pruned)

Identical to `scrape`, but the result is piped through `prune_tool_dict()` from `core.memory_backend.pruner`:
- Head + tail truncation with `[TRUNCATED: ...]` marker if `text > max_chars`
- Full content saved to `workspace/.artifacts/`
- Recovery hint included in response

**Return:** Same shape as `scrape`, but potentially truncated with artifact path.

> **Note:** `read` is the preferred action for reading web pages. Use `scrape` only when you need the raw unpruned text.

---

### 🚀 `search_and_read` — Parallel search + scrape (most powerful)

Runs `search`, deduplicates URLs while preserving rank order, then fans out to `scrape` each result in parallel via `ThreadPoolExecutor(max_workers=min(len(urls), 4))`.

**Flow:**
```text
search(query, n) → [url1, url2, url3]
 ├─ Deduplicate URLs (preserve rank order)
 ├─ ThreadPoolExecutor(max_workers=min(len(urls), 4))
 │ ├─ Worker 1: _action_scrape(url1) → result1
 │ ├─ Worker 2: _action_scrape(url2) → result2
 │ └─ Worker 3: _action_scrape(url3) → result3
 ├─ Reassemble in original URL order
 ├─ concurrent.futures.wait() with cfg.worker_timeout global timeout
 │ ├─ done futures: collect results
 │ └─ not_done futures: report as timeout errors
 ├─ shutdown(wait=False) — do not block on slow threads after timeout
 └─ prune_tool_dict() on final aggregated result
```

**Return:**
```json
{
  "status": "success",
  "data": {
    "query": "ChromaDB persistent client",
    "results": [
      {"url": "https://...", "title": "...", "text": "...", "word_count": 1500}
    ],
    "scraped_count": 3,
    "attempted": 3,
    "duplicates_removed": 2
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | Original search query |
| `results` | `list` | Successfully scraped pages, in original rank order |
| `scraped_count` | `int` | Number of pages with non-empty text |
| `attempted` | `int` | Number of unique URLs attempted |
| `duplicates_removed` | `int` | Number of duplicate URLs filtered before scraping |

> **Cross-action coupling note:** `search_and_read` directly imports `_action_search` and `_action_scrape` from sibling modules. This is intentional for performance (avoids facade overhead). If `search`/`scrape` signatures change, update this file.

---

## 🔒 Security

### 🛡️ SSRF Guard (`_is_safe_url`)

All URL parameters pass through `_is_safe_url()` in `web_ops/utils.py` before any HTTP request:

```python
def _is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    from core.net.security import is_safe_network_address
    return is_safe_network_address(hostname)
```

**Blocks:**
- Non-HTTP schemes (`file://`, `ftp://`, `javascript:`, etc.)
- Private IP ranges (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`)
- Loopback (`127.0.0.1`, `localhost`)
- Link-local (`169.254.x.x`)
- IPv6 loopback (`::1`)
- Malformed URLs (empty hostname)

**Applied to:**
- SearXNG URL in `search` (validates the configured endpoint itself)
- Target URLs in `scrape` / `read`
- All URLs in `search_and_read` (via internal `_action_scrape` calls)

### 🌐 HTTP Client

The singleton `httpx.Client` is configured with:
- `headers`: rotating User-Agent from a pool of 4 realistic browser UAs
- `timeout`: 10.0s (client default; individual requests override: `_fetch_html` uses `SCRAPE_TIMEOUT=30` from `core/net/default.py`, `_do_search` uses `SEARCH_TIMEOUT=30` from `core/net/default.py`)
- `follow_redirects`: `True`
- `limits`: `httpx.Limits(max_connections=20)`

**Thread safety:** `httpx.Client` is thread-safe. Safe to use inside `ThreadPoolExecutor` in `search_and_read`.

---

## 📤 Output & Pruning

All actions return `ok()/fail()` dicts from `core/contracts.py`.

**Pruning behavior by action:**

| Action | Pruned? | Notes |
|--------|---------|-------|
| `search` | ❌ No | Results are small; no pruning needed |
| `scrape` | ❌ No | Returns full text up to `max_chars` |
| `read` | ✅ Yes | Piped through `prune_tool_dict()` — truncated outputs saved to `workspace/.artifacts/` |
| `search_and_read` | ✅ Yes | Final result piped through `prune_tool_dict()` |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
