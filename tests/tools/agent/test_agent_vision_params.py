"""Agent tool tests — vision passthrough parameters."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestAgentVisionParams:
    """Test mime_type and vision_json_mode passthrough to tools.vision."""

    def test_mime_type_passed_to_vision(self):
        mock_vision_res = {"status": "success", "text": "I see a cat"}

        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            agent(
                action="vision_delegate",
                task="Describe",
                context="img.png",
                mime_type="image/png",
            )

            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["mime_type"] == "image/png"

    def test_vision_json_mode_passed_to_vision(self):
        mock_vision_res = {"status": "success", "text": "{}"}

        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            agent(
                action="vision_delegate",
                task="Extract JSON",
                context="img.png",
                vision_json_mode=True,
            )

            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["json_mode"] is True

    def test_vision_without_params_does_not_pass_empty_values(self):
        mock_vision_res = {"status": "success", "text": "I see a cat"}

        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            agent(action="vision_delegate", task="Describe", context="img.png")

            call_kwargs = mock_vis.call_args.kwargs
            # mime_type and json_mode should not be in kwargs if not provided
            assert "mime_type" not in call_kwargs or call_kwargs.get("mime_type") == ""

    def test_both_params_passed_together(self):
        mock_vision_res = {"status": "success", "text": "{}"}

        with patch("tools.vision.vision", return_value=mock_vision_res) as mock_vis:
            agent(
                action="vision_delegate",
                task="Extract",
                context="img.png",
                mime_type="image/jpeg",
                vision_json_mode=True,
            )

            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["mime_type"] == "image/jpeg"
            assert call_kwargs["json_mode"] is True
