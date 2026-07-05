<- Back to [Agent Overview](../AGENT.md)

# 📝 API Reference

## Tool Signature

```python
@tool
@meta_tool(
 DISPATCH.get("agent", {}),
 doc_sections=[...],
)
def agent(
 action: str = "", # Required. Literal["dispatch", "metrics", "vision_delegate", "clear_cache"]
 role: str = "", # Required for dispatch. See Roles table below.
 task: str = "", # Required for dispatch/metrics/vision_delegate.
 context: str = "", # Background information (dispatch) or image path (vision_delegate)
 content: str = "", # Raw material or base64 image string
 trace_id: str = "", # Trace identifier for observability
 temperature: float = -1.0, # Temperature override (-1 = model default)
 max_tokens: int = -1, # Max tokens override (-1 = model default)
 mime_type: str = "", # (Vision only) Override MIME type
 vision_json_mode: bool = False, # (Vision only) Request JSON output
) -> dict:
    """Agent meta-tool -- atomic actions for cognitive tasks."""
```

### Parameters

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

## ⚡ Actions

### `dispatch` -- Core LLM orchestrator

Routes tasks to specialist sub-agents based on `role` parameter.

**Flow:**
1. Validate role exists in ROLES
2. Reject vision role (use action='vision_delegate')
3. Check cache (if cacheable)
4. Inject sleep-learn rules (if role.sleep_learn)
5. `_trim_context(context, budget_tokens)` + `_trim_context(content)`
6. `llm.complete(role, system, user, context, content, json_mode)`
7. If failed: retry with fallback_role (one attempt)
8. If JSON role: parse JSON (API parsed -> brace-counting -> planner escalation)
9. Record metrics
10. Store in cache (if cacheable)
11. Return response

**Return:** Response dict with `status`, `role`, `text` or `parsed`, and optional `cached`, `parse_warning`, `escalated` fields.

---

### `metrics` -- Query per-role metrics and parse warnings

Returns collected metrics and parse warnings for one or all roles.

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

### `vision_delegate` -- Delegate to vision tool

Delegates multimodal analysis to `tools/vision.py`.

**Parameters:** `context` = file_path or public URL, `content` = base64-encoded image.

---

### `clear_cache` -- Clear response cache

Clears response cache for deterministic roles (`classify`, `route`).

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
| **Content budget** | `content` is allocated 70% of remaining tokens/chars (after `context` is trimmed), leaving 30% headroom. Previously capped at `min(1000, remaining)` which silently truncated large code files. |

### Content Budget

The `content` parameter (raw material to process) has a dedicated budget to prevent massive code dumps from consuming the entire context budget. It is allocated **70% of remaining budget** after `context` is trimmed, leaving 30% headroom for the LLM's output.

