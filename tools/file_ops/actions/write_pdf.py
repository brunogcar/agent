"""
Write PDF action handler.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action("file", "write_pdf")
def _handle_write_pdf(path: str = "", content: str = "", title: str = "", max_chars: int = 50_000, trace_id: str = "") -> dict:
    """Write text to PDF using fpdf2."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not content:
        return {"status": "error", "error": "content is required for write_pdf"}
    if p.suffix.lower() != ".pdf":
        p = p.with_suffix(".pdf")

    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        if title:
            pdf.set_title(title)
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 12, title, ln=True)
            pdf.ln(4)

        pdf.set_font("Helvetica", size=11)

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                pdf.set_font("Helvetica", "B", 14)
                pdf.ln(3)
                from fpdf import XPos, YPos
                pdf.cell(0, 9, stripped[3:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_font("Helvetica", size=11)
            elif stripped.startswith("# "):
                pdf.set_font("Helvetica", "B", 16)
                pdf.ln(4)
                pdf.cell(0, 10, stripped[2:], ln=True)
                pdf.set_font("Helvetica", size=11)
            elif stripped.startswith("### "):
                pdf.set_font("Helvetica", "B", 12)
                pdf.ln(2)
                pdf.cell(0, 8, stripped[4:], ln=True)
                pdf.set_font("Helvetica", size=11)
            elif stripped in ("---", "***"):
                pdf.ln(2)
                pdf.line(pdf.l_margin, pdf.get_y(),
                         pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(2)
            elif not stripped:
                pdf.ln(4)
            else:
                pdf.multi_cell(0, 6, line)

        p.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(p))
        return {
            "status": "success",
            "path":   str(p),
            "pages":  pdf.page,
            "size":   p.stat().st_size,
        }
    except ImportError:
        return {"status": "error", "error": "fpdf2 not installed. Run: pip install fpdf2"}
    except Exception as e:
        return {"status": "error", "error": f"PDF write failed: {type(e).__name__}: {e}"}