<- Back to [Consult Overview](../CONSULT.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add an `action` param** — the tool is not multiplexed. Wait for the `@meta_tool` refactor.
2. **Never hardcode model names** — always use `cfg.consultor_model` / `cfg.model_registry["consultor"]`.
3. **Never remove the kill-switch check** — the first `if not cfg.consultor_model` guard must remain. The tool must degrade gracefully.
4. **Never bypass `check_rate_limit()`** — always gate cloud calls behind the rate-limit pre-flight.
5. **Never increase `_MAX_CONTEXT_TOKENS` without explicit user approval** — 2000 is a deliberate safety rail.
6. **Never skip `llm.is_available("consultor")`** — verify provider readiness before any network I/O.
7. **Never print to stdout** — MCP stdio corruption. Return dicts only.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
10. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.

## ✅ ALWAYS DO

11. **Always include `warnings` when context is truncated** — consumers need to know their input was pruned.
12. **Always preserve the three return statuses** — `success`, `disabled`, `rate_limited`, `error`. Do not collapse them.
13. **Always use `compileall` before `pytest`** — catches syntax errors early.
14. **Always test the kill-switch path** — patch `cfg.consultor_model = ""` and assert `status == "disabled"`.
15. **Always test the rate-limit path** — patch `check_rate_limit` to `False` and assert `status == "rate_limited"`.
16. **Always update this doc** when adding params, changing return shapes, or modifying behavior.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
