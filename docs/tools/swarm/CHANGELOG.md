<- Back to [Swarm Overview](../SWARM.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-07-09 | Initial release — 5 actions (`consensus`, `race`, `vote`, `compare`, `list_providers`), `@meta_tool` + `swarm_ops/` pattern, direct provider calls, ThreadPoolExecutor fan-out |

---

## ⚠️ Breaking Changes

### (none — new tool)

Swarm is a brand-new tool introduced in v1.0. There are no prior versions to break compatibility with. The first version's API is the baseline.

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| `swarm()` tool facade | ✅ v1.0 | `@tool` + `@meta_tool` + manual dispatch; `action: str` (not `Literal`) |
| `swarm_ops/` subpackage | ✅ v1.0 | `_registry.py` + `helpers.py` + `actions/` (auto-imported by `__init__.py`) |
| `consensus` action | ✅ v1.0 | All providers → planner synthesis via `llm.complete(role="planner")` |
| `race` action | ✅ v1.0 | All providers in parallel → first valid wins; remaining futures cancelled (best effort) |
| `vote` action | ✅ v1.0 | All providers → agreement classification (`unanimous` / `majority` / `split` / `disagreement`) |
| `compare` action | ✅ v1.0 | All providers → side-by-side, no synthesis |
| `list_providers` action | ✅ v1.0 | Env introspection; no LLM calls; `lmstudio` always excluded |
| `_get_available_providers()` | ✅ v1.0 | Reads `llm._registry._providers`; skips `lmstudio`; skips providers without `*_BASE_MODEL`; supports comma-separated filter |
| `_call_provider()` | ✅ v1.0 | Direct `provider.chat_completion()` call; try/except captures errors per-provider |
| `_call_all_providers()` | ✅ v1.0 | ThreadPoolExecutor (max 5 workers); `as_completed(timeout+10)`; results sorted by provider name |
| `_call_providers_race()` | ✅ v1.0 | Returns on first valid response; cancels remaining futures (best effort) |
| `_build_messages()` | ✅ v1.0 | OpenAI-style messages; optional `context` prepended as user/assistant turn |
| Per-provider error isolation | ✅ v1.0 | Provider failures captured in result dict (`text=""`, `error="..."`); action only fails if ALL providers fail |
| `duration_ms` timing | ✅ v1.0 | Wall-clock timing at facade level; injected into every successful result |
| `trace_id` propagation | ✅ v1.0 | Auto-injected into result dict if missing |
| Provider filter (`providers` param) | ✅ v1.0 | Comma-separated, case-insensitive, trimmed; empty = all configured |
| Cloud-only (skip `lmstudio`) | ✅ v1.0 | Hardcoded skip in `_get_available_providers()` |
| Documentation | ✅ v1.0 | 5-file standard: SWARM.md landing + API.md + ARCHITECTURE.md + CHANGELOG.md + INSTRUCTIONS.md |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Integration with autocode debug loop | Use `swarm(vote)` to gate autocode debug-node fix decisions — if models disagree on root cause, surface both hypotheses instead of picking one. Wire into `workflows/autocode_impl/debug.py`. | P1 |
| Integration with router for vote-based routing | When router confidence is low, fall back to `swarm(vote)` across cloud providers to pick the workflow type. Adds a "second-opinion" path in `core/router.py`. | P1 |
| Per-provider rate limiting | `_call_provider()` currently bypasses `llm.complete()`'s rate limiting. Add a per-provider token-bucket (e.g. `OPENAI_RPM`, `CLAUDE_RPM` env vars) so a runaway swarm doesn't burn quotas. | P2 |
| `json_schema` support | Pass `json_schema` through to `provider.chat_completion()` so `vote` / `compare` can enforce structured outputs. Currently hardcoded `json_mode=False, json_schema=None` in `_call_provider()`. Note Claude/Gemini use different mechanisms (Anthropic tool-use, Gemini responseSchema) — see `docs/core/llm/INSTRUCTIONS.md` rule #12. | P2 |
| Benchmark tasks | Add swarm-specific tasks to `benchmark/benchmark.py` (e.g. "consensus on coding question", "vote on classification"). Wire into `ROLE_GROUPS` / `ROLE_TO_GROUP` if appropriate. | P2 |
| Test suite | Conftest with `mock_llm_registry` / `mock_env` / `mock_planner` fixtures; one test file per action + helpers. See ARCHITECTURE.md → Testing section for plan. | P2 |
| `circuit_breaker` per provider | Track per-provider failure rate inside swarm; skip providers that have failed N times in the last M seconds. Mirrors the circuit breaker in `llm.complete()` but at swarm's own layer. | P3 |
| Streaming responses | `_call_provider()` currently waits for full response. For `race`, streaming could return the first token faster (true first-byte-wins, not first-completion-wins). | P3 |
| Cost tracking | Sum `usage.total_tokens` across providers; expose `total_tokens` and estimated `cost_usd` in the result. Requires per-provider pricing table. | P3 |
| `weighted_vote` action | Like `vote` but with per-provider weights (e.g. `OPENAI_WEIGHT=2.0`). Useful when one provider is known to be more reliable for a task. | P4 |
| `audit` action | Returns full per-provider responses + latencies + token counts + cost estimate, intended for benchmarking / provider evaluation. | P4 |
| Health-check in `list_providers` | Currently `available: true` for all listed providers. Add optional lightweight ping to verify the API key is valid and the endpoint is reachable. | P5 |

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

*Last updated: 2026-07-09. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
