<- Back to [LLM Overview](../LLM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
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
| — | `complete_with_tools()` | Tool-calling loop not yet implemented at this layer. | P1 |
| 39 | **Native `json_schema` for Claude** | Anthropic tool-use conversion (current path is prompt-injected JSON; native is more reliable). Claude currently ignores `json_schema`. | P2 |
| 40 | **Native `json_schema` for Gemini** | Gemini `responseSchema` conversion (current path is prompt-injected JSON; native is more reliable). Gemini currently ignores `json_schema`. | P2 |
| 41 | Provider capability detection | `supports_json_schema()` on `BaseProvider`. Lets callers gracefully degrade when a provider doesn't support native schema. | P2 |
| 42 | OpenAI `name` field in json_schema response_format | Structured output naming for better tracing. | P2 |
| — | Decouple circuit breaker cooldown from role timeout | Cooldown is tied to `role_cfg.timeout` — a change to timeout silently changes cooldown. | P2 |
| — | Enable `/health/circuit-breakers` by default | Currently returns `null` unless `cfg.enable_metrics_endpoint` is set. | P2 |
| 43 | Post-parse enum validation | Runtime check when schema enforcement fails (Claude/Gemini path). | P3 |
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

*Last updated: 2026-07-14. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
