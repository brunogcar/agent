<- Back to [Workflow Overview](../WORKFLOW.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add a workflow type to `VALID_WORKFLOWS` without adding tests** — new types need validation, parameter guards, and execution coverage.
2. **Never remove the type allowlist** — `VALID_WORKFLOWS` is the primary defense against LLM hallucination of non-existent workflows.
3. **Never remove fail-fast parameter guards** — Autocode must validate `target_file`, `error_msg`, `feature_desc` BEFORE any filesystem mutation.
4. **Never remove the trace_id guarantee** — Every response must contain `trace_id`. Auto-generate if not provided.
5. **Never remove the router confidence guard** — Low-confidence auto-routing must abort with clarifying questions, not proceed blindly.
6. **Never hardcode workflow names** — use `VALID_WORKFLOWS` constant.
7. **Never print to stdout** — MCP stdio corruption. Return dicts only.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
10. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
11. **Never remove lazy router import** — `core.router` must stay inside the `auto` branch to prevent startup circular dependencies.
12. **Never skip `compileall` before `pytest`** — catches syntax errors early.

## ✅ ALWAYS DO

13. **Always test the kill-switch paths** — invalid type, missing goal, missing autocode params, missing understand params.
14. **Always test auto-routing** — direct, low confidence, success paths.
15. **Always test trace_id propagation** — auto-generation when not provided, preservation when provided.
16. **Always test execution failure** — mock `run_workflow` with `side_effect=Exception` and verify error response.
17. **Always include `valid_types` in type validation errors** — helps the LLM correct itself.
18. **Always update this doc** when adding workflow types, changing parameters, or modifying routing logic.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
