<- Back to [Swarm Overview](../SWARM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **Pre-v1.1 update** | 2026-07-14 | **#22: swarm `_call_provider()` now delegates to `llm.complete_provider()`.** Core LLM v1.3 introduced `LLMClient.complete_provider(provider, model, messages, ...)` — a provider-direct call path with circuit breaker + telemetry. Swarm's `_call_provider()` now delegates to it instead of calling `provider.chat_completion()` directly. Fallback to direct `provider.chat_completion()` is preserved for unit-test mocks that patch the provider method directly. Swarm gains circuit-breaker integration + telemetry on per-provider fan-out — previously it bypassed both. **No breaking changes** to swarm's public API (facade params, action handlers, return shapes all unchanged). Also: native `json_schema` for Claude (#39) and Gemini (#40) shipped in core LLM v1.3 — `_call_provider()` needs NO changes for that (it already forwards `json_schema` to the provider; the provider layer handles the conversion). |
| **v1.1** | 2026-07-14 | **Provider capability passthrough + router integration.** (1) #21: `temperature`, `json_mode`, `json_schema` params added to facade + all 4 action handlers + `_call_provider()`. Was hardcoded `temperature=0.7`. Vote now supports `temperature=0` for deterministic classification. (2) #20: `json_schema` threaded through to `provider.chat_completion()`. Claude/Gemini ignore it (different mechanisms). When native json_schema for Claude/Gemini is implemented, `_call_provider()` needs NO changes — provider layer handles conversion. (3) #18: Router swarm fallback — `ROUTER_SWARM_FALLBACK=0` (default OFF). When router confidence is low, calls `swarm(vote, temperature=0)` for second opinion. Requires unanimous/majority agreement. (4) #17: Smoke tests — 5 tests in `test_swarm_integration.py` + 8 tests in `test_router.py`. |
| v1.0.2 | 2026-07-13 | **Cross-LLM review hardening.** 1 P0 + 5 P1 + 5 P2 + 1 P3 from 7-LLM collective review. `_call_all_providers` deadlock fix, `_call_providers_race` done-future loss fix, `_sanitize_error` broadened, `_get_available_providers` race fix. Added 8 roadmap items. |
| v1.0.1 | 2026-07-13 | **Bugfix + hardening.** 2 P1 + 6 P2 + 2 P3. Race early-return fix, `_sanitize_error` API key stripping, input validation. |
| v1.0 | 2026-07-09 | **Initial release.** 5 actions (`consensus`, `race`, `vote`, `compare`, `list_providers`), `@meta_tool` + `swarm_ops/` pattern, direct provider calls, ThreadPoolExecutor fan-out. |

---

### ⚠️ Breaking Changes

#### v1.0.2 — 2026-07-13

| Change | Impact | Migration |
|--------|--------|-----------|
| `consensus` result gains `synthesis_failed: bool` + `synthesis_error: str` | Additive. Existing consumers reading `synthesis` are unaffected. | Check `synthesis_failed` if you need to distinguish synthesis crash from empty result. |
| `race` result gains `successful_count: int` | Additive (parity with consensus/compare/vote). | No migration. |
| `error_code` for parameter validation changed from `INVALID_ACTION` to `INVALID_INPUT` | Consumers routing on `error_code == "INVALID_ACTION"` for parameter errors must update. Unknown-action errors still use `INVALID_ACTION`. | Update `error_code` checks for parameter errors. |
| `_swarm_debug_consensus` in autocode fixed (P0-1) | Was completely non-functional (wrong param names + wrong result keys). | No migration — was broken before. |

#### v1.0.1 — 2026-07-13

| Change | Impact | Migration |
|--------|--------|-----------|
| `vote` action adds `single_response` agreement label | Returned when only 1 provider succeeds (was `unanimous`). | Treat as `LOW` confidence. Additive — existing labels unchanged. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| ✅ #17 | **Swarm ↔ autocode debug loop integration** | ✅ **Shipped in v1.1** — smoke tests added in `tests/workflows/autocode/test_swarm_integration.py` (2 classes, 5 tests covering `AUTOCODE_SWARM_DEBUG` enable/disable + `node_swarm_fallback` HIGH/LOW/unavailable paths). The underlying wiring was fixed in v1.0.2 (P0-1). |
| ✅ #18 | **Swarm ↔ router vote-based routing** | ✅ **Shipped in v1.1** — `core/router.py` `_swarm_fallback_route()` calls `swarm(action="vote", temperature=0)` when heuristic confidence is `low` AND `ROUTER_SWARM_FALLBACK=1` (default OFF). Requires unanimous/majority agreement + valid workflow type. Non-fatal — failures fall back to heuristic. 8 tests in `tests/core/test_router.py`. |
| 19 | Per-provider rate limiting | `OPENAI_RPM`, `CLAUDE_RPM` env vars. Prevents quota burn. `_call_provider()` currently bypasses `llm.complete()`'s rate limiting. | P2 |
| ✅ #20 | **`json_schema` support** | ✅ **Shipped in v1.1** — `json_schema` param threaded through facade → all 4 action handlers → `_call_provider()` → `provider.chat_completion()`. Claude/Gemini ignore it (they use different mechanisms — see `docs/core/llm/INSTRUCTIONS.md` rule #12). **Roadmap note:** when native json_schema for Claude/Gemini ships (P2 items #39+#40 in core/llm roadmap), `_call_provider()` needs NO changes — the provider layer handles the conversion. |
| ✅ #21 | **`temperature`/`json_mode` passthrough** | ✅ **Shipped in v1.1** — facade accepts `temperature=-1.0` (default = use 0.7), `json_mode=False`, `json_schema=""`. Was hardcoded `temperature=0.7` in `_call_provider()`. Vote now supports `temperature=0` for deterministic classification (recommendation in INSTRUCTIONS.md). |
| ✅ #22 | `llm.complete_provider()` API | ✅ **Shipped in Pre-v1.1 update** — swarm's `_call_provider()` now delegates to `llm.complete_provider()` (added in core LLM v1.3, #22). Provider-direct call path with circuit breaker + telemetry. Fallback to direct `provider.chat_completion()` preserved for unit-test mocks. Eliminates swarm's duplicated provider-invocation logic. |
| 23 | Benchmark tasks | Swarm-specific tasks in `benchmark/benchmark.py` (consensus on coding question, vote on classification). | P2 |
| 26 | Streaming responses | True first-byte-wins for race. v1.0.1 made this less urgent (race now genuinely returns on first completion). | P3 |
| 27 | Cost tracking | Sum `usage.total_tokens` across providers; expose `total_tokens` + estimated `cost_usd`. Requires per-provider pricing table. | P3 |
| 28 | Per-provider circuit breaker | Track per-provider failure rate inside swarm; skip providers failing N times in M seconds. Mirrors `llm.complete()` CB but at swarm's own layer. | P3 |
| 29 | `threading.Event` cancellation token | Pass cancel event to `provider.chat_completion()` so running (not just pending) futures can be truly cancelled in race. | P3 |
| 30 | Pluggable vote normalization | `YES` vs `Yes.` vs `TRUE.` unification. Allow caller to pass a normalizer. | P3 |
| 31 | Configurable synthesis role | `SWARM_SYNTHESIS_ROLE` env var instead of hardcoded `"planner"`. | P3 |
| 24 | `weighted_vote` action | Like `vote` but with per-provider weights (e.g. `OPENAI_WEIGHT=2.0`). | P4 |
| 25 | `audit` action | Full per-provider responses + latencies + token counts + cost estimate. For benchmarking/provider evaluation. | P4 |
| 32 | Health-check in `list_providers` | Optional lightweight ping to verify API key validity. Currently `available: true` for all listed. | P5 |

---

## 🚫 Deferred / Out of Scope

| Feature | Why Deferred |
|---------|--------------|
| Calling `lmstudio` from swarm | By design — swarm is for cloud providers only. Local models belong to `agent()` / `llm.complete()`. |
| Nested `swarm()` calls (swarm-of-swarms) | ThreadPoolExecutor nesting risk; current 5-worker cap would compound. Use a single swarm with the union of providers. |
| Calling `swarm()` from inside `parallel()` | NOT parallel-safe (see ARCHITECTURE.md). `parallel()`'s allowlist excludes swarm. |
| `push`-style streaming back to the LLM | MCP tool calls are request/response — no streaming channel back. |
| Fine-tuned / custom models per provider | Out of scope — swarm uses the model in `<NAME>_BASE_MODEL`. |

---

*Last updated: 2026-07-14 (v1.1 update — #22: swarm `_call_provider()` now delegates to `llm.complete_provider()`; v1.1 — provider capability passthrough + router swarm fallback + smoke tests; v1.0.2 cross-LLM hardening). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
