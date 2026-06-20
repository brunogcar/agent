# 🤖 Agent Tool

The `agent()` tool is the **meta-cognitive dispatcher** of the MCP Agent Stack. It routes tasks to specialist sub-agents (Router, Executor, Planner, Consultor, Vision) based on a `role` parameter, each with its own system prompt, model, timeout, and output format.

**Key characteristics:**
- **Single entry point** — The LLM sees one tool: `agent(role, task, ...)`
- **Role-specialized prompts** — 12 distinct personas, each with tailored instructions
- **Per-role model routing** — Router uses fast 2B models, Executor uses capable 9B models
- **Per-role context budgets** — Router gets 4K tokens, Planner gets 32K tokens
- **Token-aware context trimming** — Uses tiktoken when available, falls back to chars/4
- **Response caching** — Deterministic roles (`classify`, `route`) cached with 5-min TTL
- **Structured output enforcement** — JSON mode for `extract`, prompt-only JSON for `route`, `plan`, `code`, `review`
- **Structured errors** — `error_code` field enables programmatic retry decisions
- **Autonomous model escalation** — On JSON parse failure, auto-retries with planner model
- **Role fallback chains** — `classify`→`route`, `critique`→`analyze`, `consultor`→`plan` on transient failure
- **Per-role metrics** — In-memory tracking of calls, success rate, latency, tokens, parse failures
- **Prompt versioning** — Hash of all system prompts in every response for reproducibility
- **Parse warning logging** — Rolling log of JSON parse failures for data-driven prompt tuning
- **Context trimming** — Head+tail truncation with traceback preservation before reaching the LLM
- **Vision delegation** — `vision` role delegates to `tools/vision.py` for multimodal analysis
- **Vision passthrough** — Optional `mime_type` and `vision_json_mode` for full vision control
- **Sleep-learn integration** — Learned rules auto-injected for high-latency roles
- **NOT_PARALLEL_SAFE** — Serialized via global LLM client queue; no concurrent agent calls

---

## 🏗️ Architecture

The agent tool follows a **thin facade + core submodule** pattern. `tools/agent.py` is the only file scanned by `registry.py` for `@tool` discovery; all logic lives in `tools/agent_core/`.

```
tools/agent.py              # @tool facade — validation, dispatch, caching, metrics, JSON parsing
tools/agent_core/
├── __init__.py             # Package marker
├── prompts.py              # _SYSTEM_PROMPTS — 12 role-specific system prompts
├── roles.py                # ROLE_CONFIG — unified role metadata (model, json, budget, cacheable, fallback)
└── context.py              # _trim_context(), _estimate_tokens(), _max_context_tokens() — head+tail truncation
```

### Dispatch Flow

```mermaid
graph TD
    A["agent(role, task, context, content, mime_type, vision_json_mode)"] --> B{role == "metrics"?}
    B -->|Yes| C["Return metrics + parse_warnings + prompt_version"]
    B -->|No| D{role == "vision"?}
    D -->|Yes| E["Delegate to tools.vision.vision()"]
    D -->|No| F{role in ROLE_CONFIG?}
    F -->|No| G["Return: INVALID_ROLE error"]
    F -->|Yes| H["Lookup ROLE_CONFIG[role]"]
    H --> I{"cacheable and cache hit?"}
    I -->|Yes| J["Return cached response"]
    I -->|No| K["Lookup system prompt"]
    K --> L["Inject sleep-learn rules (high-latency roles only)"]
    L --> M["_trim_context(context, budget) + _trim_context(content)"]
    M --> N["llm.complete(role, system, user, context, content, json_mode)"]
    N --> O{result.ok?}
    O -->|No| P{"fallback_role configured?"}
    P -->|Yes| Q["Retry with fallback_role's LLM + prompt"]
    P -->|No| R["Return: error dict with error_code"]
    Q --> S{result.ok?}
    S -->|No| R
    S -->|Yes| T["Continue to JSON parsing"]
    O -->|Yes| T
    T --> U{role in _JSON_ROLES?}
    U -->|Yes| V["Parse JSON: API parsed or brace-counting extraction"]
    U -->|No| W["Return: text response"]
    V --> X{parse failed?}
    X -->|Yes| Y["Escalate to planner model for JSON retry"]
    X -->|No| Z["Return: response with parsed dict"]
    Y --> AA{escalation succeeded?}
    AA -->|Yes| Z
    AA -->|No| AB["Log parse_warning, return with empty parsed"]
    Z --> AC["Record metrics"]
    AC --> AD{"cacheable?"}
    AD -->|Yes| AE["Store in cache"]
    AD -->|No| AF["Skip cache"]
    AE --> AG["Return response"]
    AF --> AG
```

