<- Back to [Vision Overview](../VISION.md)

# 🗺️ Changelog

## 📝 Version History

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes recorded for pre-v1. Add here as they occur.)*

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

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `@meta_tool` refactor | Add `action` param (`describe`, `extract_text`, `analyse_ui`) with `Literal` validation and auto-generated schema | P0 |
| Un-multiplex | Extract `_do_describe`, `_do_extract_text`, `_do_analyse_ui` into atomic handlers under `vision_ops/actions/` (follow `browser_ops/actions/` pattern) | P0 |
| Test restructure | Add `conftest.py`, split `test_vision.py` into per-concern files: validation, SSRF, file, base64, URL, LLM dispatch, output, integration | P1 |
| Batch image analysis | `action="batch_analyse"` for parallel multi-image processing | P2 |
| Image comparison | `action="compare"` for diffing two images | P2 |
| OCR fallback | Fallback to OCR tool when vision model is unavailable | P2 |
| Video frame extraction | Extract key frames from video for analysis | P3 |
| PDF image extraction | Extract images from PDF pages for analysis | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Real-time video analysis** | Requires streaming infrastructure. MCP stdio doesn't support streaming. | Skip |
| 2 | **3D model analysis** | No 3D vision model in current stack. | Skip |
| 3 | **Audio-visual analysis** | Out of scope — use separate audio tool. | Skip |
| 4 | **Configurable system prompts via `.env`** | Static prompts are deliberate for consistency. Per-task prompts via `task` param. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
