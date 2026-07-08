<- Back to [LLM Overview](../LLM.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.2.1 | 2026-07-08 | **Hardening fixes (from cross-LLM review):** P0: Router schema now includes `confidence` + `clarifying_questions` (was missing — `additionalProperties: False` blocked the model from generating those fields). P0: `if json_schema:` → `if json_schema is not None:` in both providers (empty dict `{}` is falsy). P0: `payload.update(kwargs)` moved before `response_format` in both providers (was after — kwargs could silently override response_format). P1: 400 fallback — catch 400 with `response_format` in error, strip json_schema, retry with json_mode. P1: Circuit breaker no longer records failures for 4xx client errors (only 5xx + 429). P1: Escalation passes `json_schema=None` (was using plan schema — wrong). P1: `_ensure_role_sets_initialized()` uses double-checked locking (was unlocked race condition). P1: `_json_roles` now includes roles with `json_schema` but no `json_mode`. P1: Removed redundant `json_mode=True` from `distiller.py`. |
| v1.2 | 2026-07-08 | **JSON schema enforcement:** Added `json_schema` param to `complete()`, `call()`, and `chat_completion()`. When provided, providers send `response_format={"type":"json_schema","json_schema":{"schema":{...}}}` (LM Studio enforces via outlines internally). Stronger than `json_mode` (which only ensures valid JSON, not schema). `json_schema` takes precedence over `json_mode` when both are set. `json_schema` implies `json_mode` for response parsing. Backward compatible — defaults to `None`. Phase 2: schemas defined for 6 agent roles (code, route, plan, review, refactor, test) + router._model_route() + autocode debug node + procedural distill + sleep_learn distiller. |
| Pre-v1 | 2026-07-04 | Initial implementation. Role-based dispatch, circuit breaker per role, cognitive context budgeting, provider abstraction, thread-safe singleton. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Role-based dispatch | ✅ Pre-v1 | 16 roles with independent temperature/max_tokens |
| Circuit breaker per role | ✅ Pre-v1 | 3 cumulative failures, dynamic cooldown per role |
| Cognitive context budgeting | ✅ Pre-v1 | 7-tier `ContextClass` in `core/memory_backend/budget.py` |
| Provider abstraction | ✅ Pre-v1 | `BaseProvider` + `LMStudioProvider` + `OpenAICompatibleProvider` |
| Thread-safe singleton | ✅ Pre-v1 | `LLMClient` singleton with double-checked locking |
| Dual JSON extraction | ✅ Pre-v1 | `client.py` 3-layer + `router.py` `raw_decode()` |
| Dynamic factory registration | ✅ Pre-v1 | Auto-registers cloud providers based on `*_API_KEY` env vars |
| Token tracking | ✅ Pre-v1 | Prometheus metrics via `core/metrics.py` |
| json_schema adopted by callers | ✅ v1.2 (Phase 2) | 6 agent roles + router + debug + distill + sleep_learn |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `complete_with_tools()` | Tool-calling loop not yet implemented at this layer | P1 |
| YAML-based prompt loader | Currently system prompts are plain Python string constants | P3 |
| Decouple circuit breaker cooldown from role timeout | Cooldown is tied to `role_cfg.timeout` — a change to timeout silently changes cooldown | P2 |
| Enable `/health/circuit-breakers` by default | Currently returns `null` unless `cfg.enable_metrics_endpoint` is set | P2 |
| Fix `PROCEDURAL` vs `ERROR` tier weight | `PROCEDURAL` (50.0) outranks `ERROR` (40.0) but docstring claims the opposite | P3 |
| Fix stale docstring paths | `memory_backend/budget.py` still references `core/context_budget.py` | P3 |
| Provider capability detection | `supports_json_schema()` method on `BaseProvider` — detect at runtime whether provider supports json_schema, gracefully fall back to json_mode. Avoids 400 errors on older LM Studio / cloud providers. | P2 |
| OpenAI `name` field in json_schema | OpenAI's API requires a `name` field in `json_schema` response_format. LM Studio doesn't. Add `name` for OpenAI-compat provider. | P2 |
| Phase 3: consolidate defensive JSON parsing | 3 separate JSON extraction implementations (client.py 3-layer, agent_ops/json_extract.py brace-counting, router.py raw_decode). Consolidate into one shared `core/json_extract.py` module. | P2 |
| Phase 2 tests | Tests for: dispatch.py schema flow, router schema/prompt match, review enum handling, empty output handling, schema rejection fallback, nested schema validation, null type, concurrent calls with different schemas. | P2 |
| Post-parse enum validation | Runtime validation for enum values (e.g., review `verdict`) when schema enforcement fails and defensive parsing produces the JSON. | P3 |
| Centralize schemas | Schemas scattered across 10 files. Consider `core/schemas/` directory or registry for consistency. | P3 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