**Key design decisions:**
- **Unified ROLE_CONFIG** — Single dict holds `llm_role`, `json_mode`, `budget_chars`, `cacheable`, `fallback_role`. Adding a role means one entry here + one prompt in `prompts.py`.
- **Per-role context budgets** — `classify`/`route`: 16K chars (4K tokens). `plan`/`research`/`code`: 128K chars (32K tokens). Others: 48K chars (12K tokens).
- **Token-aware trimming** — `_estimate_tokens()` uses tiktoken (cached encoder) when available, falls back to chars/4. `_trim_context()` accepts `max_tokens` for accurate budget enforcement.
- **Response caching** — `classify` and `route` are deterministic: same input → same output. Cached by SHA256 hash, 5-minute TTL, 100-entry LRU.
- **Structured errors** — `error_code` field (`INVALID_ROLE`, `INVALID_INPUT`, `TIMEOUT`, `CIRCUIT_OPEN`, `RATE_LIMIT`, `MODEL_ERROR`, `PARSE_ERROR`, `MISSING_DEPENDENCY`) lets callers retry intelligently.
- **Role fallback chains** — On transient LLM failure, automatically retry with a functionally similar role (e.g., `classify`→`route` returns structured category info).
- **Autonomous model escalation** — If a prompt-only JSON role produces invalid JSON, the facade automatically retries with the planner model (heavier, more compliant) before giving up.
- **Per-role metrics** — Lightweight in-memory tracking: calls, successes, failures, total elapsed, total tokens, parse failures. Query via `agent(role="metrics", task="role_name")`.
- **Prompt versioning** — SHA256 hash of all system prompts included in every success response. Makes debugging "why did behavior change?" trivial.
- **Parse warning logging** — Rolling log (max 50 entries) of JSON parse failures per role. Enables data-driven prompt tuning: if a role's parse failure rate spikes, tighten its system prompt.
- **Vision passthrough** — `mime_type` and `vision_json_mode` params forwarded to `tools.vision.vision()` when set.
- **Sleep-learn gated** — Rule injection only runs for roles with 60s+ budgets. Router roles skip it to avoid ChromaDB overhead.

---

## 📋 Tool Signature

