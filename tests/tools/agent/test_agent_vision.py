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

    # ─── vision_delegate forwards context (Bug #13) ──────────────────────────

    def test_vision_forwards_context_parameter(self, mock_llm_result):
        """vision_delegate must forward the caller's context, not hardcode empty.

        Previously `context: ""` was hardcoded in vision_kwargs, preventing
        callers from passing additional text context (e.g., "What does this
        diagram show?").
        """
        with patch("tools.vision.vision") as mock_vis:
            mock_vis.return_value = {"status": "success", "text": "image desc"}
            agent(
                action="vision_delegate",
                task="Describe this",
                context="image.png",
                content="What does this diagram show?",
            )
            assert mock_vis.called
            call_kwargs = mock_vis.call_args.kwargs
            # The content parameter should be forwarded (as context or base64)
            # — not wiped to empty string.
            assert call_kwargs.get("context") != "" or call_kwargs.get("base64") != "", (
                "vision_delegate must forward the caller's content/context, not wipe it."
            )

    def test_vision_forwards_explicit_text_context(self, mock_llm_result):
        """When context is a URL and content is text, content should reach vision()."""
        with patch("tools.vision.vision") as mock_vis:
            mock_vis.return_value = {"status": "success", "text": "desc"}
            agent(
                action="vision_delegate",
                task="Describe",
                context="https://example.com/img.jpg",
                content="Focus on the chart in the upper right",
            )
            assert mock_vis.called
            call_kwargs = mock_vis.call_args.kwargs
            # The content should be forwarded as base64 OR context — not wiped.
            forwarded = call_kwargs.get("context", "") or call_kwargs.get("base64", "")
            assert forwarded, (
                "vision_delegate must forward caller's content/context. "
                "Both context and base64 are empty — context wiping regression."
            )
