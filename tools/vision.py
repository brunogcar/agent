"""
tools/vision.py — Vision meta-tool. Registered via @tool so MCP auto-discovers it.
The LLM sees ONE tool: vision(task, file_path, url=...)
Provide exactly ONE image source: file_path, base64, or url.

DESIGN DECISIONS
Registered with @tool (not in skills/) so MCP server discovers it at startup.
Uses llm.call() directly because it needs multimodal messages.
JSON mode uses llm.call()'s built-in parsing (response_format + fence stripping)
rather than duplicating the logic.
URL sources are automatically downloaded and converted to a data URI, ensuring
compatibility with LM Studio even if it doesn't accept raw HTTP URLs.
SSRF protection blocks localhost and private IP ranges.
"""
from __future__ import annotations

import base64 as _b64
import ipaddress
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from registry import tool
from core.config import cfg
from core.llm import llm
from core.tracer import tracer


# ── Constants ────────────────────────────────────────────────────────────────
HTTP_TIMEOUT = 30.0  # seconds
MAX_IMAGE_BYTES = int(os.environ.get("VISION_MAX_FILE_BYTES", 20_000_000))
MAX_BASE64_LEN = int(os.environ.get("VISION_MAX_BASE64_LEN", 10_000_000))


# ── System prompts ───────────────────────────────────────────────────────────
_VISION_SYSTEM = """
You are a precise visual analysis specialist.
Describe ONLY what is visible — never hallucinate details.
Structure your response:
Overview: one sentence summary
Key Elements: list of main visible components
Text Content: any readable text, or "none"
Notable Details: patterns, colours, anomalies
"""

_VISION_JSON_SYSTEM = """
You are a precise visual analysis specialist. Output ONLY valid JSON — no prose, no markdown fences.
{
 "overview": "one sentence",
 "elements": ["visible", "elements"],
 "text_content": "readable text or null",
 "colors": ["dominant", "colors"],
 "details": "patterns or anomalies",
 "confidence": "high|medium|low"
}
"""


# ── SSRF Protection ─────────────────────────────────────────────────────────
def _is_private_or_localhost(hostname: str) -> bool:
    """Block by network scope. Respects ALLOWED_INTERNAL_HOSTS allowlist."""
    hostname = hostname.lower().strip()
    
    # Handle IPv6 with port: [::1]:8080 → ::1
    if hostname.startswith("[") and "]:" in hostname:
        hostname = hostname.split("]:")[0].lstrip("[")
    # Handle IPv4 with port: 127.0.0.1:3000 → 127.0.0.1
    # But NOT IPv6 without brackets (like ::1) - don't strip colons from IPv6
    elif ":" in hostname and not hostname.startswith("[") and "::" not in hostname:
        hostname = hostname.split(":")[0]
    
    if hostname in cfg.allowed_internal_hosts:
        return False
    if hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    if hostname.endswith((".local", ".test", ".localhost", ".invalid")):
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        pass
    return False


# ── Validation ───────────────────────────────────────────────────────────────
def _validate_vision_inputs(file_path: str, base64_str: str, url: str) -> tuple[bool, str]:
    """
    Validate that exactly one image source is provided and perform safety checks.
    Returns: (is_valid, error_message)
    """
    sources = [s for s in [file_path, base64_str, url] if s and s.strip()]
    if len(sources) == 0:
        return False, "Exactly one image source (file_path, base64, or url) is required."
    if len(sources) > 1:
        return False, "Provide exactly ONE image source, not multiple."
        
    if url:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return False, "Invalid URL: missing hostname"
        # SSRF Protection: Network-scope blocking + allowlist
        if _is_private_or_localhost(hostname):
            tracer.warning("SSRF", {"action": "blocked", "url": url, "hostname": hostname, "reason": "private_network"})
            return False, f"SSRF blocked: {url} points to private/localhost network"
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed."
            
    if file_path:
        p = Path(file_path)
        if not p.exists():
            return False, f"File not found: {file_path}"
        if not p.is_file():
            return False, f"Not a file: {file_path}"
        if p.stat().st_size > MAX_IMAGE_BYTES:
            return False, f"File too large ({p.stat().st_size} bytes, max {MAX_IMAGE_BYTES})."
            
    if base64_str:
        if len(base64_str) > MAX_BASE64_LEN:
            return False, f"Base64 string too long ({len(base64_str)} chars, max {MAX_BASE64_LEN})."

    return True, ""


