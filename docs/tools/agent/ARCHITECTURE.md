<- Back to [Agent Overview](../AGENT.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `.env` | **New roles:** Add `NEWROLE_MODEL=` (empty = fallback chain) |
| `core/config.py` | **New roles:** `model_registry` entry via `_make_entry()` with env var fallback. Add direct timeout attribute if consumed outside `model_registry`. |
| `core/llm_backend/config.py` | **New roles:** Add entry to `_defaults` dict with `model`, `provider`, `timeout`, `temperature`, `max_tokens`. |
| `tools/agent.py` | `@tool` + `@meta_tool` facade: validation, dispatch, compress_result |
| `tools/agent_ops/__init__.py` | Auto-discovers `actions/*.py` and `roles/*.py` at import time |
| `tools/agent_ops/_registry.py` | `DISPATCH` dict + `@register_action` decorator with duplicate guard |
| `tools/agent_ops/context.py` | `_trim_context()`, `_estimate_tokens()`, `_max_context_tokens()`, `_max_context_chars()` |
| `tools/agent_ops/cache.py` | `_cache_key()`, `_get_cached()`, `_set_cached()`, `_clear_cache()` |
| `tools/agent_ops/metrics.py` | `_record_metric()`, `_get_metrics()`, `_clear_metrics()` |
| `tools/agent_ops/parse_warnings.py` | `_log_parse_warning()`, `_get_parse_warnings()`, `_clear_parse_warnings()` |
| `tools/agent_ops/json_extract.py` | `_extract_first_json()` — brace-counting extraction with dict-preference scoring |
| `tools/agent_ops/actions/dispatch.py` | `@register_action("agent", "dispatch")` — core LLM orchestrator |
| `tools/agent_ops/actions/metrics.py` | `@register_action("agent", "metrics")` — query per-role metrics |
| `tools/agent_ops/actions/vision_delegate.py` | `@register_action("agent", "vision_delegate")` — delegate to tools.vision |
| `tools/agent_ops/actions/clear_cache.py` | `@register_action("agent", "clear_cache")` — clear response cache |
| `tools/agent_ops/roles/*.py` | 12 files: `SYSTEM_PROMPT` + `ROLE_CONFIG` per role |
| `tests/tools/agent/conftest.py` | Test fixtures: `mock_cfg` (autouse), `mock_llm_result` |
| `tests/tools/agent/test_agent_validation.py` | Validation and role coverage tests |
| `tests/tools/agent/test_agent_vision.py` | Vision delegation tests |
| `tests/tools/agent/test_agent_vision_params.py` | Vision passthrough parameter tests |
| `tests/tools/agent/test_agent_llm_dispatch.py` | LLM dispatch and error handling tests |
| `tests/tools/agent/test_agent_json_parsing.py` | JSON parsing fallback tests |
| `tests/tools/agent/test_agent_context.py` | Context trimming unit tests |
| `tests/tools/agent/test_agent_sleep_learn.py` | Sleep-learn injection integration tests |
| `tests/tools/agent/test_agent_roles.py` | ROLE_CONFIG validation and budget override tests |
| `tests/tools/agent/test_agent_caching.py` | Response caching hit/miss/TTL tests |
| `tests/tools/agent/test_agent_errors.py` | Structured error taxonomy tests |
| `tests/tools/agent/test_agent_token_aware.py` | Token-aware trimming tests |
| `tests/tools/agent/test_agent_metrics.py` | Per-role metrics tests |
| `tests/tools/agent/test_agent_parse_warnings.py` | Parse warning logging tests |
| `tests/tools/agent/test_agent_escalation.py` | Autonomous model escalation tests |
| `tests/tools/agent/test_agent_fallback.py` | Role fallback chain tests |

---

## Module Tree

```
tools/agent.py                    # @tool + @meta_tool facade — validation, dispatch
tools/agent_ops/
├── __init__.py                   # Auto-discovers actions/*.py and roles/*.py
├── _registry.py                  # DISPATCH dict + @register_action decorator
├── context.py                    # _trim_context(), _estimate_tokens(), _max_context_chars()
├── cache.py                      # Response cache: SHA256 key, 5-min TTL, 100-entry LRU
├── metrics.py                    # Per-role in-memory metrics collection
├── parse_warnings.py             # Rolling log of JSON parse failures (max 50)
├── json_extract.py               # Brace-counting JSON extraction with dict-preference scoring
├── actions/
│   ├── dispatch.py               # Core LLM orchestrator: role lookup → trim → llm.complete()
│   ├── metrics.py                # Query per-role metrics and parse warnings
│   ├── vision_delegate.py        # Delegate to tools.vision.vision() (multimodal)
│   └── clear_cache.py            # Clear response cache for deterministic roles
└── roles/
    ├── classify.py               # Fast classifier (router model, 4K budget)
    ├── route.py                  # Task router (router model, 4K budget)
    ├── research.py               # Research synthesizer (executor model, 32K budget)
    ├── summarize.py              # Text summarizer (executor model, 32K budget)
    ├── extract.py                # Information extractor (executor model, 16K budget)
    ├── critique.py               # Quality critic (executor model, 16K budget)
    ├── analyze.py                # Data analyst (executor model, 32K budget)
    ├── code.py                   # Code generator (executor model, 32K budget)
    ├── review.py                 # Code reviewer (executor model, 16K budget)
    ├── plan.py                   # Task planner (planner model, 32K budget)
    ├── consultor.py              # Cross-model consultant (planner model, 16K budget)
    ├── vision.py                 # Vision persona (NOT a dispatch role — delegates to tools/vision.py)
    ├── refactor.py               # Code refactoring specialist (executor model, 32K budget)
    ├── test.py                   # Test generation specialist (executor model, 32K budget)
    └── document.py               # Documentation specialist (executor model, 32K budget)
```

---

## Dispatch Flow

```
1. agent(action='dispatch', role='classify', task='...')
2. Validate role exists in ROLES
3. Reject vision role (use action='vision_delegate')
4. Check cache (if cacheable)
5. Inject sleep-learn rules (if role.sleep_learn)
6. _trim_context(context, budget_tokens) + _trim_context(content)
7. llm.complete(role, system, user, context, content, json_mode)
8. If failed: retry with fallback_role (one attempt)
9. If JSON role: parse JSON (API parsed → brace-counting → planner escalation)
10. Record metrics
11. Store in cache (if cacheable)
12. Return response
```

---

## Key Design Decisions

### @meta_tool pattern

`action` parameter is a `Literal["dispatch", "metrics", "vision_delegate", "clear_cache"]` auto-generated from `DISPATCH`. `role` is a standard `str` consumed internally by the `dispatch` action.

### Dynamic role config

`_json_roles` and `_sleep_learn_roles` are derived from `ROLE_CONFIG` at runtime, not hardcoded. Changing a role's `json_mode` or `sleep_learn` flag immediately affects behavior without touching `dispatch.py`.

### Per-role context budgets

`budget_tokens` takes precedence over `budget_chars`. If both are set, the tighter constraint wins (defensive against config drift).

### Token-aware trimming

`_estimate_tokens()` uses tiktoken (cached encoder) when available, falls back to chars/4. `_trim_context()` accepts `max_tokens` for accurate budget enforcement. The `max_tokens` path uses `budget * 3` as a conservative char-to-token multiplier for slicing.

### Response caching

`classify` and `route` are deterministic: same input → same output. Cached by SHA256 hash, 5-minute TTL, 100-entry LRU.

### Structured errors

`error_code` field (`INVALID_ROLE`, `INVALID_INPUT`, `TIMEOUT`, `CIRCUIT_OPEN`, `RATE_LIMIT`, `MODEL_ERROR`) lets callers retry intelligently.

### Role fallback chains

On transient LLM failure, automatically retry with a functionally similar role (e.g., `classify`→`route` returns structured category info).

### Autonomous model escalation

If a prompt-only JSON role produces invalid JSON, the facade automatically retries with the planner model (heavier, more compliant) before giving up.

### Per-role metrics

Lightweight in-memory tracking: calls, successes, failures, total elapsed, total tokens, parse failures. Query via `agent(action="metrics", task="role_name")`.

### Parse warning logging

Rolling log (max 50 entries) of JSON parse failures per role. Enables data-driven prompt tuning: if a role's parse failure rate spikes, tighten its system prompt.

### Vision is an action, not a role

`vision_delegate` is a separate action that delegates to `tools/vision.vision()`. The `vision` role file exists for documentation but is rejected by `dispatch` with a helpful error message.

### Sleep-learn per-role configurable

`sleep_learn: bool` in `ROLE_CONFIG` controls whether a role gets rule injection. Previously hardcoded to roles with 60s+ budgets; now explicit in config.

### Auto-Discovery

`tools/agent_ops/__init__.py` uses `pathlib` + `importlib` to auto-discover all `.py` files in `actions/` and `roles/` at import time. This means:
- **Adding an action**: drop a file in `actions/`, decorate with `@register_action("agent", "action_name")`
- **Adding a role**: drop a file in `roles/`, export `SYSTEM_PROMPT` and `ROLE_CONFIG`
- **No manual registration lists** — zero risk of forgetting to wire a new action or role

---

## 🧪 Testing

```powershell
# Run all core/net tests
.\venv\Scripts\python tests/tools/agen/t -W error --tb=short -v

> **Note:** Ensure `pytest` resolves to your venv. If not, use `python -m pytest` or the full venv path (`venv\Scripts\pytest.exe` on Windows, `venv/bin/pytest` on Unix).
```

**Test architecture:**
- `conftest.py` provides `mock_cfg` (autouse, FakeCfg with `max_context_tokens=8000`) and `mock_llm_result` fixtures
- `mock_cfg` prevents AsyncMock leakage from other tests per test isolation rule
- Tests are **fully isolated** — no real LLM calls, no network, no shared state
- Module-level state (cache, metrics, parse warnings) is cleared between tests via `clear_agent_state` autouse fixture

### Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `conftest.py` | - | Shared fixtures (mock_cfg, mock_llm_result) |
| `test_agent_validation.py` | - | Unknown action, unknown role, missing task |
| `test_agent_vision.py` | - | Vision delegation to tools.vision |
| `test_agent_vision_params.py` | - | mime_type and vision_json_mode passthrough |
| `test_agent_llm_dispatch.py` | - | Successful LLM call, LLM failure, param passthrough |
| `test_agent_json_parsing.py` | - | Valid JSON, invalid JSON, markdown fences, extraction |
| `test_agent_context.py` | - | _trim_context unit tests + traceback preservation |
| `test_agent_sleep_learn.py` | - | Sleep-learn injection: call site, gating, fallback |
| `test_agent_roles.py` | - | ROLE_CONFIG validation and budget override tests |
| `test_agent_caching.py` | - | Response caching hit/miss/TTL tests |
| `test_agent_errors.py` | - | Structured error taxonomy tests |
| `test_agent_token_aware.py` | - | Token-aware trimming and _estimate_tokens tests |
| `test_agent_metrics.py` | - | Per-role metrics collection and query tests |
| `test_agent_parse_warnings.py` | - | Parse warning logging and retrieval tests |
| `test_agent_escalation.py` | - | Autonomous model escalation on parse failure |
| `test_agent_fallback.py` | - | Role fallback chain retry tests |

### Mock Strategy

- `llm.complete` is patched at `tools.agent_ops.actions.dispatch.llm.complete` (where it is used)
- `tools.vision.vision` is patched at `tools.vision.vision` (where it is imported inline)
- `cfg` is patched at `tools.agent_ops.context.cfg` (module-level import)
- `mock_llm_result` is a pre-built class with all required attributes matching `LLMResponse.usage` shape: `{'prompt': int, 'completion': int, 'total': int}`
- Cache, metrics, and parse warning logs are cleared via `clear_agent_state` autouse fixture

### Current Test Layout

```
tests/tools/agent/
├── conftest.py
├── test_agent_validation.py
├── test_agent_vision.py
├── test_agent_vision_params.py
├── test_agent_llm_dispatch.py
├── test_agent_json_parsing.py
├── test_agent_context.py
├── test_agent_sleep_learn.py
├── test_agent_roles.py
├── test_agent_caching.py
├── test_agent_errors.py
├── test_agent_token_aware.py
├── test_agent_metrics.py
├── test_agent_parse_warnings.py
├── test_agent_escalation.py
└── test_agent_fallback.py
```

---

*Last updated: 2026-07-03. See [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
