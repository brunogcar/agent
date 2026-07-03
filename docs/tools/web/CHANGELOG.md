<- Back to [Web Overview](../WEB.md)

# 🗺️ Changelog

## ⚠️ Breaking Changes

### v1.1 (Hardening + Guards)

| Change | Impact |
|--------|--------|
| `max_chars` facade default fixed | Was `int = 0` (broken: truncated all text to 0 chars). Now `Optional[int] = None` (handlers resolve `cfg.web_max_text_chars`). Callers omitting `max_chars` now get the config default instead of empty text. |
| Content-type guard added | `_fetch_html` now rejects `application/pdf` and `image/*` responses with structured errors. Previously, binary data was passed to BeautifulSoup, producing garbage. |
| Response size guard added | `_fetch_html` rejects responses with `Content-Length > 10 MB`. Previously, malicious servers could stream multi-GB responses into memory. |
| Retry with exponential backoff added | `_fetch_html` retries once on transient errors (503, 429, timeout, connect error) with `sleep(min(2^attempt, 8))`. Previously, a single transient error permanently dropped the URL. |
| PDF pre-flight detection | URLs ending in `.pdf` are rejected before any HTTP request. Previously, PDFs were fetched and passed to BeautifulSoup. |
| User-agent rotation added | Singleton client now uses a rotating pool of 4 browser UAs. Previously, a single hardcoded UA was used. |
| Scheme allowlist in `_is_safe_url` | Only `http://` and `https://` are allowed. Previously, `file:///etc/passwd` could bypass hostname checks. |
| `is_safe_network_address` lazy import | Moved from module-level to inside `_is_safe_url()`. Prevents `core.net.security` from being loaded at `web_ops` import time. |
| `ThreadPoolExecutor` shutdown fix | `search_and_read` now uses explicit `ex.shutdown(wait=False)` after `wait()` returns. Previously, the `with` context manager called `shutdown(wait=True)`, blocking until all threads finished and making `cfg.worker_timeout` ineffective. |

### v1.0 (`@meta_tool` refactor + atomic actions)

