# 👁️ Vision Tool

The `vision()` tool provides **multimodal image analysis** using a dedicated vision model. It accepts images via local file path, base64 string, or URL, and routes the analysis through one of three action-specific system prompts (`describe` / `extract_text` / `analyse_ui`).

**Key characteristics:**
- **`@meta_tool` facade** — 3 actions (`describe` / `extract_text` / `analyse_ui`) auto-discovered from `vision_ops/actions/` via the `DISPATCH` registry. Adding a new action = drop a file; the `action: Literal[...]` annotation and docstring update themselves.
- **8-file `vision_ops/` subpackage** — `_registry.py` (DISPATCH + `register_action`), `__init__.py` (auto-discovery), `helpers.py` (7 shared utilities including `_call_vision` + `_download_image_to_data_uri`), `prompts.py` (3 base prompts × 2 variants + format/context-type modifiers), `actions/{__init__,describe,extract_text,analyse_ui}.py`.
- **Same LLM, different prompts** — all 3 actions route to one configured `vision` role (`cfg.vision_model`). Only the system prompt differs (base + format suffix + context-type modifier).
- **Three input sources** — `file_path`, `base64`, or `url` (exactly one required). URL downloads go through `core/net retry_sync` (max 2 retries, `is_retryable_error` classification).
- **SSRF protection** — `is_safe_network_address()` blocks localhost and private IP ranges for URL inputs (runs in `_validate_vision_inputs()`).
- **Structured output** — `json_mode=True` selects the action's JSON variant prompt; `json_schema='...'` forwards a parsed schema dict to `llm.call(json_schema=...)` for response validation. `parsed` + `parse_warning` in the response.
- **Context modifiers** — `format` (`markdown`/`json`/`bullet_points`) and `context_type` (`screenshot`/`diagram`/`photo`/`document`) append orthogonal suffixes to the base prompt.
- **Kill-switch ready** — Returns `{"status": "disabled"}` if `VISION_MODEL` is unset; no crashes, no silent fallbacks.
- **Observability built in** — `trace_id` threaded through every return path; `duration_ms` always present.
- **Deprecated `task` alias** — backward compat with `tools/agent_ops/actions/vision_delegate.py`. When `action` is empty AND `task` is non-empty, mapped to `action="describe"` + `question=task` with a deprecation warning. **Will be removed in v2.0.**
- **NOT parallel-safe** — uses LLM calls; do NOT add to `PARALLEL_SAFE`.

---

## 🚀 Quick Start

```python
# Describe — general image description (default action)
vision(action="describe", file_path="screenshot.png")

# Extract text — OCR-style extraction preserving reading order
vision(action="extract_text", url="https://example.com/receipt.jpg", context_type="photo")

# Analyse UI — senior UI/UX designer critique
vision(action="analyse_ui", file_path="dashboard.png", context_type="screenshot")

# Structured JSON output via json_schema
vision(
    action="describe",
    base64="<b64...>",
    json_schema='{"type":"object","properties":{"objects":{"type":"array","items":{"type":"string"}}},"required":["objects"]}',
    context_type="photo",
    trace_id="wf-1234",
)

# Bullet-point output via format suffix
vision(action="describe", file_path="landscape.jpg", format="bullet_points")

# Focus question
vision(action="analyse_ui", file_path="ui.png", question="Focus on the nav bar and breadcrumbs")

# Deprecated task alias (still works — emits deprecation warning)
vision(task="Describe this image in detail.", file_path="screenshot.png")
# → mapped to vision(action="describe", question="Describe this image in detail.", file_path="screenshot.png")

# Disabled by default — returns clear status if unconfigured
vision(action="describe", file_path="screenshot.png")
# → {"status": "disabled", "error": "VISION_MODEL not set in .env — add it to your .env file"}
```

---

## ⚙️ Configuration & Kill-Switch

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `vision_model` | `cfg.vision_model` (`VISION_MODEL` env var) | — | Vision-capable model name (e.g., `gpt-4o`, `claude-3-opus`). **Required.** Empty → `status=disabled`. |
| `VISION_MAX_FILE_BYTES` | Environment | 20,000,000 | Max file size for local images (20MB) |
| `VISION_MAX_BASE64_LEN` | Environment | 10,000,000 | Max base64 string length (10M chars) |
| `core/net/default.py RETRY_BASE_DELAY` | `core/net/default.py` | (project-wide) | Base delay (seconds) for URL download retry backoff |
| `core/net/default.py RETRY_MAX_DELAY` | `core/net/default.py` | (project-wide) | Max delay cap (seconds) for URL download retry backoff |
| `_VISION_DOWNLOAD_RETRIES` | `tools/vision_ops/helpers.py` | 2 | Vision-specific retry count for URL downloads (one fewer than `web`/`tavily` — single image fetch, not a search) |

