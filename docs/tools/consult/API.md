<- Back to [Consult Overview](../CONSULT.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
from registry import tool
from tools._meta_tool import meta_tool
from tools.consult_ops._registry import DISPATCH

@tool
@meta_tool(
    DISPATCH.get("consult", {}),
    doc_sections=[ ... ],   # auto-generated action list + param notes
)
def consult(
    action: str = "",          # Literal["advise", "explain", "review"] (auto-generated)
    question: str = "",
    context: str = "",
    trace_id: str = "",
    format: str = "markdown",
    context_type: str = "",
) -> dict:
    """Advisory consultation meta-tool — advise | review | explain."""
```

> The `action: Literal[...]` annotation and the action list in the docstring are **auto-generated** by `@meta_tool` from `DISPATCH["consult"]` keys at import time. Adding a new action file in `consult_ops/actions/` automatically extends the `Literal` and the docstring — no facade edits required.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | `str` (`Literal["advise","explain","review"]`) | **Yes** | `""` | Which advisory mode to invoke. Empty / unknown values return `status=error`. |
| `question` | `str` | **Yes** (per-action) | `""` | The core question, decision, or focus area. Empty → `status=error`. |
| `context` | `str` | No | `""` | Supporting background (logs, traces, source code, architecture notes). Truncated to ~2000 tokens via `tiktoken` cl100k_base if oversized; `warnings` field populated on truncation. |
| `trace_id` | `str` | No | `""` | Observability trace ID. Forwarded to `llm.complete(trace_id=...)` and included in the response **only when non-empty**. |
| `format` | `str` | No | `"markdown"` | Output shape control: `markdown` (no suffix; base prompt already implies structured Markdown) / `json` (append "Output as JSON with keys: {summary, details, recommendations}") / `bullet_points` (append "Format as bullet points only, no prose"). Unknown values silently degrade to `markdown`. |
| `context_type` | `str` | No | `""` | Context kind hint appended as a suffix to the system prompt: `""` (no modifier) / `code` (focus on code quality/patterns/issues) / `logs` (focus on error patterns/timing/ops) / `architecture` (focus on design patterns/scalability/trade-offs). Unknown values silently degrade to `""`. |

---

## 🎬 Actions

### `consult(action="advise", ...)` — General Advisory

**Purpose:** Architectural advice, deadlock-breakers, trade-off analysis. Preserves the original Pre-v1 consult behavior — same prompt, same response key (`advice`).

**Required:** `question`
**Optional:** `context`, `trace_id`, `format`, `context_type`

**Example:**
```python
# Basic advisory
consult(action="advise", question="What are the trade-offs between async and sync database drivers in Python?")

# With context + format
consult(
    action="advise",
    question="Should we adopt event sourcing for our billing service?",
    context="Current architecture: PostgreSQL + Kafka. 50M events/day. Read-heavy workload...",
    format="bullet_points",
    context_type="architecture",
)

# With trace_id (for workflow observability)
consult(action="advise", question="How to migrate from Celery to RQ?", trace_id="wf-1234")
```

**Success response:**
```json
{
  "status": "success",
  "action": "advise",
  "provider": "openai",
  "model": "gpt-4o",
  "advice": "Event sourcing is a strong fit for billing because...",
  "trace_id": "wf-1234",
  "warnings": ["Context truncated from ~5000 to 2000 tokens..."]
}
```
> `trace_id` is omitted when the caller didn't pass one. `warnings` is omitted when no truncation occurred.

---

### `consult(action="review", ...)` — Structured Code Review

**Purpose:** Critique code with severity-tagged findings across 5 dimensions: correctness, security, performance, maintainability, best practices. The system prompt instructs the model to use `CRITICAL`/`WARNING`/`INFO` severity levels.

**Required:** `question` (what to focus on), `context` (the code to review)
**Optional:** `trace_id`, `format`, `context_type` (defaults to `""`; pass `"code"` for an explicit code-focused modifier)

**Example:**
```python
# Standard code review
consult(
    action="review",
    question="Focus on the auth flow and token rotation logic",
    context="<full source of auth.py>",
)

# JSON output for downstream parsing
consult(
    action="review",
    question="Any race conditions in this cache invalidation code?",
    context="<source>",
    format="json",
    context_type="code",
)
```

**Success response:**
```json
{
  "status": "success",
  "action": "review",
  "provider": "openai",
  "model": "gpt-4o",
  "review": "## CRITICAL\n\n- Line 42: The token refresh window has a TOCTOU race...\n\n## WARNING\n\n- Line 87: ..."
}
```

---

### `consult(action="explain", ...)` — Concept Explanation

**Purpose:** Educational deep-dive on a concept, mechanism, or trade-off. Uses an educator persona with analogies, examples, and step-by-step breakdowns; adapts depth to the question's sophistication.

**Required:** `question` (the concept to explain)
**Optional:** `context` (background material), `trace_id`, `format`, `context_type`

**Example:**
```python
# Pure concept explanation
consult(action="explain", question="How does RAG differ from fine-tuning?")

# With context for tailored depth
consult(
    action="explain",
    question="Explain the CAP theorem",
    context="We use Cassandra for a multi-region deployment with strict latency SLAs...",
    format="bullet_points",
)
```

**Success response:**
```json
{
  "status": "success",
  "action": "explain",
  "provider": "openai",
  "model": "gpt-4o",
  "explanation": "## RAG vs Fine-Tuning\n\nThink of RAG as..."
}
```

---

## 📤 Output Schema (All Actions)

Every response is a flat `dict` with a `status` key. The action-specific payload key (`advice` / `review` / `explanation`) is determined by the `action` field.

### Success
```json
{
  "status": "success",
  "action": "advise",                       // or "review" / "explain"
  "provider": "openai",
  "model": "gpt-4o",
  "advice": "...",                          // or "review" / "explanation"
  "trace_id": "wf-1234",                    // only if caller passed one
  "warnings": ["Context truncated..."],     // only if truncation occurred
  "duration_ms": 1842                       // always present, set by facade
}
```

### Disabled
```json
{
  "status": "disabled",
  "error": "Consultor is disabled. Set CONSULTOR_MODEL in .env to enable.",
  "trace_id": "wf-1234"                     // only if caller passed one
}
```

### Rate Limited
```json
{
  "status": "rate_limited",
  "error": "Rate limit exceeded for openai. Please wait before consulting again.",
  "provider": "openai",
  "trace_id": "wf-1234"                     // only if caller passed one
}
```

### LLM Error (handler-level)
```json
{
  "status": "error",
  "provider": "openai",
  "model": "gpt-4o",
  "error": "HTTP 503: Service unavailable",
  "trace_id": "wf-1234"                     // only if caller passed one
}
```

### Facade-Level Errors

| Trigger | Response |
|---------|----------|
| `action` empty / whitespace | `{"status": "error", "error": "action is required (advise \| explain \| review)", "trace_id": ...}` |
| `action` not in `DISPATCH` | `{"status": "error", "error": "Unknown action '<x>'. Use: advise \| explain \| review", "trace_id": ...}` |
| Handler raises an exception | `{"status": "error", "error": "Consult action failed: <exc>", "trace_id": ...}` |
| Handler returns non-dict | `{"status": "error", "error": "Handler returned <type>, expected dict.", "trace_id": ...}` |
| `question` empty (handler-level) | `{"status": "error", "error": "The question parameter cannot be empty.", "trace_id": ...}` |

---

## ⚠️ Error Handling

| Condition | `status` | Returned by | `provider` / `model` | `trace_id` | `warnings` |
|-----------|----------|-------------|----------------------|------------|------------|
| `action` empty | `error` | Facade | ❌ | ✅ (if passed) | ❌ |
| `action` unknown | `error` | Facade | ❌ | ✅ (if passed) | ❌ |
| `question` empty | `error` | Handler | ❌ | ✅ (if passed) | ❌ |
| Consultor not configured (kill-switch) | `disabled` | Handler (`_check_consultor_available`) | ❌ | ✅ (if passed) | ❌ |
| Provider unavailable (`llm.is_available` False) | `disabled` | Handler (`_check_consultor_available`) | ✅ | ✅ (if passed) | ❌ |
| Rate limit exceeded | `rate_limited` | Handler (`_check_rate_limit`) | ✅ | ✅ (if passed) | ❌ |
| LLM call fails (`result.ok = False`) | `error` | Handler | ✅ + ✅ | ✅ (if passed) | ❌ |
| Handler raises exception | `error` | Facade (try/except) | ❌ | ✅ (if passed) | ❌ |
| Handler returns non-dict | `error` | Facade (isinstance check) | ❌ | ✅ (if passed) | ❌ |
| Success (no truncation) | `success` | Handler | ✅ + ✅ | ✅ (if passed) | ❌ |
| Success (with truncation) | `success` | Handler | ✅ + ✅ | ✅ (if passed) | ✅ |

**Notes:**
- `provider`/`model` are only present on errors that occur *after* the consultor role is resolved (LLM call failures) or on success. Facade-level errors (bad `action`) never reach the registry lookup, so they don't have provider info.
- `trace_id` is **always** included when the caller passed one — even on facade-level validation errors. This ensures workflow tracing can correlate a failed `consult` call to its trace.
- `warnings` is only present on success when `_truncate_context()` truncated the input. It is never present on error responses.
- `duration_ms` is added by the facade on **every** return path (including facade-level errors) — useful for SLO monitoring without separate instrumentation.

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **Kill-switch** | Returns `disabled` immediately if `cfg.consultor_model` is falsy — no network call |
| **Rate-limit guard** | `_check_rate_limit()` wraps `check_rate_limit(provider)` and blocks the call before any HTTP request |
| **Context truncation** | `_estimate_tokens()` + hard 2000-token ceiling prunes oversized `context` before dispatch. Prevents both context-window overruns and prompt-injection-via-oversized-input attacks. |
| **No local FS access** | `consult` only processes text passed by the caller. Never reads files or executes code directly |
| **Isolated config** | Uses dedicated `CONSULTOR_*` env vars resolved through `cfg.model_registry`. Never shares keys with local LM Studio |
| **No local fallback** | If the consultor role is unavailable, the tool returns `disabled` — it never silently falls back to a local model. Cloud-only is a deliberate design constraint |
| **Action allowlist via `DISPATCH`** | The facade only invokes handlers registered through `@register_action`. Unknown `action` values return `error` before any handler runs — no eval, no string-to-function mapping |
| **`trace_id` is caller-supplied** | The tool never generates its own `trace_id`. This prevents log-injection via fabricated trace IDs — callers are responsible for the IDs they pass |

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
