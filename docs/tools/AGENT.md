# 🤖 Agent Tool

The `agent()` tool is the **meta-cognitive dispatcher** of the MCP Agent Stack. It routes tasks to specialist sub-agents based on a `role` parameter, each with its own system prompt, model, timeout, and output format.

**Key characteristics:**
- **Single entry point** — The LLM sees one tool: `agent(action, role, task, ...)`
- **Action-based routing** — `action` is a `@meta_tool` Literal enum: `dispatch`, `metrics`, `vision_delegate`, `clear_cache`
- **Role-specialized prompts** — 15 distinct personas, each with tailored instructions
- **Per-role model routing** — Router uses fast 2B models, Executor uses capable 9B models
- **Per-role context budgets** — Router gets 4K tokens, Planner gets 32K tokens
- **Token-aware context trimming** — Uses tiktoken when available, falls back to chars/4
- **Response caching** — Deterministic roles (`classify`, `route`) cached with 5-min TTL
- **Structured output enforcement** — JSON mode for `extract`, prompt-only JSON for `route`, `plan`, `code`, `review`
- **Structured errors** — `error_code` field enables programmatic retry decisions
- **Autonomous model escalation** — On JSON parse failure, auto-retries with planner model
- **Role fallback chains** — `classify`→`route`, `critique`→`analyze`, `consultor`→`plan` on transient failure
- **Per-role metrics** — In-memory tracking of calls, success rate, latency, tokens, parse failures
- **Parse warning logging** — Rolling log of JSON parse failures for data-driven prompt tuning
- **Context trimming** — Head+tail truncation with traceback preservation before reaching the LLM
- **Vision delegation** — `vision_delegate` action delegates to `tools/vision.py` for multimodal analysis
- **Sleep-learn integration** — Learned rules auto-injected for roles with `sleep_learn: True` (configurable per role)
- **NOT_PARALLEL_SAFE** — Serialized via global LLM client queue; no concurrent agent calls

---

## 🏗️ Architecture

The agent tool follows the **@meta_tool + actions/roles** pattern established by `git`, `file`, `report`, and `cli`. `tools/agent.py` is a thin `@tool` facade with `@meta_tool` auto-generated docstring. All business logic lives in `tools/agent_core/`.