**Kill-switch behavior:**

| Condition | Return Status | Message |
|-----------|--------------|---------|
| `action` empty / whitespace (and no `task` alias) | `error` | `action is required (describe \| extract_text \| analyse_ui)` |
| `action` not in DISPATCH | `error` | `Unknown action '<x>'. Use: describe \| extract_text \| analyse_ui` |
| `VISION_MODEL` empty / unset | `disabled` | `VISION_MODEL not set in .env — add it to your .env file` |
| Zero or multiple image sources | `error` | `Exactly one image source (file_path, base64, or url) is required.` / `Provide exactly ONE image source, not multiple.` |
| SSRF blocked (URL hostname resolves to private/localhost) | `error` | `SSRF blocked: {url} points to private/localhost network` |
| Non-http URL scheme | `error` | `Invalid URL scheme: {scheme}. Only http/https allowed.` |
| File not found / too large | `error` | `File not found: {path}` / `File too large ({size} bytes, max {MAX_IMAGE_BYTES}).` |
| URL download timeout / HTTP error | `error` | `Timeout downloading image from {url} (>{timeout}s)` / `HTTP error {status} downloading image.` |
| Handler raises exception | `error` | `Vision action failed: <exc>` |

> **Note:** The router's vision-routing heuristic was already in place — no router changes were needed for v1.0. The `agent(role="vision")` path uses `vision_delegate.py`, which still calls `vision(task=...)` via the deprecated alias — update it before v2.0.

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| General image description ("what's in this image?") | `vision(action="describe")` | Overview / Key Elements / Text Content / Notable Details |
| Extract visible text (OCR) | `vision(action="extract_text")` | Preserves reading order, notes location, marks `[unclear]` text |
| UI/UX critique | `vision(action="analyse_ui")` | Components / Layout / Accessibility / UX Patterns / Design System / Strengths / Issues / Recommendations |
| Structured image data | `vision(action="describe", json_schema=...)` | JSON output validated against a caller-supplied schema |
| Read image metadata (no LLM) | `file(get_file_info)` | Fast, no LLM cost |
| Convert image format | `file` operations | File system, no LLM |
| Multi-model consensus on an image | `swarm` | Cross-provider fan-out (vision models across providers) |
| Code review with severity tags (text only) | `consult(action="review")` | Cloud LLM advisory, no image input |
| Simple image resize | External tool | Not a vision task |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](vision/ARCHITECTURE.md) | Source code reference (8-file subpackage), module tree, dispatch flow, `_call_vision` indirection, 3-action pattern, `task` deprecation alias, JSON schema / format / context-type modifiers, `core/net retry_sync` adoption, design decisions, test coverage (143 tests across 6 files) |
| [API.md](vision/API.md) | Full `@meta_tool` signature, 3 action sections (describe/extract_text/analyse_ui) with params/returns/examples, new params (`json_schema`/`format`/`context_type`/`trace_id`), deprecated `task` alias, error handling table, security (SSRF / file size limits / core/net retry) |
| [CHANGELOG.md](vision/CHANGELOG.md) | v1.0 entry, breaking changes (`task`→`action`+`question`), completed table, in-progress + roadmap (13 suggested items including `compare`/`batch_analyse`/`detect_objects`/`count`/`translate`/`chart_extract`/`diagram_to_code`/`accessibility_audit`/streaming/video_frame/pdf_page/ocr_fallback/multi_image_context + v2.0 task removal), deferred |
| [INSTRUCTIONS.md](vision/INSTRUCTIONS.md) | AI editing rules — NEVER DO (reversed #1, 19 rules including never-call-`llm.call`-directly, never-bypass-SSRF, never-bypass-`retry_sync`, never-leave-temp-files), ALWAYS DO (16 rules), anti-patterns from the `_call_vision` discovery |

---

*Last updated: 2026-07-15 (v1.0). See subfiles for detailed documentation.*