```python
@tool
def agent(
    role: str,              # Required. See Roles table below.
    task: str,              # Required. The instruction or question.
    context: str = "",     # Background information injected before the task
    content: str = "",     # Raw material: code, text, data, or base64 image string
    trace_id: str = "",    # Trace identifier for observability and logging
    temperature: float = -1.0,  # Temperature override (-1 = model default)
    max_tokens: int = -1,   # Max tokens override (-1 = model default)
    # Vision passthrough (optional):
    mime_type: str = "",           # Override MIME type for image (e.g. "image/webp")
    vision_json_mode: bool = False, # Request JSON output from vision
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | `str` | — | **Required.** See Roles table below |
| `task` | `str` | — | **Required.** The instruction or question for this agent |
| `context` | `str` | `""` | Background information injected before the task |
| `content` | `str` | `""` | Raw material: code, text, data, or base64 image string |
| `trace_id` | `str` | `""` | Trace identifier for observability and logging |
| `temperature` | `float` | `-1.0` | Temperature override (-1 = model default) |
| `max_tokens` | `int` | `-1` | Max tokens override (-1 = model default) |
| `mime_type` | `str` | `""` | **(Vision only)** Override MIME type for image |
| `vision_json_mode` | `bool` | `False` | **(Vision only)** Request JSON output from vision |

**Meta-role:** `role="metrics"`, `task="role_name"` (or empty for all) returns collected metrics and parse warnings.

**For vision role:** `context` = file_path or public URL, `content` = base64-encoded image.

---

## 🎭 Roles

| Role | LLM Role | Timeout | Budget | Cacheable | Fallback | Output | Description |
|------|----------|---------|--------|-----------|----------|--------|-------------|
| `classify` | `router` | 15s | 4K tokens | ✅ | `route` | Single word | Fast binary/category decision |
| `route` | `router` | 15s | 4K tokens | ✅ | — | JSON | Workflow + tool routing decision |
| `research` | `research` | 120s | 32K tokens | ❌ | — | Markdown | Synthesize web/memory content |
| `summarize` | `summarize` | 60s | 12K tokens | ❌ | — | Markdown | Dense, accurate summary |
| `extract` | `extract` | 60s | 12K tokens | ❌ | — | JSON | Structured data extraction (API json_mode) |
| `critique` | `critique` | 90s | 12K tokens | ❌ | `analyze` | Markdown | Quality evaluation: APPROVE / REVISE / REJECT |
| `analyze` | `analyze` | 90s | 12K tokens | ❌ | — | Markdown | Deep code/data analysis, no fixes |
| `code` | `code` | 120s | 32K tokens | ❌ | — | JSON | Generate Python patch: `{analysis, patch, tests}` |
| `review` | `review` | 90s | 12K tokens | ❌ | — | JSON | Review patch: `{verdict, issues, corrected_patch}` |
| `plan` | `planner` | 90s | 32K tokens | ❌ | — | JSON | Decompose goal into ordered steps |
| `consultor` | `consultor` | 60s | 12K tokens | ❌ | `plan` | Markdown | Expert advisory on architecture/best practices |
| `vision` | *(delegated)* | 60s | — | ❌ | — | Markdown | Image analysis via `tools/vision.py` |
| `metrics` | *(internal)* | — | — | ❌ | — | JSON | Query per-role metrics and parse warnings |

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
| **Per-role budget** | `classify`/`route`: 16K chars (4K tokens). `plan`/`research`/`code`: 128K chars (32K tokens). Others: 48K chars (12K tokens) |
| **Token-aware** | `_estimate_tokens()` uses tiktoken (cached encoder) when available, falls back to chars/4 |
| **Dynamic budget** | `cfg.max_context_tokens` fallback (config-reloadable, clamped to minimum 4000 chars) |
| **Traceback preservation** | If a Python traceback is detected, it is preserved in full within the tail. Uses line-by-line frame detection (not `\n\n` heuristics) for robustness. |
| **Custom max_chars** | `_trim_context(text, max_chars=500)` for one-off overrides |
| **Custom max_tokens** | `_trim_context(text, max_tokens=100)` for token-accurate trimming |
| **Content budget** | `content` is capped at ~1000 tokens, but also constrained by remaining role-specific budget |

### Content Budget

The `content` parameter (raw material to process) has a dedicated budget to prevent massive code dumps from consuming the entire context budget. However, it is also dynamically constrained: if `context` already consumed most of the role-specific budget, `content` gets whatever remains.

```python
# Example: plan role budget = 128K chars
# context = 120K chars (trimmed to ~118K after head+tail)
# content = 5K chars → trimmed to 4K (hard cap) → then to 0 (budget exhausted)
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
inject learned procedural rules into system prompts for high-latency roles.

**Gated roles:** `research`, `analyze`, `code`, `review`, `plan`, `consultor`

**Router roles excluded:** `classify`, `route` — ChromaDB round-trip would
consume a significant portion of their 15s budget.

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
result1 = agent(role="classify", task="Is this a bug?")
# Second call (within 5 min) → returns from cache
result2 = agent(role="classify", task="Is this a bug?")
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
result = agent(role="metrics", task="classify")
# Returns: {"status": "success", "metrics": {"calls": 42, "successes": 40, ...}}

# Metrics for all roles
result = agent(role="metrics", task="")
# Returns: {"status": "success", "metrics": {"classify": {...}, "route": {...}}}
```

**Parse warning log:**

```python
result = agent(role="metrics", task="")
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
| `PARSE_ERROR` | JSON extraction failed | No (check prompt) |
| `MISSING_DEPENDENCY` | `tools/vision.py` not found | No (install dependency) |

