"""
Read PDF action handler.
"""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action("file", "read_pdf")
def _handle_read_pdf(path: str = "", max_chars: int = 50_000) -> dict:
    """Extract text from a PDF file using pdfplumber."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}
    if p.suffix.lower() != ".pdf":
        return {"status": "error", "error": f"Not a PDF file: {p.name}"}

    try:
        import pdfplumber

        pages_text = []
        with pdfplumber.open(str(p)) as pdf:
            total_pages = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(text)

        full_text = "\n\n".join(pages_text)
        truncated = len(full_text) > max_chars
        if truncated:
            full_text = full_text[:max_chars] + f"\n\n[...truncated — {total_pages} pages total]"

        return {
            "status":    "success",
            "path":      str(p),
            "text":      full_text,
            "pages":     total_pages,
            "truncated": truncated,
            "word_count": len(full_text.split()),
        }
    except ImportError:
        return {"status": "error", "error": "pdfplumber not installed. Run: pip install pdfplumber"}
    except Exception as e:
        return {"status": "error", "error": f"PDF read failed: {type(e).__name__}: {e}"}