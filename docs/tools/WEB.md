# 🌐 Web Tool

The `web()` tool provides web search and content extraction via **SearXNG** (self-hosted metasearch) and **BeautifulSoup4** (HTML parsing). It is the agent\'s primary tool for discovering URLs and reading static HTML pages.

**Key characteristics:**
- **Free / self-hosted** — requires only a running SearXNG instance (no API keys)
- **Static HTML only** — JavaScript-rendered pages may return empty/short text
- **Parallel scraping** — `search_and_read` fans out to `ThreadPoolExecutor` for concurrent page fetching
- **JS-heavy page support (v1.3 prototype)** — `crawl` action uses [crawl4ai](https://github.com/unclecode/crawl4AI) to handle React/Angular/Vue SPAs natively, returning clean markdown
- **Lightweight** — pure Python (`httpx` + `BS4`), no browser overhead
- **Connection pooling** — singleton `httpx.Client` reuses TCP/TLS connections across calls
- **SSRF protection** — all URLs validated via `core.net.security.is_safe_network_address` before any HTTP request
- **Content-type guard** — rejects PDFs, images, and oversized responses before parsing
- **Retry with backoff** — uses `retry_sync()` from `core/net/retry.py` with unified `is_retryable_error()` classification and configurable constants from `core/net/default.py`
- **User-agent rotation** — rotates through a pool of browser UAs to reduce 403 blocks

---

## 🚀 Quick Start

```python
# Search the web
web(action="search", query="FastMCP python tutorial", max_results=5)

# Read a single page
web(action="read", url="https://docs.python.org/3/library/pathlib.html")

# Scrape a page (same as read, but no pruning)
web(action="scrape", url="https://example.com")

# Search + scrape top results in parallel
web(action="search_and_read", query="ChromaDB persistent client", max_results=5)

# JS-heavy page via crawl4ai (v1.3 prototype)
web(action="crawl", url="https://react-app-example.com")
```

---

## ⚙️ Configuration

```ini
SEARXNG_URL=http://localhost:8080
WEB_MAX_SEARCH_RESULTS=10
WEB_SNIPPET_CHARS=300
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick search | `web(search)` | Free, SearXNG, no API costs |
| Static page text (full) | `web(scrape)` | Fast, lightweight, no overhead, no pruning |
| Static page text (pruned) | `web(read)` | Same as scrape but with truncation guard for large pages |
| Bulk scrape from search | `web(search_and_read)` | Parallel, automated, deduplicated |
| JS-heavy page (markdown) | `web(crawl)` | crawl4ai, handles JS natively, returns markdown (v1.3 prototype, soft dep) |
| AI-ranked search | `tavily(search)` | Better relevance, citations, AI answer |
| JS-rendered page | `browser(navigate+text_content)` | Renders JavaScript |
| Bulk URL extraction | `tavily(extract)` | Optimized batch extraction |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](web/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](web/API.md) | Full tool signature, all actions, security, output & pruning, error handling |
| [CHANGELOG.md](web/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](web/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
