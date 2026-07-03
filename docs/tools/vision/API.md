<- Back to [Vision Overview](../VISION.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
def vision(
    task:       str  = "Describe this image in detail.",
    file_path:  str  = "",
    base64:     str  = "",
    url:        str  = "",
    mime_type:  str  = "image/jpeg",
    json_mode:  bool = False,
    context:    str  = "",
    trace_id:   str  = "",
) -> dict:
    """Analyse an image using the vision model (cfg.vision_model).
    Provide exactly ONE of: file_path, base64, or url.
    """
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task` | `str` | No | `"Describe this image in detail."` | The analysis instruction sent to the vision model |
| `file_path` | `str` | No | `""` | Local file path to the image |
| `base64` | `str` | No | `""` | Base64-encoded image data |
| `url` | `str` | No | `""` | HTTP(S) URL to the image |
| `mime_type` | `str` | No | `"image/jpeg"` | MIME type for base64 inputs. Auto-detected for file_path. |
| `json_mode` | `bool` | No | `False` | Return structured JSON output with schema |
| `context` | `str` | No | `""` | Additional background text prepended to the task |
| `trace_id` | `str` | No | `""` | Trace identifier for observability |

**Input rule:** Exactly one of `file_path`, `base64`, or `url` must be provided. Zero or multiple sources are rejected.

---

## ⚡ Input Validation

| Check | Behavior |
|-------|----------|
| **Zero sources** | Error: `"Exactly one image source (file_path, base64, or url) is required."` |
| **Multiple sources** | Error: `"Provide exactly ONE image source, not multiple."` |
| **URL SSRF** | `is_safe_network_address(hostname)` blocks localhost/private IPs. Error: `"SSRF blocked: {url} points to private/localhost network"` |
| **URL scheme** | Only `http`/`https` allowed. Error: `"Invalid URL scheme: {scheme}. Only http/https allowed."` |
| **File not found** | Error: `"File not found: {file_path}"` |
| **File too large** | Error: `"File too large ({size} bytes, max {MAX_IMAGE_BYTES})."` |
| **Base64 too long** | Error: `"Base64 string too long ({len} chars, max {MAX_BASE64_LEN})."` |

---

## 📤 Output

### Success (standard mode)
```json
{
  "status": "success",
  "text": "Overview: A dashboard showing sales metrics...",
  "model": "gpt-4o",
  "elapsed": 2.34,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150},
  "trace_id": "abc123"
}
```

### Success (json_mode)
```json
{
  "status": "success",
  "text": "{\"overview\": \"...\", \"elements\": [...]}",
  "parsed": {
    "overview": "A dashboard showing sales metrics",
    "elements": ["chart", "table", "filter bar"],
    "text_content": "Q3 Revenue: $1.2M",
    "colors": ["blue", "green", "white"],
    "details": "Line chart shows upward trend",
    "confidence": "high"
  },
  "parse_warning": null,
  "model": "gpt-4o",
  "elapsed": 2.34,
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150},
  "trace_id": "abc123"
}
```

> `parse_warning` is present (with message) when `json_mode=True` but the LLM response was not valid JSON.

### Error (VISION_MODEL unset)
```json
{
  "status": "error",
  "error": "VISION_MODEL not set in .env — add it to your .env file",
  "trace_id": "abc123"
}
```

### Error (validation)
```json
{
  "status": "error",
  "error": "SSRF blocked: http://localhost/image.png points to private/localhost network",
  "trace_id": "abc123"
}
```

### Error (LLM call failed)
```json
{
  "status": "error",
  "error": "Vision model call failed: <exception>",
  "model": "gpt-4o",
  "elapsed": 0.0,
  "trace_id": "abc123"
}
```

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **SSRF protection** | `is_safe_network_address(hostname)` blocks localhost, private IP ranges, and link-local addresses before any HTTP request |
| **URL scheme validation** | Only `http`/`https` allowed. Rejects `file://`, `ftp://`, etc. |
| **File size limits** | `VISION_MAX_FILE_BYTES` (20MB default) prevents memory exhaustion |
| **Base64 length limits** | `VISION_MAX_BASE64_LEN` (10M chars default) prevents memory exhaustion |
| **No local FS access beyond image read** | Only reads the specified file path. No directory traversal. |
| **Kill-switch** | Returns clear error if `cfg.vision_model` is unset — no network call |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
