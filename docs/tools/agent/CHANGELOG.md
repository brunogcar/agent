<- Back to [Agent Overview](../AGENT.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.6 | 2026-07-12 | **[Hardening] Cross-LLM review fixes.** `str(result.error)` safety (was crashing on Exception objects). `try/except` around `llm.complete()` with error classification (TIMEOUT/CIRCUIT_OPEN/RATE_LIMIT). Stronger default system prompt (JSON output + context fencing). Metrics recording for all paths. `parsed` field preserved through `compress_result`. `inspect.signature()` cached at registration time in `_registry.py` (was: on every call). |
| v1.5 | 2026-07-12 | **Subagent dispatch adopted by callers.** `action="subagent"` (registered in `actions/subagent.py`) is now consumed by autoresearch's `propose` node (v1.1) and autocode's `node_systematic_debug` via `AUTOCODE_SUBAGENT_DEBUG=1` (v2.0.2). Subagent gets isolated curated context — no session history (superpowers pattern: "you construct exactly what they need"). Was previously a future/deferred item; single-dispatch path now in use. Parallel multi-subagent dispatch (one per hypothesis) still future. |
| v1.4 | 2026-07-08 | **JSON schema enforcement:** Added `json_schema` to ROLE_CONFIG for 6 JSON-returning roles (code, route, plan, review, refactor, test). `dispatch.py` reads `json_schema` from role config and passes to `llm.complete()`. LM Studio enforces schema at generation time via outlines. Defensive JSON parsing stays as fallback. |
| v1.3 | 2026-07-05 | Bugfix batch: escalation uses planner prompt (#7), `escalated_from` tracking (#8), content budget 70% of remaining (#9), fallback re-trims context (#11), role sets module-level (#12), vision_delegate forwards context (#13), llm_role validation at import — warning only, not error (#18), cache limits configurable (#19), metrics JSONL persistence (#20), cache key includes model (#23), metrics aggregation (#24), parse_warnings severity (#25), `unregister_action` added (#27), `_trim_context` head truncation fix (#21). Note: Bug #10 (classify/consultor fallback mismatch) was NOT fixed — fallbacks are intentional escalation paths per maintainer design decision. |
| v0.1 | 2024-01-15 | Initial monolithic agent tool (~420 lines) |
| v0.2 | 2024-02-01 | Added response cache and metrics |
| v0.3 | 2024-02-15 | Added sleep-learn injection |
| v0.4 | 2024-03-01 | Added vision_delegate action |
| v0.5 | 2024-03-15 | Added token-aware context trimming |
| v1.0 | 2024-04-01 | `@meta_tool` refactor -- actions/ + roles/ directories, auto-discovery |
| v1.1 | 2024-04-15 | Hardening pass: `**kwargs` removal, vision guard, dynamic sleep-learn config, `budget_chars` `or` trap fix, traceback scoping, char multiplier tightening, metrics `.copy()`, test budget fix, `sleep_learn` per-role flags |
| v1.2 | 2024-05-01 | Added 3 autonomous maintenance roles: `refactor`, `test`, `document`. Timeout single source of truth. Escalation response completeness. Cache key includes temperature/max_tokens. Consultor guard. Scaled context trimming for large budgets. |

---

## ⚠️ Breaking Changes

### v1.3

| Change | Impact | Migration |
|--------|--------|-----------|
| Escalation now uses planner's system prompt instead of original role's | Escalation produces better JSON (planner prompt is designed for structured output). Callers that inspected the `system` parameter of escalation calls will see a different value. | No migration — escalation is internal and transparent to callers. |
| `escalated_from` field added to escalated responses | New field `{"role": "...", "model": "..."}` tracks the origin model. Existing callers that check `escalated` still work. | Optional — callers can now use `escalated_from` for debugging, but it doesn't break existing code. |
| Content budget changed from `min(1000, remaining)` to `70% of remaining` | Large content (code files) is no longer silently truncated to ~1000 tokens. Roles like `code`, `refactor`, `test`, `document` now receive larger context. | No migration — strictly better behavior. Callers that depended on truncation will see more content. |
| Fallback now re-trims context for fallback role's budget | Fallback calls no longer receive oversized context. | No migration — strictly better behavior. |
| Cache key now includes model name | Swapping models invalidates stale cache entries. | No migration — strictly better behavior. Existing cache entries from before the fix will miss on first call after upgrade, then populate normally. |
| Cache limits now read from `cfg.agent_cache_max` / `cfg.agent_cache_ttl_seconds` | Defaults unchanged (100 entries, 300s TTL). New env vars: `AGENT_CACHE_MAX`, `AGENT_CACHE_TTL_SECONDS`. | Optional — add env vars to `.env` to customize. Defaults match old behavior. |
| Metrics now persisted to `.agent_metrics.jsonl` | Metrics survive restart. New env var: `AGENT_METRICS_PERSIST=0` to disable. | Optional — set `AGENT_METRICS_PERSIST=0` to disable. File is append-only, best-effort. |
| `unregister_action()` added to `_registry` | New public function for hot-reload/testing. | No migration — additive. |
| `_trim_context` head truncation searches 200-char window instead of full head | Head preservation is tighter — less context discarded between last `\n\n` and boundary. | No migration — strictly better behavior. |
| `llm_role` validated against `cfg.model_registry` at import time (warning only) | Typos like `"cod"` instead of `"code"` now emit a stderr warning at import. Opt-in roles (consultor when `CONSULTOR_MODEL` is unset) are not flagged as errors — they're expected to be absent. | No migration — warning only, does not break startup. |

### v1.0

| Old | New | Migration |
|-----|-----|-----------|
| Monolithic `tools/agent.py` (~420 lines) | Atomic `actions/` + `roles/` directories + thin facade | No migration needed -- same API |
| Manual `if action == "search": ... elif ...` dispatch in facade | `@register_action` auto-discovery + `@meta_tool` | No migration needed -- same API |

### v1.1

| Old | New | Migration |
|-----|-----|-----------|
| `run_dispatch(**kwargs)` | Explicit parameter list | No migration -- internal fix |
| `budget_chars` `or` default | `is None` check for `0`/`False` | No migration -- internal fix |
| `char_budget = budget * 5` | `char_budget = budget * 3` | No migration -- internal fix |
| Hardcoded `_json_roles` / `_sleep_learn_roles` sets | Runtime-derived from `ROLE_CONFIG` | No migration -- internal fix |
| `vision` role dispatchable | Rejected with helpful error | No migration -- use `action="vision_delegate"` |
| `max_context_tokens` missing in `FakeCfg` | Added to test fixtures | No migration -- test fix |
| `_get_metrics` returned live dict | Returns `.copy()` | No migration -- internal fix |
| `except (RuntimeError, OSError, ConnectionError)` for sleep-learn | `except Exception:` | No migration -- internal fix |
| Single-quoted multi-line prompts | Triple-quoted strings | No migration -- code generation fix |
| `tb_tokens` undefined in chars branch | Set `tb_tokens = None` | No migration -- internal fix |

### v1.2

| Old | New | Migration |
|-----|-----|-----------|
| 12 core roles | 15 roles (+`refactor`, `test`, `document`) | No migration -- new roles available |
| Timeout hardcoded | Single source of truth via `core/llm_backend/config.py` | No migration -- internal fix |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 12 core roles (classify, route, research, summarize, extract, critique, analyze, code, review, plan, consultor, vision) | ✅ v0.1-v1.0 | Initial role set |
| Response cache and metrics | ✅ v0.2 | SHA256 key, 5-min TTL, 100-entry LRU |
| Sleep-learn injection | ✅ v0.3 | Auto-injected for high-latency roles |
| `vision_delegate` action | ✅ v0.4 | Delegates to `tools/vision.py` |
| Token-aware context trimming | ✅ v0.5 | tiktoken + chars/4 fallback |
| `@meta_tool` refactor -- actions/ + roles/ directories | ✅ v1.0 | Auto-discovery, dynamic config |
| `**kwargs` removal, vision guard, dynamic sleep-learn config | ✅ v1.1 | Hardening pass |
| `budget_chars` `or` trap fix, traceback scoping | ✅ v1.1 | Config robustness |
| Char multiplier tightening (5->3), metrics `.copy()` | ✅ v1.1 | Trim accuracy |
| `max_context_tokens` in `FakeCfg`, test robustness | ✅ v1.1 | Test fixes |
| `sleep_learn` per-role flags | ✅ v1.1 | Explicit config |
| 3 new autonomous maintenance roles: `refactor`, `test`, `document` | ✅ v1.2 | Requires `core/config.py` and `.env` and `core/llm_backend/config.py` updates |
| Timeout single source of truth | ✅ v1.2 | `core/llm_backend/config.py` |
| Escalation response completeness | ✅ v1.2 | |
| Cache key includes temperature/max_tokens | ✅ v1.2 | |
| Consultor guard | ✅ v1.2 | |
| Scaled context trimming for large budgets | ✅ v1.2 | |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Self-improving prompts via sleep-learn feedback loop | Auto-tune system prompts based on success/failure metrics from per-role metrics | P1 |
| `dry_run` / `estimate_cost` mode | Pre-flight cost estimation without calling LLM | P2 |
| Streaming support | Partial responses for long-running roles; requires `core/llm.py` redesign | P3 |
| Role composition chaining | Chain multiple roles in single call: `analyze` -> `code` -> `review` | P3 |
| Parallel tool execution | Expose `core/parallel_executor.py` as a `parallel` tool for research workflows | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| *(No deferred items yet. Add here when a feature is explicitly rejected or postponed.)* |

> **Rule:** When adding a deferred item, include the explicit decision reason — not just "not needed." Link to the discussion or commit if available.

---

*Last updated: 2026-07-12. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
