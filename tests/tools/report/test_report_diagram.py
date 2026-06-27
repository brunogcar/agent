"""Tests for diagram builder."""
from pathlib import Path

from tools.report_core import diagrams


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

    def test_build_from_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
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
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = diagrams.build(
            trace_id="test-diagram-dict",
            title="Architecture",
            data={"nodes": [{"id": "A", "label": "API"}], "edges": []},
            config={"diagram_type": "flowchart"},
        )
        assert result["type"] == "diagram"
        assert Path(result["html_path"]).exists()

    def test_build_default_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = diagrams.build(
            trace_id="test-diagram-default",
            title="Default",
            data=None,
            config={},
        )
        assert result["type"] == "diagram"
        assert Path(result["html_path"]).exists()
