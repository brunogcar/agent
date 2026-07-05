<- Back to [Agent Overview](../AGENT.md)

## 🛡️ AI Instructions

## NEVER DO

1. **Never add business logic to `agent.py`** — the facade should only validate, dispatch, cache, and parse. Move prompts to `prompts.py`, role config to `roles.py`, trimming to `context.py`.
2. **Never strip or rewrite entire files** — only add comments, docstrings, or formatting. Preserve all existing code exactly.
3. **Never route `vision` through `llm.complete()`** — Always delegate to `tools/vision.py`.
4. **Never break traceback logic** — `_trim_context()` traceback detection must not be broken. Tracebacks are high-signal debugging content.
5. **Never create `.bak` files** — forbidden by project rules.
6. **Never use `git commit --amend --no-edit` for new work** — use `git commit -m` with detailed info.

---

## ALWAYS DO

7. **Add roles in two places** — new roles require: (a) entry in `ROLE_CONFIG` in `roles.py`, (b) prompt in `prompts.py`.
8. **Patch `cfg` at the right module** — `context.py` imports `cfg` at module level. If conftest patches it, the patch must target `tools.agent_core.context.cfg`.
9. **Test with `mock_llm_result`** — new tests must use the `mock_llm_result` fixture from `conftest.py`.
10. **Handle JSON parsing fallback** — prompt-only JSON roles must handle markdown fences, surrounding text, arrays at root, and parse failures gracefully.
11. **Gate sleep-learn to high-latency roles** — if adding `inject_rules_into_prompt` calls, gate to high-latency roles only. Router roles must not pay ChromaDB overhead.
12. **Clear cache or bump version when changing prompts** — if changing `classify`/`route` system prompts, the cache key does NOT include prompt version. Clear cache or bump version manually.
13. **Remember metrics are in-memory** — `_ROLE_METRICS` and `_PARSE_WARNING_LOG` are not persisted. Do not rely on them across process restarts.
14. **Limit fallback to one-shot** — if primary fails and fallback also fails, return error. Do not chain more than one fallback.
15. **Limit escalation to one-shot** — if planner model also fails to produce valid JSON, return `parse_warning`. Do not loop.

---

## 🚫 Anti-Patterns & Lessons Learned

These are hard-won lessons from the Phase 7 `@meta_tool` refactor. Read before modifying.

### 1. Never use `**kwargs` on `@register_action` handlers

**What happened:** `run_dispatch(**kwargs)` silently swallowed misspelled parameters from the facade.

**Why it matters:** The facade passes `mime_type`, `vision_json_mode`, and other params. If the facade passes a typo (e.g., `mim_type`), `**kwargs` eats it instead of raising `TypeError`. This makes debugging impossible.

**Fix:** Explicit parameter list. No `**kwargs`. If the facade adds a new param, the handler must declare it.

### 2. Never use `or` for config defaults with `0` or `False`

**What happened:** `budget_chars = role_cfg.get("budget_chars") or _max_context_chars()` meant `budget_chars=0` ("never use context") was overridden with the global default.

**Fix:** `budget_chars = role_cfg.get("budget_chars"); if budget_chars is None: budget_chars = _max_context_chars()`

### 3. Never assume `budget_tokens` and `budget_chars` are consistent

**What happened:** `classify` had `budget_tokens=4000` but `budget_chars=16000`. The code took the `budget_tokens` branch and `_trim_context` with `max_tokens=4000` returned 25000 chars because the char multiplier was `* 5` (too loose).

**Fix:** `char_budget = budget * 3` (was `* 5`). The multiplier must be tighter than the fallback heuristic (`chars // 4`) to guarantee the trimmed text fits within the token budget.

### 4. Never hardcode role sets in `dispatch.py`

**What happened:** `_prompt_json_roles = {"route", "plan", "code", "review"}` and `_sleep_learn_roles = {"research", "analyze", ...}` were hardcoded. If a role's `json_mode` or `sleep_learn` flag changed, the sets drifted.

**Fix:** Derive at runtime: `{k for k, v in ROLES.items() if v["role_config"].get("json_mode") == "prompt"}`

### 5. Never let the `vision` role be dispatched as text

**What happened:** `roles/vision.py` existed with `llm_role='vision'`. If someone called `agent(action='dispatch', role='vision', ...)`, it would try to use the text LLM with a vision model role name, producing garbage.

**Fix:** `dispatch` rejects `role='vision'` with a helpful error: `Use action='vision_delegate' for vision tasks`. Vision is an action, not a dispatch role.

### 6. Never forget `max_context_tokens` in `FakeCfg`

