<- Back to [Consult Overview](../CONSULT.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never bypass `@meta_tool` for action dispatch** — the v1.0 refactor reversed the Pre-v1 rule. Every action MUST be registered via `@register_action("consult", "<name>", ...)` in `consult_ops/actions/<name>.py`. The `action: Literal[...]` annotation and docstring action list are auto-generated from `DISPATCH` — do not hand-write them in `tools/consult.py`.
2. **Never call `llm.complete()` directly from an action handler** — always go through `helpers._call_consultor(system, user, context, trace_id)`. Direct `llm.complete()` calls bypass the conftest patch surface and break testability (see Anti-Patterns #1 below).
3. **Never add a new action without `@register_action`** — dropping a `.py` file in `consult_ops/actions/` without the decorator is a silent no-op: the file is auto-imported by `__init__.py`, but the handler is never registered in `DISPATCH`, so callers get `Unknown action`. The decorator is the contract.
4. **Never hardcode model names** — always use `cfg.consultor_model` / `cfg.model_registry["consultor"]` (via `_get_consultor_provider()` helper). Hardcoded model strings break the kill-switch and provider isolation.
5. **Never remove the kill-switch check** — the `_check_consultor_available()` call is the first thing every handler runs after validating `question`. The tool must degrade gracefully to `status=disabled` when the consultor stack is unconfigured.
6. **Never bypass `_check_rate_limit()`** — always gate cloud calls behind the rate-limit pre-flight. The wrapper centralizes provider-name lookup so handlers don't poke `cfg.model_registry` directly.
7. **Never increase `_MAX_CONTEXT_TOKENS` without explicit user approval** — 2000 is a deliberate safety rail against context-window overruns and prompt-injection-via-oversized-input attacks.
8. **Never skip the `question` empty-check in a handler** — return `{"status": "error", "error": "The question parameter cannot be empty.", "trace_id": trace_id}` before any pre-flight. This is the handler's contract with the facade.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never create `.bak` files** — forbidden by project rules.
11. **Never rewrite the entire facade (`tools/consult.py`) for a new action** — surgical edits only. New actions go in `consult_ops/actions/<name>.py`; the facade's `action: Literal[...]` and docstring update themselves via `@meta_tool`.
12. **Never add `**kwargs` to the `@tool @meta_tool` facade** — FastMCP schema breaks. All params must be explicit named kwargs.
13. **Never collapse the three return statuses** — `success`, `disabled`, `rate_limited`, `error` are distinct. Do not merge `disabled` into `error`; downstream callers (router, workflows) branch on these.

## ✅ ALWAYS DO

14. **Always include `trace_id` in every return path** — when the caller passed a non-empty `trace_id`, every response (success, disabled, rate_limited, error) MUST echo it back. Workflow tracing depends on this. The facade handles facade-level errors; handlers handle their own returns.
15. **Always include `warnings` when context is truncated** — `_truncate_context()` returns `(context, warnings)`; only attach `warnings` to the response when the list is non-empty. Empty `warnings` would pollute the response shape.
16. **Always set `duration_ms` on the response** — the facade does this unconditionally after the handler returns. Do not override it in handlers. Even error returns carry timing.
17. **Always use `compileall` before `pytest`** — catches syntax errors early across the 8-file subpackage.
18. **Always test the kill-switch path** — patch `tools.consult_ops.helpers.cfg.consultor_model = ""` and assert `status == "disabled"`. Patch via the `helpers` module, not `core.config` (see Anti-Patterns #1).
19. **Always test the rate-limit path** — patch `tools.consult_ops.helpers.check_rate_limit` to `False` and assert `status == "rate_limited"`.
20. **Always test `format` and `context_type` params** — for each action, verify that `format="json"` appends the JSON suffix and `context_type="code"` appends the code modifier to the system prompt passed to `_call_consultor`. The `test_advise.py` / `test_review.py` / `test_explain.py` `Format` and `ContextType` classes are the contract.
21. **Always add a test class for any new action** — mirror the 8-class structure (`Success` / `Disabled` / `RateLimited` / `LLMError` / `ContextTruncation` / `TraceID` / `Format` / `ContextType`). Skipping any class leaves a coverage hole.
22. **Always register new actions with help text + examples** — `@register_action("consult", "<name>", help_text=..., examples=[...])`. The help text feeds the auto-generated docstring; the examples show up in the `@meta_tool` doc_sections.
23. **Always preserve the handler signature `(question, context, trace_id, format, context_type, **kwargs)`** — the facade calls every handler with these exact kwargs. Adding handler-specific params requires either extending the facade (rare) or using `**kwargs` to absorb extras. Never break the shared signature.
24. **Always update this doc** when adding params, changing return shapes, modifying behavior, or discovering a new anti-pattern.

---

## 🚫 Anti-Patterns & Lessons Learned

### #1 — Direct `llm.complete()` calls in action handlers (DISCOVERED DURING v1.0 REFACTOR)

> - **What happened:** The first v1.0 test run had 43 failures. Action handlers did `from core.llm import llm` and called `llm.complete(...)` directly. The conftest fixture `mock_llm` patches `tools.consult_ops.helpers.llm`, but the handlers' local `llm` binding was unaffected — they kept calling the real (unconfigured) LLMClient.
> - **Why it matters:** Python's `from X import Y` creates a local binding at import time. Patching `X.Y` later has no effect on already-imported local references. The tests appear to "pass" the patch but the handler bypasses it silently — leading to mysterious failures that look like config issues but are actually import-binding issues.
> - **Fix:** Added `helpers._call_consultor(system, user, context, trace_id)` which calls `llm.complete(role="consultor", ...)`. Refactored all 3 action handlers to call `_call_consultor()` instead of `llm.complete()` directly. After the refactor, `_call_consultor` looks up `llm` in the `helpers` module namespace at call time (not import time), so patching `tools.consult_ops.helpers.llm` transparently intercepts every LLM call. Failures dropped 43 → 6 (all tiktoken-related) → 0.
> - **Generalization:** this applies to *every* external dependency accessed from action handlers — `cfg`, `llm`, `check_rate_limit`. Centralize access in `helpers.py` so conftest only needs 3 patch points (`mock_cfg`, `mock_llm`, `mock_budget`) to control all 4 dependencies.

### #2 — Hand-writing the `action: Literal[...]` annotation in the facade

> - **What happened:** (Hypothetical — caught during review.) A maintainer adds a 4th action `compare` and manually edits `tools/consult.py` to add `"compare"` to the `Literal`. The next session adds a 5th action and forgets to update the facade — callers get `Unknown action 'compare'` even though the handler is registered.
> - **Why it matters:** The facade annotation is the LLM's schema. If it drifts from `DISPATCH`, the LLM is told an action exists that the runtime can't dispatch (or vice versa).
> - **Fix:** Never hand-write the `Literal`. `@meta_tool` generates it from `DISPATCH.get("consult", {})` keys. Adding a new action = drop a file in `consult_ops/actions/` with `@register_action`. The facade updates itself.

### #3 — Mutating the base system prompts at runtime

> - **What happened:** (Hypothetical.) A handler does `ADVISE_SYSTEM_PROMPT += "\n\nExtra rules..."` to inject caller-specific guidance. The next call sees the polluted prompt because the module-level string was mutated.
> - **Why it matters:** Module-level strings are shared across all calls in the process. Mutation = state leak = nondeterministic behavior.
> - **Fix:** Base prompts are immutable strings. Format and context-type customization happens via *suffix concatenation* (`BASE + FORMAT_SUFFIXES[format] + CONTEXT_TYPE_MODIFIERS[context_type]`) inside the handler — never via mutation. If a caller needs custom rules, add a new `context_type` modifier to `prompts.py`.

### #4 — Adding `provider` / `model` to facade-level error responses

> - **What happened:** (Hypothetical.) A maintainer adds `"provider": "unknown"` to the empty-action error response "for consistency". This pollutes the error schema and breaks callers that branch on `if "provider" in result`.
> - **Why it matters:** Facade-level errors (bad `action`, exception in handler) happen *before* the consultor role is resolved. There is no provider to report. Handlers add `provider`/`model` only on errors that occur after `_get_consultor_provider()` has run.
> - **Fix:** Facade errors carry `status`, `error`, `trace_id` (and `duration_ms`). Handler errors carry `status`, `error`, `provider`, `model`, `trace_id` (and `duration_ms`). Do not unify the schemas.

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
