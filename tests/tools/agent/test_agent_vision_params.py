"""Agent tool tests — vision passthrough parameters."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestAgentVisionParams:
    """Test mime_type and vision_json_mode passthrough to tools.vision."""

    def test_mime_type_passed_to_vision(self):
        mock_res = {"status": "success", "text": "image analyzed"}

        with patch("tools.vision.vision", return_value=mock_res) as mock_vis:
            agent(
                role="vision",
                task="Analyze this",
                context="image.webp",
                mime_type="image/webp",
            )

            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["mime_type"] == "image/webp"

    def test_vision_json_mode_passed_to_vision(self):
        mock_res = {"status": "success", "text": '{"objects": ["cat"]}'}

        with patch("tools.vision.vision", return_value=mock_res) as mock_vis:
            agent(
                role="vision",
                task="List objects",
                context="photo.jpg",
                vision_json_mode=True,
            )

            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["json_mode"] is True

    def test_vision_without_params_does_not_pass_empty_values(self):
        mock_res = {"status": "success", "text": "image analyzed"}

        with patch("tools.vision.vision", return_value=mock_res) as mock_vis:
            agent(role="vision", task="Describe", context="img.png")

            call_kwargs = mock_vis.call_args.kwargs
            assert "mime_type" not in call_kwargs
            assert "json_mode" not in call_kwargs

    def test_both_params_passed_together(self):
        mock_res = {"status": "success", "text": "{}"}

        with patch("tools.vision.vision", return_value=mock_res) as mock_vis:
            agent(
                role="vision",
                task="Extract data",
                content="data:image/png;base64,abc",
                mime_type="image/png",
                vision_json_mode=True,
            )

            call_kwargs = mock_vis.call_args.kwargs
            assert call_kwargs["mime_type"] == "image/png"
            assert call_kwargs["json_mode"] is True
            assert call_kwargs["base64"] == "data:image/png;base64,abc"
