<- Back to [Consult Overview](../CONSULT.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.0** | 2026-07-15 | `@meta_tool` refactor: 3 actions (`advise`/`review`/`explain`), `consult_ops/` subpackage (8 files), new params (`trace_id`, `format`, `context_type`), 92 tests across 6 files. Old `test_consult.py` deleted. |
| Pre-v1 | 2026-07-03 | Initial advisory tool: single `consult(question, context)` facade, `_ADVISORY_SYSTEM_PROMPT`, kill-switch, rate-limit guard, token-aware truncation. 8 tests in one `test_consult.py`. |

---

## ⚠️ Breaking Changes

| Version | Change | Migration |
|---------|--------|-----------|
| **v1.0** | `action` is now a required parameter. Legacy `consult(question="...")` returns `{"status": "error", "error": "action is required (advise \| explain \| review)"}`. | Update callers to `consult(action="advise", question="...")`. `advise` preserves the old advisory prompt verbatim; `review`/`explain` are new. The router's `_RE_DIRECT_CONSULT` heuristic was already in place — no router changes needed. |
| **v1.0** | Response payload keys differ per action: `advise` → `advice`, `review` → `review`, `explain` → `explanation`. (Pre-v1 always returned `advice`.) | Inspect the `action` field in the response to pick the correct key, or read `result.get("advice") or result.get("review") or result.get("explanation")`. |
| **v1.0** | `format` is a soft-reserved keyword argument name. Callers passing `format=` for any other purpose will conflict. | Standard behavior — only matters if a caller was abusing `**kwargs` (the old `@tool` facade didn't accept `**kwargs` either, so this is theoretical). |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Kill-switch (`disabled` status) | ✅ Pre-v1 | Returns clear error if `CONSULTOR_MODEL` unset |
| Rate-limit pre-flight | ✅ Pre-v1 | `check_rate_limit()` before every call |
| Token-aware truncation | ✅ Pre-v1 | `tiktoken` cl100k_base with char-count fallback |
| Provider isolation | ✅ Pre-v1 | Resolved via `cfg.model_registry["consultor"]` |
| Three return statuses | ✅ Pre-v1 | `success` / `disabled` / `rate_limited` / `error` |
| `@meta_tool` refactor | ✅ v1.0 | Facade is now a thin dispatch wrapper; `action: Literal["advise","explain","review"]` auto-generated from `DISPATCH` |
| Un-multiplex into `consult_ops/` | ✅ v1.0 | 8-file subpackage: `_registry.py`, `__init__.py`, `helpers.py`, `prompts.py`, `actions/{__init__,advise,review,explain}.py` |
| 3 actions (`advise` / `review` / `explain`) | ✅ v1.0 | Same LLM call, different system prompts. Review adds 5-dimension structured findings; explain uses educator persona with analogies + step-by-step breakdowns |
| `trace_id` support | ✅ v1.0 | Forwarded to `llm.complete()`; threaded through every return path (success + all error states when present) |
| `format` param | ✅ v1.0 | `markdown` (default) / `json` / `bullet_points` — appends a suffix to the system prompt |
| `context_type` param | ✅ v1.0 | `""` (default) / `code` / `logs` / `architecture` — appends a context-type modifier to the system prompt |
| Test restructure | ✅ v1.0 | 92 tests across 6 files (`conftest.py` + `test_advise.py` / `test_review.py` / `test_explain.py` / `test_dispatch.py` / `test_helpers.py`). Old `test_consult.py` deleted. |
| Centralized LLM access (`_call_consultor`) | ✅ v1.0 | Action handlers call `helpers._call_consultor()` instead of `llm.complete()` directly — enables clean test patching via `tools.consult_ops.helpers.llm` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Memory hook | Auto-store lightweight episodic memory on successful consult (action, question摘要, advice摘要) | P2 |
| Cost tracking | Tokens × price metadata for agent budget visibility; surface `tokens_in`/`tokens_out`/`cost_usd` in the response | P2 |
| Batch review | `action="batch_review"` for parallel multi-file analysis (one LLM call per file, results aggregated) | P3 |

### 💡 Suggested Roadmap (Future Sessions)

The following items are **proposed** for future consult roadmap sessions. They are not yet committed — list them here so the next maintainer can pick the highest-value ones.

| Feature | Notes | Priority |
|---------|-------|----------|
| `consult(action="compare")` | Side-by-side comparison of two approaches (like `swarm compare` but single-model). Caller passes two `context` blocks; consultor returns a structured trade-off matrix. | P2 |
| `consult(action="validate")` | Validate a design decision against best practices. Caller passes a decision + constraints; consultor returns `valid`/`invalid`/`partial` with citations to industry patterns. | P2 |
| `consult(action="brainstorm")` | Generate N alternative approaches for a problem. Useful as input to `parallel` or `swarm` for downstream evaluation. | P2 |
| `json_schema` support | Pass `json_schema` to `llm.complete()` for structured output (e.g. `{findings: [{severity, dimension, line, issue, fix}]}` for review). Pairs naturally with `format="json"` but gives type safety. | P2 |
| Streaming support | Stream consultor responses via gateway mode (HTTP transport). MCP stdio transport can't stream today — this would require the gateway-only mode. *(v1.4 note: `complete_with_tools()` is now implemented for native tool calling, but streaming still requires gateway mode — these are separate features.)* | P3 |
| Conversation memory | Optional episodic memory storage per consult session. Differs from the existing "Memory hook" (which is fire-and-forget storage); this would let follow-up `consult` calls reference prior Q&A in the same trace. | P3 |
| Multi-model consult | Consult multiple models and compare (like a mini-swarm but routed through the consultor role only). Lower overhead than `swarm` for 2-model tie-breakers. | P3 |
| Context preprocessing | Auto-detect code language and add language-specific review rules (e.g. Python → PEP 8, Rust → clippy rules). Replaces the manual `context_type="code"` opt-in. | P3 |
| Severity filtering | For `review` action, filter findings by severity level (`CRITICAL` only, `CRITICAL+WARNING`, etc.). Saves caller-side post-processing. | P3 |
| Cost tracking (deduplicated) | Tokens × price per consult call. Listed in the In Progress table above — kept here for visibility because it's the most-requested follow-up. | P2 |

> **Note for future maintainers:** items in the table above are *suggestions* gathered during v1.0 docs work. Before implementing any of them, re-check the current source (`tools/consult_ops/`) and `core/llm_backend/` to confirm prerequisites (e.g. gateway mode for streaming, `json_schema` plumbing for structured output) are in place. *(v1.4: `complete_with_tools()` is implemented for native tool calling — not related to streaming.)*

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Local model fallback** | Consultor is explicitly *cloud-only*. Local fallback defeats the purpose of stronger external reasoning. | Skip |
| 2 | **Streaming responses** *(legacy entry)* | MCP stdio transport doesn't support streaming. Re-listed in the Roadmap above. Requires gateway mode (HTTP transport) — not `complete_with_tools()`. | Skip (until gateway mode) |
| 3 | **Conversation history** *(legacy entry)* | `consult` is stateless by design. The Roadmap "Conversation memory" item revisits this with an opt-in episodic variant. | Skip |
| 4 | **Image/multimodal input** | Vision tasks are handled by the `vision` role. Consultor is text-only advisory. | Skip |
| 5 | **Configurable `_MAX_CONTEXT_TOKENS` via `.env`** | Hardcoded 2000 is a deliberate safety rail. User must explicitly request a change. | Skip |

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
