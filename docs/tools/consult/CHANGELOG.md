<- Back to [Consult Overview](../CONSULT.md)

# 🗺️ Changelog

## 📝 Version History

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes recorded for pre-v1. Add here as they occur.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Kill-switch (`disabled` status) | ✅ Pre-v1 | Returns clear error if `CONSULTOR_MODEL` unset |
| Rate-limit pre-flight | ✅ Pre-v1 | `check_rate_limit()` before every call |
| Token-aware truncation | ✅ Pre-v1 | `tiktoken` cl100k_base with char-count fallback |
| Provider isolation | ✅ Pre-v1 | Resolved via `cfg.model_registry["consultor"]` |
| Three return statuses | ✅ Pre-v1 | `success` / `disabled` / `rate_limited` / `error` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `@meta_tool` refactor | Add `action` param (`review`, `advise`, `explain`) with `Literal` validation and auto-generated schema | P0 |
| Un-multiplex | Extract `_do_review`, `_do_advise`, `_do_explain` into atomic handlers (follow `browser_ops/actions/` pattern) | P0 |
| Test restructure | Add `conftest.py`, split `test_consult.py` into per-action files | P1 |
| `trace_id` support | Inject `trace_id` into all responses for observability | P1 |
| `format` param | `markdown` / `json` / `bullet_points` output formatting | P1 |
| Memory hook | Auto-store lightweight episodic memory on successful consult | P2 |
| Cost tracking | Tokens × price metadata for agent budget visibility | P2 |
| Context type auto-detection | `context_type` param (`code`, `logs`, `architecture`) to auto-select specialized system prompts | P2 |
| Batch review | `action="batch_review"` for parallel multi-file analysis | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Local model fallback** | Consultor is explicitly *cloud-only*. Local fallback defeats the purpose of stronger external reasoning. | Skip |
| 2 | **Streaming responses** | MCP stdio transport doesn't support streaming. Would require gateway-only mode. | Skip |
| 3 | **Conversation history** | `consult` is stateless by design. Memory integration (episodic) covers recall without conversation state. | Skip |
| 4 | **Image/multimodal input** | Vision tasks are handled by the `vision` role. Consultor is text-only advisory. | Skip |
| 5 | **Configurable `_MAX_CONTEXT_TOKENS` via `.env`** | Hardcoded 2000 is a deliberate safety rail. User must explicitly request a change. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
