<- Back to [Web Overview](../WEB.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.3 | 2026-07-08 | **New action: `crawl`** — crawl4ai prototype. Handles JS-heavy pages natively, returns clean markdown. Soft dependency (lazy import). Async→sync bridge. Does NOT fall back to scrape on failure (prototype). |
| v1.2 | 2026-07-05 | **core/net adoption.** scrape.py uses `retry_sync()` from `core/net/retry.py`. Constants from `core/net/default.py`. Error classification via `is_retryable_error()`. |
| v1.1 | — | **Hardening + guards.** `max_chars` sentinel fix, content-type guard, response size guard, retry with backoff, PDF pre-flight, user-agent rotation, scheme allowlist, lazy security import, ThreadPoolExecutor shutdown fix. |
| v1.0 | — | **`@meta_tool` refactor + atomic actions.** Split monolithic `tools/web.py` into `tools/web_ops/` subpackage. 4 actions (`search`, `scrape`, `read`, `search_and_read`). `@register_action` auto-discovery. Test restructure. |

---

### ⚠️ Breaking Changes

#### v1.2 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| `scrape.py` retry moved to `core/net/retry.py` | `time.sleep` now patched in `core.net.retry`, not `tools.web_ops.actions.scrape`. | Tests must update patch targets. |
| `_MAX_RETRIES` removed | Was 1 (2 total attempts). Now uses `SCRAPE_MAX_RETRIES=3` (4 total attempts). | No migration. |
| `_RETRYABLE_STATUS_CODES` / `_RETRYABLE_EXCEPTIONS` removed | Now uses `is_retryable_error()` from `core/net/errors.py`. | No migration. |
| `timeout=20` → `SCRAPE_TIMEOUT=30` | Default scrape timeout increased. | No migration. |
| `timeout=15` → `SEARCH_TIMEOUT=30` | Default search timeout increased. | No migration. |
| Backoff changed | Was `min(2^attempt, 8)`. Now `get_retry_delay()` with jitter. | No migration. |

#### v1.1 — Hardening + Guards

| Change | Impact | Migration |
|--------|--------|-----------|
| `max_chars` facade default fixed | Was `int = 0` (broken). Now `Optional[int] = None`. | Callers omitting `max_chars` now get the config default. |
| Content-type guard added | Rejects `application/pdf` and `image/*`. | No migration. |
| Response size guard added | Rejects `Content-Length > 10 MB`. | No migration. |
| Retry with exponential backoff added | One retry on transient errors. | No migration. |
| PDF pre-flight detection | URLs ending in `.pdf` rejected before HTTP request. | No migration. |
| User-agent rotation added | 4-browser UA pool. | No migration. |
| Scheme allowlist in `_is_safe_url` | Only `http://` and `https://` allowed. | No migration. |
| `ThreadPoolExecutor` shutdown fix | `search_and_read` uses `shutdown(wait=False)` after `wait()`. | No migration. |

#### v1.0 — `@meta_tool` refactor

| Change | Impact | Migration |
|--------|--------|-----------|
| Split monolithic `tools/web.py` into `tools/web_ops/` subpackage | Node functions moved to `web_ops/actions/*.py`. | Import from `tools.web_ops.actions.<action>`. |
| Added `@register_action` auto-discovery | Via `pathlib` + `importlib` in `web_ops/__init__.py`. | No migration. |
| Added `@meta_tool` auto-generated `Literal` enum | `action` parameter is now `Literal["search", "scrape", "read", "search_and_read"]`. | No migration. |
| Replaced `as_completed` with `concurrent.futures.wait()` | Global timeout via `cfg.worker_timeout`. | No migration. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 49 | **Browser fallback in `search_and_read`** | When `_action_scrape` returns `< 300` chars, auto-retry with `browser(navigate+text_content)` for JS-rendered pages. Run sequentially after `ThreadPoolExecutor` closes, NOT inside workers. | P1 |
| 50 | crawl4ai quality validation | Validate `crawl` action against real JS-heavy pages. Gating item for research/deep_research refactors. | P2 |
| 52 | SearXNG circuit breaker / Tavily fallback | If SearXNG fails (timeout, 503, connection error), auto-fallback to `tavily(action="search")` if `TAVILY_API_KEY` configured. | P2 |
| 53 | Standardize `max_results` | Use `cfg.web_max_search_results` consistently across `web/search`, `research`, and `deep_research`. Currently `web` defaults to 5, `research` hardcodes 3, `deep_research` hardcodes 5. | P2 |
| 54 | PDF handling | Detect `.pdf` URLs, download to `workspace/.artifacts/`, return structured reference. Or route to `file(action="read_pdf")`. | P2 |
| 55 | `read` vs `scrape` consolidation | `read` is `scrape` + `prune_tool_dict`. Consider making `read` the default and `scrape` internal, or adding a `prune` flag. | P2 |
| 56 | LRU cache for `read` | `functools.lru_cache` or disk-backed cache keyed by URL hash. Avoids re-fetching the same page twice in a trace. | P3 |
| 57 | Robots.txt respect | Check `robots.txt` before scraping. Cache parsed robots.txt per domain. | P3 |
| 58 | Per-domain rate limiting | Track request timestamps per domain. Sleep if exceeding N requests/second. Prevents 429 bans. | P3 |
| 51 | crawl4ai LLM extraction | `web(action="crawl", extract_schema={...})` — structured data extraction. Requires transformers/PyTorch (~2GB). Deferred until base crawl action is validated. | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **LLM summarization in `search_and_read`** | Never implemented. Summarization belongs in the `research` workflow, not the web tool. | Skip |
| 2 | **`include_raw` parameter** | Never existed. Raw HTML bloats context windows. Use `browser(extract_html)`. | Skip |
| 3 | **Structured extraction (`headers`, `links`, `images`)** | Never existed. `scrape` only returns `url`, `title`, `text`, `word_count`, `truncated`. Use `browser(extract_links)` / `browser(extract_tables)`. | Skip |
| 4 | **JavaScript rendering in web tool (via browser)** | v1.3 added `web(action="crawl")` using crawl4ai. Browser tool still needed for interactive automation. | Resolved (v1.3) |
| 5 | **Rate limiting / politeness delay** | `search_and_read` already has implicit politeness via connection pooling. | Skip |
| 6 | **Proxy / SOCKS5 support** | Not needed for current deployment. | Skip |
| 7 | **Browser fallback inside thread pool workers** | Browser is `NOT_PARALLEL_SAFE`. Fallback must run sequentially after `ThreadPoolExecutor` closes. | Skip |
| 8 | **HTTP connection pooling optimization** | Already optimal. Singleton `httpx.Client` with `Limits(max_connections=20)`. | Skip |
| 9 | **Response compression** | `httpx` already handles gzip/brotli transparently. | Skip |

---

*Last updated: 2026-07-14. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
