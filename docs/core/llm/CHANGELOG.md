<- Back to [LLM Overview](../LLM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.4** | 2026-07-16 | **`complete_with_tools()` — native LLM tool-calling loop.** (1) New `ToolCall` dataclass + `tool_calls` field on `LLMResponse` (backward-compatible default `[]`). (2) New `core/llm_backend/tools.py` — `ToolDefinition` + `tool_def_from_meta_tool()` (generates 1 tool def per `@meta_tool`, not per action) + provider converters. (3) All 3 providers accept `tools` kwarg: OpenAI (native), Anthropic (reuse tool-use plumbing), Gemini (`functionDeclarations` + position-based synthetic IDs). (4) `_parse_response()` handles `content=None` + extracts `tool_calls`. (5) `complete_with_tools()` loop: `max_iterations=10`, `max_consecutive_errors=3`, token aggregation, cancellation check. (6) `tool_calling_mode` config. 26 new tests. |
| **v1.3** | 2026-07-14 | **Native json_schema for Claude/Gemini + provider capabilities + complete_provider() API.** (1) #41: `supports_json_schema()` on `BaseProvider` — callers can check before passing schema. (2) #39: Claude — json_schema → Anthropic tool-use conversion (define tool with `input_schema`, force `tool_choice`, extract `tool_use` block's `input` as JSON). (3) #40: Gemini — json_schema → `responseSchema` conversion (strip `additionalProperties`/union types, set `responseMimeType=application/json`). (4) #42: OpenAI — `name` field + `strict: True` in `response_format` for tracing. (5) #43: Post-parse enum validation — `_validate_enum_constraints()` walks schema recursively, graceful degradation on failure. (6) #22: `llm.complete_provider()` — provider-direct calls with circuit breaker + telemetry. Swarm's `_call_provider()` now delegates to it. |
| v1.2.2 | 2026-07-08 | **4 new cloud providers.** Claude (Anthropic, native), Gemini (Google, native), Z.ai/GLM (OpenAI-compatible), MiMo/Xiaomi (OpenAI-compatible). Claude and Gemini ignore `json_schema` in Phase 1 (fall back to `json_mode` — native schema support deferred). All use httpx directly (no SDK dependencies). |
| v1.2 | 2026-07-08 | **JSON schema enforcement.** Added `json_schema` param to `complete()`, `call()`, and `chat_completion()`. LM Studio enforces via outlines. Phase 2: schemas for 6 agent roles + router + autocode debug + distill + sleep_learn. |
| Pre-v1 | 2026-07-04 | **Initial implementation.** Role-based dispatch, circuit breaker per role, cognitive context budgeting, provider abstraction, thread-safe singleton. |

---

### ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| — | `complete_with_tools()` | Tool-calling loop not yet implemented at this layer. See `INSTRUCTIONS.md` → In Progress / Next Up for the detailed roadmap. | P1 |
| ✅ #39 | **Native `json_schema` for Claude** | ✅ **Shipped in v1.3** — Anthropic tool-use conversion (define tool with `input_schema`, force `tool_choice`, extract `tool_use` block's `input` as JSON). |
| ✅ #40 | **Native `json_schema` for Gemini** | ✅ **Shipped in v1.3** — `responseSchema` conversion (strip `additionalProperties`/union types, set `responseMimeType=application/json`). |
| ✅ #41 | Provider capability detection | ✅ **Shipped in v1.3** — `supports_json_schema()` on `BaseProvider`. All providers return `True`. |
| ✅ #42 | OpenAI `name` field in json_schema response_format | ✅ **Shipped in v1.3** — `schema_name` from schema title or `"structured_output"`, plus `strict: True` for tracing. |
| — | Decouple circuit breaker cooldown from role timeout | Cooldown is tied to `role_cfg.timeout` — a change to timeout silently changes cooldown. | P2 |
| — | Enable `/health/circuit-breakers` by default | Currently returns `null` unless `cfg.enable_metrics_endpoint` is set. | P2 |
| ✅ #43 | Post-parse enum validation | ✅ **Shipped in v1.3** — `_validate_enum_constraints()` walks schema recursively, logs warning on failure (graceful degradation). |
| ✅ #22 | `llm.complete_provider()` API | ✅ **Shipped in v1.3** — provider-direct calls with circuit breaker + telemetry. Swarm's `_call_provider()` now delegates to it (with fallback to direct `provider.chat_completion()` for unit-test mocks). |
| 44 | Centralize schemas in `core/schemas/` | Single source of truth for all JSON schemas. | P3 |
| — | YAML-based prompt loader | Currently system prompts are plain Python string constants. | P3 |
| — | Fix `PROCEDURAL` vs `ERROR` tier weight | `PROCEDURAL` (50.0) outranks `ERROR` (40.0) but docstring claims the opposite. | P3 |
| — | Fix stale docstring paths | `memory_backend/budget.py` still references `core/context_budget.py`. | P3 |

---

## 🚫 Deferred / Out of Scope

| Feature | Why Deferred | Priority |
|---------|--------------|----------|
| ~~Migrate `_parse_response` JSON extraction to `core/json_extract.py`~~ | ✅ Done — `_parse_response` now calls `extract_first_json()`. All 3 JSON extraction implementations consolidated. | ~~P2~~ Done |

---

*Last updated: 2026-07-14 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
