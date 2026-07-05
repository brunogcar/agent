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

> - **What happened:** `report` was listed in `VALID_WORKFLOWS` but no `report` workflow existed — `run_workflow()` returned "Unknown workflow type" when the LLM called `workflow(type="report")`.
> - **Why it matters:** The LLM would attempt to use `workflow(type="report")` based on the docstring, waste a turn, and get a confusing error. Report generation is a tool (`report(action="...")`), not a workflow.
> - **Fix:** Removed `report` from `VALID_WORKFLOWS`, `WorkflowType` Literal, and docstring. The `report` tool is called directly when needed.

> - **What happened:** `deep_research` workflow existed and `run_workflow()` handled it, but it was missing from `VALID_WORKFLOWS` — the LLM couldn't invoke it directly, only via `type="auto"` routing.
> - **Why it matters:** Users couldn't explicitly request deep research; they had to hope the router would pick it. For known-complex research tasks, explicit invocation is better.
> - **Fix:** Added `deep_research` to `VALID_WORKFLOWS`, `WorkflowType` Literal, and docstring.

> - **What happened:** `WorkflowType` Literal was missing `"understand"` even though `VALID_WORKFLOWS` included it — type checkers and IDE autocomplete missed it.
> - **Why it matters:** Developers writing `workflow(type="understand")` would get type errors despite the runtime accepting it.
> - **Fix:** Added `"understand"` to the `WorkflowType` Literal. The Literal now matches `VALID_WORKFLOWS` exactly.

> - **What happened:** Auto-routing low-confidence guard only aborted if `clarifying_questions` was non-empty. Low confidence with empty questions fell through to execution.
> - **Why it matters:** The guard's purpose is to prevent wasting 15+ minutes on misunderstood tasks. Empty questions shouldn't bypass that protection.
> - **Fix:** Abort on low confidence regardless of whether questions exist. Provide a default question ("Please provide more details...") when none were given.

---

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
