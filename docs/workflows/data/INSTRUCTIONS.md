<- Back to [Data Overview](../DATA.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove memory recall from `node_recall`** — Context improves code quality significantly.
4. **Never skip `node_error` on execution failure** — Always log errors to trace and checkpoint.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`. Always pass `action="dispatch"` for LLM calls.
9. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).
10. **Never use `content=` for text in `node_critique`** — `content` is for base64 images. Use `context=` for text. [Fix #4]
11. **Never store procedural memory for user-provided code** — Check `state["code_generated"]` first. [Fix #5]
12. **Never add `route_after_critique` back** — It was dead code (always returned `"store"`). `critique` → `store` is a direct edge. [Fix #10]
13. **Never inline `import re` in a node** — Code extraction lives in `workflows/data_impl/helpers.py`. [Fix #9]
14. **Never let `notify()` failure flip a successful analysis to failed** — Wrap it in `try/except` + `tracer.error`, then still call `node_done`. [Fix #10]

## ✅ ALWAYS DO

15. **Always return a partial `dict` from nodes** — Only changed keys.
16. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
17. **Always set `exec_error` on failure in `node_execute`** — So `route_after_execute` routes to END (both code-gen and execution failures).
18. **Always test `route_after_execute` with both paths** — Assert `"failed"` (exec_error set) and `"critique"` (no exec_error).
19. **Always set `code_generated` in `node_execute`** — `True` when LLM-generated, `False` when user-provided.
20. **Always wrap `memory.*` and `notify()` in `try/except`** — Non-fatal; log via `tracer.error` and continue.
21. **Always log critique failure via `tracer.error`** — Never silently fall back to raw output.
22. **Always log the empty-output critique skip via `node_step`** — Never silent.
23. **Always patch at the SOURCE module in tests** — `tools.agent.agent`, `tools.python.python`, `core.memory_engine.memory`, `tools.notify.notify` (nodes import these inside the function body).
24. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** Code-gen failure routed to `node_critique` instead of END.
> - **Why it matters:** `node_error()` set `status:failed` but not `exec_error`; `route_after_execute` only checked `exec_error`, so the workflow tried to critique an empty output.
> - **Fix:** Both failure paths in `node_execute` now set `exec_error`. [Fix #2/#3]

> - **What happened:** Procedural memory stored user-provided code as "working generated code".
> - **Why it matters:** Polluted procedural memory with code the LLM never wrote.
> - **Fix:** `node_execute` sets `code_generated`; `node_store` gates `store_procedural` on it. [Fix #5]

> - **What happened:** `node_critique` passed the code output via `content=` (base64 image channel).
> - **Why it matters:** Semantic mismatch — `content` is for vision, `context` is for text. Both reach `llm.complete()`, but `context` is the primary text channel.
> - **Fix:** Use `context=`. [Fix #4]

> - **What happened:** A `notify()` exception crashed `node_notify` before `node_done`, so a successful analysis reported as failed.
> - **Why it matters:** Notification is post-hoc; it must not flip the workflow result.
> - **Fix:** Wrap `notify()` in `try/except` + `tracer.error`, then always call `node_done`. [Fix #10]

---

*Last updated: 2026-07-06 (v1.0 split). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
