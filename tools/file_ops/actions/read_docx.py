"""Read DOCX action handler."""

from __future__ import annotations

import re as _re
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "read_docx",
    help_text="""Read a DOCX file using python-docx. Returns structured text with headings, paragraphs, tables.
Required: path
Optional: max_chars (default 50000)
Returns: {text, sections, tables, paragraphs, truncated}""",
    examples=[
        'file(action="read_docx", path="report.docx")',
    ],
)
def _handle_read_docx(path: str = "", max_chars: int = 50_000, trace_id: str = "", **kwargs) -> dict:
    """Read a DOCX file using python-docx."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}
    if p.suffix.lower() != ".docx":
        return {"status": "error", "error": f"Not a .docx file: {p.name}"}

    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        doc = Document(str(p))
        sections = []
        tables = []

        for elem in doc.element.body:
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

            if tag == "p":
                para = Paragraph(elem, doc)
                text = para.text.strip()
                style = para.style.name if para.style else ""
                if not text:
                    continue
                if style.startswith("Heading"):
                    level = style.replace("Heading ", "").strip()
                    sections.append({"type": "heading", "level": level, "text": text})
                else:
                    sections.append({"type": "paragraph", "text": text})

            elif tag == "tbl":
                tbl = Table(elem, doc)
                rows = []
                for row in tbl.rows:
                    rows.append([c.text.strip() for c in row.cells])
                tables.append(rows)
                sections.append({"type": "table", "rows": rows})

        flat = "\n".join(
            ("#" * int(s.get("level", 1)) + " " + s["text"])
            if s["type"] == "heading"
            else s["text"]
            if s["type"] == "paragraph"
            else "[TABLE: " + " | ".join(s["rows"][0]) + " ...]"
            if s["type"] == "table" and s["rows"]
            else ""
            for s in sections
        ).strip()

        truncated = len(flat) > max_chars
        if truncated:
            flat = flat[:max_chars] + f"\n\n[...truncated]"

        return {
            "status": "success",
            "path": str(p),
            "text": flat,
            "sections": sections,
            "tables": len(tables),
            "paragraphs": len([s for s in sections if s["type"] == "paragraph"]),
            "truncated": truncated,
        }
    except ImportError:
        return {"status": "error", "error": "python-docx not installed. Run: pip install python-docx"}
    except Exception as e:
        return {"status": "error", "error": f"DOCX read failed: {type(e).__name__}: {e}"}
