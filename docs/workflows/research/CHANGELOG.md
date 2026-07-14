<- Back to [Research Overview](../RESEARCH.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1.1 | 2026-07-14 | **P0 routing fix + P1 exception isolation + URL validation.** P0: `route_after_synthesize` returned `"report"` but conditional edges mapped `"trim"` — trim node unreachable since v1.1. P1: `node_recall`/`node_store`/`node_notify` wrapped in try/except. P1: `node_synthesize` `r["text"]` → `r.get("text", "")`. #13: URL validation. P2: doc drift fixes. |
| v1.1 | 2026-07-06 | **Trim node wired in.** `trim_state_node` between synthesize and report — evicts oversized `search_results`. |
| v1.0 | 2026-07-05 | **Subpackage split + 8 bug fixes + test restructure.** Split monolithic `workflows/research.py` (513 lines) into `workflows/research_impl/` subpackage. Added `WORKFLOW_METADATA`. Fixed 8 bugs. |
| Pre-v1.0 | 2026-07-05 | **Bug fix:** `node_search` uses `cfg.web_max_search_results` (was hardcoded `3`). `node_synthesize` calls `agent(action="dispatch", ...)` (was missing `action`). |
| Pre-v1.0 | — | In development — monolithic `workflows/research.py` with 8-node pipeline. |

---

### ⚠️ Breaking Changes

#### v1.0 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| Monolithic `workflows/research.py` → `research_impl/` subpackage | Node functions moved to `workflows/research_impl/nodes/<node>.py`. | Import nodes from `workflows.research_impl.nodes.<node>`. `build_research_graph` + `WORKFLOW_METADATA` still importable from `workflows.research`. |
| Nodes return partial dicts (not `{**state, ...}`) | LangGraph best practice — only changed keys. | No migration — callers consume the merged final state from `graph.invoke()`. |

#### Pre-v1.0 — 2026-07-05 (bug fix)

| Change | Impact | Migration |
|--------|--------|-----------|
| `node_synthesize` now calls `agent(action="dispatch", role="research", ...)` | Internal bug fix. | No migration — the previous call was always broken (returned `Unknown action ''`). |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 16 | **Streaming synthesis** | Stream synthesis output for real-time feedback. | P3 |
| 17 | **Multi-language support** | Support non-English search and synthesis. | P3 |
| 18 | **crawl4ai integration** | Replace `_browser_fallback_scrape` with `web(action="crawl")`. Crawl4ai handles JS-heavy pages natively. Depends on quality validation. See `docs/tools/web/CHANGELOG.md` v1.3. | P2 (evaluation) |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **Remove parallel scraping** | Sequential scraping would be too slow. Parallel is essential. | Skip |
| 2 | **Remove citation tracking** | Attribution is important for trust. | Skip |
| 3 | **Add real-time streaming** | Would require WebSocket/SSE infrastructure. | Skip |
| 4 | **Support non-web sources** | The workflow is designed for web research. | Skip |
| 5 | **Automatic fact-checking** | Would require additional LLM calls and complex logic. | Skip |

---

*Last updated: 2026-07-14 (v1.1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