```
tools/agent.py                    # @tool + @meta_tool facade — validation, dispatch
tools/agent_core/
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

### Auto-Discovery

`tools/agent_core/__init__.py` uses `pathlib` + `importlib` to auto-discover all `.py` files in `actions/` and `roles/` at import time. This means:
- **Adding an action**: drop a file in `actions/`, decorate with `@register_action("agent", "action_name")`
- **Adding a role**: drop a file in `roles/`, export `SYSTEM_PROMPT` and `ROLE_CONFIG`
- **No manual registration lists** — zero risk of forgetting to wire a new action or role

### Dispatch Flow

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

**Key design decisions:**
- **@meta_tool pattern** — `action` parameter is a `Literal["dispatch", "metrics", "vision_delegate", "clear_cache"]` auto-generated from `DISPATCH`. `role` is a standard `str` consumed internally by the `dispatch` action.
- **Dynamic role config** — `_json_roles` and `_sleep_learn_roles` are derived from `ROLE_CONFIG` at runtime, not hardcoded. Changing a role's `json_mode` or `sleep_learn` flag immediately affects behavior without touching `dispatch.py`.
- **Per-role context budgets** — `budget_tokens` takes precedence over `budget_chars`. If both are set, the tighter constraint wins (defensive against config drift).
- **Token-aware trimming** — `_estimate_tokens()` uses tiktoken (cached encoder) when available, falls back to chars/4. `_trim_context()` accepts `max_tokens` for accurate budget enforcement. The `max_tokens` path uses `budget * 3` as a conservative char-to-token multiplier for slicing.
- **Response caching** — `classify` and `route` are deterministic: same input → same output. Cached by SHA256 hash, 5-minute TTL, 100-entry LRU.
- **Structured errors** — `error_code` field (`INVALID_ROLE`, `INVALID_INPUT`, `TIMEOUT`, `CIRCUIT_OPEN`, `RATE_LIMIT`, `MODEL_ERROR`) lets callers retry intelligently.
- **Role fallback chains** — On transient LLM failure, automatically retry with a functionally similar role (e.g., `classify`→`route` returns structured category info).
- **Autonomous model escalation** — If a prompt-only JSON role produces invalid JSON, the facade automatically retries with the planner model (heavier, more compliant) before giving up.
- **Per-role metrics** — Lightweight in-memory tracking: calls, successes, failures, total elapsed, total tokens, parse failures. Query via `agent(action="metrics", task="role_name")`.
- **Parse warning logging** — Rolling log (max 50 entries) of JSON parse failures per role. Enables data-driven prompt tuning: if a role's parse failure rate spikes, tighten its system prompt.
- **Vision is an action, not a role** — `vision_delegate` is a separate action that delegates to `tools/vision.vision()`. The `vision` role file exists for documentation but is rejected by `dispatch` with a helpful error message.
- **Sleep-learn per-role configurable** — `sleep_learn: bool` in `ROLE_CONFIG` controls whether a role gets rule injection. Previously hardcoded to roles with 60s+ budgets; now explicit in config.

---

## 📋 Tool Signature

```python
@tool
@meta_tool(
    DISPATCH.get("agent", {}),
    doc_sections=[...],
)
def agent(
    action: str = "",              # Required. Literal["dispatch", "metrics", "vision_delegate", "clear_cache"]
    role: str = "",              # Required for dispatch. See Roles table below.
    task: str = "",              # Required for dispatch/metrics/vision_delegate.
    context: str = "",           # Background information (dispatch) or image path (vision_delegate)
    content: str = "",           # Raw material or base64 image string
    trace_id: str = "",          # Trace identifier for observability
    temperature: float = -1.0,   # Temperature override (-1 = model default)
    max_tokens: int = -1,         # Max tokens override (-1 = model default)
    mime_type: str = "",         # (Vision only) Override MIME type
    vision_json_mode: bool = False,  # (Vision only) Request JSON output
) -> dict:
    """Agent meta-tool — atomic actions for cognitive tasks."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `Literal[...]` | `""` | **Required.** `dispatch` | `metrics` | `vision_delegate` | `clear_cache` |
| `role` | `str` | `""` | **Required for dispatch.** See Roles table below |
| `task` | `str` | `""` | **Required.** The instruction or question |
| `context` | `str` | `""` | Background info (dispatch) or image path/URL (vision_delegate) |
| `content` | `str` | `""` | Raw material or base64 image string |
| `trace_id` | `str` | `""` | Trace identifier for observability and logging |
| `temperature` | `float` | `-1.0` | Temperature override (-1 = model default) |
| `max_tokens` | `int` | `-1` | Max tokens override (-1 = model default) |
| `mime_type` | `str` | `""` | **(Vision only)** Override MIME type for image |
| `vision_json_mode` | `bool` | `False` | **(Vision only)** Request JSON output from vision |

**Meta-role:** `action="metrics"`, `task="role_name"` (or empty for all) returns collected metrics and parse warnings.

**For vision_delegate:** `context` = file_path or public URL, `content` = base64-encoded image.

---

## 🎭 Roles

| Role | LLM Role | Budget (tokens) | Budget (chars) | Cacheable | Fallback | Output | sleep_learn | Description |
|------|----------|-----------------|----------------|-----------|----------|--------|-------------|-------------|
| `classify` | `router` | 4K | 16K | ✅ | `route` | Single word | ❌ | Fast binary/category decision |
| `route` | `router` | 4K | 16K | ✅ | — | JSON | ❌ | Workflow + tool routing decision |
| `research` | `research` | 32K | 128K | ❌ | — | Markdown | ✅ | Synthesize web/memory content |
| `summarize` | `summarize` | 12K | 48K | ❌ | — | Markdown | ❌ | Dense, accurate summary |
| `extract` | `extract` | 12K | 48K | ❌ | — | JSON | ❌ | Structured data extraction (API json_mode) |
| `critique` | `critique` | 12K | 48K | ❌ | `analyze` | Markdown | ❌ | Quality evaluation: APPROVE / REVISE / REJECT |
| `analyze` | `analyze` | 12K | 48K | ❌ | — | Markdown | ✅ | Deep code/data analysis, no fixes |
| `code` | `code` | 32K | 128K | ❌ | — | JSON | ✅ | Generate Python patch: `{analysis, patch, tests}` |
| `review` | `review` | 12K | 48K | ❌ | — | JSON | ✅ | Review patch: `{verdict, issues, corrected_patch}` |
| `plan` | `planner` | 32K | 128K | ❌ | — | JSON | ✅ | Decompose goal into ordered steps |
| `consultor` | `consultor` | 12K | 48K | ❌ | `plan` | Markdown | ✅ | Expert advisory on architecture/best practices |
| `vision` | *(n/a)* | — | — | ❌ | — | — | ❌ | **Not dispatchable** — use `action="vision_delegate"` |
| `refactor` | `refactor` | 32K | 128K | ❌ | `code` | JSON | ✅ | Autonomous code refactoring |
| `test` | `test` | 32K | 128K | ❌ | `code` | JSON | ✅ | Autonomous test generation |
| `document` | `document` | 32K | 128K | ❌ | `summarize` | Markdown | ✅ | Autonomous documentation generation |

### Fallback Chains

When a role's primary LLM call fails (timeout, circuit open, rate limit), the agent automatically retries with its fallback role:

| Primary Role | Fallback Role | Rationale |
|--------------|---------------|-----------|
| `classify` | `route` | Route returns structured JSON with category info, functionally similar |
| `critique` | `analyze` | Analysis is a subset of critique (no verdict, but identifies issues) |
| `consultor` | `plan` | Plan provides structured advice, overlapping with consultor's advisory role |

Fallback is **one attempt only**. If the fallback also fails, the error is returned to the caller.

---

## ✂️ Context Trimming

Before any LLM call, `context` and `content` are passed through `_trim_context()`:

| Feature | Behavior |
|---------|----------|
| **Head + Tail** | Keeps first 2000 chars (goal/objective) and last 4000 chars (recent interactions) |
| **Per-role budget** | `classify`/`route`: 4K tokens (16K chars). `plan`/`research`/`code`: 32K tokens (128K chars). Others: 12K tokens (48K chars) |
| **Token-aware** | `_estimate_tokens()` uses tiktoken (cached encoder) when available, falls back to chars/4 |
| **Dynamic budget** | `cfg.max_context_tokens` fallback (config-reloadable, clamped to minimum 4000 chars) |
| **Traceback preservation** | If a Python traceback is detected, it is preserved in full. Uses line-by-line frame detection (not `\n\n` heuristics) for robustness. |
| **Custom max_chars** | `_trim_context(text, max_chars=500)` for one-off overrides |
| **Custom max_tokens** | `_trim_context(text, max_tokens=100)` for token-accurate trimming |
| **Content budget** | `content` is capped at ~1000 tokens, but also constrained by remaining role-specific budget |

### Content Budget

The `content` parameter (raw material to process) has a dedicated budget to prevent massive code dumps from consuming the entire context budget. However, it is also dynamically constrained: if `context` already consumed most of the role-specific budget, `content` gets whatever remains.

```python
# Example: plan role budget = 32K tokens
# context = 30K tokens worth of text → trimmed to ~30K tokens
# content = 5K tokens → trimmed to 2K (remaining budget) → then to min(1000, 2000) = 1000
```

### Traceback Preservation

```python
# Input: massive context with an embedded traceback
text = "Goal: fix bug..." + "\n" * 50000 + traceback + "\nRecent: tool result"

# Output: head preserved, traceback intact, tail after traceback preserved
result = _trim_context(text)
# "Goal: fix bug...\n\n[... 45000 chars truncated ...]\n\nTraceback (most recent call last):...\nZeroDivisionError"
```

---

## 📊 JSON Output Handling

Three categories of JSON roles:

| Category | Roles | Mechanism |
|----------|-------|-----------|
| **API json_mode** | `extract` | `llm.complete(json_mode=True)` — model enforces JSON schema |
| **Prompt-only JSON** | `route`, `plan`, `code`, `review` | System prompt demands JSON; post-hoc brace-counting extraction if model adds prose |
| **Non-JSON** | `classify`, `research`, `summarize`, `critique`, `analyze`, `consultor` | Free-form text output |

### JSON Parsing: Three-Stage Fallback

For prompt-only JSON roles, the parser uses a robust three-stage approach:

1. **Fast path** — Try `json.loads()` on the clean text (after stripping markdown fences).
   Works for well-behaved models that output clean JSON.

2. **Brace-counting extraction** — If fast path fails, scan for all `{` and `[` positions
   and use depth tracking (respecting string boundaries and escaped quotes) to find
   the complete JSON structure. Handles nested objects, arrays at root, and braces
   inside string values. Prefers dicts over arrays (since agent roles expect dict-root
   JSON), then the largest valid structure to handle prose before JSON.

3. **Autonomous model escalation** — If extraction fails, the facade automatically
   retries with the planner model (heavier, more JSON-compliant) before giving up.
   If escalation succeeds, `escalated: true` is set in the response.

   **Note:** Fallback + escalation can produce up to 3 sequential LLM calls
   (primary → fallback → planner escalation). This is intentional defense-in-depth,
   but be aware of compounding timeout risk.

4. **Graceful failure** — If all attempts fail, returns `parsed: {}` with a
   `parse_warning` so callers can safely do `result.get("parsed", {}).get("field")`
   without crashing.

```python
# Model output: "Here is the result:\n```json\n{\"verdict\": \"APPROVE\"}\n```"
# Extracted: {"verdict": "APPROVE"}
```

If parsing fails entirely, returns `parsed: {}` with a `parse_warning`:

```json
{
  "status": "success",
  "role": "review",
  "text": "I think this looks good...",
  "parsed": {},
  "parse_warning": "Response was not valid JSON for role 'review'. Empty dict returned for parsed. Check response.text for raw output."
}
```

**`parse_warning` field:** When JSON parsing fails, the response includes a
`parse_warning` string explaining what went wrong. This is a diagnostic aid
for debugging prompt issues — callers should not rely on it for control flow.

---

## 🧠 Sleep-Learn Integration

The agent tool integrates with `core.sleep_learn.injector` to automatically
inject learned procedural rules into system prompts for roles with `sleep_learn: True`.

**Enabled roles:** `research`, `analyze`, `code`, `review`, `plan`, `consultor`

**Disabled roles:** `classify`, `route`, `summarize`, `extract`, `critique`

**Behavior:**
- Rules are injected after system prompt lookup, before context trimming
- If `inject_rules_into_prompt` fails (ChromaDB down, collection empty, import missing),
  the original system prompt is used — agent call succeeds without sleep-learn rules
- Rules are logged to `injections.jsonl` for the feedback loop

**Requirements:**
- `core.sleep_learn.injector` module must exist and export `inject_rules_into_prompt`
- ChromaDB must have the `procedural_meta` collection populated by the sleep-learn daemon

---

## 💾 Response Caching

Deterministic roles (`classify`, `route`) are cached to eliminate redundant LLM calls:

| Feature | Behavior |
|---------|----------|
| **Cache key** | SHA256 hash of `role:task:context:content` |
| **TTL** | 5 minutes |
| **Max entries** | 100 (LRU eviction) |
| **Cache hit marker** | Response includes `"cached": true` |
| **Non-cacheable roles** | All others (outputs depend on dynamic content) |

```python
# First call → hits LLM
result1 = agent(action="dispatch", role="classify", task="Is this a bug?")
# Second call (within 5 min) → returns from cache
result2 = agent(action="dispatch", role="classify", task="Is this a bug?")
assert result2["cached"] is True
```

---

## 📈 Per-Role Metrics

Lightweight in-memory metrics are collected for every agent call:

| Metric | Description |
|--------|-------------|
| `calls` | Total invocations |
| `successes` | Successful completions |
| `failures` | Failed completions (LLM error, timeout, etc.) |
| `total_elapsed` | Cumulative wall-clock time |
| `total_tokens` | Cumulative token consumption (reads `usage["total"]`) |
| `parse_failures` | JSON parse failures (prompt-only JSON roles) |
| `last_call` | Unix timestamp of most recent call |

**Query metrics:**

```python
# Metrics for a specific role
result = agent(action="metrics", task="classify")
# Returns: {"status": "success", "metrics": {"calls": 42, "successes": 40, ...}}

# Metrics for all roles
result = agent(action="metrics", task="")
# Returns: {"status": "success", "metrics": {"classify": {...}, "route": {...}}}
```

**Parse warning log:**

```python
result = agent(action="metrics", task="")
# Also returns: {"parse_warnings": [{"timestamp": ..., "role": "plan", "warning": "...", "text_preview": "..."}]}
```

---

## ⚠️ Structured Error Taxonomy

All error responses include an `error_code` field for programmatic handling:

| `error_code` | When | Retryable? |
|--------------|------|------------|
| `INVALID_ROLE` | Unknown role string | No (fix caller) |
| `INVALID_INPUT` | Missing required `task` | No (fix caller) |
| `TIMEOUT` | LLM call exceeded timeout | Yes (with backoff) |
| `CIRCUIT_OPEN` | Circuit breaker open | Yes (after cooldown) |
| `RATE_LIMIT` | API quota exceeded | Yes (after delay) |
| `MODEL_ERROR` | Generic LLM failure | Maybe (check error text) |

```python
result = agent(action="dispatch", role="code", task="Fix bug")
if result["status"] == "error":
    if result["error_code"] == "TIMEOUT":
        # Retry with exponential backoff
        pass
    elif result["error_code"] == "INVALID_ROLE":
        # Log and alert — this is a bug in the caller
        pass
```

---

## ⚙️ Configuration

No dedicated `.env` variables. Uses:
- `cfg.max_context_tokens` — fallback for `_max_context_chars()` (default: 8000 tokens → 32,000 chars)
- Per-role model config in `core/config.py` — `ROUTER_MODEL`, `EXECUTOR_MODEL`, `PLANNER_MODEL`, etc.
- Per-role budgets in `ROLE_CONFIG` — override global default per role

### ROLE_CONFIG Fields

```python
ROLE_CONFIG = {
    "llm_role": "router",          # Maps to env var / model config
    "json_mode": "prompt",         # "api", "prompt", or None
    "budget_chars": 16000,         # Character budget (fallback when no tiktoken)
    "budget_tokens": 4000,         # Token budget (preferred, takes precedence)
    "cacheable": True,             # Whether responses are cached
    "fallback_role": "route",      # Role to retry on transient failure
    "sleep_learn": False,          # Whether sleep-learn rules are injected
}
```

---

## 🔒 Security & Safety

| Feature | Implementation |
|---------|---------------|
| **Input validation** | Unknown actions rejected immediately; unknown roles rejected; empty tasks rejected; `vision` role rejected from dispatch |
| **Case normalization** | `role.strip().lower()` prevents case-sensitive mismatches |
| **Context bounds** | `_trim_context()` prevents unbounded conversation history from reaching the LLM |
| **Vision isolation** | Vision delegates to `tools/vision.py` — never mixed with text LLM paths |
| **No arbitrary code execution** | All roles are prompt-based; no `eval()` or `exec()` |
| **Sleep-learn fallback** | Rule injection failures are non-fatal; original prompt always available |
| **Cache isolation** | Cache keyed on full input; no cross-role or cross-task leakage |
| **Metrics privacy** | In-memory only; no persistence to disk or external services |

---

## 🧪 Testing

```powershell
# Run all agent tests (fully mocked, no LLM calls)
D:\mcp\agent\venv\Scripts\pytest.exe tests/tools/agent -v -W error
```

**Test architecture:**
- `conftest.py` provides `mock_cfg` (autouse, FakeCfg with `max_context_tokens=8000`) and `mock_llm_result` fixtures
- `mock_cfg` prevents AsyncMock leakage from other tests per test isolation rule
- Tests are **fully isolated** — no real LLM calls, no network, no shared state
- Module-level state (cache, metrics, parse warnings) is cleared between tests via `clear_agent_state` autouse fixture

**Test file layout (mirrors source concerns):**

```
tests/tools/agent/
├── conftest.py                  # Shared fixtures (mock_cfg, mock_llm_result)
├── test_agent_validation.py     # Unknown action, unknown role, missing task
├── test_agent_vision.py         # Vision delegation to tools.vision
├── test_agent_vision_params.py  # mime_type and vision_json_mode passthrough
├── test_agent_llm_dispatch.py   # Successful LLM call, LLM failure, param passthrough
├── test_agent_json_parsing.py   # Valid JSON, invalid JSON, markdown fences, extraction
├── test_agent_context.py        # _trim_context unit tests + traceback preservation
├── test_agent_sleep_learn.py    # Sleep-learn injection: call site, gating, fallback
├── test_agent_roles.py          # ROLE_CONFIG validation and budget override tests
├── test_agent_caching.py        # Response caching hit/miss/TTL tests
├── test_agent_errors.py         # Structured error taxonomy tests
├── test_agent_token_aware.py    # Token-aware trimming and _estimate_tokens tests
├── test_agent_metrics.py        # Per-role metrics collection and query tests
├── test_agent_parse_warnings.py # Parse warning logging and retrieval tests
├── test_agent_escalation.py     # Autonomous model escalation on parse failure
└── test_agent_fallback.py       # Role fallback chain retry tests
```

**Mock strategy:**
- `llm.complete` is patched at `tools.agent_core.actions.dispatch.llm.complete` (where it is used)
- `tools.vision.vision` is patched at `tools.vision.vision` (where it is imported inline)
- `cfg` is patched at `tools.agent_core.context.cfg` (module-level import)
- `mock_llm_result` is a pre-built class with all required attributes matching `LLMResponse.usage` shape: `{'prompt': int, 'completion': int, 'total': int}`
- Cache, metrics, and parse warning logs are cleared via `clear_agent_state` autouse fixture

---

## 🔀 When to Use vs. Alternatives

| Need | Tool | Why |
|------|------|-----|
| Fast classification | `agent(dispatch, classify)` | Router, single word output, cached |
| Task routing | `agent(dispatch, route)` | Router, structured JSON, cached |
| Web research synthesis | `agent(dispatch, research)` | Executor, cites sources |
| Summarize long content | `agent(dispatch, summarize)` | Executor, dense output |
| Extract structured data | `agent(dispatch, extract)` | Executor, API json_mode |
| Evaluate quality | `agent(dispatch, critique)` | Executor, APPROVE/REVISE/REJECT |
| Analyze code | `agent(dispatch, analyze)` | Executor, no fixes — analysis only |
| Generate code patch | `agent(dispatch, code)` | Executor, returns `{analysis, patch, tests}` |
| Review code patch | `agent(dispatch, review)` | Executor, returns `{verdict, issues, corrected_patch}` |
| Decompose goal | `agent(dispatch, plan)` | Planner, returns ordered steps JSON |
| Architecture advice | `agent(dispatch, consultor)` | Consultor, best practices |
| Image analysis | `agent(vision_delegate, ...)` | Delegates to `tools/vision.py` |
| Debug metrics | `agent(metrics, ...)` | Returns per-role metrics and parse warnings |
| Clear cache | `agent(clear_cache)` | Clears response cache for deterministic roles |

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

**Fix:** Keep `except Exception:` for sleep-learn. It's a non-fatal enhancement — any failure should fall back to the original prompt. The `ImportError` for the module import is already handled separately.

### 9. Never use single-quoted strings for multi-line prompts with braces

**What happened:** When generating role files programmatically, single-quoted strings with unescaped newlines and JSON braces caused `SyntaxError: unterminated string literal`.

**Fix:** Always use triple-quoted strings (`"""..."""`) for multi-line prompts. Never mix single quotes with embedded JSON.

### 10. Never forget the `tb_tokens` variable in traceback branches

**What happened:** In `_trim_context`, `tb_tokens` was only set in the `tokens` branch but referenced unconditionally in the fit check. When `budget_type == "chars"`, `tb_tokens` was undefined, causing `UnboundLocalError`.

**Fix:** Set `tb_tokens = None` in the `chars` branch. The fit check uses `(tb_tokens is not None and tb_tokens <= budget) or (tb_tokens is None and tb_len <= budget)`.

### 11. Never write role files with JSON-style booleans

**What happened:** Generated role files with `"cacheable": false` (JSON) instead of `"cacheable": False` (Python). Python raised `NameError: name 'false' is not defined`.

**Fix:** Always use Python booleans (`True`/`False`) in generated Python code. Use `str(value)` not `json.dumps(value)` for booleans.

### 12. Never skip `_trim_context` unit tests for `max_tokens` path

**What happened:** No direct test for `_trim_context(text, max_tokens=N)`. The bug (multiplier too loose) only surfaced in an integration test.

**Fix:** Add dedicated unit tests for `_trim_context` with `max_tokens` parameter, testing both with and without tiktoken.

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying the agent tool:

1. **Never add business logic to `agent.py`** — the facade should only validate, dispatch, and return. Move logic to `actions/` or `roles/`.
2. **Never strip or rewrite entire files** — only add comments, docstrings, or formatting. Preserve all existing code exactly.
3. **Add roles in one place** — new roles require: (a) file in `roles/`, (b) `SYSTEM_PROMPT` and `ROLE_CONFIG` exports, (c) `sleep_learn` flag set appropriately.
4. **Add actions in one place** — new actions require: (a) file in `actions/`, (b) `@register_action("agent", "action_name")` decorator, (c) handler function.
5. **Module-level cfg import** — `context.py` imports `cfg` at module level. If conftest patches it, the patch must target `tools.agent_core.context.cfg`.
6. **Vision stays special** — never route `vision` through `llm.complete()`. Always use `action="vision_delegate"`.
7. **Preserve traceback logic** — `_trim_context()` traceback detection must not be broken. Tracebacks are high-signal debugging content.
8. **Test with mock_llm_result** — new tests must use the `mock_llm_result` fixture from `conftest.py`.
9. **JSON parsing fallback** — prompt-only JSON roles must handle markdown fences, surrounding text, arrays at root, and parse failures gracefully.
10. **No backup files** — never create `.bak` files when applying fixes.
11. **Commit workflow** — use `git commit -m` for new work. Only `git commit --amend --no-edit` for fixing the LAST commit.
12. **Sleep-learn gating** — set `sleep_learn: True` in `ROLE_CONFIG` for high-latency roles. Router roles must not pay ChromaDB overhead.
13. **Cache invalidation** — if changing `classify`/`route` system prompts, the cache key does NOT include prompt version. Clear cache or bump version manually.
14. **Metrics are in-memory** — `_ROLE_METRICS` and `_PARSE_WARNING_LOG` are not persisted. Do not rely on them across process restarts.
15. **Fallback chains are one-shot** — if primary fails and fallback also fails, return error. Do not chain more than one fallback.
16. **Escalation is one-shot** — if planner model also fails to produce valid JSON, return `parse_warning`. Do not loop.
17. **Dynamic config drives behavior** — `_json_roles` and `_sleep_learn_roles` are derived from `ROLE_CONFIG` at runtime. No hardcoded sets in `dispatch.py`.
18. **Budget precedence** — `budget_tokens` takes precedence over `budget_chars`. If both set, the tighter constraint wins.
19. **No `**kwargs` in handlers** — explicit parameter lists only. Misspelled params must raise `TypeError`, not be silently swallowed.
20. **Use `is None` for config defaults** — `or` overrides `0` and `False`. Use `value = cfg.get(key); if value is None: value = default`.
21. **Triple-quote multi-line prompts** — never use single quotes for prompts containing newlines or JSON braces.
22. **Python booleans only** — `True`/`False`, never `true`/`false` in generated Python code.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/agent.py` | `@tool` + `@meta_tool` facade: validation, dispatch, compress_result |
| `tools/agent_core/__init__.py` | Auto-discovers `actions/*.py` and `roles/*.py` at import time |
| `tools/agent_core/_registry.py` | `DISPATCH` dict + `@register_action` decorator with duplicate guard |
| `tools/agent_core/context.py` | `_trim_context()`, `_estimate_tokens()`, `_max_context_tokens()`, `_max_context_chars()` |
| `tools/agent_core/cache.py` | `_cache_key()`, `_get_cached()`, `_set_cached()`, `_clear_cache()` |
| `tools/agent_core/metrics.py` | `_record_metric()`, `_get_metrics()`, `_clear_metrics()` |
| `tools/agent_core/parse_warnings.py` | `_log_parse_warning()`, `_get_parse_warnings()`, `_clear_parse_warnings()` |
| `tools/agent_core/json_extract.py` | `_extract_first_json()` — brace-counting extraction with dict-preference scoring |
| `tools/agent_core/actions/dispatch.py` | `@register_action("agent", "dispatch")` — core LLM orchestrator |
| `tools/agent_core/actions/metrics.py` | `@register_action("agent", "metrics")` — query per-role metrics |
| `tools/agent_core/actions/vision_delegate.py` | `@register_action("agent", "vision_delegate")` — delegate to tools.vision |
| `tools/agent_core/actions/clear_cache.py` | `@register_action("agent", "clear_cache")` — clear response cache |
| `tools/agent_core/roles/*.py` | 12 files: `SYSTEM_PROMPT` + `ROLE_CONFIG` per role |
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

## 🔮 Future Roadmap

### ✅ Completed Phases

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Core roles: classify, route, research, summarize, extract, critique, analyze, code, review, plan, consultor, vision |
| **Phase 2** | ✅ Complete | Agent split: monolithic `tools/agent.py` (~420 lines) → `@meta_tool` facade + `actions/` + `roles/` directories |
| **Phase 3** | ✅ Complete | Bug fixes: broken imports, JSON regex → brace-counting parser, test coverage gaps |
| **Phase 4** | ✅ Complete | Features: sleep-learn injection wired for high-latency roles, `parse_warning` docs, vision limitations documented |
| **Phase 5** | ✅ Complete | Infrastructure: ROLE_CONFIG unified dict, per-role context budgets, response caching, structured errors, vision passthrough params |
| **Phase 6** | ✅ Complete | Advanced: token-aware trimming, prompt versioning, per-role metrics, parse warning logging, autonomous model escalation, role fallback chains |
| **Phase 7** | ✅ Complete | `@meta_tool` refactor: thin facade (`tools/agent.py`), `actions/` directory (4 actions), `roles/` directory (12 roles), auto-discovery, dynamic `_json_roles`/`_sleep_learn_roles`, `sleep_learn` per-role config, vision guard, `budget_chars` `or` trap fix, `char_budget` multiplier fix (5→3), `_get_metrics` returns `.copy()`, `max_context_tokens` in `FakeCfg`, test robustness, 95/95 tests passing |
| **Phase 8** | ✅ Complete | | New roles: `refactor`, `test`, `document` | Required `core/config.py` and `.env` and `core/llm_backend/config.py` updates for new model entries |


### 🔵 Later (Blocked or Large)

| Priority | Item | Effort | Why | Blocked On |
|----------|------|--------|-----|------------|
| 🔵 1 | Self-improving prompts via sleep-learn feedback loop | Large | Auto-tune system prompts based on success/failure metrics from per-role metrics | Per-role metrics (now available) |
| 🔵 2 | `dry_run` / `estimate_cost` mode | Medium | Pre-flight cost estimation without calling LLM | Structured errors (available) |
| 🔵 3 | Streaming support | Large | Partial responses for long-running roles; requires `core/llm.py` redesign | MCP stdio protocol changes |
| 🔵 4 | Role composition chaining | Large | Chain multiple roles in single call: `analyze` → `code` → `review` | Streaming decision |
| 🔵 5 | Parallel tool execution | Medium | Expose `core/parallel_executor.py` as a `parallel` tool for research workflows | Concrete use case demanding it |

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.1 | 2024-01-15 | Initial monolithic agent tool (~420 lines) |
| v0.2 | 2024-02-01 | Added response cache and metrics |
| v0.3 | 2024-02-15 | Added sleep-learn injection |
| v0.4 | 2024-03-01 | Added vision_delegate action |
| v0.5 | 2024-03-15 | Added token-aware context trimming |
| v1.0 | 2024-04-01 | `@meta_tool` refactor — actions/ + roles/ directories, auto-discovery |
| v1.1 | 2024-04-15 | Hardening pass: `**kwargs` removal, vision guard, dynamic sleep-learn config, `budget_chars` `or` trap fix, traceback scoping, char multiplier tightening, metrics `.copy()`, test budget fix, `sleep_learn` per-role flags |
| v1.2 | 2024-05-01 | Added 3 autonomous maintenance roles: `refactor`, `test`, `document`. Timeout single source of truth. Escalation response completeness. Cache key includes temperature/max_tokens. Consultor guard. Scaled context trimming for large budgets. |

---

*Last updated: Phase 7 complete — `@meta_tool` refactor with actions/roles directories, auto-discovery, dynamic config-driven behavior, 95/95 tests passing, 1212 passed full suite. Architecture: thin facade + agent_core submodules (actions, roles, context, cache, metrics, parse_warnings, json_extract) + @meta_tool pattern consistent with git/file/report/cli.*

