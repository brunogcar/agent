<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.1 | 2026-07-06 | **Metadata + citations + P0/P1 fixes + trim analysis:** Added `WORKFLOW_METADATA` for MCP client introspection. Wired the citation tracker into `_node_report` + `_node_notify` (sources were collected by `node_search` and discarded). Fixed P0 #2 (`task`/`content` swap in `node_synthesize`), P0 #4 (API budget decremented on Tavily attempt not success), P1 #6 (removed `_agent_ok`/`_agent_text` dead wrappers), P1 #7 (partial-dict returns), P1 #8 (`_node_recall` logs memory failures), P1 #10 (`_node_store` full result, no 800-char truncation), P1 #22 (`synthesis` field declared in state). **Trim analysis:** `trim_state()` not wired in — deep_research already bounds its state (`knowledge_base` capped at 6000 chars via `_cap_knowledge()`, `extracted_evidence` cleared each iteration by synthesize). Evicting `knowledge_base` would break convergence detection (routes.py compares `_prev_knowledge` vs `knowledge_base`). See `docs/workflows/base/CHANGELOG.md` #18. |
| v1.0.2 | 2026-07-05 | **Bug fix:** API budget (`budget_api_calls`) now only decremented for Tavily searches, not web (SearXNG) searches. |
| v1.0.1 | 2026-07-05 | **Bug fix:** Both `agent()` calls in `node_synthesize` now pass `action="dispatch"`. Removed dead `completeness_threshold = 0.85` local. |
| v1.0 | — | Released — 8-node cyclic LangGraph StateGraph with budget management, convergence detection, multi-tool search, and memory integration |

---

## ⚠️ Breaking Changes

### v1.1 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| `_node_*` helpers return partial dicts (was `{**state, ...}`) | LangGraph best practice — only changed keys. | No migration — callers consume the merged final state from `graph.invoke()`. |
| `_node_store` stores full result (was `result[:800]`) | Semantic memory now holds complete research. | No migration — larger stored text is the intended improvement. |
| `_node_notify` returns `artifacts` (source URLs) | Was `return state`. | No migration — callers read `result["artifacts"]`; was always empty before. |
| `node_synthesize` uses `task=` for user instruction, `context=` for system prompt | Was swapped (`task=`=system prompt, `content=`=user instruction). | No migration — the old mapping was broken (system prompt landed in `user=` slot). |
| API budget decrements on Tavily ATTEMPT, not success | Failed Tavily calls now correctly consume budget. | No migration — more accurate tracking. |
| Removed `_agent_ok` / `_agent_text` wrappers | Dead code handling a legacy `LLMResponse` shape. | If external code imported them, inline the `dict` access (`result.get("status") == "success"`, `result.get("text", "")`). |

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
| `agent()` passes `action="dispatch"` | ✅ v1.0.1 | Both synthesize + evaluate calls (was missing) |
| API budget only for Tavily, not web | ✅ v1.0.2 | Web (SearXNG) is free; only Tavily decrements |
| `WORKFLOW_METADATA` | ✅ v1.1 | MCP client introspection (8 nodes, cyclic edges) |
| Citations wired into report + notify | ✅ v1.1 | Sources collected by `node_search` now surface in report + artifacts |
| `task`/`content` swap fixed in synthesize | ✅ v1.1 | P0 #2 — `task=`=user instruction, `context=`=system prompt |
| API budget on Tavily attempt | ✅ v1.1 | P0 #4 — failed Tavily calls now consume budget |
| `_agent_ok`/`_agent_text` removed | ✅ v1.1 | P1 #6 — dead wrappers for legacy `LLMResponse` shape |
| Partial-dict returns in graph nodes | ✅ v1.1 | P1 #7 — no more `{**state, ...}` |
| `_node_recall` logs memory failures | ✅ v1.1 | P1 #8 — was silent `except: pass` |
| `_node_store` full result | ✅ v1.1 | P1 #10 — was `result[:800]` (truncated semantic memory) |
| `synthesis` field in state | ✅ v1.1 | P1 #22 — was returned by `node_synthesize` but undeclared |
| Trim analysis (not needed) | ✅ v1.1 | `trim_state()` not wired — `knowledge_base` already capped at 6000 chars, `extracted_evidence` cleared each iteration. Evicting `knowledge_base` would break convergence detection. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 9 | **`_node_report` empty report not handled** | Empty `knowledge_base` + `synthesis` produces empty report with `"incomplete"` status. | P1 |
| 11 | **`route_after_synthesize` recomputing `converged`** | Already computed in `node_synthesize`. Redundant and may diverge. | P1 |
| 12 | **Remove `format_audit` dead code** | Function exists but never called. | P3 |
| 13 | **Remove `JS_HEAVY_HINTS` dead code** | Defined in `constants.py` but never used. `search.py` uses hardcoded indicators. | P2 |
| 14 | **Fix `_parse_sub_queries` regex fragility** | Character class `r'[\-*•]'` has unnecessary escape. May emit `SyntaxWarning`. | P1 |
| 15 | **Fix `_parse_sub_queries` trailing comma handling** | LLMs may output trailing commas in JSON. `json.loads` rejects them. | P1 |
| 16 | **`node_search` hardcoded `max_results=5`** | Should be configurable via `.env`. | P2 |
| 17 | **`node_search` not filtering empty queries** | Empty strings in `queries` cause searches for `""`. | P2 |
| 18 | **`_summarize_evidence` bypassing role config** | Uses custom system prompt instead of role's configured prompt. | P2 |
| 19 | **`_extract_evidence` hardcoded top 3** | Should be configurable. | P2 |
| 20 | **`_parse_score` removing negative numbers incorrectly** | `re.sub(r"-\d+", "", text)` removes numbers from ranges like "85-90". | P1 |
| 21 | **`_cap_knowledge` may exceed max after prefix** | Truncation + prefix may exceed `max_chars`. | P2 |
| 24 | **Configurable convergence threshold** | Make `CONVERGENCE_SIMILARITY_THRESHOLD` actually use `.env` value | P2 |
| 25 | **Streaming synthesis** | Stream synthesis output for real-time feedback | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove cyclic workflow** | Single-pass research would miss important information. Iteration is essential. | Skip |
| 2 | **Remove budget management** | Budget tracking prevents runaway costs. | Skip |
| 3 | **Remove convergence detection** | Without it, the workflow would run indefinitely or stop prematurely. | Skip |
| 4 | **Remove multi-tool search** | Single-tool search would have limited coverage. | Skip |
| 5 | **Real-time collaboration** | Multi-user research would require complex state synchronization. | Skip |

---

*Last updated: 2026-07-06 (v1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
