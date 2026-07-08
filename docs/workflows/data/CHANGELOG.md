<- Back to [Data Overview](../DATA.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.1 | 2026-07-08 | **Wired `trim_state_node`:** Added trim node between critique and store. After critique produces `result`, oversized `output` is evicted to episodic memory (chonkie-aware — splits into chunks, evicts each individually, keeps first chunk as preview). Falls back to whole-string eviction if chonkie is missing. Uses `trim_state_node()` from `workflows/base.py` (v1.3). Graph: `recall → execute → critique → trim → store → notify`. First workflow to wire in `trim_state()` (see `base/CHANGELOG.md` #18). |
| v1.0 | 2026-07-06 | **Subpackage split:** Split monolithic `workflows/data.py` (231 lines) into `workflows/data_impl/` subpackage with per-node modules (`recall`, `execute`, `critique`, `store`, `notify`). Added `WORKFLOW_METADATA` for MCP client introspection. Thin facade re-exports `build_data_graph`, `WORKFLOW_METADATA`. Tests split into per-node files + `conftest.py` + `TestSubpackageStructure`. Applied 12 audit fixes (see below). |
| Pre-v1.0 | 2026-07-05 | Bug fix: `node_execute` and `node_critique` now call `agent(action="dispatch", ...)` (was missing `action`, always returned `Unknown action ''`). |

---

## ⚠️ Breaking Changes

### v1.0 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| Monolithic `workflows/data.py` → `data_impl/` subpackage | Node functions moved to `workflows/data_impl/nodes/<node>.py`. | Import nodes from `workflows.data_impl.nodes.<node>` (the facade no longer re-exports individual nodes — same as `research_impl`). `build_data_graph` and `WORKFLOW_METADATA` still importable from `workflows.data`. |
| `route_after_critique` removed | It was dead code (always returned `"store"`). | `critique` → `store` is now a direct edge. No caller used `route_after_critique`. |
| Nodes return partial dicts (not `{**state, ...}`) | LangGraph best practice — only changed keys. | No migration — callers consume the merged final state from `graph.invoke()`. |
| `node_critique` uses `context=` (was `content=`) | `content` is for base64 images; `context` is for text. | No migration — both flow to `llm.complete()`, but `context` is the primary text channel. |
| New state key `code_generated` | Set by `node_execute`, read by `node_store`. | No migration — flows as a plain dict key; not in the `WorkflowState` TypedDict. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Subpackage split (v1.0 pattern) | ✅ v1.0 | `data_impl/` with `graph.py`, `routes.py`, `helpers.py`, `nodes/` |
| `WORKFLOW_METADATA` | ✅ v1.0 | MCP client introspection (nodes + conditional edges) |
| Partial-dict node returns | ✅ v1.0 | [Fix #1] No more `{**state, ...}` |
| Code-gen failure routes to END | ✅ v1.0 | [Fix #2] Both failure paths set `exec_error` |
| Execution failure logged via `node_error` | ✅ v1.0 | [Fix #3] Trace + checkpoint (was only `node_step`) |
| `context=` for critique text | ✅ v1.0 | [Fix #4] `content=` was for images |
| Procedural memory only for generated code | ✅ v1.0 | [Fix #5] `code_generated` flag gates `store_procedural` |
| Empty-output critique skip logged | ✅ v1.0 | [Fix #6] Was silent `return state` |
| Critique failure logged via `tracer.error` | ✅ v1.0 | [Fix #7] Was silent fallback |
| Exception isolation (memory/notify/agent) | ✅ v1.0 | [Fix #8] `try/except` + `tracer.error`, non-fatal |
| Observable code extraction | ✅ v1.0 | [Fix #9] `_extract_code_from_response` helper, `tracer.warning` on fallback |
| Dead `route_after_critique` removed | ✅ v1.0 | [Fix #10] Direct `critique` → `store` edge |
| `notify()` failure non-fatal | ✅ v1.0 | [Fix #10] `node_done` always reached |

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
|---|---------|------------|----------|
| 1 | **Remove memory integration** | Memory recall improves code quality. | Skip |
| 2 | **Remove critique node** | Critique provides quality assurance. | Skip |
| 3 | **Support non-Python languages** | The workflow is specifically for Python data analysis. | Skip |
| 4 | **Real-time streaming output** | Would require WebSocket/SSE infrastructure. | Skip |

---

*Last updated: 2026-07-06 (v1.0 split). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
