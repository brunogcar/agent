"""Agent tool tests — vision delegation."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestAgentVisionDelegation:
    """Vision action must NOT call llm.complete, it must call tools.vision."""

    def test_vision_delegates_to_vision_tool(self):
        mock_vision_res = {"status": "success", "text": "I see a cat"}

        # Patch where it is imported inside the function
        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            result = agent(action="vision_delegate", task="What is this?", context="img.png")

            assert mock_vis.called
            assert result["status"] == "success"
            assert result["text"] == "I see a cat"

    def test_vision_with_url_context(self):
        mock_vision_res = {"status": "success", "text": "I see a dog"}

        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            result = agent(
                action="vision_delegate",
                task="Describe this",
                context="https://example.com/img.jpg",
            )

            assert mock_vis.called
            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["url"] == "https://example.com/img.jpg"

    def test_vision_with_base64_content(self):
        mock_vision_res = {"status": "success", "text": "I see a bird"}

        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            result = agent(
                action="vision_delegate",
                task="Identify",
                content="data:image/png;base64,abc123",
            )

            assert mock_vis.called
            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["base64"] == "data:image/png;base64,abc123"
