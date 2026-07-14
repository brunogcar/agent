<- Back to [Data Overview](../DATA.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1.1 | 2026-07-13 | **Bugfix + doc drift.** P1: `node_critique` `r['text']` → `r.get('text', '')` (KeyError). P2: ARCHITECTURE.md mermaid diagram updated to include `trim` node. DATA.md "report workflow" → "report tool". |
| v1.1 | 2026-07-06 | **Trim node wired in.** `trim_state_node` between critique and store — evicts oversized `output`. |
| v1.0 | 2026-07-06 | **Subpackage split.** Split monolithic `workflows/data.py` (231 lines) into `workflows/data_impl/` subpackage. Added `WORKFLOW_METADATA`. Applied 12 audit fixes. |
| Pre-v1.0 | 2026-07-05 | **Bug fix:** `node_execute` and `node_critique` now call `agent(action="dispatch", ...)` (was missing `action`). |

---

### ⚠️ Breaking Changes

#### v1.0 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| Monolithic `workflows/data.py` → `data_impl/` subpackage | Node functions moved to `workflows/data_impl/nodes/<node>.py`. | Import nodes from `workflows.data_impl.nodes.<node>`. `build_data_graph` + `WORKFLOW_METADATA` still importable from `workflows.data`. |
| `route_after_critique` removed | Dead code (always returned `"store"`). | `critique` → `store` is now a direct edge. No caller used `route_after_critique`. |
| Nodes return partial dicts (not `{**state, ...}`) | LangGraph best practice — only changed keys. | No migration — callers consume the merged final state from `graph.invoke()`. |
| `node_critique` uses `context=` (was `content=`) | `content` is for base64 images; `context` is for text. | No migration — both flow to `llm.complete()`, but `context` is the primary text channel. |
| New state key `code_generated` | Set by `node_execute`, read by `node_store`. | No migration — flows as a plain dict key; not in the `WorkflowState` TypedDict. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Execution retry loop** | On execution failure, retry with an LLM-generated fix instead of ending. | P3 |
| 2 | **Visualization support** | Detect matplotlib/plotly output and return as an artifact. | P3 |
| 3 | **Configurable code-gen timeout** | Hardcoded agent timeout; make configurable via `.env`. | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **Remove memory integration** | Memory recall improves code quality. | Skip |
| 2 | **Remove critique node** | Critique provides quality assurance. | Skip |
| 3 | **Support non-Python languages** | The workflow is specifically for Python data analysis. | Skip |
| 4 | **Real-time streaming output** | Would require WebSocket/SSE infrastructure. | Skip |

---

*Last updated: 2026-07-13 (v1.1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
