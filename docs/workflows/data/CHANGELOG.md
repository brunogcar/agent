<- Back to [Data Overview](../DATA.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| Pre-v1.0 | — | Released — 5-node LangGraph pipeline with memory, code generation, execution, critique, and notification |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. This section is reserved for future releases.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 5-node LangGraph pipeline | ✅ Pre-v1.0 | recall → execute → critique → store → notify |
| Memory recall integration | ✅ Pre-v1.0 | Phase 1: recalls relevant past analyses |
| Code generation + execution | ✅ Pre-v1.0 | Phase 2: generates Python, executes in sandbox |
| Conditional routing | ✅ Pre-v1.0 | Execution failure → END, success → critique |
| Critique review | ✅ Pre-v1.0 | Phase 3: LLM reviews output |
| Memory storage | ✅ Pre-v1.0 | Phase 4: stores semantic + procedural memory |
| User notification | ✅ Pre-v1.0 | Phase 5: notifies user of completion |
| Result compression | ✅ Pre-v1.0 | `compress_result()` prevents oversized responses |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Fix `agent()` missing `action="dispatch"`** | `node_execute` and `node_critique` call `agent()` without required `action` parameter. Always returns error. | P0 |
| 2 | **Fix code-gen failure routing to critique instead of END** | `node_execute` returns `node_error()` on failure, but `route_after_execute` checks `exec_error` (not set by `node_error`), so workflow routes to `node_critique` instead of END. | P0 |
| 3 | **Fix execution failure not calling `node_error`** | When `python()` execution fails, `node_execute` sets `exec_error` but never calls `node_error()`. No trace step, no error checkpoint. | P0 |
| 4 | **Fix `**state` spreading in all nodes** | All nodes return `{**state, ...}` which violates LangGraph best practice. Should return partial dicts with only changed keys. | P0 |
| 5 | **Add exception isolation to all nodes** | No `try/except` in any node. Tool call exceptions crash the entire workflow. | P1 |
| 6 | **Fix `content` param misused for text in `node_critique`** | `content` is documented as "base64-encoded image string". Using it for arbitrary text is a semantic mismatch. Use `context` instead. | P1 |
| 7 | **Fix procedural memory stored for user-provided code** | `node_store` stores procedural memory for ALL successful executions, not just LLM-generated code. Should distinguish. | P1 |
| 8 | **Fix regex escape inconsistency in code extraction** | `r"```python\n(.*?)\`\`\`"` has malformed escape `\`\`\``. Emits `SyntaxWarning`. Should be `r"```python\n(.*?)\n```"`. | P1 |
| 9 | **Fix silent empty output critique skip** | `node_critique` silently skips when `output` is empty. Should log reason. | P1 |
| 10 | **Handle `notify()` failure in `node_notify`** | If `notify()` raises or returns error, `node_notify` crashes or propagates error dict. | P2 |
| 11 | **Test restructure** | Split `test_data_flow.py` into per-node files + `conftest.py` | P1 |
| 12 | **Configurable code generation timeout** | Hardcoded agent timeout. Make configurable via `.env` | P2 |
| 13 | **Code extraction fallback** | If regex fails, try JSON extraction or raw text | P2 |
| 14 | **Execution retry loop** | On execution failure, retry with fix instead of ending | P3 |
| 15 | **Visualization support** | Detect matplotlib/plotly output and return as artifact | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove memory integration** | Memory recall improves code quality. Removing it would degrade results. | Skip |
| 2 | **Remove critique node** | Critique provides valuable feedback. Removing it would lose quality assurance. | Skip |
| 3 | **Add execution retry loop** | Current single-pass execution is intentional. Retry loops add complexity and may not improve reliability. | Skip |
| 4 | **Support non-Python languages** | The workflow is specifically designed for Python data analysis. Other languages would require significant changes. | Skip |
| 5 | **Real-time streaming output** | Streaming would require WebSocket or SSE infrastructure. Out of scope for current architecture. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
