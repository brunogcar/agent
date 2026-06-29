"""Tests for diagram builder."""
from pathlib import Path

import pytest

from tools.report_ops import diagrams


class TestDiagramBuilder:
    """Mermaid.js diagram builders."""

    def test_dict_to_mermaid(self):
        src = diagrams._dict_to_mermaid({
            "nodes": [{"id": "A", "label": "Start"}, {"id": "B", "label": "End"}],
            "edges": [{"from": "A", "to": "B"}]
        }, "flowchart")
        assert "A[Start]" in src
        assert "B[End]" in src
        assert "A --> B" in src

    def test_dict_to_mermaid_with_labels(self):
        src = diagrams._dict_to_mermaid({
            "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
            "edges": [{"from": "A", "to": "B", "label": "yes"}]
        }, "flowchart")
        assert "A -->|yes| B" in src

    def test_dict_to_mermaid_escapes_html(self):
        """Labels with HTML tags are escaped in _dict_to_mermaid."""
        src = diagrams._dict_to_mermaid({
            "nodes": [{"id": "A", "label": "<script>alert(1)</script>"}],
            "edges": []
        }, "flowchart")
        assert "<script>" not in src
        assert "&lt;script&gt;" in src

    def test_sanitize_mermaid_strips_script_tags(self):
        """Standalone <script> tags are stripped from raw mermaid strings."""
        raw = "flowchart TD\n A[Start]\n<script>alert(1)</script>\n B[End]"
        sanitized = diagrams._sanitize_mermaid(raw)
        assert "<script>" not in sanitized
        assert "alert(1)" not in sanitized
        assert "A[Start]" in sanitized
        assert "B[End]" in sanitized

    def test_sanitize_mermaid_strips_iframes(self):
        raw = "flowchart TD\n A[Start]\n<iframe src='evil.com'></iframe>\n B[End]"
        sanitized = diagrams._sanitize_mermaid(raw)
        assert "<iframe>" not in sanitized
        assert "evil.com" not in sanitized

    def test_sanitize_mermaid_strips_event_handlers(self):
        raw = "flowchart TD\n A[Start] onerror=alert(1)\n B[End]"
        sanitized = diagrams._sanitize_mermaid(raw)
        assert "onerror" not in sanitized
        assert "alert(1)" not in sanitized

    def test_sanitize_mermaid_strips_javascript_urls(self):
        raw = "flowchart TD\n A[<a href='javascript:alert(1)'>Link</a>]"
        sanitized = diagrams._sanitize_mermaid(raw)
        assert "javascript:" not in sanitized

    def test_sanitize_mermaid_preserves_mermaid_syntax(self):
        """Mermaid arrows and brackets are preserved."""
        raw = "flowchart TD\n A[Node A] -->|label| B[Node B]"
        sanitized = diagrams._sanitize_mermaid(raw)
        assert "A[Node A]" in sanitized
        assert "-->" in sanitized
        assert "|label|" in sanitized

    def test_build_from_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = diagrams.build(
            trace_id="test-diagram",
            title="Flow",
            data="flowchart TD\n A[Start] --> B[End]",
            config={},
        )
        assert result["type"] == "diagram"
        assert result["diagram_type"] == "flowchart"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Flow" in content
        assert "mermaid" in content.lower()

    def test_build_from_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = diagrams.build(
            trace_id="test-diagram-dict",
            title="Architecture",
            data={"nodes": [{"id": "A", "label": "API"}], "edges": []},
            config={"diagram_type": "flowchart"},
        )
        assert result["type"] == "diagram"
        assert Path(result["html_path"]).exists()

    def test_build_default_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = diagrams.build(
            trace_id="test-diagram-default",
            title="Default",
            data=None,
            config={},
        )
        assert result["type"] == "diagram"
        assert Path(result["html_path"]).exists()
