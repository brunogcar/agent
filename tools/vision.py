"""
tools/vision.py — Vision meta-tool. Registered via @tool so MCP auto-discovers it.

The LLM sees ONE tool: vision(task, file_path, url=...)

Provide exactly ONE image source: file_path, base64, or url (base64 encoded).

DESIGN DECISIONS
----------------
- Registered with @tool (not in skills/) so MCP server discovers it at startup.
- Uses llm.call() directly instead of llm.complete() for multimodal messages.
- Image input convention:
    file_path — local file, auto base64-encoded (most common)
    base64    — pre-encoded string (required by some models)
    url       — base64-encoded image data (LM Studio expects this format)

Note: LM Studio's vision API expects base64 in the 'url' field, not HTTP URLs.
To use external URLs, convert them to base64 or download locally first.
"""

from __future__ import annotations

import base64 as _b64
from pathlib import Path

from registry import tool
from core.config import cfg
from core.llm import llm


# ── System prompts ────────────────────────────────────────────────────────────

_VISION_SYSTEM = """\
You are a precise visual analysis specialist.
Describe ONLY what is visible — never hallucinate details.
Structure your response:
  Overview: one sentence summary
  Key Elements: list of main visible components
  Text Content: any readable text, or "none"
  Notable Details: patterns, colours, anomalies"""

_VISION_JSON_SYSTEM = """\
You are a precise visual analysis specialist. Output ONLY valid JSON — no prose, no markdown fences.
{
  "overview": "one sentence",
  "elements": ["visible", "elements"],
  "text_content": "readable text or null",
  "colors": ["dominant", "colors"],
  "details": "patterns or anomalies",
  "confidence": "high|medium|low"
}"""


# ── Image helpers ─────────────────────────────────────────────────────────────_

_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
    ".gif": "image/gif",  ".bmp":  "image/bmp",
}


def _file_to_block(file_path: str) -> tuple[dict, str]:
    """Read local file → OpenAI image_url content block. Returns (block, error)."""
    p = Path(file_path)
    if not p.exists():
        return {}, f"File not found: {file_path}"
    if not p.is_file():
        return {}, f"Not a file: {file_path}"
    mime = _MIME_MAP.get(p.suffix.lower(), "image/jpeg")
    try:
        data = _b64.b64encode(p.read_bytes()).decode("utf-8")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}, ""
    except Exception as e:
        return {}, f"Read error: {e}"


def _b64_to_block(b64_str: str, mime_type: str) -> tuple[dict, str]:
    """Base64 string → OpenAI image_url content block."""
    if b64_str.startswith("data:"):
        return {"type": "image_url", "image_url": {"url": b64_str}}, ""
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_str}"}}, ""


def _url_to_block(url: str) -> tuple[dict, str]:
    """Public URL → OpenAI image_url content block (for models that accept raw URLs)."""
    if not url.startswith(("http://", "https://")):
        return {}, f"URL must start with http:// or https://. Got: {url}"
    # LM Studio typically accepts the raw URL directly in some implementations
    # But some versions require base64 - check which works first
    return {"type": "image_url", "image_url": {"url": url}}, ""


# ── Tool ──────────────────────────────────────────────────────────────────────

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
    """
    Analyse an image using the vision model (cfg.vision_model).

    Provide exactly ONE of: file_path, base64, or url.

    task       : what to ask about the image (default: full description)
    file_path  : path to a local image file — auto base64-encoded
    base64     : already base64-encoded image string (or data URI)
    url        : public image URL (http/https) — some models accept this directly
    mime_type  : MIME type when using base64 (default: image/jpeg)
    json_mode  : if True, return structured JSON in result.parsed
    context    : optional background context injected before the image
    trace_id   : attach to workflow trace

    Returns:
        {status, text, model, elapsed, usage}               — text mode
        {status, text, parsed, model, elapsed, usage}       — json_mode=True

    Examples:
        vision(task="What errors are shown?", file_path="workspace/screenshot.png")
        vision(task="Extract all numbers from this chart.", url="https://example.com/chart.png", json_mode=True)
        vision(task="Read all text in this image.", base64="...", mime_type="image/png")
    """
    # Guard: model must be configured
    if not cfg.vision_model:
        return {
            "status": "error",
            "error":  "VISION_MODEL not set in .env — add: VISION_MODEL=qwen/qwen3.5-9b",
        }

    # Build image content block from whichever source was provided
    if file_path:
        img_block, err = _file_to_block(file_path)
    elif base64:
        img_block, err = _b64_to_block(base64, mime_type)
    elif url:
        img_block, err = _url_to_block(url)
    else:
        return {"status": "error", "error": "Provide one of: file_path, base64, or url"}

    if err:
        return {"status": "error", "error": err}

    # Build multimodal messages — image block + text prompt in same user turn
    system = _VISION_JSON_SYSTEM if json_mode else _VISION_SYSTEM
    user_content: list[dict] = []
    if context:
        user_content.append({"type": "text", "text": f"Context: {context}\n\n"})
    # Add image block - it has 'type': 'image_url' and 'image_url' keys
    user_content.append(img_block)
    user_content.append({"type": "text", "text": task})

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ]

    # Call vision role — resolves to cfg.vision_model via _build_role_configs()
    result = llm.call(role="vision", messages=messages, trace_id=trace_id)

    if not result.ok:
        return {
            "status":  "error",
            "error":   result.error,
            "model":   result.model,
            "elapsed": result.elapsed,
        }

    response: dict = {
        "status":  "success",
        "text":    result.text,
        "model":   result.model,
        "elapsed": result.elapsed,
        "usage":   result.usage,
    }

    # Parse JSON response if json_mode was requested
    if json_mode:
        import json as _json
        import re as _re
        clean = result.text.strip()
        for fence in ("```json", "```"):
            if clean.startswith(fence):
                clean = clean[len(fence):]
        clean = clean.strip().rstrip("`").strip()
        m = _re.search(r"\{.*\}", clean, _re.DOTALL)
        if m:
            clean = m.group(0)
        try:
            response["parsed"] = _json.loads(clean)
        except _json.JSONDecodeError:
            response["parsed"]       = {}
            response["parse_warning"] = "Response was not valid JSON. Check response.text."

    return response