# ── Image helpers ────────────────────────────────────────────────────────────
_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
    ".gif": "image/gif",  ".bmp":  "image/bmp",
}

def _file_to_block(file_path: str) -> tuple[dict, str]:
    """Read local file → OpenAI image_url content block. Returns (block, error)."""
    p = Path(file_path)
    mime = _MIME_MAP.get(p.suffix.lower(), "image/jpeg")
    if not _MIME_MAP.get(p.suffix.lower()):
        print(f"[vision] Unknown extension {p.suffix}, defaulting to image/jpeg", file=sys.stderr)
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

def _download_image_to_data_uri(url: str, timeout: float = HTTP_TIMEOUT) -> tuple[str, str]:
    """
    Download an image from a URL and return a data URI.
    Returns (data_uri, error) where error is "" on success.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
    except httpx.TimeoutException:
        return "", f"Timeout downloading image from {url} (>{timeout}s)"
    except httpx.HTTPStatusError as e:
        return "", f"HTTP error {e.response.status_code} downloading image."
    except Exception as e:
        return "", f"Download error: {e}"
    content_type = resp.headers.get("content-type", "image/jpeg")
    if not content_type.startswith("image/"):
        suffix = Path(url.split("?")[0]).suffix.lower()
        content_type = _MIME_MAP.get(suffix, "image/jpeg")

    b64 = _b64.b64encode(resp.content).decode("utf-8")
    return f"data:{content_type};base64,{b64}", ""


# ── Tool ─────────────────────────────────────────────────────────────────────
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
    """
    # Guard: model must be configured
    if not cfg.vision_model:
        return {
            "status": "error",
            "error":  "VISION_MODEL not set in .env — add it to your .env file",
            "trace_id": trace_id,
        }

    # 1. Input Validation & SSRF Protection
    is_valid, err = _validate_vision_inputs(file_path, base64, url)
    if not is_valid:
        tracer.error(trace_id, "vision", f"Validation failed: {err}")
        return {"status": "error", "error": err, "trace_id": trace_id}

    # 2. Build image content block
    if file_path:
        img_block, err = _file_to_block(file_path)
    elif base64:
        img_block, err = _b64_to_block(base64, mime_type)
    elif url:
        data_uri, err = _download_image_to_data_uri(url)
        if err:
            return {"status": "error", "error": err, "trace_id": trace_id}
        img_block, err = _b64_to_block(data_uri, mime_type)
        
    if err:
        return {"status": "error", "error": err, "trace_id": trace_id}

    # 3. Build multimodal messages
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

    # 4. Call vision role
    try:
        result = llm.call(
            role="vision",
            messages=messages,
            json_mode=json_mode,
            trace_id=trace_id,
        )
    except Exception as e:
        tracer.error(trace_id, "vision", f"LLM call failed: {e}")
        return {"status": "error", "error": f"Vision model call failed: {e}", "trace_id": trace_id}

    if not result.ok:
        return {
            "status":   "error",
            "error":   result.error,
            "model":   result.model,
            "elapsed": result.elapsed,
            "trace_id": trace_id,
        }

    response: dict = {
        "status":   "success",
        "text":    result.text,
        "model":   result.model,
        "elapsed": result.elapsed,
        "usage":   result.usage,
        "trace_id": trace_id,
    }

    if json_mode:
        response["parsed"] = result.parsed or {}
        if not result.parsed:
            response["parse_warning"] = "LLM response was not valid JSON. Check response.text."

    return response