```python
result = agent(role="code", task="Fix bug")
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

---

## 🔒 Security & Safety

| Feature | Implementation |
|---------|---------------|
| **Input validation** | Unknown roles rejected immediately; empty tasks rejected |
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
- `conftest.py` provides `mock_cfg` (autouse, MagicMock) and `mock_llm_result` fixtures
- `mock_cfg` prevents AsyncMock leakage from other tests per test isolation rule
- Tests are **fully isolated** — no real LLM calls, no network, no shared state

**Test file layout (mirrors source concerns):**

```
tests/tools/agent/
├── conftest.py                    # Shared fixtures (mock_cfg, mock_llm_result)
├── test_agent_validation.py       # Unknown role, missing task, role→prompt coverage
├── test_agent_vision.py           # Vision delegation to tools.vision
├── test_agent_vision_params.py    # mime_type and vision_json_mode passthrough
├── test_agent_llm_dispatch.py     # Successful LLM call, LLM failure, param passthrough
├── test_agent_json_parsing.py     # Valid JSON, invalid JSON, markdown fences, extraction
├── test_agent_context.py          # _trim_context unit tests + traceback preservation
├── test_agent_sleep_learn.py      # Sleep-learn injection: call site, gating, fallback
├── test_agent_roles.py            # ROLE_CONFIG validation and budget override tests
├── test_agent_caching.py          # Response caching hit/miss/TTL tests
├── test_agent_errors.py           # Structured error taxonomy tests
├── test_agent_token_aware.py      # Token-aware trimming and _estimate_tokens tests
├── test_agent_prompt_version.py   # Prompt versioning in responses
├── test_agent_metrics.py          # Per-role metrics collection and query tests
├── test_agent_parse_warnings.py   # Parse warning logging and retrieval tests
├── test_agent_escalation.py       # Autonomous model escalation on parse failure
└── test_agent_fallback.py         # Role fallback chain retry tests
```

**Mock strategy:**
- `llm.complete` is patched at `tools.agent.llm.complete` (where it is used)
- `tools.vision.vision` is patched at `tools.vision.vision` (where it is imported inline)
- `cfg` is patched at `tools.agent_core.context.cfg` (module-level import)
- `mock_llm_result` is a pre-built `MagicMock` with all required attributes matching `LLMResponse.usage` shape: `{"prompt": int, "completion": int, "total": int}`
- Cache, metrics, and parse warning logs are cleared via `setup_method` in each test class

---

## 🔀 When to Use vs. Alternatives

| Need | Tool | Why |
|------|------|-----|
| Fast classification | `agent(classify)` | 15s Router, single word output, cached |
| Task routing | `agent(route)` | 15s Router, structured JSON, cached |
| Web research synthesis | `agent(research)` | 120s Executor, cites sources |
| Summarize long content | `agent(summarize)` | 60s Executor, dense output |
| Extract structured data | `agent(extract)` | 60s Executor, API json_mode |
| Evaluate quality | `agent(critique)` | 90s Executor, APPROVE/REVISE/REJECT |
| Analyze code | `agent(analyze)` | 90s Executor, no fixes — analysis only |
| Generate code patch | `agent(code)` | 120s Executor, returns `{analysis, patch, tests}` |
| Review code patch | `agent(review)` | 90s Executor, returns `{verdict, issues, corrected_patch}` |
| Decompose goal | `agent(plan)` | 90s Planner, returns ordered steps JSON |
| Architecture advice | `agent(consultor)` | 60s Consultor, best practices |
| Image analysis | `agent(vision)` | Delegates to `tools/vision.py` |
| Debug metrics | `agent(metrics)` | Returns per-role metrics and parse warnings |

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying the agent tool:

1. **Never add business logic to `agent.py`** — the facade should only validate, dispatch, cache, and parse. Move prompts to `prompts.py`, role config to `roles.py`, trimming to `context.py`.
2. **Never strip or rewrite entire files** — only add comments, docstrings, or formatting. Preserve all existing code exactly.
3. **Add roles in two places** — new roles require: (a) entry in `ROLE_CONFIG` in `roles.py`, (b) prompt in `prompts.py`.
4. **Module-level cfg import** — `context.py` imports `cfg` at module level. If conftest patches it, the patch must target `tools.agent_core.context.cfg`.
5. **Vision stays special** — never route `vision` through `llm.complete()`. Always delegate to `tools/vision.py`.
6. **Preserve traceback logic** — `_trim_context()` traceback detection must not be broken. Tracebacks are high-signal debugging content.
7. **Test with mock_llm_result** — new tests must use the `mock_llm_result` fixture from `conftest.py`.
8. **JSON parsing fallback** — prompt-only JSON roles must handle markdown fences, surrounding text, arrays at root, and parse failures gracefully.
9. **No backup files** — never create `.bak` files when applying fixes.
10. **Commit workflow** — use `git commit -m` for new work. Only `git commit --amend --no-edit` for fixing the LAST commit.
11. **Sleep-learn gating** — if adding `inject_rules_into_prompt` calls, gate to high-latency roles only. Router roles must not pay ChromaDB overhead.
12. **Cache invalidation** — if changing `classify`/`route` system prompts, the cache key does NOT include prompt version. Clear cache or bump version manually.
13. **Metrics are in-memory** — `_ROLE_METRICS` and `_PARSE_WARNING_LOG` are not persisted. Do not rely on them across process restarts.
14. **Fallback chains are one-shot** — if primary fails and fallback also fails, return error. Do not chain more than one fallback.
15. **Escalation is one-shot** — if planner model also fails to produce valid JSON, return `parse_warning`. Do not loop.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/agent.py` | `@tool` facade: validation, dispatch, caching, metrics, JSON parsing, vision delegation, sleep-learn injection, error taxonomy, fallback chains, model escalation |
| `tools/agent_core/prompts.py` | `_SYSTEM_PROMPTS` — 12 role-specific system prompts |
| `tools/agent_core/roles.py` | `ROLE_CONFIG` — unified role metadata: model, json_mode, budget, cacheable, fallback_role |
| `tools/agent_core/context.py` | `_trim_context()`, `_estimate_tokens()`, `_max_context_tokens()`, `_max_context_chars()` |
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
| `tests/tools/agent/test_agent_prompt_version.py` | Prompt versioning tests |
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
| **Phase 2** | ✅ Complete | Agent split: `tools/agent_tool.py` → `tools/agent.py` + `tools/agent_core/` (prompts, roles, context) |
| **Phase 3** | ✅ Complete | Bug fixes: broken imports, JSON regex → brace-counting parser, test coverage gaps |
| **Phase 4** | ✅ Complete | Features: sleep-learn injection wired for high-latency roles, `parse_warning` docs, vision limitations documented |
| **Phase 5** | ✅ Complete | Infrastructure: ROLE_CONFIG unified dict, per-role context budgets, response caching, structured errors, vision passthrough params |
| **Phase 6** | ✅ Complete | Advanced: token-aware trimming, prompt versioning, per-role metrics, parse warning logging, autonomous model escalation, role fallback chains |

