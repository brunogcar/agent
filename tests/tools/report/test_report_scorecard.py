"""Tests for scorecard builder."""
from pathlib import Path

import pytest

from tools.report_core import scorecard


class TestScorecard:
    """RAG status dashboard builder."""

    def test_rag_status_green(self):
        assert scorecard._rag_status(95, 90) == "green"
        assert scorecard._rag_status(90, 90) == "green"

    def test_rag_status_amber(self):
        assert scorecard._rag_status(75, 90) == "amber"
        assert scorecard._rag_status(72, 90) == "amber"

    def test_rag_status_red(self):
        assert scorecard._rag_status(50, 90) == "red"
        assert scorecard._rag_status(0, 90) == "red"

    def test_rag_status_zero_target(self):
        assert scorecard._rag_status(0, 0) == "green"
        assert scorecard._rag_status(1, 0) == "red"

    def test_rag_color_dark(self):
        assert scorecard._rag_color("green", "dark") == "#22c55e"
        assert scorecard._rag_color("amber", "dark") == "#f59e0b"
        assert scorecard._rag_color("red", "dark") == "#ef4444"

    def test_rag_color_light(self):
        assert scorecard._rag_color("green", "light") == "#16a34a"
        assert scorecard._rag_color("amber", "light") == "#d97706"
        assert scorecard._rag_color("red", "light") == "#dc2626"

    def test_build_radar_config(self):
        dims = [{"name": "CPU", "score": 85, "target": 90}]
        cfg = scorecard._build_radar_config(dims)
        assert cfg["type"] == "radar"
        assert cfg["data"]["labels"] == ["CPU"]
        assert cfg["data"]["datasets"][0]["label"] == "Current"
        assert cfg["data"]["datasets"][1]["label"] == "Target"

    def test_build_creates_html(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = scorecard.build(
            trace_id="test-scorecard",
            title="Health Check",
            data=[{"name": "CPU", "score": 85, "target": 90, "weight": 1.0}],
            config={"theme": "dark"},
        )
        assert result["type"] == "scorecard"
        assert result["dimensions"] == 1
        assert result["overall_score"] == 85.0
        html_path = Path(result["html_path"])
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Health Check" in content
        assert "85.0" in content or "85" in content

    def test_build_missing_data_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        with pytest.raises(ValueError, match="scorecard requires"):
            scorecard.build(trace_id="test-missing", title="X", data=[], config={})

    def test_build_weighted_score(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.report_core.paths.cfg.workspace_root", tmp_path)
        result = scorecard.build(
            trace_id="test-weighted",
            title="Weighted",
            data=[
                {"name": "A", "score": 100, "target": 100, "weight": 2.0},
                {"name": "B", "score": 50, "target": 100, "weight": 1.0},
            ],
            config={},
        )
        # (100*2 + 50*1) / 3 = 250/3 = 83.3
        assert result["overall_score"] == 83.3
