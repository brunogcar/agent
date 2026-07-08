<- Back to [Research Overview](../RESEARCH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v1.1 | 2026-07-08 | **Trim node wired in:** Added `trim_state_node` between synthesize and report. After synthesize produces `result`, oversized `search_results` (up to 40KB) is evicted to episodic memory (chonkie-aware — splits into chunks, evicts each individually, keeps first chunk as preview). Falls back to whole-string eviction if chonkie is missing. Uses `trim_state_node()` from `workflows/base.py` (v1.3). Graph: `recall → search → parallel_scrape → synthesize → trim → report → store → distill → notify`. Second workflow to wire in `trim_state()` (see `base/CHANGELOG.md` #18). |
| v1.0 | 2026-07-05 | **Subpackage split + 8 bug fixes + test restructure:** Split monolithic `workflows/research.py` (513 lines) into `workflows/research_impl/` subpackage with per-node modules. Thin facade re-exports `build_research_graph`, `WORKFLOW_METADATA`. Added `WORKFLOW_METADATA` for MCP client introspection (8 nodes + 10 edges). Tests split into per-node files + `conftest.py` + `TestSubpackageStructure` (11 structural tests). Fixed 8 bugs (see below). |
| Pre-v1.0 | 2026-07-05 | **Bug fix:** `node_search` now uses `cfg.web_max_search_results` (default 10) instead of hardcoded `max_results=3`. `node_synthesize` error check changed from confusing `not r.get("status") == "success"` to explicit `r.get("status") != "success"` for readability. `node_synthesize` now calls `agent(action="dispatch", role="research", ...)` (was missing `action`, always returned `Unknown action ''`). |
| Pre-v1.0 | — | In development — Monolithic `workflows/research.py` with 8-node pipeline. |

---

## ⚠️ Breaking Changes

### Pre-v1.0 — 2026-07-05 (bug fix)

| Change | Impact |
|--------|--------|
| `node_synthesize` now calls `agent(action="dispatch", role="research", ...)` | Internal bug fix. No migration — the previous call was always broken (returned `Unknown action ''` error). Callers now see real synthesis results instead of `node_error()` failures. |

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
| #1 Fix `agent()` missing `action="dispatch"` | ✅ Pre-v1.0 | `node_synthesize` now passes `action="dispatch"` |
| #2 Fix `not r.get("status") == "success"` | ✅ Pre-v1.0 | Changed to explicit `r.get("status") != "success"` |
| #3 Fix `max_results=3` hardcoded | ✅ Pre-v1.0 | Now uses `cfg.web_max_search_results` (default 10) |
| #4 Fix `as_completed` timeout semantics | ✅ v1.0 | Changed to `concurrent.futures.wait(timeout=)` — global timeout, not per-first-future |
| #5 Add future cancellation on timeout | ✅ v1.0 | Pending futures now `.cancel()` on timeout — prevents zombie threads |
| #7 Fix semantic memory only storing 800 chars | ✅ v1.0 | Now stores full `result` (was `result[:800]`). Semantic memory is for content retrieval — truncation defeated the purpose. |
| #8 Remove redundant `status` check in `node_distill` | ✅ v1.0 | Dead code removed (`if state.get("status") == "failed": return state` — distill only runs on success paths) |
| #9 Fix nested-call guard | ✅ v1.0 | `_is_nested_parallel()` guard fixed for worker thread recursion |
| #10 Fix `artifacts` containing dict not strings | ✅ v1.0 | `artifacts` is now `list[str]` (was `list[dict]`) |
| #12 Add URL deduplication | ✅ v1.0 | `node_search` now deduplicates URLs via `seen_urls` set |
| #14 Test restructure | ✅ v1.0 | Split `test_research_flow.py` into per-node files + `conftest.py` + `TestSubpackageStructure` |
| Subpackage split (`research_impl/`) | ✅ v1.0 | Thin facade + per-node modules + `WORKFLOW_METADATA` |
| Trim node wired in | ✅ v1.1 | `trim_state_node` between synthesize and report — evicts oversized `search_results` |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 6 | **Fix `report_tool` signature** | Verify `report()` tool signature matches usage. The v1.0 code calls `report_tool(action="report", ...)` — verify this matches the current report tool API. | P2 |
| 11 | **Fix dossier truncation splitting headers** | Truncation may cut `### [Source N]` headers in half. v1.0 improved truncation (uses `rfind("\n\n")` to cut at paragraph boundary), but edge cases may remain. | P3 |
| 13 | **Add URL validation** | `r["url"]` could be `javascript:void(0)` or relative paths. v1.0 added URL dedup (#12) but not validation. | P3 |
| 15 | **Configurable search results** | Make `max_results` configurable via `.env` (currently uses `cfg.web_max_search_results`). | P3 |
| 16 | **Streaming synthesis** | Stream synthesis output for real-time feedback | P3 |
| 17 | **Multi-language support** | Support non-English search and synthesis | P3 |
| 18 | **crawl4ai integration** | **Potential refactor:** Replace `_browser_fallback_scrape` with `web(action="crawl")`. Crawl4ai handles JS-heavy pages natively (returns clean markdown), eliminating the browser fallback for JS walls. Depends on crawl4ai quality validation against real JS-heavy pages. See `docs/TOOLS.md` § "Crawl4ai integration" and `docs/tools/web/CHANGELOG.md` v1.3. | P2 (evaluation) |

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

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
