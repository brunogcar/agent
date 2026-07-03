<- Back to [Base Overview](../BASE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove checkpoint saving from `node_error`** — Checkpoints are the safety net for resumability.
4. **Never let `node_error` return an empty message** — The guard ensures meaningful error logs.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never return `None` from LangGraph nodes** — `node_step()` returns `None` which violates the node contract. Return `{}` at minimum.

## ✅ ALWAYS DO

10. **Always return `dict` from `node_error` and `node_done`** — Not `WorkflowState`. Partial updates only.
11. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
12. **Always validate checkpoint version** — `_checkpoint_version == 1` before resuming.
13. **Always handle unknown workflow types** — Return `"failed"` with clear error, never crash.
14. **Always test `trim_state` with oversized fields** — Assert fields are evicted and replaced with placeholder text.
15. **Always test checkpoint resumption** — Mock `get_latest` to return valid/invalid checkpoints.
16. **Always test autocode compatibility** — Assert `task` key exists when `workflow_type="autocode"`.
17. **Always update this doc** when adding fields to `WorkflowState`, changing helper signatures, or modifying dispatch logic.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for utility signatures, [CHANGELOG.md](CHANGELOG.md) for version history.*
