<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1.1 | 2026-07-14 | **Bugfix batch + dead code cleanup.** P1: `node_decompose_goal` returns partial dicts. #11: `route_after_synthesize` reads `state["converged"]` instead of recomputing. #20: `_parse_score` range bug fix. #9: Empty report → "No results found". #12/#13: Removed `format_audit` + `JS_HEAVY_HINTS` dead code. #14/#15/#17: Regex + trailing comma + empty query fixes. |
| v1.1 | 2026-07-06 | **Metadata + citations + P0/P1 fixes.** Added `WORKFLOW_METADATA`. Wired citation tracker into report + notify. Fixed P0 #2 (`task`/`content` swap), P0 #4 (API budget on Tavily attempt). P1 #6/#7/#8/#10/#22. Trim analysis: not needed (`knowledge_base` already capped). |
| v1.0.2 | 2026-07-05 | **Bug fix:** API budget (`budget_api_calls`) now only decremented for Tavily searches, not web (SearXNG) searches. |
| v1.0.1 | 2026-07-05 | **Bug fix:** Both `agent()` calls in `node_synthesize` now pass `action="dispatch"`. Removed dead `completeness_threshold = 0.85` local. |
| v1.0 | — | **Released** — 8-node cyclic LangGraph StateGraph with budget management, convergence detection, multi-tool search, and memory integration. |

---

### ⚠️ Breaking Changes

#### v1.1 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| `_node_*` helpers return partial dicts (was `{**state, ...}`) | LangGraph best practice — only changed keys. | No migration — callers consume the merged final state from `graph.invoke()`. |
| `_node_store` stores full result (was `result[:800]`) | Semantic memory now holds complete research. | No migration — larger stored text is the intended improvement. |
| `_node_notify` returns `artifacts` (source URLs) | Was `return state`. | No migration — callers read `result["artifacts"]`; was always empty before. |
| `node_synthesize` uses `task=` for user instruction, `context=` for system prompt | Was swapped. | No migration — the old mapping was broken. |
| API budget decrements on Tavily ATTEMPT, not success | Failed Tavily calls now correctly consume budget. | No migration — more accurate tracking. |
| Removed `_agent_ok` / `_agent_text` wrappers | Dead code handling a legacy `LLMResponse` shape. | If external code imported them, inline the `dict` access (`result.get("status") == "success"`, `result.get("text", "")`). |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 16 | **`node_search` hardcoded `max_results=5`** | Should be configurable via `.env`. | P2 |
| 18 | **`_summarize_evidence` bypassing role config** | Uses custom system prompt instead of role's configured prompt. | P2 |
| 19 | **`_extract_evidence` hardcoded top 3** | Should be configurable. | P2 |
| 21 | **`_cap_knowledge` may exceed max after prefix** | Truncation + prefix may exceed `max_chars`. | P2 |
| 24 | **Configurable convergence threshold** | Make `CONVERGENCE_SIMILARITY_THRESHOLD` actually use `.env` value. | P2 |
| 25 | **Streaming synthesis** | Stream synthesis output for real-time feedback. | P3 |
| 26 | **crawl4ai integration** | Replace three-tier `tavily → web → browser` with two-tier `tavily → web(crawl)`. Depends on quality validation. See `docs/tools/web/CHANGELOG.md` v1.3. | P2 (evaluation) |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **Remove cyclic workflow** | Single-pass research would miss important information. Iteration is essential. | Skip |
| 2 | **Remove budget management** | Budget tracking prevents runaway costs. | Skip |
| 3 | **Remove convergence detection** | Without it, the workflow would run indefinitely or stop prematurely. | Skip |
| 4 | **Remove multi-tool search** | Single-tool search would have limited coverage. | Skip |
| 5 | **Real-time collaboration** | Multi-user research would require complex state synchronization. | Skip |

---

*Last updated: 2026-07-14 (v1.1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
