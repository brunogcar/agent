<- Back to [LLM Overview](../LLM.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.2.2 | 2026-07-08 | **4 new cloud providers:** Claude (Anthropic, native AnthropicProvider), Gemini (Google, native GeminiProvider), Z.ai/GLM (OpenAI-compatible), MiMo/Xiaomi (OpenAI-compatible). Claude and Gemini ignore `json_schema` in Phase 1 (fall back to `json_mode` — native schema support deferred). Z.ai and MiMo support `json_schema` via OpenAI-compatible API. All providers use httpx directly (no SDK dependencies). |
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

---

## 🚫 Deferred / Out of Scope

| Feature | Why Deferred | Priority |
|---------|--------------|----------|
| ~~Migrate `_parse_response` JSON extraction to `core/json_extract.py`~~ | ✅ Done — `_parse_response` now calls `extract_first_json()` from `core/json_extract.py`. All 3 JSON extraction implementations (helpers, router, llm_backend) now consolidated into one. | ~~P2~~ Done |

---

*Last updated: 2026-07-11. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
