"""Tests for map builder."""
from pathlib import Path

from tools.report_ops import maps


class TestMapBuilder:
    """Leaflet.js map builders."""

    def test_build_creates_html(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = maps.build(
            trace_id="test-map",
            title="Locations",
            data=[{"lat": -15.78, "lon": -47.93, "label": "Brasilia"}],
            config={"zoom": 6},
        )
        assert result["type"] == "map"
        assert result["title"] == "Locations"
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Locations" in content
        assert "leaflet" in content.lower()

    def test_build_default_center(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        result = maps.build(
            trace_id="test-map-default",
            title="Default",
            data=[],
            config={},
        )
        assert result["type"] == "map"
        assert Path(result["html_path"]).exists()

    def test_build_with_data_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_ops.paths.cfg.workspace_root", tmp_path)
        # Create a JSON data file
        data_file = tmp_path / "map_data.json"
        data_file.write_text("[{\"lat\":0,\"lon\":0}]", encoding="utf-8")
        result = maps.build(
            trace_id="test-map-file",
            title="From File",
            data=None,
            config={"data_path": str(data_file)},
        )
        assert result["type"] == "map"
        assert Path(result["html_path"]).exists()
