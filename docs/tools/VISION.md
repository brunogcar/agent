# 👁️ Vision Tool

The `vision()` tool provides **multimodal image analysis** using a dedicated vision model. It accepts images via local file path, base64 string, or URL, and returns structured text analysis.

**Key characteristics:**
- **Multimodal LLM dispatch** — Routes to `cfg.vision_model` via `llm.call(role="vision")`
- **Three input sources** — `file_path`, `base64`, or `url` (exactly one required)
- **SSRF protection** — `is_safe_network_address()` blocks localhost and private IP ranges for URL inputs
- **JSON mode** — Structured output with schema validation via `json_mode=True`
- **Context support** — Optional `context` parameter for additional background information
- **Kill-switch ready** — Returns clear error if `VISION_MODEL` is unset

---

## 🚀 Quick Start

```python
# Analyse a local image
vision(task="Describe this image in detail.", file_path="screenshot.png")

# Analyse an image from URL
vision(task="What text is visible?", url="https://example.com/chart.png")

# Structured JSON output
vision(task="Extract all visible text.", file_path="document.png", json_mode=True)

# With context
vision(
    task="Is this UI accessible?",
    file_path="ui.png",
    context="This is a login form for a financial app."
)
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `vision_model` | `cfg.vision_model` | — | Vision-capable model name (e.g., `gpt-4o`, `claude-3-opus`). **Required.** |
| `VISION_MAX_FILE_BYTES` | Environment | 20,000,000 | Max file size for local images (20MB) |
| `VISION_MAX_BASE64_LEN` | Environment | 10,000,000 | Max base64 string length (10M chars) |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Analyse image content | `vision` | Multimodal LLM for visual understanding |
| Extract text from image | `vision` (with `json_mode`) | Structured text extraction |
| UI/UX review | `vision` (with `context`) | Visual + contextual analysis |
| Read image metadata | `file(get_file_info)` | Fast, no LLM cost |
| Convert image format | `file` operations | File system, no LLM |
| Simple image resize | External tool | Not a vision task |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](vision/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](vision/API.md) | Full tool signature, input validation, output format, security |
| [CHANGELOG.md](vision/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](vision/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
