<- Back to [LLM Overview](../LLM.md)

# 🛡️ AI LLM Instructions

## ❌ NEVER DO

1. **Never bypass circuit breakers** — always check `breaker.can_execute()` before making LLM calls.
2. **Never remove the `_lock` from `CircuitBreaker` or `LMStudioProvider`** — thread safety depends on these locks.
3. **Never hardcode provider names in business logic** — always use the `provider` field from `RoleConfig`.
4. **Never construct raw HTTP requests to the LLM server** — always use `llm.complete(role="...", ...)` or `llm.call(role="...", ...)`.
5. **Never bypass `complete_with_tools()` for multi-turn tool calling** — `complete_with_tools()` (v1.4) is the canonical native tool-calling loop. The legacy JSON-parsing path in `subagent.py` (`_run_multi_turn`) is a fallback for models that don't support native tool calling. Use `complete()` + `call()` for single-turn calls.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never use `json_mode` when you know the schema** — v1.2: Prefer `json_schema` over `json_mode` when the expected JSON structure is known. `json_mode` only ensures valid JSON; `json_schema` enforces the schema at generation time (LM Studio uses outlines internally). This eliminates the need for defensive parsing.
11. **Never remove the defensive JSON parsing in `_parse_response`** — v1.2: The 3-layer JSON extraction (direct parse → markdown fence → regex) is the fallback when schema enforcement fails or isn't available (cloud providers, older LM Studio). Schema enforcement makes it a safety net, not the primary path — but it must stay.
12. **Never assume Claude/Gemini silently ignore `json_schema`** — v1.3: All providers support `json_schema` natively. Claude uses Anthropic tool-use conversion (define tool with `input_schema`, force `tool_choice`, extract `tool_use` block's `input` as JSON); Gemini uses `responseSchema` conversion (strip `additionalProperties`/union types, set `responseMimeType=application/json`). OpenAI-compatible providers send `response_format={"type":"json_schema",...}` with a `name` + `strict: True`. Always test with real API keys before relying on schema enforcement.

## ✅ ALWAYS DO

10. **Always use role-based calls** — `llm.complete(role="...", ...)` or `llm.call(role="...", ...)`.
11. **Always make new sub-role models fall back to `executor_model`** — not `planner_model`. Planner is expensive.
12. **Always log every call via `tracer.step()`** with `trace_id`.
13. **Always use `core/json_extract.py` for LLM JSON extraction** — `client.py` and `router.py` both delegate to it. Don't introduce a third approach. **[Autocode v2.0]** Migration complete: `_parse_response` now calls `extract_first_json()` instead of its own 60-line inline regex. Schema validation for tool calls stays in `_parse_response` (llm-backend-specific).
14. **Always go through `core/memory_backend/budget.py`'s `budget_messages()`** for context truncation — never raw-truncate messages. (Not `llm_backend/context_budget.py` — that file doesn't exist.)
15. **Always use `CHARS_PER_TOKEN = / 3.5` for budgeting decisions** — the `// 4` estimates in `client.py` debug log and `rate_limit.py` are unrelated to what gets kept/trimmed.
16. **Always read timeout from `cfg.model_registry[role]["timeout"]`** — single source of truth in `core/config.py`. Never add timeout to `llm_backend/config.py`.
17. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
18. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
19. **Always update this doc** when adding roles, changing response shapes, or modifying circuit breaker behavior.
20. **Always prefer `json_schema` over `json_mode` when the schema is known** — v1.2: `json_schema` enforces structure at generation time; `json_mode` only ensures valid JSON. Use `json_schema` for all new JSON-returning roles (router, executor code, debug, distill, etc.).
21. **Always keep defensive JSON parsing as a fallback** — v1.2: Schema enforcement can fail (cloud provider doesn't support it, LM Studio version too old, model too small). The 3-layer extraction in `_parse_response` catches these cases. Never remove it.
22. **Never call `provider.chat_completion()` directly from swarm — use `llm.complete_provider()`** — v1.3 (#22): `LLMClient.complete_provider(provider, model, messages, ...)` provides the provider-direct call path with circuit breaker integration + telemetry. Swarm's `_call_provider()` now delegates to it. Direct `provider.chat_completion()` calls bypass the circuit breaker and lose telemetry — only use from inside `complete_provider()` itself (or as a fallback for unit-test mocks that patch the method).

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** The codebase had 7+ places with defensive JSON parsing (brace-counting, markdown fence extraction, regex fallbacks, `raw_decode()` scanning) because `json_mode` only ensures valid JSON — not schema conformance. Models could output `{"random": "stuff"}` when `{"root_cause": "...", "fix": "..."}` was expected.
> - **Why it matters:** Small models (gemma-2-2b, lfm2-1.2b) used for executor/router roles frequently produce malformed JSON or schema-wrong JSON. The defensive parsing catches the syntax issues but can't fix schema-wrong output — the caller gets a dict with missing/wrong keys.
> - **Fix (v1.2):** Added `json_schema` param to `complete()`/`call()`/`chat_completion()`. When provided, LM Studio enforces the schema at generation time via outlines — the model literally cannot generate schema-invalid output. The defensive parsing stays as a fallback for providers that don't support `json_schema`. Phase 2 complete: schemas defined for 6 agent roles (code, route, plan, review, refactor, test) + router._model_route() + autocode debug node + procedural distill + sleep_learn distiller.
> - **Followup (v1.3):** Claude + Gemini now support `json_schema` natively (Claude via Anthropic tool-use conversion, Gemini via `responseSchema`). OpenAI-compatible providers send `name` + `strict: True` in `response_format`. Post-parse enum validation (`_validate_enum_constraints()`) catches schema-wrong enum values that slip through cloud providers' schema enforcement (graceful degradation — logs warning, doesn't block).

---

## ✅ Recently Completed

### `complete_with_tools()` — Native tool-calling loop (v1.4 — COMPLETE)

**Implemented in v1.4.** See [API.md](API.md) for the full signature + usage. Key design: 1 tool def per `@meta_tool` (action list in description, `action` as enum), provider adapters convert to native format, tool errors stay in-loop, `max_consecutive_errors=3` bail.

This is the next major LLM-layer feature. The detailed roadmap:

- **What.** A native tool-calling loop at the LLM layer: `complete_with_tools(tools=[...], messages=[...])` — the LLM returns `tool_calls`, the caller executes them, results are appended to messages, and the loop continues until the LLM returns a text response (no tool calls). Today the codebase fakes this via `json_schema`-enforced `{"tool": ..., "action": ..., "args": ...}` JSON parsing inside `_parse_response` — that works but requires every model to produce well-formed JSON and forces callers to do their own loop.
- **Why.** More reliable than JSON-parsing — the API enforces the tool-call format natively (no markdown fences, no prose-prefixed JSON, no half-truncated arguments). Foundation for agentic features (subagent self-routing, multi-step tool chains). The subagent ReAct loop in `core/subagent.py` could be simplified dramatically — instead of re-prompting the model with `Observation: ...` lines and parsing JSON tool calls, the loop would just dispatch the API's native `tool_calls` field. Removes an entire class of small-model JSON-formatting bugs.
- **What it touches.**
  - `BaseProvider` (`core/llm_backend/provider.py`) — add a `tools` param to `chat_completion()`.
  - All 3 provider implementations: OpenAI (`tools` + `tool_choice`), Claude (Anthropic `tools` + `tool_use` content blocks), Gemini (`functionDeclarations` + `functionCall` parts).
  - `LLMResponse` (`core/llm_backend/response.py`) — add a `tool_calls` field (list of `{name, args}`).
  - `LLMClient` (`core/llm_backend/client.py`) — new `complete_with_tools()` loop method.
  - `core/subagent.py` — simplify the ReAct loop to dispatch native `tool_calls` instead of JSON-parsed ones.
- **TOOLS.md.** When implemented, the "New Tool Checklist" needs a new entry: "Register tool definitions for `complete_with_tools()` if the tool wants to be callable by the LLM natively."

---

*Last updated: 2026-07-16 (v1.5 — provider-level tests, Literal reason, execute timeout, tool_calling_mode removed). — complete_with_tools implemented). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
