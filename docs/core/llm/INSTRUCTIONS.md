<- Back to [LLM Overview](../LLM.md)

# 🛡️ AI LLM Instructions

## ❌ NEVER DO

1. **Never bypass circuit breakers** — always check `breaker.can_execute()` before making LLM calls.
2. **Never remove the `_lock` from `CircuitBreaker` or `LMStudioProvider`** — thread safety depends on these locks.
3. **Never hardcode provider names in business logic** — always use the `provider` field from `RoleConfig`.
4. **Never construct raw HTTP requests to the LLM server** — always use `llm.complete(role="...", ...)` or `llm.call(role="...", ...)`.
5. **Never add `complete_with_tools()` without verifying it doesn't exist** — confirmed not in codebase. Use `complete()` + `call()` only.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.

## ✅ ALWAYS DO

10. **Always use role-based calls** — `llm.complete(role="...", ...)` or `llm.call(role="...", ...)`.
11. **Always make new sub-role models fall back to `executor_model`** — not `planner_model`. Planner is expensive.
12. **Always log every call via `tracer.step()`** with `trace_id`.
13. **Always use the existing JSON extraction pipeline** — `client.py` uses 3-layer regex; `router.py` uses `raw_decode()`. Don't introduce a third approach.
14. **Always go through `core/memory_backend/budget.py`'s `budget_messages()`** for context truncation — never raw-truncate messages. (Not `llm_backend/context_budget.py` — that file doesn't exist.)
15. **Always use `CHARS_PER_TOKEN = / 3.5` for budgeting decisions** — the `// 4` estimates in `client.py` debug log and `rate_limit.py` are unrelated to what gets kept/trimmed.
16. **Always read timeout from `cfg.model_registry[role]["timeout"]`** — single source of truth in `core/config.py`. Never add timeout to `llm_backend/config.py`.
17. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
18. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
19. **Always update this doc** when adding roles, changing response shapes, or modifying circuit breaker behavior.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
