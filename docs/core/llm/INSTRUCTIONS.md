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
10. **Never use `json_mode` when you know the schema** — v1.2: Prefer `json_schema` over `json_mode` when the expected JSON structure is known. `json_mode` only ensures valid JSON; `json_schema` enforces the schema at generation time (LM Studio uses outlines internally). This eliminates the need for defensive parsing.
11. **Never remove the defensive JSON parsing in `_parse_response`** — v1.2: The 3-layer JSON extraction (direct parse → markdown fence → regex) is the fallback when schema enforcement fails or isn't available (cloud providers, older LM Studio). Schema enforcement makes it a safety net, not the primary path — but it must stay.

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
20. **Always prefer `json_schema` over `json_mode` when the schema is known** — v1.2: `json_schema` enforces structure at generation time; `json_mode` only ensures valid JSON. Use `json_schema` for all new JSON-returning roles (router, executor code, debug, distill, etc.).
21. **Always keep defensive JSON parsing as a fallback** — v1.2: Schema enforcement can fail (cloud provider doesn't support it, LM Studio version too old, model too small). The 3-layer extraction in `_parse_response` catches these cases. Never remove it.

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** The codebase had 7+ places with defensive JSON parsing (brace-counting, markdown fence extraction, regex fallbacks, `raw_decode()` scanning) because `json_mode` only ensures valid JSON — not schema conformance. Models could output `{"random": "stuff"}` when `{"root_cause": "...", "fix": "..."}` was expected.
> - **Why it matters:** Small models (gemma-2-2b, lfm2-1.2b) used for executor/router roles frequently produce malformed JSON or schema-wrong JSON. The defensive parsing catches the syntax issues but can't fix schema-wrong output — the caller gets a dict with missing/wrong keys.
> - **Fix (v1.2):** Added `json_schema` param to `complete()`/`call()`/`chat_completion()`. When provided, LM Studio enforces the schema at generation time via outlines — the model literally cannot generate schema-invalid output. The defensive parsing stays as a fallback for providers that don't support `json_schema`. Phase 2 complete: schemas defined for 6 agent roles (code, route, plan, review, refactor, test) + router._model_route() + autocode debug node + procedural distill + sleep_learn distiller.

> - **What happened:** Router schema defined 4 fields (`workflow`, `tool`, `complexity`, `reason`) with `additionalProperties: False`, but `ROUTER_SYSTEM_PROMPT` told the model to output 6 fields (also `confidence`, `clarifying_questions`). Outlines blocked the model from generating the extra 2 fields. `RoutingDecision` always defaulted to `confidence="medium"` and `clarifying_questions=[]` — the confidence-based routing logic was silently broken.
> - **Why it matters:** Schema and system prompt MUST match. When `additionalProperties: False` is set, every field the system prompt mentions must be in the schema — or outlines will block the model from generating it. The model gets contradictory instructions: "output confidence" (prompt) vs "you cannot output confidence" (schema).
> - **Fix (v1.2.1):** Added `confidence` and `clarifying_questions` to the router schema. Always verify schema fields match system prompt fields when using `additionalProperties: False`.

> - **What happened:** `if json_schema:` used truthy check instead of `if json_schema is not None:`. An empty dict `{}` is a valid JSON Schema (accepts anything) but is falsy in Python — it would fall through to `json_mode` instead of being sent as a schema.
> - **Why it matters:** Truthy checks on dicts are a Python gotcha. Always use `is not None` for optional dict parameters.
> - **Fix (v1.2.1):** Changed to `if json_schema is not None:` in both providers.

> - **What happened:** `payload.update(kwargs)` was called AFTER setting `response_format`. If any caller passed `response_format` in kwargs, it silently overwrote the schema enforcement.
> - **Why it matters:** Order matters when merging dicts. Always merge user-provided kwargs FIRST, then set your own fields that shouldn't be overridden.
> - **Fix (v1.2.1):** Moved `payload.update(kwargs)` before the `response_format` assignment in both providers.

> - **What happened:** Escalation to planner passed `json_schema=plan_cfg.get("json_schema")` — the PLAN schema, not the original role's schema. If the `code` role failed, the escalation forced the planner to output a plan structure (goal/steps/risks), not a code patch (analysis/patch/assumptions/tests).
> - **Why it matters:** When escalating to a different model, the schema must match what the CALLER expects, not what the escalation model's role normally produces. Using the wrong schema produces structurally valid but semantically wrong output.
> - **Fix (v1.2.1):** Escalation now passes `json_schema=None` — no schema enforcement on escalation. The planner produces freeform JSON, and the defensive parsing handles it. This is the safest approach because the planner model may not produce good results with a different role's schema.

> - **What happened:** `HTTPStatusError` handler recorded circuit breaker failures for ALL HTTP errors, including 4xx client errors (400 = bad request, 401 = auth, 403 = forbidden). A 400 from an unsupported `json_schema` would count as a failure — after 3 such failures, the circuit breaker opened and the role became unavailable.
> - **Why it matters:** Circuit breakers are for SERVER availability issues (5xx, 429). Client errors (4xx) are not retriable and don't indicate the server is down. Recording them as breaker failures causes false circuit-open events.
> - **Fix (v1.2.1):** Circuit breaker now only records failures for status codes >= 500. 4xx errors are logged but don't trigger the breaker.

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
