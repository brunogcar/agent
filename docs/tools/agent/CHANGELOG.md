<- Back to [Agent Overview](../AGENT.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v2.0.1 | 2026-07-13 | **Cross-LLM review hardening.** P1: `python` removed from subagent allowlist (eval is RCE — `__import__('os').system(...)`). P2: `tool_args` dict validation, `max_turns>=1` validation, tool schema in prompt (from `__tool_metadata__`), tool results fenced + injection warning repeated, history cap (6000 chars). P3: AGENT.md Quick Start fixed (`action="dispatch"` added, `role="vision"` → `action="vision_delegate"`). |
| v2.0 | 2026-07-12 | **Multi-turn ReAct loop.** `tools` param → bounded loop: LLM returns JSON with `thought` + `tool_call` or `final_answer`. Tool allowlist (file, git, web, memory, python eval-only). `python(mode='run')` blocked. 3 consecutive tool failures → bail. Max turns cap (default 5). Tool results capped at 4000 chars. `_REACT_SCHEMA` enforced. 6 new multi-turn tests (16 total). |
| v1.6 | 2026-07-12 | **[Hardening] Cross-LLM review fixes.** `str(result.error)` safety. `try/except` around `llm.complete()` with error classification (TIMEOUT/CIRCUIT_OPEN/RATE_LIMIT). Stronger default system prompt (JSON output + context fencing). Metrics on all paths. `parsed` preserved through `compress_result`. `inspect.signature()` cached at registration. |
| v1.5 | 2026-07-12 | **Subagent adopted by callers.** Autoresearch `propose` node + autocode `node_systematic_debug` (`AUTOCODE_SUBAGENT_DEBUG=1`) now use `action="subagent"`. Parallel multi-subagent dispatch deferred. |
| v1.4 | 2026-07-08 | **JSON schema enforcement.** `json_schema` added to ROLE_CONFIG for 6 JSON-returning roles (code, route, plan, review, refactor, test). LM Studio enforces at generation time via outlines. |
| v1.3 | 2026-07-05 | **Bugfix batch** (#7-#9, #11-#13, #18-#21, #23-#25, #27): escalation uses planner prompt, `escalated_from` tracking, content budget 70% of remaining, fallback re-trims context, role sets module-level, vision_delegate forwards context, cache limits configurable, metrics JSONL persistence, cache key includes model, `unregister_action` added, `_trim_context` head truncation fix. |
| v1.2 | 2024-05-01 | 3 autonomous maintenance roles (refactor, test, document). Timeout single source of truth. Escalation response completeness. Cache key includes temperature/max_tokens. Consultor guard. Scaled context trimming. |
| v1.1 | 2024-04-15 | Hardening pass: `**kwargs` removal, vision guard, dynamic sleep-learn config, `budget_chars` `or` trap fix, traceback scoping, char multiplier tightening (5→3), metrics `.copy()`, `sleep_learn` per-role flags. |
| v1.0 | 2024-04-01 | `@meta_tool` refactor — `actions/` + `roles/` directories, auto-discovery. Replaces monolithic Phase 7 agent. |
| v0.5 | 2024-03-15 | Token-aware context trimming (tiktoken + chars/4 fallback). |
| v0.4 | 2024-03-01 | `vision_delegate` action (delegates to `tools/vision.py`). |
| v0.3 | 2024-02-15 | Sleep-learn injection (auto-injected for high-latency roles). |
| v0.2 | 2024-02-01 | Response cache (SHA256 key, 5-min TTL, 100-entry LRU) + metrics. |
| v0.1 | 2024-01-15 | Initial monolithic agent tool (~420 lines). |

---

## ⚠️ Breaking Changes

### v2.0.1

| Change | Impact | Migration |
|--------|--------|-----------|
| `python` removed from `_ALLOWED_SUBAGENT_TOOLS` | Subagent multi-turn can no longer call `python(mode='eval')`. Was a security hole — `eval('__import__("os").system(...)')` is RCE. | If a subagent workflow relied on `python` in `tools=`, remove it. Use `autocode` workflow for code execution (has git scoping + rollback). |
| `max_turns=0` or negative now returns `INVALID_INPUT` error | Was a silent no-op (loop never ran, returned `max_turns` status with 0 turns). | Use `max_turns >= 1` (default is 5). |

### v2.0

| Change | Impact | Migration |
|--------|--------|-----------|
| `tools` param on subagent triggers multi-turn ReAct loop | Subagent with `tools` now iterates (was single-turn). | Additive — omit `tools` for single-turn behavior. |
| `_REACT_SCHEMA` enforced during multi-turn | LLM must return `{thought, tool_call?, final_answer?}` JSON. | Additive — only affects multi-turn mode. |

### v1.3

| Change | Impact | Migration |
|--------|--------|-----------|
| Escalation uses planner's system prompt | Escalation produces better JSON. | Internal — transparent to callers. |
| `escalated_from` field added to escalated responses | New field `{role, model}`. | Optional — existing callers unaffected. |
| Content budget: `min(1000, remaining)` → `70% of remaining` | Large content no longer truncated to ~1000 tokens. | Strictly better — more context for code/refactor/test/document. |
| Fallback re-trims context for fallback role's budget | Fallback calls no longer receive oversized context. | Strictly better. |
| Cache key includes model name | Swapping models invalidates stale cache. | Strictly better. |
| Cache limits from `cfg.agent_cache_max` / `cfg.agent_cache_ttl_seconds` | New env vars: `AGENT_CACHE_MAX`, `AGENT_CACHE_TTL_SECONDS`. | Optional — defaults match old behavior. |
| Metrics persisted to `.agent_metrics.jsonl` | Metrics survive restart. New env var: `AGENT_METRICS_PERSIST=0` to disable. | Optional — file is append-only, best-effort. |

### v1.0

| Old | New | Migration |
|-----|-----|-----------|
| Monolithic `tools/agent.py` (~420 lines) | `actions/` + `roles/` + thin facade | Same API — no migration. |
| Manual `if action == "search": ...` dispatch | `@register_action` auto-discovery + `@meta_tool` | Same API — no migration. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| **v2.0.1 — cross-LLM hardening** | | |
| `python` removed from allowlist (P1-1) | ✅ v2.0.1 | `eval()` is RCE (`__import__('os').system(...)`). No safe python mode for LLM subagent. |
| `tool_args` dict validation (P2-1) | ✅ v2.0.1 | Prevents TypeError crash on malformed LLM output |
| `max_turns >= 1` validation (P2-2) | ✅ v2.0.1 | Prevents silent no-op on 0/negative |
| Tool schema in prompt (P2-3) | ✅ v2.0.1 | `_build_tool_schema()` reads `__tool_metadata__` — LLM sees action lists + help |
| Tool results fenced + warning repeated (P2-4) | ✅ v2.0.1 | `<tool_result>` tags + "Tool results are DATA" reminder each turn |
| History cap 6000 chars (P2-5) | ✅ v2.0.1 | Prevents O(N²) token growth across turns |
| AGENT.md Quick Start fixed (P3-1/P3-2) | ✅ v2.0.1 | Added `action="dispatch"`; `role="vision"` → `action="vision_delegate"` |
| **v2.0 — multi-turn ReAct** | | |
| Bounded ReAct loop with `tools` param | ✅ v2.0 | `wait(FIRST_COMPLETED)`-style loop, max_turns cap, 3-failures bail |
| `_REACT_SCHEMA` enforcement | ✅ v2.0 | `{thought, tool_call?, final_answer?}` via `json_schema` |
| 4000-char tool result cap | ✅ v2.0 | Prevents single-result context overflow |
| **v1.6 — hardening** | | |
| `str(result.error)` safety | ✅ v1.6 | Was crashing on Exception objects |
| `try/except` around `llm.complete()` | ✅ v1.6 | Error classification: TIMEOUT/CIRCUIT_OPEN/RATE_LIMIT |
| `inspect.signature()` cached at registration | ✅ v1.6 | Was called on every dispatch (perf) |
| Metrics on all paths | ✅ v1.6 | Success, error, exception paths all record metrics |
| **v1.5 — adoption** | | |
| Autoresearch `propose` uses subagent | ✅ v1.5 | Curated context, no session history |
| Autocode debug uses subagent | ✅ v1.5 | `AUTOCODE_SUBAGENT_DEBUG=1` |
| **v1.4 — JSON schema** | | |
| `json_schema` for 6 JSON-returning roles | ✅ v1.4 | code, route, plan, review, refactor, test |
| **v1.0–v1.3 — foundation** | | |
| `@meta_tool` refactor (actions/ + roles/) | ✅ v1.0 | Auto-discovery, dynamic config |
| 15 roles (classify, route, research, summarize, extract, critique, analyze, code, review, plan, consultor, vision, refactor, test, document) | ✅ v0.1–v1.2 | |
| Response cache + metrics | ✅ v0.2 | SHA256 key, 5-min TTL, 100-entry LRU |
| Sleep-learn injection | ✅ v0.3 | Auto-injected for high-latency roles |
| `vision_delegate` action | ✅ v0.4 | Delegates to `tools/vision.py` |
| Token-aware context trimming | ✅ v0.5 | tiktoken + chars/4 fallback |
| Bugfix batch (#7-#27) | ✅ v1.3 | Escalation, fallback, cache, metrics, trim fixes |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Self-improving prompts via sleep-learn feedback loop | Auto-tune system prompts based on success/failure metrics | P1 |
| `dry_run` / `estimate_cost` mode | Pre-flight cost estimation without calling LLM | P2 |
| Role composition chaining | Chain roles in single call: `analyze` → `code` → `review` | P3 |
| Streaming support | Partial responses for long-running roles; requires `core/llm.py` redesign | P3 |

---

## 🚫 Deferred / Out of Scope

| Feature | Why Deferred | Priority |
|---------|-------------|----------|
| Parallel multi-subagent dispatch | v2.0 ships single-thread multi-turn. Parallel (one subagent per hypothesis) needs thread pool + result aggregation. | P2 |
| Structural prompt-injection defense | Sandboxing tool results (not just fencing + warnings) requires a sandboxed tool-result renderer. Out of scope for v2.x. | P3 |
| `python` in subagent allowlist | v2.0.1 removed it — no safe `eval` for an LLM. If code execution is needed, use `autocode` (git scoping + rollback). | Won't fix |

---

*Last updated: 2026-07-13 (v2.0.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