### 🔵 Later (Blocked or Large)

| Priority | Item | Effort | Why | Blocked On |
|----------|------|--------|-----|------------|
| 🔵 1 | Self-improving prompts via sleep-learn feedback loop | Large | Auto-tune system prompts based on success/failure metrics from per-role metrics | Per-role metrics (now available) |
| 🔵 2 | `dry_run` / `estimate_cost` mode | Medium | Pre-flight cost estimation without calling LLM | Structured errors (available) |
| 🔵 3 | Streaming support | Large | Partial responses for long-running roles; requires `core/llm.py` redesign | MCP stdio protocol changes |
| 🔵 4 | Role composition chaining | Large | Chain multiple roles in single call: `analyze` → `code` → `review` | Streaming decision |
| 🔵 5 | New roles: `refactor`, `test`, `document` | Medium each | Autonomous code maintenance workflows. Requires `core/config.py` and `.env` updates for new model entries | Centralized ROLE_CONFIG stable |
| 🔵 6 | Parallel tool execution | Medium | Expose `core/parallel_executor.py` as a `parallel` tool for research workflows | Concrete use case demanding it |

---

*Last updated: Phase 6 complete + hardening. Token-aware trimming with tiktoken caching, prompt versioning, per-role metrics with correct usage key, parse warning logging, autonomous model escalation with hardened parse_warning handling, role fallback chains, and line-by-line traceback detection. 90+ agent tests passing. Architecture: thin facade + agent_core submodules + advanced resilience features.*
