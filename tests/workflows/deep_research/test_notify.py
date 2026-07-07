"""tests/workflows/deep_research/test_notify.py
Tests for _node_notify — notification + artifacts.
"""
from __future__ import annotations


class TestNodeNotify:
    def test_calls_notify_with_correct_signature(self, mocker):
        """_node_notify must call notify with action='send'."""
        from workflows.deep_research_impl.graph import _node_notify
        mock_notify = mocker.patch("workflows.deep_research_impl.graph.notify")
        mocker.patch("core.citations.citations.get_sources", return_value=[])
        state = {"result": "Test research result", "trace_id": "test-123"}
        result = _node_notify(state)
        mock_notify.assert_called_once_with(
            action="send",
            title="DeepResearch",
            message="Test research result",
        )
        assert "artifacts" in result
        assert result["artifacts"] == []

    def test_returns_source_urls_as_artifacts(self, mocker):
        """v1.1: _node_notify must return source URLs as artifacts (list[str])."""
        from workflows.deep_research_impl.graph import _node_notify
        mocker.patch("workflows.deep_research_impl.graph.notify")
        mocker.patch(
            "core.citations.citations.get_sources",
            return_value=[
                {"url": "https://a.example"},
                {"url": "https://b.example"},
            ],
        )
        state = {"result": "r", "trace_id": "t1", "status": "success"}
        result = _node_notify(state)
        assert result["artifacts"] == ["https://a.example", "https://b.example"]
