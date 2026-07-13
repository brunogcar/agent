<- Back to [Swarm Overview](../SWARM.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-07-09 | Initial release — 5 actions (`consensus`, `race`, `vote`, `compare`, `list_providers`), `@meta_tool` + `swarm_ops/` pattern, direct provider calls, ThreadPoolExecutor fan-out |
| v1.0.1 | 2026-07-13 | Bugfix + hardening release — 2 P1 + 6 P2 + 2 P3 fixes from cross-LLM code review. See "Completed" below. |
| v1.0.2 | 2026-07-13 | Cross-LLM review hardening — 1 P0 + 5 P1 + 5 P2 + 1 P3 fixes from 7-LLM collective review (OpenAI, DeepSeek, Mistral, Qwen, Kimi, MiMo + internal). Added 8 roadmap items. See "Completed" below. |

---

## ⚠️ Breaking Changes

### (none — new tool in v1.0)

Swarm is a brand-new tool introduced in v1.0. There are no prior versions to break compatibility with. The first version's API is the baseline.

**v1.0.1 minor schema addition:** `vote` action adds a new `agreement` label `single_response` (returned when only 1 provider succeeds, where v1.0 returned `unanimous`). Downstream consumers reading the `agreement` field should handle the new label (treat as `LOW` confidence). This is additive, not breaking — existing labels (`unanimous`/`majority`/`split`/`disagreement`) are unchanged.

**v1.0.2 additive schema additions:**
- `consensus` result gains `synthesis_failed: bool` and `synthesis_error: str` fields (P1-5). `synthesis_failed` is `False` on success, `True` if the planner synthesis crashed. `synthesis_error` carries the error message. Existing consumers that only read `synthesis` are unaffected.
- `race` result gains `successful_count: int` (P3-4) for parity with consensus/compare/vote. Additive.
- `error_code` for parameter validation changed from `INVALID_ACTION` to `INVALID_INPUT` (P2-4). Consumers routing on `error_code == "INVALID_ACTION"` for parameter errors must update to `INVALID_INPUT`. Unknown-action errors still use `INVALID_ACTION`.
- `_swarm_debug_consensus` in `workflows/autocode_impl/vcs_ops.py` fixed (P0-1) — was completely non-functional due to wrong param names (`prompt=` → `question=`), wrong result keys (`response` → `synthesis`, `providers_count` → `provider_count`), and missing `single_response` in `confidence_map`. Now passes `trace_id` and checks `synthesis_failed`.

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| `swarm()` tool facade | ✅ v1.0 | `@tool` + `@meta_tool` + manual dispatch; `action: str` (with `Literal` enum applied by `@meta_tool`, plus manual dispatch for direct callers) |
| `swarm_ops/` subpackage | ✅ v1.0 | `_registry.py` + `helpers.py` + `actions/` (auto-imported by `__init__.py`) |
| `consensus` action | ✅ v1.0 / **hardened v1.0.2** | All providers → planner synthesis. **v1.0.2:** synthesis failure surfaced via `synthesis_failed`/`synthesis_error` (P1-5); whitespace-only responses filtered (P1-3); synthesis passes `trace_id`+`max_tokens`+`context` (P2-5/P2-6); per-response truncated to 2000 chars before synthesis (P2-7) |
| `race` action | ✅ v1.0 / **fixed v1.0.1** / **hardened v1.0.2** | All providers in parallel → first valid wins. **v1.0.1:** now actually returns early (was blocked on `shutdown(wait=True)`). **v1.0.2:** whitespace-only responses no longer win (P1-3); added `successful_count` to result (P3-4) |
| `vote` action | ✅ v1.0 / **fixed v1.0.1** / **hardened v1.0.2** | All providers → agreement classification. **v1.0.1:** fixed `split` misclassification + added `single_response`. **v1.0.2:** whitespace-only responses filtered out (P1-3) |
| `compare` action | ✅ v1.0 / **hardened v1.0.2** | All providers → side-by-side, no synthesis. **v1.0.2:** whitespace-only responses filtered (P1-3) |
| `list_providers` action | ✅ v1.0 | Env introspection; no LLM calls; `lmstudio` always excluded |
| `_get_available_providers()` | ✅ v1.0 / **hardened v1.0.2** | Reads `llm._registry._providers`; skips `lmstudio`; skips providers without `*_BASE_MODEL`. **v1.0.2 (P2-2 cross-LLM):** snapshots provider dict before iteration (mutation-during-iteration race). **(P2-3 cross-LLM):** cleans filter (drops empties + dedupes) |
| `_call_provider()` | ✅ v1.0 / **hardened v1.0.1** | Direct `provider.chat_completion()` call; try/except captures errors per-provider. **v1.0.1:** errors sanitized via `_sanitize_error()` to strip API keys (Gemini puts key in URL query string) |
| `_call_all_providers()` | ✅ v1.0 / **rewritten v1.0.2** | ThreadPoolExecutor (max 5 workers); results sorted by provider name. **v1.0.2 (P1-1 cross-LLM):** rewrote to mirror race's shutdown pattern — explicit executor + `try/except TimeoutError` + `finally: shutdown(wait=False, cancel_futures=True)`. v1.0.1's `with ThreadPoolExecutor` + `as_completed(timeout=...)` could deadlock on a hanging provider (affected consensus/vote/compare) |
| `_call_providers_race()` | ✅ v1.0 / **rewritten v1.0.1** / **fixed v1.0.2** | Returns on first valid response. **v1.0.1:** rewrote to actually return early. **v1.0.2 (P1-2 cross-LLM):** fixed done-future loss — `wait(FIRST_COMPLETED)` can return multiple futures; v1.0.1 broke on first winner, discarding sibling done futures. Now collects ALL done futures before checking winner |
| `_build_messages()` | ✅ v1.0 | OpenAI-style messages; optional `context` prepended as user/assistant turn |
| `_sanitize_error()` | ✅ v1.0.1 (new) / **hardened v1.0.2** | Strips API keys / tokens from exception strings. **v1.0.2 (P1-4 cross-LLM):** self-guarded against pathological exceptions that crash `str()`/`repr()`. **(P2-1 cross-LLM):** broadened patterns — camelCase JSON (`apiKey`), hyphenated (`api-key`), bare provider prefixes in prose (`AIzaSy...`, `sk-ant-...`, `sk-...`), base64 chars (`+/=`), 16-char threshold (was 32) |
| Per-provider error isolation | ✅ v1.0 | Provider failures captured in result dict (`text=""`, `error="..."`); action only fails if ALL providers fail |
| Input validation (`max_tokens` / `timeout` bounds) | ✅ v1.0.1 (new) / **fixed v1.0.2** | `max_tokens ∈ [1, 8192]`; `timeout ∈ [1, 300]`s. **v1.0.2 (P2-4 cross-LLM):** `error_code` corrected from `INVALID_ACTION` → `INVALID_INPUT` (semantically correct — the action name is valid, the parameter value is not) |
| `duration_ms` timing | ✅ v1.0 | Wall-clock timing at facade level; injected into every successful result |
| `trace_id` propagation | ✅ v1.0 | Auto-injected into result dict if missing |
| Provider filter (`providers` param) | ✅ v1.0 | Comma-separated, case-insensitive, trimmed; empty = all configured |
| Cloud-only (skip `lmstudio`) | ✅ v1.0 | Hardcoded skip in `_get_available_providers()` |
| Test suite | ✅ v1.0 (6 files) / **expanded v1.0.1** / **expanded v1.0.2** | v1.0 shipped 6 test files. **v1.0.1:** +`test_helpers.py`, vote classification tests, race latency test, input validation. **v1.0.2:** +sanitize broadened patterns (8 tests), sanitize self-guard (2 tests), `_call_all_providers` timeout regression (1 test), consensus synthesis-failure + whitespace tests, race whitespace + successful_count tests. 74 total (was 57) |
| Autocode debug-loop integration | ✅ v1.3 (commit `8b374dd`) / **fixed v1.0.2** | `_swarm_debug_consensus` in `workflows/autocode_impl/vcs_ops.py`. **v1.0.2 (P0-1 cross-LLM):** fixed 7 interface bugs that made it completely non-functional — `prompt=`→`question=`, `role=` dropped, `response`→`synthesis`, `providers_count`→`provider_count`, added `single_response`→LOW to confidence_map, passes `trace_id`, checks `synthesis_failed` |
| Documentation | ✅ v1.0 / **updated v1.0.1** / **updated v1.0.2** | 5-file standard. **v1.0.1:** corrected Literal/path drift, filled Anti-Patterns. **v1.0.2:** added v1.0.2 Anti-Patterns (5 lessons), new INSTRUCTIONS rules (#38-#42), API.md schema additions (`synthesis_failed`/`synthesis_error`/`successful_count`/`INVALID_INPUT`), 8 new roadmap items |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Integration with router for vote-based routing | When router confidence is low, fall back to `swarm(vote)` across cloud providers to pick the workflow type. Adds a "second-opinion" path in `core/router.py`. | P1 |
| Per-provider rate limiting | `_call_provider()` currently bypasses `llm.complete()`'s rate limiting. Add a per-provider token-bucket (e.g. `OPENAI_RPM`, `CLAUDE_RPM` env vars) so a runaway swarm doesn't burn quotas. | P2 |
| `json_schema` support | Pass `json_schema` through to `provider.chat_completion()` so `vote` / `compare` can enforce structured outputs. Currently hardcoded `json_mode=False, json_schema=None` in `_call_provider()`. Note Claude/Gemini use different mechanisms (Anthropic tool-use, Gemini responseSchema) — see `docs/core/llm/INSTRUCTIONS.md` rule #12. | P2 |
| Benchmark tasks | Add swarm-specific tasks to `benchmark/benchmark.py` (e.g. "consensus on coding question", "vote on classification"). Wire into `ROLE_GROUPS` / `ROLE_TO_GROUP` if appropriate. | P2 |
| `circuit_breaker` per provider | Track per-provider failure rate inside swarm; skip providers that have failed N times in the last M seconds. Mirrors the circuit breaker in `llm.complete()` but at swarm's own layer. | P3 |
| Streaming responses | `_call_provider()` currently waits for full response. For `race`, streaming could return the first token faster (true first-byte-wins). **v1.0.1 note:** the v1.0 premise here ("not first-completion-wins") was based on the false assumption that v1.0 race returned on first completion — it actually blocked on all completions (P1-2). Now that v1.0.1 race genuinely returns on first completion, streaming would only shave the time-to-first-token within the winning provider's call. | P3 |
| Cost tracking | Sum `usage.total_tokens` across providers; expose `total_tokens` and estimated `cost_usd` in the result. Requires per-provider pricing table. | P3 |
| `weighted_vote` action | Like `vote` but with per-provider weights (e.g. `OPENAI_WEIGHT=2.0`). Useful when one provider is known to be more reliable for a task. | P4 |
| `audit` action | Returns full per-provider responses + latencies + token counts + cost estimate, intended for benchmarking / provider evaluation. | P4 |
| Health-check in `list_providers` | Currently `available: true` for all listed providers. Add optional lightweight ping to verify the API key is valid and the endpoint is reachable. | P5 |
| `llm.complete_provider()` API (OpenAI) | Expose a provider-direct call path that still uses registry plumbing (circuit breakers, telemetry) but bypasses role routing. Would eliminate swarm's duplicated provider-invocation logic and the "bypasses everything" concern. | P2 |
| Pluggable vote normalization (OpenAI) | `YES` vs `Yes.` vs `TRUE.` currently differ. Allow caller to pass a normalizer (e.g. extract first uppercase token) for classification tasks. | P3 |
| `threading.Event` cancellation token (Qwen) | Pass a cancel event down to `provider.chat_completion()` so running (not just pending) futures can be truly cancelled in race. Currently `cancel_futures=True` only cancels PENDING futures — running HTTP connections continue in the background. | P3 |
| Configurable synthesis role (Mistral) | `SWARM_SYNTHESIS_ROLE` env var instead of hardcoded `"planner"`. Allows using a faster/specialized role for synthesis. | P3 |
| `temperature` / `json_mode` / `json_schema` passthrough (Mistral + Kimi) | Currently hardcoded in `_call_provider` (`temperature=0.7`, `json_mode=False`). Needed for the `json_schema` roadmap item + allows vote to use `temperature=0` for deterministic classification. | P2 |
| Rename `list_providers` `available` → `configured` (Kimi) | `available: true` is misleading — a provider can have `*_BASE_MODEL` set while `*_API_KEY` is missing/invalid. Rename to `configured: true` (accurate) or add a health-check ping. Schema change — defer to v1.1. | P3 |
| Tracer integration in facade (Kimi) | `tracer` is imported but unused. Add `tracer.step()` at action dispatch + `tracer.error()` on handler crash (v1.0.2 added the error call; step calls still missing). | P3 |

---

## 🚫 Deferred / Out of Scope

| Feature | Why deferred |
|---------|--------------|
| Calling `lmstudio` from swarm | By design — swarm is for cloud providers only. Local models belong to `agent()` / `llm.complete()`. Adding `lmstudio` would defeat the "different models, different vendors" premise. |
| Nested `swarm()` calls (swarm-of-swarms) | ThreadPoolExecutor nesting risk; current 5-worker cap would compound. If needed, use a single swarm with the union of providers instead. |
| Calling `swarm()` from inside `parallel()` | NOT parallel-safe (see ARCHITECTURE.md). `parallel()`'s allowlist excludes swarm. If you need to run swarm alongside other tools, call them sequentially or use a different orchestration pattern. |
| `push`-style streaming back to the LLM | MCP tool calls are request/response — no streaming channel back. Streaming would only help within `_call_provider()` (see "Streaming responses" roadmap item). |
| Fine-tuned / custom models per provider | Out of scope — swarm uses the model configured in `<NAME>_BASE_MODEL`. Switching models mid-call is a future feature (`model` override param). |

---

*Last updated: 2026-07-13 (v1.0.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
