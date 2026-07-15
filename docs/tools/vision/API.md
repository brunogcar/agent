<- Back to [Vision Overview](../VISION.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
from registry import tool
from tools._meta_tool import meta_tool
from tools.vision_ops._registry import DISPATCH

@tool
@meta_tool(
    DISPATCH.get("vision", {}),
    doc_sections=[ ... ],   # auto-generated action list + param notes
)
def vision(
    action: str = "",          # Literal["describe", "extract_text", "analyse_ui"] (auto-generated)
    question: str = "",
    file_path: str = "",
    base64: str = "",
    url: str = "",
    mime_type: str = "image/jpeg",
    json_mode: bool = False,
    json_schema: str = "",
    context: str = "",
    context_type: str = "",
    format: str = "markdown",
    trace_id: str = "",
    task: str = "",            # DEPRECATED — backward-compat alias for question when action is empty
) -> dict:
    """Vision meta-tool — describe | extract_text | analyse_ui."""
```

> The `action: Literal[...]` annotation and the action list in the docstring are **auto-generated** by `@meta_tool` from `DISPATCH["vision"]` keys at import time. Adding a new action file in `vision_ops/actions/` automatically extends the `Literal` and the docstring — no facade edits required.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | `str` (`Literal["describe","extract_text","analyse_ui"]`) | **Yes** | `""` | Which vision action to invoke. Empty / unknown values return `status=error`. |
| `question` | `str` | No | `""` | Optional focus question / instruction for the model. Defaults to the action's default instruction when empty (`"Describe this image in detail."` / `"Extract all visible text from this image."` / `"Analyse this UI in detail."`). |
| `file_path` | `str` | No (one of `file_path`/`base64`/`url` required) | `""` | Local file path to an image (`.jpg`/`.jpeg`/`.png`/`.webp`/`.gif`/`.bmp`). MIME auto-detected from extension; unknown extensions fall back to `image/jpeg`. |
| `base64` | `str` | No (one of `file_path`/`base64`/`url` required) | `""` | Base64-encoded image data (with or without `data:` prefix). MIME controlled by `mime_type`. |
| `url` | `str` | No (one of `file_path`/`base64`/`url` required) | `""` | Public HTTP(S) URL to an image. **SSRF-protected** via `is_safe_network_address()`. Downloaded via `core/net retry_sync` (max 2 retries). |
| `mime_type` | `str` | No | `"image/jpeg"` | MIME type override for `base64` sources. Ignored for `file_path` (extension-based) and `url` (content-type based). |
| `json_mode` | `bool` | No | `False` | Request JSON-formatted output. When `True`, the action's `*_JSON_SYSTEM` prompt variant is selected and `result.parsed` is populated by `llm.call()`'s built-in JSON parser. |
| `json_schema` | `str` | No | `""` | JSON schema string for structured output validation. Parsed as a dict and forwarded to `llm.call(json_schema=...)`. Implies JSON-mode prompt selection (same as `json_mode=True`). Malformed schema strings silently degrade to no-schema (caller detects via `result.parsed=None` + `parse_warning`). |
| `context` | `str` | No | `""` | Supplementary text shown to the model alongside the image (prepended as a `Context: ...` text block in the multimodal user content). Useful for "this screenshot was taken from the billing page" hints. |
| `context_type` | `str` | No | `""` | Image-kind modifier appended as a suffix to the system prompt: `""` (no modifier) / `screenshot` (focus on interface elements) / `diagram` (focus on structure/connections) / `photo` (focus on subjects/setting) / `document` (focus on text content). Applied in **both** the base-prompt and JSON-variant branches. Unknown values silently degrade to `""`. |
| `format` | `str` | No | `"markdown"` | Output shape control: `markdown` (no suffix; base prompt already implies structured Markdown) / `json` (append `"Output your response as valid JSON."`) / `bullet_points` (append `"Format your response as bullet points only."`). **Ignored** when `json_mode`/`json_schema` is active (the JSON variant already specifies the shape). Unknown values silently degrade to `markdown`. |
| `trace_id` | `str` | No | `""` | Observability trace ID. Forwarded to `llm.call(trace_id=...)` and included in the response **only when non-empty**. |
| `task` | `str` | No (deprecated) | `""` | **DEPRECATED.** Backward-compat alias for `question` when `action` is empty. If `action` is empty AND `task` is non-empty, mapped to `action="describe"` + `question=task` with a deprecation warning. **Will be removed in v2.0.** Update callers to `action`+`question`. |

**Input rule:** Exactly one of `file_path`, `base64`, or `url` must be provided. Zero or multiple sources are rejected.

---

## 🎬 Actions

### `vision(action="describe", ...)` — General Image Description

**Purpose:** General image understanding. Preserves the Pre-v1 `_VISION_SYSTEM` behavior — Overview / Key Elements / Text Content / Notable Details. Use this when the caller wants "what's in this image?".

**Required:** `file_path` OR `base64` OR `url` (exactly one)
**Optional:** `question`, `mime_type`, `json_mode`, `json_schema`, `context`, `context_type`, `format`, `trace_id`

**Examples:**
```python
# Basic local image description
vision(action="describe", file_path="screenshot.png")

# URL with a focus question
vision(action="describe", url="https://example.com/img.jpg", question="Focus on the colors used")

# Structured JSON output with a custom schema
vision(
    action="describe",
    base64="<b64...>",
    json_schema='{"type":"object","properties":{"objects":{"type":"array","items":{"type":"string"}},"colors":{"type":"array","items":{"type":"string"}}},"required":["objects","colors"]}',
    context_type="photo",
    trace_id="wf-1234",
)

# Bullet-point output
vision(action="describe", file_path="landscape.jpg", format="bullet_points", context_type="photo")
```

**Success response:**
```json
{
  "status": "success",
  "action": "describe",
  "description": "Overview: A dashboard showing sales metrics...\nKey Elements: ...\nText Content: ...\nNotable Details: ...",
  "model": "gpt-4o",
  "elapsed": 2.34,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150},
  "trace_id": "wf-1234",
  "duration_ms": 2362
}
```
> `trace_id` is omitted when the caller didn't pass one. `parsed` + `parse_warning` are added when `json_mode`/`json_schema` is active.

**JSON-mode response:**
```json
{
  "status": "success",
  "action": "describe",
  "description": "{\"overview\":\"...\",\"elements\":[...],\"text_content\":null,\"colors\":[\"blue\",\"green\"],\"details\":\"...\",\"confidence\":\"high\"}",
  "parsed": {
    "overview": "A dashboard showing sales metrics",
    "elements": ["chart", "table", "filter bar"],
    "text_content": null,
    "colors": ["blue", "green", "white"],
    "details": "Line chart shows upward trend",
    "confidence": "high"
  },
  "model": "gpt-4o",
  "elapsed": 2.34,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150},
  "duration_ms": 2362
}
```
> When `result.parsed` is falsy (LLM produced invalid JSON), `parse_warning: "LLM response was not valid JSON. Check response.description."` is added and `parsed` is set to `{}`.

---

### `vision(action="extract_text", ...)` — OCR-Style Text Extraction

**Purpose:** Extract ALL visible text from an image in reading order. The system prompt instructs the model to act as an OCR specialist: preserve top-to-bottom / left-to-right reading order, note text location/region (header / body / sidebar / caption / footer), distinguish headings / body text / labels / captions, mark low-confidence text as `[unclear]`, and respond with `"No readable text found in the image."` when the image has no text.

**Required:** `file_path` OR `base64` OR `url` (exactly one)
**Optional:** `question`, `mime_type`, `json_mode`, `json_schema`, `context`, `context_type` (default `"document"` recommended), `format`, `trace_id`

**Examples:**
```python
# Extract text from a receipt
vision(action="extract_text", file_path="receipt.png")

