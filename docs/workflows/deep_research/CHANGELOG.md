<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v1.0.1 | 2026-07-05 | **Bug fix:** Both `agent()` calls in `node_synthesize` (synthesize + evaluate) now pass `action="dispatch"`. Previously both returned `Unknown action ''` error — synthesis fell back to `prev_knowledge` (always `""` on first iteration), and evaluate always returned `score=0.0` (completeness permanently 0). Also removed dead `completeness_threshold = 0.85` local (was 0-1 scale, never used; real threshold comparison is `85.0` on 0-100 scale in `routes.py` and `graph.py`). |
| v1.0 | — | Released — 8-node cyclic LangGraph StateGraph with budget management, convergence detection, multi-tool search, and memory integration |

---

## ⚠️ Breaking Changes

### v1.0.1 — 2026-07-05

| Change | Impact |
|--------|--------|
| `node_synthesize` synthesize call now passes `action="dispatch"` | Internal fix. No migration — the previous call was always broken. Knowledge base now advances per iteration instead of staying empty. |
| `node_synthesize` evaluate call now passes `action="dispatch"` | Internal fix. No migration — the previous call was always broken. Completeness score now reflects the evaluate agent's output instead of being permanently `0.0`. |
| Removed dead `completeness_threshold = state.get("completeness_threshold", 0.85)` local | No behavior change — the local was read but never referenced. Real threshold comparison lives in `routes.py:30` and `graph.py:75` (default `85.0` on 0-100 scale, matching `_parse_score()`'s output). Replaced with an explanatory comment to prevent re-introduction. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Cyclic LangGraph workflow | ✅ v1.0 | Search → synthesize → evaluate → loop until convergence |
| Budget management | ✅ v1.0 | API calls + browser actions tracked separately |
| Convergence detection | ✅ v1.0 | Cosine similarity between knowledge bases |
| Multi-tool search | ✅ v1.0 | Tavily → web → browser fallback |
| Goal decomposition | ✅ v1.0 | Planner LLM breaks goal into sub-queries |
| Evaluation | ✅ v1.0 | Executor LLM evaluates synthesis quality |
| Memory integration | ✅ v1.0 | Recall + store for context and future use |
| Report generation | ✅ v1.0 | Structured report with synthesis and sources |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Fix `agent()` missing `action="dispatch"` in `node_synthesize` and `node_evaluate`** | `agent()` requires `action` parameter. Without it, returns error dict. | P0 |
| 2 | **Fix `task` parameter used for system prompt in `agent()` calls** | `task` is passed to `llm.complete(user=task)`. System prompt should be separate. | P0 |
| 3 | **Fix API budget decremented for web searches** | `node_search` decrements `budget_api_calls` for ALL successful searches, including web. Only Tavily should decrement. | P0 |
| 4 | **Fix API budget NOT decremented for failed Tavily searches** | Failed Tavily calls still consume API budget. Not reflected in tracking. | P0 |
| 5 | **Fix `completeness_threshold` scale mismatch** | Node defaults to `0.85` (0-1), route and `.env` use `85.0` (0-100). Route check always true for score >= 1. | P0 |
| 6 | **Remove `_agent_ok` and `_agent_text` dead code** | `agent()` returns `dict`, not `LLMResponse`. Wrappers are unnecessary. | P1 |
| 7 | **Fix `**state` spreading in graph nodes** | All nodes return `{**state, ...}`. Should return partial dicts. | P1 |
| 8 | **Fix memory failure silent in `_node_recall`** | Exception caught, returns empty context. No trace step, no error log. | P1 |
| 9 | **Fix `_node_report` empty report not handled** | Empty `knowledge_base` + `synthesis` produces empty report with `"incomplete"` status. | P1 |
| 10 | **Fix `_node_store` only storing 800 chars** | Long research results truncated. Semantic memory nearly useless. | P1 |
| 11 | **Fix `route_after_synthesize` recomputing `converged`** | Already computed in `node_synthesize`. Redundant and may diverge. | P1 |
| 12 | **Remove `format_audit` dead code** | Function exists but never called. | P3 |
| 13 | **Remove `JS_HEAVY_HINTS` dead code** | Defined in `constants.py` but never used. `search.py` uses hardcoded indicators. | P2 |
| 14 | **Fix `_parse_sub_queries` regex fragility** | Character class `r'[\-*•]'` has unnecessary escape. May emit `SyntaxWarning`. | P1 |
| 15 | **Fix `_parse_sub_queries` trailing comma handling** | LLMs may output trailing commas in JSON. `json.loads` rejects them. | P1 |
| 16 | **Fix `node_search` hardcoded `max_results=5`** | Should be configurable via `.env`. | P2 |
| 17 | **Fix `node_search` not filtering empty queries** | Empty strings in `queries` cause searches for `""`. | P2 |
| 18 | **Fix `_summarize_evidence` bypassing role config** | Uses custom system prompt instead of role's configured prompt. | P2 |
| 19 | **Fix `_extract_evidence` hardcoded top 3** | Should be configurable. | P2 |
| 20 | **Fix `_parse_score` removing negative numbers incorrectly** | `re.sub(r"-\d+", "", text)` removes numbers from ranges like "85-90". | P1 |
| 21 | **Fix `_cap_knowledge` may exceed max after prefix** | Truncation + prefix may exceed `max_chars`. | P2 |
| 22 | **Add `synthesis` field to `DeepResearchState`** | Field returned by `node_synthesize` but not declared in TypedDict. | P3 |
| 23 | **Test restructure** | Split `test_deep_research.py` into per-node files + `conftest.py` | P1 |
| 24 | **Configurable convergence threshold** | Make `CONVERGENCE_SIMILARITY_THRESHOLD` actually use `.env` value | P2 |
| 25 | **Streaming synthesis** | Stream synthesis output for real-time feedback | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove cyclic workflow** | Single-pass research would miss important information. Iteration is essential. | Skip |
| 2 | **Remove budget management** | Budget tracking prevents runaway costs. Removing it would risk excessive API usage. | Skip |
| 3 | **Remove convergence detection** | Without convergence detection, the workflow would run indefinitely or stop prematurely. | Skip |
| 4 | **Remove multi-tool search** | Single-tool search would have limited coverage. Multi-tool is essential. | Skip |
| 5 | **Real-time collaboration** | Multi-user research would require complex state synchronization. Out of scope. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
