"""
tools/vision.py — Vision meta-tool. Registered via @tool so MCP auto-discovers it.

The LLM sees ONE tool: vision(task, file_path, url=...)

Provide exactly ONE image source: file_path, base64, or url.

DESIGN DECISIONS
----------------
- Registered with @tool (not in skills/) so MCP server discovers it at startup.
- Uses llm.call() directly because it needs multimodal messages.
- JSON mode uses llm.call()'s built-in parsing (response_format + fence stripping)
  rather than duplicating the logic.
- URL sources are automatically downloaded and converted to a data URI, ensuring
  compatibility with LM Studio even if it doesn't accept raw HTTP URLs.
"""

from __future__ import annotations

import base64 as _b64
import os
import sys
from pathlib import Path
from typing import Optional

import httpx

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


# ── Image helpers ─────────────────────────────────────────────────────────────

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

    # ── File size guard (default 20 MB, configurable via env) ──
    max_bytes = int(os.environ.get("VISION_MAX_FILE_BYTES", 20_000_000))
    if p.stat().st_size > max_bytes:
        return {}, f"File too large ({p.stat().st_size} bytes, max {max_bytes})"

    mime = _MIME_MAP.get(p.suffix.lower(), "image/jpeg")
    if not _MIME_MAP.get(p.suffix.lower()):
        print(f"[vision] Unknown extension {p.suffix}, defaulting to image/jpeg",
              file=sys.stderr)

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


def _download_image_to_data_uri(url: str, timeout: int = 15) -> tuple[str, str]:
    """
    Download an image from a URL and return a data URI.
    Returns (data_uri, error) where error is "" on success.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
    except httpx.TimeoutException:
        return "", f"Timeout downloading image from {url}"
    except Exception as e:
        return "", f"Download error: {e}"

    content_type = resp.headers.get("content-type", "image/jpeg")
    if not content_type.startswith("image/"):
        suffix = Path(url.split("?")[0]).suffix.lower()
        content_type = _MIME_MAP.get(suffix, "image/jpeg")

    b64 = _b64.b64encode(resp.content).decode("utf-8")
    return f"data:{content_type};base64,{b64}", ""


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
    url        : public image URL (http/https) — automatically downloaded
                 and converted to a data URI for maximum compatibility.
    mime_type  : MIME type when using base64 (default: image/jpeg)
    json_mode  : if True, return structured JSON in result.parsed
    context    : optional background context injected before the image
    trace_id   : attach to workflow trace

    Returns:
        {status, text, model, elapsed, usage}               — text mode
        {status, text, parsed, model, elapsed, usage}       — json_mode=True

    Examples:
        vision(task="What errors are shown?", file_path="workspace/screenshot.png")
        vision(task="Extract all numbers from this chart.",
               url="https://example.com/chart.png", json_mode=True)
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
        # ── Base64 length guard (default 10 MB chars, configurable via env) ──
        max_b64_len = int(os.environ.get("VISION_MAX_BASE64_LEN", 10_000_000))
        if len(base64) > max_b64_len:
            return {
                "status": "error",
                "error": f"Base64 string too long ({len(base64)} chars, max {max_b64_len})",
            }
        img_block, err = _b64_to_block(base64, mime_type)
    elif url:
        data_uri, err = _download_image_to_data_uri(url)
        if err:
            return {"status": "error", "error": err}
        img_block, err = _b64_to_block(data_uri, mime_type)
    else:
        return {"status": "error", "error": "Provide one of: file_path, base64, or url"}

    if err:
        return {"status": "error", "error": err}

    # Build multimodal messages — image block + text prompt in same user turn
    system = _VISION_JSON_SYSTEM if json_mode else _VISION_SYSTEM
    user_content: list[dict] = []
    if context:
        user_content.append({"type": "text", "text": f"Context: {context}\n\n"})
    user_content.append(img_block)
    user_content.append({"type": "text", "text": task})

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ]

    # Call vision role — json_mode is handled by llm.call() internally
    result = llm.call(
        role="vision",
        messages=messages,
        json_mode=json_mode,
        trace_id=trace_id,
    )

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

    if json_mode:
        response["parsed"] = result.parsed or {}
        if not result.parsed:
            response["parse_warning"] = "LLM response was not valid JSON. Check response.text."

    return response