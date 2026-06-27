"""Tests for XSS prevention in templates."""
from pathlib import Path

from tools.report_core import html


class TestXssPrevention:
    """Verify user-controlled text is escaped in output HTML."""

    def test_report_text_escaped(self, tmp_path):
        out = tmp_path / "xss_test.html"
        payload = "<script>alert('xss')</script>"
        html.render_template("report.html", {
            "title": "XSS Test",
            "sections": [{"title": "Sec", "text": payload}],
            "kpis": [], "sources": [],
            "theme": "dark", "trace_id": "", "accent": "#0d9488",
        }, out)
        content = out.read_text(encoding="utf-8")
        # The payload in sec.text should be escaped
        assert "&lt;script&gt;" in content

    def test_dashboard_text_escaped(self, tmp_path):
        out = tmp_path / "xss_dash.html"
        payload = "<img src=x onerror=alert(1)>"
        html.render_template("dashboard.html", {
            "title": "XSS Dash",
            "tabs": [{"title": "Tab1", "text": payload}],
            "kpis": [], "charts": [], "columns": 2,
            "theme": "dark", "trace_id": "", "accent": "#0d9488",
        }, out)
        content = out.read_text(encoding="utf-8")
        assert "&lt;img" in content

    def test_diagram_mermaid_escaped(self, tmp_path):
        out = tmp_path / "xss_diagram.html"
        payload = "flowchart TD\n A[<script>alert(1)</script>] --> B[End]"
        html.render_template("diagram.html", {
            "title": "XSS Diagram",
            "mermaid_src": payload,
            "theme": "dark", "accent": "#0d9488",
        }, out)
        content = out.read_text(encoding="utf-8")
        # Find the mermaid div content — should be escaped
        # The payload appears inside <div class="mermaid">...</div>
        import re
        mermaid_match = re.search(r'<div class="mermaid">(.*?)</div>', content, re.DOTALL)
        assert mermaid_match is not None
        mermaid_content = mermaid_match.group(1)
        assert "<script>" not in mermaid_content
        assert "&lt;script&gt;" in mermaid_content

    def test_collapsible_content_escaped(self, tmp_path):
        out = tmp_path / "xss_collapsible.html"
        payload = "<iframe src='evil.com'></iframe>"
        # Use report.html which uses macros that may include collapsible
        html.render_template("report.html", {
            "title": "XSS Collapsible",
            "sections": [{"title": "Sec", "text": payload}],
            "kpis": [], "sources": [],
            "theme": "dark", "trace_id": "", "accent": "#0d9488",
        }, out)
        content = out.read_text(encoding="utf-8")
        assert "&lt;iframe" in content