**What happened:** `conftest.py` `FakeCfg` lacked `max_context_tokens`. When a role fell through to `_max_context_chars()` (no `budget_tokens` set), it hit `AttributeError` on `cfg.max_context_tokens`.

**Fix:** Always include `max_context_tokens = 8000` in test fixtures that patch `cfg`.

### 7. Never mutate `_get_metrics` return value

**What happened:** `_get_metrics` returned the actual dict reference. Callers could mutate it, corrupting the module-level state.

**Fix:** Return `.copy()` so callers get a shallow copy.

### 8. Never narrow sleep-learn exceptions too much

**What happened:** Changed `except Exception:` to `except (RuntimeError, OSError, ConnectionError):`. The test patched `inject_rules_into_prompt` to raise `Exception("injector failed")`, which was no longer caught.

**Fix:** Keep `except Exception:` for sleep-learn. It's a non-fatal enhancement -- any failure should fall back to the original prompt. The `ImportError` for the module import is already handled separately.

### 9. Never use single-quoted strings for multi-line prompts with braces

**What happened:** When generating role files programmatically, single-quoted strings with unescaped newlines and JSON braces caused `SyntaxError: unterminated string literal`.

**Fix:** Always use triple-quoted strings for multi-line prompts. Never mix single quotes with embedded JSON.

### 10. Never forget the `tb_tokens` variable in traceback branches

**What happened:** In `_trim_context`, `tb_tokens` was only set in the `tokens` branch but referenced unconditionally in the fit check. When `budget_type == "chars"`, `tb_tokens` was undefined, causing `UnboundLocalError`.

**Fix:** Set `tb_tokens = None` in the `chars` branch. The fit check uses `(tb_tokens is not None and tb_tokens <= budget) or (tb_tokens is None and tb_len <= budget)`.

### 11. Never write role files with JSON-style booleans

**What happened:** Generated role files with `"cacheable": false` (JSON) instead of `"cacheable": False` (Python). Python raised `NameError: name 'false' is not defined`.

**Fix:** Always use Python booleans (`True`/`False`) in generated Python code. Use `str(value)` not `json.dumps(value)` for booleans.

### 12. Never skip `_trim_context` unit tests for `max_tokens` path

**What happened:** No direct test for `_trim_context(text, max_tokens=N)`. The bug (multiplier too loose) only surfaced in an integration test.

**Fix:** Add dedicated unit tests for `_trim_context` with `max_tokens` parameter, testing both with and without tiktoken.

### 13. Never call `on_failure()` per retry attempt

**What happened:** `retry_async_factory` called `on_failure()` on every retryable exception inside the loop. A call that needed 2 retries to succeed recorded 2 CB failures permanently. Since `record_success()` is a no-op in CLOSED CB state, 3 successful-but-retried calls would open the CB.

**Fix:** Call `on_failure()` only on final raise (retry exhaustion), not per-attempt. Preserves v1.4 semantics: non-retryable errors still don't trip the CB.

### 14. Never build role sets at module load time

**What happened:** `_SLEEP_LEARN_ROLES`, `_JSON_ROLES` were built at module import, but `ROLES` wasn't populated yet (`__init__.py` imports actions before roles). The sets were empty, so JSON parsing and sleep-learn injection were silently skipped.

**Fix:** Use lazy init — build the sets on first `run_dispatch()` call via `_ensure_role_sets_initialized()`, then cache. Idempotent after first call.

### 15. Never reuse primary's trimmed context for fallback role

**What happened:** When the primary LLM call failed and fallback was triggered, the fallback reused the primary's trimmed context. If the fallback role had a smaller budget, it received oversized context.

**Fix:** Re-trim context/content for the fallback role's budget using the same 70% content budget fraction.

### 16. Never hardcode `json_mode=False` for escalation

**What happened:** Escalation to planner hardcoded `json_mode=False` while requesting JSON output. Also used the original role's system prompt instead of the plan role's prompt.

**Fix:** Use `ROLES["plan"]["role_config"]["json_mode"] == "api"` for escalation's json_mode, and `ROLES["plan"]["system_prompt"]` for the system prompt. The plan role is designed for structured output.

### 17. Never fail-open on unknown operations in `check_protected_file`

**What happened:** `check_protected_file` returned `(True, "")` (allow) for unknown operations. New write actions added to tools but forgotten in `WRITE_OPERATIONS` would silently bypass protection on protected files.

**Fix:** Fail-closed — return `(False, error_msg)` for unknown operations. New actions must be explicitly added to `READ_OPERATIONS` or `WRITE_OPERATIONS`.

---

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
