"""Read media file action handler — returns base64-encoded binary data.

TODO: Integrate with vision.py when the vision pipeline is fully implemented.
For now, returns base64-encoded binary data with MIME type detection.
"""

from __future__ import annotations

import base64
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
}


@register_action(
    "file",
    "read_media_file",
    help_text="""Read a binary file (image, audio, video) and return base64-encoded data with MIME type.
TODO: Integrate with vision.py when vision pipeline is fully implemented.
Required: path
Returns: {data (base64), mime_type, type, size}""",
    examples=[
        'file(action="read_media_file", path="image.png")',
    ],
)
def _handle_read_media_file(path: str = "", trace_id: str = "", **kwargs) -> dict:
    """Read a binary file and return base64-encoded data with MIME type."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}
    if not p.is_file():
        return {"status": "error", "error": f"Not a file: {p}"}

    ext = p.suffix.lower()
    mime_type = MIME_TYPES.get(ext, "application/octet-stream")

    type_category = "blob"
    if mime_type.startswith("image/"):
        type_category = "image"
    elif mime_type.startswith("audio/"):
        type_category = "audio"
    elif mime_type.startswith("video/"):
        type_category = "video"

    try:
        data = p.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        return {
            "status": "success",
            "path": str(p),
            "data": encoded,
            "mime_type": mime_type,
            "type": type_category,
            "size": len(data),
        }
    except Exception as e:
        return {"status": "error", "error": f"Media read failed: {e}"}