# URL with context_type hint
vision(action="extract_text", url="https://example.com/sign.jpg", context_type="photo")

# Structured JSON output with block-level confidence
vision(action="extract_text", file_path="form.png", json_mode=True)
```

**Success response:**
```json
{
  "status": "success",
  "action": "extract_text",
  "text_extracted": "Source: receipt\nText:\n[header] ACME STORE\n[body] Milk    $3.99\n[body] Bread   $2.49\n[footer] Total  $6.48",
  "model": "gpt-4o",
  "elapsed": 1.87,
  "usage": {"prompt_tokens": 1100, "completion_tokens": 95},
  "duration_ms": 1903
}
```

---

### `vision(action="analyse_ui", ...)` — UI/UX Analysis

**Purpose:** Critique an interface screenshot. The system prompt instructs the model to act as a senior UI/UX designer and produce an 8-section analysis: Components, Layout, Accessibility, UX Patterns, Design System, Strengths (2-3 things), Issues (2-3 specific problems with `CRITICAL`/`WARNING`/`INFO` severity), and Recommendations (2-3 actionable improvements).

**Required:** `file_path` OR `base64` OR `url` (exactly one)
**Optional:** `question` (focus area — e.g. "Focus on the nav bar"), `mime_type`, `json_mode`, `json_schema`, `context`, `context_type` (default `"screenshot"` recommended), `format`, `trace_id`

**Examples:**
```python
# Analyse a dashboard
vision(action="analyse_ui", file_path="dashboard.png")

