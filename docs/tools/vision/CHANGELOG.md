<- Back to [Vision Overview](../VISION.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.0** | 2026-07-15 | `@meta_tool` refactor: 3 actions (`describe`/`extract_text`/`analyse_ui`), `vision_ops/` subpackage (8 files), breaking `task`→`action`+`question` rename (with deprecated `task` alias for backward compat with `vision_delegate.py`), new params (`json_schema`, `format`, `context_type`, `trace_id`), `core/net retry_sync` adoption for URL downloads. 143 tests across 6 files. Old `test_vision.py` deleted. |
| Pre-v1 | 2026-07-03 | Initial multimodal tool: single `vision(task, file_path, base64, url, ...)` facade, `_VISION_SYSTEM` / `_VISION_JSON_SYSTEM` static prompts, kill-switch, SSRF protection, MIME auto-detection, file/base64/URL sources. Tests in one `test_vision.py`. |

---

## ⚠️ Breaking Changes

| Version | Change | Migration |
|---------|--------|-----------|
| **v1.0** | The legacy `task` parameter is replaced by `action` + `question`. `vision(task="Describe this image")` no longer dispatches to the analysis flow when called directly — `action` is now required. | Update callers to `vision(action="describe", question="Describe this image")`. A **deprecated `task` alias** is kept for backward compat: when `action` is empty AND `task` is non-empty, the call is treated as `action="describe"` + `question=task` and a deprecation warning is logged. `tools/agent_ops/actions/vision_delegate.py` still relies on this alias — update it before v2.0. The alias will be removed in v2.0. |
| **v1.0** | Response payload keys are action-specific: `describe` → `description`, `extract_text` → `text_extracted`, `analyse_ui` → `analysis`. (Pre-v1 always returned `text`.) | Inspect the `action` field in the response to pick the correct key, or read `result.get("description") or result.get("text_extracted") or result.get("analysis")`. |
| **v1.0** | The Pre-v1 `vision(task, ...)` returned `{"status": "success", "text": "..."}`. v1.0 returns `{"status": "success", "action": "<name>", "<action_key>": "...", "model", "elapsed", "usage", "duration_ms"}` — note the added `action`, `model`, `elapsed`, `usage`, and `duration_ms` keys, plus the action-specific payload key. | Update any caller that reads `result["text"]` unconditionally. The router's vision routing heuristic was already in place — no router changes needed for v1.0. |
| **v1.0** | `format` is a soft-reserved keyword argument name. Callers passing `format=` for any other purpose will conflict. | Standard behavior — only matters if a caller was abusing `**kwargs` (the old `@tool` facade didn't accept `**kwargs` either, so this is theoretical). |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Multimodal image analysis | ✅ Pre-v1 | `llm.call(role="vision")` with image_url content blocks |
| Three input sources | ✅ Pre-v1 | `file_path`, `base64`, `url` — exactly one required |
| SSRF protection | ✅ Pre-v1 | `is_safe_network_address()` blocks localhost/private IPs |
| URL to data URI conversion | ✅ Pre-v1 | Downloads and converts to base64 data URI for LM Studio compatibility |
| JSON mode | ✅ Pre-v1 | Structured output with `json_mode=True` and built-in parsing |
| Context support | ✅ Pre-v1 | Optional `context` parameter for background info |
| File size limits | ✅ Pre-v1 | `VISION_MAX_FILE_BYTES` (20MB) and `VISION_MAX_BASE64_LEN` (10M chars) |
| MIME type auto-detection | ✅ Pre-v1 | From file extension, fallback to `image/jpeg` |
| Kill-switch | ✅ Pre-v1 | Clear error if `VISION_MODEL` unset |
| Tracer integration | ✅ Pre-v1 | `tracer.error()` and `tracer.warning()` for observability |
| `@meta_tool` refactor | ✅ v1.0 | Facade is now a thin dispatch wrapper; `action: Literal["describe","extract_text","analyse_ui"]` auto-generated from `DISPATCH` |
| Un-multiplex into `vision_ops/` | ✅ v1.0 | 8-file subpackage: `_registry.py`, `__init__.py`, `helpers.py`, `prompts.py`, `actions/{__init__,describe,extract_text,analyse_ui}.py` |
| 3 actions (`describe` / `extract_text` / `analyse_ui`) | ✅ v1.0 | Same LLM call, different system prompts. `describe` preserves the Pre-v1 `_VISION_SYSTEM` behavior; `extract_text` adds OCR-specialist prompt with reading-order + location notes; `analyse_ui` adds senior UI/UX designer prompt with components / layout / accessibility / UX patterns / design system / strengths / issues / recommendations |
| Deprecated `task` alias (backward compat) | ✅ v1.0 | When `action` is empty AND `task` is non-empty, mapped to `action="describe"` + `question=task` with a deprecation warning. Keeps `tools/agent_ops/actions/vision_delegate.py` working until v2.0 |
| New params: `trace_id` / `format` / `context_type` / `json_schema` | ✅ v1.0 | `trace_id` (observability, threaded through all return paths); `format` (`markdown`/`json`/`bullet_points` — appended suffix to base prompt); `context_type` (`""`/`screenshot`/`diagram`/`photo`/`document` — appended modifier); `json_schema` (structured output via `llm.call(json_schema=...)`, parsed as dict and forwarded) |
| `core/net retry_sync` adoption | ✅ v1.0 | `_download_image_to_data_uri()` now wraps `httpx.Client.get()` in `retry_sync()` from `core/net/retry.py` with `is_retryable_error()` classification. `RETRY_BASE_DELAY` and `RETRY_MAX_DELAY` come from `core/net/default.py`. Vision uses `max_retries=2` (one fewer than the web tool — single image fetch, not a search) |
| JSON schema validation | ✅ v1.0 | When `json_schema` is non-empty, the action handler selects the action's `*_JSON_SYSTEM` prompt variant and forwards the parsed schema dict to `llm.call(json_schema=...)`. Result includes `parsed` (dict or `{}`) and `parse_warning` when the LLM response wasn't valid JSON |
| Format suffixes | ✅ v1.0 | `FORMAT_SUFFIXES` dict in `prompts.py` — `markdown` (no suffix), `json` ("Output your response as valid JSON."), `bullet_points` ("Format your response as bullet points only."). Skipped when `json_mode`/`json_schema` is active (the JSON variant already specifies the shape) |
| Context-type modifiers | ✅ v1.0 | `CONTEXT_TYPE_MODIFIERS` dict — orthogonal to `format`, appended even in JSON mode. `screenshot` / `diagram` / `photo` / `document` each focus the model on the image kind |
| Centralized LLM access (`_call_vision`) | ✅ v1.0 | Action handlers call `helpers._call_vision()` instead of `llm.call()` directly — enables clean test patching via `tools.vision_ops.helpers.llm` |
| Test restructure | ✅ v1.0 | 143 tests across 6 files (`conftest.py` + `test_describe.py` / `test_extract_text.py` / `test_analyse_ui.py` / `test_dispatch.py` / `test_helpers.py`). Old `test_vision.py` deleted. |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Update `vision_delegate.py` to use `action`+`question` | `tools/agent_ops/actions/vision_delegate.py` still calls `vision(task=...)`. Update it to `vision(action="describe", question=...)` so the deprecated `task` alias can be removed in v2.0. | P2 |

### 💡 Suggested Roadmap (Future Sessions)

The following items are **proposed** for future vision roadmap sessions. They are not yet committed — list them here so the next maintainer can pick the highest-value ones.

| Feature | Notes | Priority |
|---------|-------|----------|
| `vision(action="compare")` | Side-by-side comparison of two images (diff two screenshots, before/after states). Caller passes two `file_path`s or `url`s; vision returns a structured diff. Mirrors `swarm compare` but for images. | P2 |
| `vision(action="batch_analyse")` | Parallel multi-image analysis — accept a list of image sources and run the configured action on each (ThreadPoolExecutor), aggregating results. Useful for processing a folder of screenshots. | P2 |
| `vision(action="detect_objects")` | Object detection with bounding boxes — return `{label, confidence, bbox}` list. Requires a vision model with detection capability (or a separate detector); may need a new `*_JSON_SYSTEM` variant encoding the bbox schema. | P2 |
| `vision(action="count")` | Count specific objects in an image — caller passes a `target_label` (e.g. "people", "cars"); vision returns `{count, items: [{bbox, confidence}]}`. Common follow-up to `detect_objects`. | P3 |
| `vision(action="translate")` | Translate visible text in the image — combines `extract_text` with a translation pass. Returns original text + translated text per block. Useful for OCR of foreign-language signage / documents. | P3 |
| `vision(action="chart_extract")` | Extract data from charts/graphs as structured JSON — bar/line/pie/scatter chart → `{chart_type, axes: {x, y}, series: [{name, points: [...]}]}`. Pairs naturally with `json_schema`. | P3 |
| `vision(action="diagram_to_code")` | Convert UI mockups/diagrams to code — wireframe → HTML/CSS, ER diagram → SQL DDL, flowchart → Mermaid. Likely needs a `target_format` param (html/react/sql/mermaid/plantuml). | P3 |
| `vision(action="accessibility_audit")` | WCAG compliance check for UI screenshots — automated contrast ratio estimation, alt-text gaps, focus-indicator audit, semantic-structure review. Output: structured `{violations: [{criterion, severity, element, fix}]}`. | P3 |
| `streaming` support | Stream vision responses when `complete_with_tools()` is implemented in `core/llm_backend/`. MCP stdio transport can't stream today — this would require gateway-only mode. Useful for large-description feedback during long analyses. | P3 |
| `video_frame_extraction` | Extract key frames from a video file for analysis — accept `file_path` to a `.mp4` / `.mov`, extract N evenly-spaced or scene-change frames, then run `describe`/`extract_text` on each. Likely uses `ffmpeg` subprocess. | P3 |
| `pdf_page_extraction` | Extract images from PDF pages for analysis — accept `file_path` to a `.pdf`, render each page (via `pypdfium2` or `pdf2image`) to PNG, then run a vision action on each. Pairs with `file(read_pdf)` for text+vision combined extraction. | P3 |
| `ocr_fallback` | Fallback to `pytesseract` (or similar local OCR) when the vision model is unavailable (kill-switch fired). Lower quality than the LLM but works offline. Toggled by an env flag (e.g. `VISION_OCR_FALLBACK=true`). | P3 |
| `multi_image_context` | Pass multiple images in one call for comparison/sequence analysis — accept `image_sources: List[Dict]` instead of a single source. Enables "compare these two", "describe this sequence of screenshots", "are these the same person" use cases without needing a dedicated `compare` action. | P3 |
| Remove deprecated `task` param in v2.0 | After `vision_delegate.py` is migrated to `action`+`question` (see In Progress above), remove the `task` parameter from `tools/vision.py` and the deprecation-warning block. Bump the version to v2.0 with a breaking-change entry. | P3 (after delegate migration) |

> **Note for future maintainers:** items in the table above are *suggestions* gathered during v1.0 docs work. Before implementing any of them, re-check the current source (`tools/vision_ops/`), `core/llm/`, and `core/llm_backend/` to confirm prerequisites (e.g. `complete_with_tools()` for streaming, `json_schema` plumbing for structured output, ffmpeg/pytesseract availability) are in place.

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Real-time video analysis** | Requires streaming infrastructure. MCP stdio doesn't support streaming. Re-listed in the Roadmap above for when `complete_with_tools()` lands. | Skip (until gateway mode) |
| 2 | **3D model analysis** | No 3D vision model in current stack. | Skip |
| 3 | **Audio-visual analysis** | Out of scope — use separate audio tool. | Skip |
| 4 | **Configurable system prompts via `.env`** | Static prompts are deliberate for consistency. Per-action prompts via `action`/`question`/`format`/`context_type` params cover the variance surface. | Skip |

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
