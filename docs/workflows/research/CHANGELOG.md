<- Back to [Research Overview](../RESEARCH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| Pre-v1.0 | — | In development — Monolithic `workflows/research.py` with 8-node pipeline. Will be split into subpackage with per-node modules following `deep_research_impl/` and `autocode_impl/` patterns. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. This section is reserved for future releases.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 8-node LangGraph pipeline | ✅ Pre-v1.0 | search → scrape → synthesize → report → store → distill → notify |
| Parallel scraping | ✅ Pre-v1.0 | ThreadPoolExecutor with max_workers=3 |
| Timeout handling | ✅ Pre-v1.0 | 30s scrape + 30s summarization per source |
| Deduplication | ✅ Pre-v1.0 | seen_urls prevents duplicate scraping |
| Citation tracking | ✅ Pre-v1.0 | citations module tracks sources per trace_id |
| Memory storage | ✅ Pre-v1.0 | Semantic + procedural memory storage |
| Report generation | ✅ Pre-v1.0 | Structured report with synthesis and sources |
| Result compression | ✅ Pre-v1.0 | compress_result() prevents oversized responses |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Fix `agent()` missing `action="dispatch"` in `node_synthesize`** | `agent()` requires `action` parameter. Without it, returns error dict. | P0 |
| 2 | **Fix `not r.get("status") == "success"` always false** | `(not "success") == "success"` → `False`. Error path never fires. | P0 |
| 3 | **Fix `max_results=3` hardcoded in `node_search`** | Should use `cfg.web_max_search_results` (default 10). | P1 |
| 4 | **Fix `as_completed` timeout semantics** | Timeout is for first future, not total. Subsequent futures can hang. | P1 |
| 5 | **Add future cancellation on timeout** | Pending ThreadPoolExecutor futures keep running on timeout. | P1 |
| 6 | **Fix `report_tool` signature** | Verify `report()` tool signature matches usage. | P1 |
| 7 | **Fix semantic memory only storing 800 chars** | Long research results truncated. Semantic memory nearly useless. | P1 |
| 8 | **Remove redundant `status` check in `node_distill`** | `node_distill` only runs on success paths. Check is dead code. | P1 |
| 9 | **Fix nested-call guard** | `_is_nested_parallel()` guard is broken for worker thread recursion. | P2 |
| 10 | **Fix `artifacts` containing dict not strings** | `artifacts` should be list of strings. Passing dict breaks consumers. | P2 |
| 11 | **Fix dossier truncation splitting headers** | Truncation may cut `### [Source N]` headers in half. | P2 |
| 12 | **Add URL deduplication** | `node_search` may return duplicate URLs from different results. | P2 |
| 13 | **Add URL validation** | `r["url"]` could be `javascript:void(0)` or relative paths. | P3 |
| 14 | **Test restructure** | Split `test_research_flow.py` into per-node files + `conftest.py` | P1 |
| 15 | **Configurable search results** | Make `max_results` configurable via `.env` | P2 |
| 16 | **Streaming synthesis** | Stream synthesis output for real-time feedback | P3 |
| 17 | **Multi-language support** | Support non-English search and synthesis | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove parallel scraping** | Sequential scraping would be too slow. Parallel is essential. | Skip |
| 2 | **Remove citation tracking** | Attribution is important for trust. Removing it would degrade quality. | Skip |
| 3 | **Add real-time streaming** | Streaming would require WebSocket/SSE infrastructure. Out of scope. | Skip |
| 4 | **Support non-web sources** | The workflow is designed for web research. Other sources would require significant changes. | Skip |
| 5 | **Automatic fact-checking** | Fact-checking would require additional LLM calls and complex logic. Out of scope. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
