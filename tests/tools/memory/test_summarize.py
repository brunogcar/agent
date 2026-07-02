"""Tests for the summarize action."""
from __future__ import annotations

from tools.memory import memory


class TestSummarizeSuccess:
    def test_summarize(self, mock_cfg, mock_store):
        result = memory(action="summarize")
        assert result["status"] == "success"
        mock_store.summarize.assert_called_once()

    def test_summarize_with_collections(self, mock_cfg, mock_store):
        memory(action="summarize", collections=["procedural"])
        call_kwargs = mock_store.summarize.call_args.kwargs
        assert call_kwargs["collections"] == ["procedural"]
