<- Back to [Tools Overview](.)

# 🔬 Tavily Tool

The `tavily()` tool provides **AI-optimized web search and content extraction** via the [Tavily API](https://tavily.com). It complements the existing `web` tool with superior ranking, automatic citations, and bulk extraction capabilities.

**Key characteristics:**
- **AI-ranked results** - Tavily's relevance engine outperforms raw SearXNG for research queries
- **Automatic citations** - Every result includes URL, title, and confidence score
- **Bulk extraction** - `extract` action can process up to 10 URLs in one call
- **Keyless mode** - Works without API key for `search` and `extract` (rate-limited)
- **Resilient by design** - Circuit breaker, rate-limit retry, structured error codes, API budget tracking

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

# Keyless mode - works without API key for search/extract
result = tavily(action="search", query="Python async patterns")
# -> {"status": "success", "data": {"keyless": true, ...}}

# Domain-scoped search
result = tavily(
    action="search",
    query="Python asyncio",
    include_domains=["github.com", "docs.python.org"],
    exclude_domains=["pinterest.com", "quora.com"]
)

# News-scoped search
result = tavily(action="search", query="AI regulation", topic="news")
```

---

## ⚙️ Configuration

```ini
# .env
TAVILY_API_KEY=tvly-...       # Optional - enables full functionality (crawl, map, research)
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

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick search (free) | `web(search)` | SearXNG, no API costs |
| AI-ranked search | `tavily(search)` | Better relevance, citations, AI answer |
| Domain-scoped search | `tavily(search, include_domains=...)` | Research precision |
| News/current events | `tavily(search, topic="news")` | Time-relevant results |
| Single static page (free) | `web(read)` | Fast, lightweight, no API costs |
| Bulk URL extraction | `tavily(extract)` | Optimized batch, AI-powered, up to 10 URLs |
| Site crawling | `tavily(crawl)` | Follows links, discovers pages (API key required) |
| Site structure | `tavily(map)` | Discovers hierarchy without fetching content (API key required) |
| Deep research | `workflows/deep_research.py` | Uses `run_research()` internally (not exposed as tool action) |
| JS-rendered page | `browser(navigate+text_content)` | Renders JavaScript |
| Interactive forms | `browser(click, fill)` | Supports interaction |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](tavily/ARCHITECTURE.md) | Module tree, design decisions, dispatch flow, test coverage, source code reference |
| [API.md](tavily/API.md) | Full tool signature, all actions (`search`, `extract`, `crawl`, `map`, `research`), validation rules, error handling, security |
| [CHANGELOG.md](tavily/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](tavily/INSTRUCTIONS.md) | AI editing rules - NEVER DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
