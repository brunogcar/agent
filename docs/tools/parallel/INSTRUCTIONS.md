<- Back to [Parallel Overview](../PARALLEL.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add runtime tool discovery** — `_TOOL_MAP` is explicit. Dynamic loading risks circular imports and non-deterministic behavior.
2. **Never expand `PARALLEL_SAFE` without testing** — Adding `git`, `memory`, or `cli` causes real-world lock collisions and data corruption.
3. **Never remove the nested-call guard** — `threading.local()` is the only protection against `parallel → parallel` deadlock.
4. **Never hardcode timeout values** — Always use `cfg.worker_timeout`. The `.env` is the single source of truth.
5. **Never use `as_completed()` for timeout** — It blocks indefinitely. Always use `concurrent.futures.wait()`.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never skip `compileall` before `pytest`** — catches syntax errors early.

## ✅ ALWAYS DO

11. **Always clamp `max_workers` to 1–8** — Both in the facade and the executor. Defense in depth.
12. **Always include `trace_id` in `fail()` and `ok()` calls** — Observability requires trace correlation.
13. **Always test the kill-switch paths** — Empty `tools`, bad types, missing `name`, unknown tool, unsafe tool.
14. **Always test the nested-call guard** — Patch `_parallel_depth.value` and assert the error message.
15. **Always test timeout behavior** — Mock `cfg.worker_timeout` to a small value and verify `not_done` futures are marked timed out.
16. **Always update this doc** when adding tools to `_TOOL_MAP`, changing `PARALLEL_SAFE`, or modifying timeout behavior.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
