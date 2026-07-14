<- Back to [Swarm Overview](../SWARM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
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
| 17 | **Swarm ↔ autocode debug loop integration** | Wire `AUTOCODE_SWARM_DEBUG=1` end-to-end + add smoke test. Was the original P1 but was silently broken. Now actually works (v1.0.2 fixed it). | P1 |
| 18 | **Swarm ↔ router vote-based routing** | When router confidence is low, fall back to `swarm(vote)`. Adds second-opinion path in `core/router.py`. | P1 |
| 19 | Per-provider rate limiting | `OPENAI_RPM`, `CLAUDE_RPM` env vars. Prevents quota burn. `_call_provider()` currently bypasses `llm.complete()`'s rate limiting. | P2 |
| 20 | `json_schema` support | Pass `json_schema` through to `provider.chat_completion()`. Vote/compare get structured outputs. Note Claude/Gemini use different mechanisms — see `docs/core/llm/INSTRUCTIONS.md` rule #12. | P2 |
| 21 | `temperature`/`json_mode` passthrough | Currently hardcoded `temperature=0.7`. Needed for deterministic vote (`temperature=0`). | P2 |
| 22 | `llm.complete_provider()` API | Expose a provider-direct call path that still uses registry plumbing (CB, telemetry) but bypasses role routing. Eliminates swarm's duplicated provider-invocation logic. | P2 |
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

*Last updated: 2026-07-14 (v1.0.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