# Focus on a specific area
vision(action="analyse_ui", url="https://example.com/app.jpg", question="Focus on the navigation bar and breadcrumbs")

# JSON output with structured findings
vision(
    action="analyse_ui",
    file_path="ui.png",
    json_mode=True,
    context_type="screenshot",
    trace_id="wf-1234",
)
```

**Success response:**
```json
{
  "status": "success",
  "action": "analyse_ui",
  "analysis": "Components: [button, input, card, nav, modal]\nLayout: ...\nAccessibility: ...\nUX Patterns: ...\nDesign System: ...\nStrengths: ...\nIssues: [CRITICAL: contrast ratio on secondary buttons is 3.1:1, below WCAG AA 4.5:1]\nRecommendations: ...",
  "model": "gpt-4o",
  "elapsed": 3.12,
  "usage": {"prompt_tokens": 1300, "completion_tokens": 220},
  "trace_id": "wf-1234",
  "duration_ms": 3148
}
```

---

## 📤 Output Schema (All Actions)

Every response is a flat `dict` with a `status` key. The action-specific payload key (`description` / `text_extracted` / `analysis`) is determined by the `action` field.

### Success
```json
{
  "status": "success",
  "action": "describe",                       // or "extract_text" / "analyse_ui"
  "description": "...",                        // or "text_extracted" / "analysis"
  "model": "gpt-4o",
  "elapsed": 2.34,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150},
  "trace_id": "wf-1234",                       // only if caller passed one
  "parsed": {...},                             // only if json_mode / json_schema active
  "parse_warning": "...",                      // only if json_mode active AND result.parsed is falsy
  "duration_ms": 2362                          // always present, set by facade
}
```

### Disabled
```json
{
  "status": "disabled",
  "error": "VISION_MODEL not set in .env — add it to your .env file",
  "trace_id": "wf-1234"                        // only if caller passed one
}
```

### LLM Error (handler-level)
```json
{
  "status": "error",
  "error": "Vision model call failed: <exception>",
  "model": "gpt-4o",
  "elapsed": 0.0,
  "trace_id": "wf-1234"                        // only if caller passed one
}
```

### Validation Error (handler-level)
```json
{
  "status": "error",
  "error": "SSRF blocked: http://localhost/image.png points to private/localhost network",
  "trace_id": "wf-1234"
}
```

### Facade-Level Errors

| Trigger | Response |
|---------|----------|
| `action` empty / whitespace (and no `task` alias) | `{"status": "error", "error": "action is required (describe \| extract_text \| analyse_ui)", "trace_id": ...}` |
| `action` not in `DISPATCH` | `{"status": "error", "error": "Unknown action '<x>'. Use: describe \| extract_text \| analyse_ui", "trace_id": ...}` |
| Handler raises an exception | `{"status": "error", "error": "Vision action failed: <exc>", "trace_id": ...}` |
| Handler returns non-dict | `{"status": "error", "error": "Handler returned <type>, expected dict.", "trace_id": ...}` |

---

## ⚠️ Error Handling

| Condition | `status` | Returned by | `model` / `elapsed` | `trace_id` | `parsed` / `parse_warning` |
|-----------|----------|-------------|----------------------|------------|-----------------------------|
| `action` empty (no `task` alias) | `error` | Facade | ❌ | ✅ (if passed) | ❌ |
| `action` unknown | `error` | Facade | ❌ | ✅ (if passed) | ❌ |
| Deprecated `task` alias used | (deprecation warning logged) | Facade → mapped to `action="describe"` + `question=task` | — | — | — |
| Handler raises exception | `error` | Facade (try/except) | ❌ | ✅ (if passed) | ❌ |
| Handler returns non-dict | `error` | Facade (isinstance check) | ❌ | ✅ (if passed) | ❌ |
| `VISION_MODEL` unset (kill-switch) | `disabled` | Handler (`_check_vision_available`) | ❌ | ✅ (if passed) | ❌ |
| Validation failure (zero/multiple sources, SSRF, file size, base64 length, bad URL scheme) | `error` | Handler (`_validate_vision_inputs`) | ❌ | ✅ (if passed) | ❌ |
| Image-block build failure (file read error, download failure) | `error` | Handler (`_build_image_block`) | ❌ | ✅ (if passed) | ❌ |
| LLM call fails (`result.ok = False`) | `error` | Handler | ✅ + ✅ | ✅ (if passed) | ❌ |
| LLM call raises exception | `error` | Handler (try/except) | ❌ | ✅ (if passed) | ❌ |
| Success (no JSON) | `success` | Handler | ✅ + ✅ | ✅ (if passed) | ❌ |
| Success (json_mode/json_schema, valid JSON) | `success` | Handler | ✅ + ✅ | ✅ (if passed) | ✅ `parsed`, no `parse_warning` |
| Success (json_mode/json_schema, invalid JSON) | `success` | Handler | ✅ + ✅ | ✅ (if passed) | ✅ `parsed={}` + ✅ `parse_warning` |

**Notes:**
- `model`/`elapsed` are only present on errors that occur *after* the LLM call returns (LLM call failures) or on success. Facade-level errors and validation errors never reach the LLM, so they don't carry `model`/`elapsed`.
- `trace_id` is **always** included when the caller passed one — even on facade-level validation errors. This ensures workflow tracing can correlate a failed `vision` call to its trace.
- `parsed` is only present on success when `json_mode` or `json_schema` is active.
- `parse_warning` is only present on success when `json_mode`/`json_schema` is active AND `result.parsed` is falsy. It is never present on error responses.
- `duration_ms` is added by the facade on **every** return path (including facade-level errors) — useful for SLO monitoring without separate instrumentation.

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **SSRF protection** | `is_safe_network_address(hostname)` (from `core/net/security.py`) blocks localhost, private IP ranges (RFC 1918), link-local, and other reserved ranges **before** any HTTP request. DNS resolution happens inside the check. Tracer warning emitted on block. |
| **URL scheme validation** | Only `http`/`https` allowed. Rejects `file://`, `ftp://`, `data:`, etc. with `"Invalid URL scheme: {scheme}. Only http/https allowed."` |
| **File size limits** | `MAX_IMAGE_BYTES` (20MB default, env-configurable via `VISION_MAX_FILE_BYTES`) prevents memory exhaustion from oversized local files. |
| **Base64 length limits** | `MAX_BASE64_LEN` (10M chars default, env-configurable via `VISION_MAX_BASE64_LEN`) prevents memory exhaustion from oversized base64 strings. |
| **`core/net retry_sync` for URL downloads** | `_download_image_to_data_uri()` wraps `httpx.Client.get()` in `retry_sync()` with `max_retries=2` (vision-specific — single image fetch, not a search). `is_retryable_error()` classifies `httpx` exceptions and HTTP status codes (5xx + 429 retryable; 4xx other than 429 fail fast). `RETRY_BASE_DELAY` / `RETRY_MAX_DELAY` come from `core/net/default.py` (centrally tunable). Jitter prevents thundering-herd. |
| **No local FS access beyond image read** | Only reads the specified `file_path`. No directory traversal. No write operations. |
| **Kill-switch** | Returns `status="disabled"` immediately if `cfg.vision_model` is falsy — no network call, no LLM call. Empty `VISION_MODEL` in `.env` is the documented opt-out. |
| **Action allowlist via `DISPATCH`** | The facade only invokes handlers registered through `@register_action`. Unknown `action` values return `error` before any handler runs — no eval, no string-to-function mapping. |
| **`trace_id` is caller-supplied** | The tool never generates its own `trace_id`. This prevents log-injection via fabricated trace IDs — callers are responsible for the IDs they pass. |
| **Deprecation warning on `task` alias** | When the deprecated `task` parameter is used, a warning is emitted to both `logger.warning` and `tracer.warning` (with `task_preview` truncated to 100 chars). This surfaces legacy callers so they can be migrated before v2.0. |
| **JSON schema string parsed locally** | `json_schema` is parsed via `json.loads()` inside `_call_vision()`. On parse failure (malformed JSON), it silently degrades to `schema_dict=None` — the call proceeds without a schema, and the caller detects the issue via `parsed=None` + `parse_warning`. Never propagates untrusted strings to the LLM backend verbatim. |

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