```python
# Example: plan role budget = 32K tokens
# context = 30K tokens -> trimmed to ~30K tokens
# remaining = 32K - 30K = 2K tokens
# content = 5K tokens -> trimmed to int(2K * 0.70) = 1400 tokens
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
| **API json_mode** | `extract` | `llm.complete(json_mode=True)` -- model enforces JSON schema |
| **Prompt-only JSON** | `route`, `plan`, `code`, `review` | System prompt demands JSON; post-hoc brace-counting extraction if model adds prose |
| **Non-JSON** | `classify`, `research`, `summarize`, `critique`, `analyze`, `consultor` | Free-form text output |

### JSON Parsing: Three-Stage Fallback

For prompt-only JSON roles, the parser uses a robust three-stage approach:

1. **Fast path** -- Try `json.loads()` on the clean text (after stripping markdown fences).
 Works for well-behaved models that output clean JSON.

2. **Brace-counting extraction** -- If fast path fails, scan for all `{` and `[` positions
 and use depth tracking (respecting string boundaries and escaped quotes) to find
 the complete JSON structure. Handles nested objects, arrays at root, and braces
 inside string values. Prefers dicts over arrays (since agent roles expect dict-root
 JSON), then the largest valid structure to handle prose before JSON.

3. **Autonomous model escalation** -- If extraction fails, the facade automatically
 retries with the planner model (heavier, more JSON-compliant) before giving up.
 Escalation uses the **plan role's** system prompt (not the original role's prompt)
 since the plan role is designed for structured output.
 If escalation succeeds, `escalated: true` and `escalated_from: {"role": "...", "model": "..."}`
 are set in the response, so callers can detect that the primary model failed and
 identify which model originally produced the unparseable output.

 **Note:** Fallback + escalation can produce up to 3 sequential LLM calls
 (primary -> fallback -> planner escalation). This is intentional defense-in-depth,
 but be aware of compounding timeout risk.

4. **Graceful failure** -- If all attempts fail, returns `parsed: {}` with a
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
for debugging prompt issues -- callers should not rely on it for control flow.

---

## 🧠 Sleep-Learn Integration

The agent tool integrates with `core.sleep_learn.injector` to automatically
inject learned procedural rules into system prompts for roles with `sleep_learn: True`.

**Enabled roles:** `research`, `analyze`, `code`, `review`, `plan`, `consultor`

**Disabled roles:** `classify`, `route`, `summarize`, `extract`, `critique`

**Behavior:**
- Rules are injected after system prompt lookup, before context trimming
- If `inject_rules_into_prompt` fails (ChromaDB down, collection empty, import missing),
 the original system prompt is used -- agent call succeeds without sleep-learn rules
- Rules are logged to `injections.jsonl` for the feedback loop

**Requirements:**
- `core.sleep_learn.injector` module must exist and export `inject_rules_into_prompt`
- ChromaDB must have the `procedural_meta` collection populated by the sleep-learn daemon

---

## 💾 Response Caching

Deterministic roles (`classify`, `route`) are cached to eliminate redundant LLM calls:

| Feature | Behavior |
|---------|----------|
| **Cache key** | SHA256 hash of `role:task:context:content` + optional `:mdl={model}` (v1.3: includes model name to prevent stale hits on model swap) |
| **TTL** | 5 minutes (configurable via `AGENT_CACHE_TTL_SECONDS` env var) |
| **Max entries** | 100 (configurable via `AGENT_CACHE_MAX` env var, LRU eviction) |
| **Cache hit marker** | Response includes `"cached": true` |
| **Non-cacheable roles** | All others (outputs depend on dynamic content) |

```python
# First call -> hits LLM
result1 = agent(action="dispatch", role="classify", task="Is this a bug?")
# Second call (within 5 min) -> returns from cache
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

**v1.3 additions:**
- **JSONL persistence** — Metrics are appended to `.agent_metrics.jsonl` in the workspace root on each call, surviving process restarts. Set `AGENT_METRICS_PERSIST=0` in `.env` to disable. The in-memory dict remains the primary store for fast reads; the JSONL is an append-only audit log.
- **Aggregation** — `_get_aggregate_metrics()` returns cross-role totals: `total_calls`, `total_successes`, `total_failures`, `overall_success_rate`, `avg_latency`, `total_tokens`, `total_parse_failures`, `roles_tracked`.
- **Parse warning severity** — `_get_parse_warnings_by_severity()` groups warnings by frequency: `high` (>=5), `medium` (>=2), `low` (<2). Useful for prioritizing which role prompts need tightening.

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
     # Log and alert -- this is a bug in the caller
     pass
```

---

## 🔒 Security & Safety

| Feature | Implementation |
|---------|---------------|
| **Input validation** | Unknown actions rejected immediately; unknown roles rejected; empty tasks rejected; `vision` role rejected from dispatch |
| **Case normalization** | `role.strip().lower()` prevents case-sensitive mismatches |
| **Context bounds** | `_trim_context()` prevents unbounded conversation history from reaching the LLM |
| **Vision isolation** | Vision delegates to `tools/vision.py` -- never mixed with text LLM paths |
| **No arbitrary code execution** | All roles are prompt-based; no `eval()` or `exec()` |
| **Sleep-learn fallback** | Rule injection failures are non-fatal; original prompt always available |
| **Cache isolation** | Cache keyed on full input; no cross-role or cross-task leakage |
| **Metrics privacy** | In-memory only; no persistence to disk or external services |

---

## ⚙️ Configuration

### ROLE_CONFIG Fields

```python
ROLE_CONFIG = {
 "llm_role": "router", # Maps to env var / model config
 "json_mode": "prompt", # "api", "prompt", or None
 "budget_chars": 16000, # Character budget (fallback when no tiktoken)
 "budget_tokens": 4000, # Token budget (preferred, takes precedence)
 "cacheable": True, # Whether responses are cached
 "fallback_role": "route", # Role to retry on transient failure
 "sleep_learn": False, # Whether sleep-learn rules are injected
}
```

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
