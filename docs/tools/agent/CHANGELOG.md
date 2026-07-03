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

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