| Change | Impact |
|--------|--------|
| Split monolithic `tools/web.py` into `tools/web_ops/` subpackage | `web_ops/_registry.py`, `web_ops/__init__.py`, `web_ops/state.py`, `web_ops/client.py`, `web_ops/utils.py`, and `web_ops/actions/{search,scrape,read,search_and_read}.py` |
| Added `@register_action` auto-discovery | Via `pathlib` + `importlib` in `web_ops/__init__.py` |
| Added `@meta_tool` auto-generated `Literal` enum and docstring | `action` parameter is now `Literal["search", "scrape", "read", "search_and_read"]` |
| Moved singleton client logic to `web_ops/client.py` | `_get_singleton_client()`, `_make_client()`, `_close_client()`, `_SingletonClientContext` |
| Moved global state to `web_ops/state.py` | `_HTTP_CLIENT`, `_HTTP_CLIENT_LOCK`, `reset_state()`, `reset_loop()` |
| Extracted `_is_safe_url` to `web_ops/utils.py` | Shared SSRF guard used by both `search` and `scrape` actions |
| Replaced `as_completed` with `concurrent.futures.wait()` in `search_and_read` | Global timeout via `cfg.worker_timeout`, `not_done` futures reported as timeout errors |
| `atexit.register(_close_client)` moved to `client.py` | Was in `web.py`. Now only in `client.py` module level. |
| `reset_state()` now closes sockets | Calls `._close()` before nullifying `_HTTP_CLIENT`. Prevents connection leaks in tests. |
| `sorted()` in `__init__.py` glob | `sorted(_actions_dir.glob("*.py"))` for deterministic import order across filesystems. |
| Test restructure | Added `conftest.py` with shared fixtures, split into 9 focused test files matching action structure |
| Added `test_registry.py` | Verifies all 4 actions registered in `DISPATCH` |
| Added `test_facade.py` | Verifies `@meta_tool` generates `Literal` enum, unknown action error, param filtering |

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 4 actions (`search`, `scrape`, `read`, `search_and_read`) | ✅ v1.0 | `read` is `scrape` + pruning alias |
| `@meta_tool` + `@register_action` auto-discovery | ✅ v1.0 | `Literal` enum, dynamic docstring, no central wiring |
| SearXNG integration | ✅ v1.0 | `httpx` GET to `/search?format=json` |
| BeautifulSoup4 extraction | ✅ v1.0 | Decomposes `script`, `style`, `nav`, `footer`, `header`, `aside`, `noscript`, `iframe`; targets `main`/`article`/content id/class |
| Module-level singleton `httpx.Client` | ✅ v1.0 | Connection pooling, `atexit` cleanup, thread-safe |
| SSRF protection | ✅ v1.0 | `_is_safe_url` → `core.net.security.is_safe_network_address` |
| URL deduplication in `search_and_read` | ✅ v1.0 | Preserves rank order, counts `duplicates_removed` |
| Parallel scraping with global timeout | ✅ v1.0 | `ThreadPoolExecutor` + `concurrent.futures.wait()` + `cfg.worker_timeout` |
| Config-driven limits | ✅ v1.0 | `cfg.web_max_text_chars`, `cfg.web_snippet_chars`, `cfg.web_max_search_results`, `cfg.searxng_url` |
| `prune_tool_dict` integration | ✅ v1.0 | `read` and `search_and_read` pipe through pruner |
| Test restructure with conftest.py | ✅ v1.0 | 9 focused test files, shared fixtures, no duplication |
| `max_chars` sentinel fix | ✅ v1.1 | `Optional[int] = None` instead of broken `int = 0` |
| Content-type guard | ✅ v1.1 | Rejects PDF/image before BS4 parsing |
| Response size guard | ✅ v1.1 | 10 MB ceiling on `Content-Length` |
| Retry with exponential backoff | ✅ v1.1 | One retry on transient errors |
| PDF pre-flight detection | ✅ v1.1 | Rejects `.pdf` URLs before HTTP request |
| User-agent rotation | ✅ v1.1 | 4-browser UA pool |
| Scheme allowlist | ✅ v1.1 | `http`/`https` only |
| Lazy `is_safe_network_address` import | ✅ v1.1 | Inside `_is_safe_url()`, not module-level |
| `ThreadPoolExecutor` shutdown fix | ✅ v1.1 | `shutdown(wait=False)` after `wait()` timeout |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Standardize `max_results` across tools | Use `cfg.web_max_search_results` consistently across `web/search`, `research`, and `deep_research` nodes. Currently `web` defaults to 5, `research` hardcodes 3, `deep_research` hardcodes 5. **Will be addressed when research/deep_research are refactored.** | P2 |
| Browser fallback in `search_and_read` | When `_action_scrape` returns `< 300` chars, auto-retry with `browser(navigate+text_content)` for JS-rendered pages. Run sequentially after `ThreadPoolExecutor` closes, NOT inside workers | P1 |
| SearXNG circuit breaker / Tavily fallback | If SearXNG fails (timeout, 503, connection error), auto-fallback to `tavily(action="search")` if `TAVILY_API_KEY` is configured | P2 |
| PDF handling | Detect `.pdf` URLs, download to `workspace/.artifacts/`, return structured reference. Or route to `file(action="read_pdf")` | P2 |
| `read` vs `scrape` consolidation discussion | `read` is `scrape` + `prune_tool_dict`. Consider making `read` the default and `scrape` internal, or adding a `prune` flag | P2 |
| LRU cache for `read` | `functools.lru_cache` or disk-backed cache keyed by URL hash. Avoids re-fetching the same page twice in a trace | P2 |
| Cached read | `web(action="cached_read", url=...)` — check local cache before fetching, TTL-based invalidation | P3 |
| Robots.txt respect | Check `robots.txt` before scraping to avoid getting blocked. Cache parsed robots.txt per domain | P3 |
| Rate limiting per domain | Track request timestamps per domain. Sleep if exceeding N requests/second. Prevents 429 bans | P3 |
| Extract `_html_to_text` to `core/html.py` | Pure HTML→text converter. Extract when a second consumer appears (email tool, RSS reader, etc.) | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **LLM summarization in `search_and_read`** | The old doc incorrectly claimed this exists. It was never implemented. Summarization belongs in the `research` workflow, not the web tool. | Skip |
| 2 | **`include_raw` parameter** | Never existed in the code. Raw HTML bloats context windows. Use `browser(extract_html)` if DOM structure is needed. | Skip |
| 3 | **Structured extraction (`headers`, `links`, `images`)** | The old LLM draft fabricated this. `scrape` only returns `url`, `title`, `text`, `word_count`, `truncated`. Use `browser(extract_links)` / `browser(extract_tables)` for structured extraction. | Skip |
| 4 | **JavaScript rendering in web tool** | Out of scope. Use `browser` for JS-rendered pages. | Skip |
| 5 | **Rate limiting / politeness delay** | `search_and_read` already has implicit politeness via connection pooling. Explicit delays would slow down parallel scraping. | Skip |
| 6 | **Proxy / SOCKS5 support** | Not needed for current deployment. Can be added via `httpx` proxy config if required. | Skip |
| 7 | **Browser fallback inside thread pool workers** | Browser is `NOT_PARALLEL_SAFE`. Fallback must run sequentially after `ThreadPoolExecutor` closes, not inside worker threads. | Skip |
| 8 | **HTTP connection pooling optimization** | Already optimal. Singleton `httpx.Client` with `Limits(max_connections=20)` is reused across all threads. Nothing to tune. | Skip |
| 9 | **Response compression** | `httpx` already handles gzip/brotli transparently via `Accept-Encoding`. No action needed. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
