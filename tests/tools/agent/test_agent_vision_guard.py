"""Agent tool tests — vision guard rejects dispatch."""
from __future__ import annotations

from tools.agent import agent


class TestVisionGuard:
    """Test that vision role is rejected from dispatch."""

    def test_vision_role_rejected_from_dispatch(self):
        """role='vision' with action='dispatch' must return INVALID_ROLE."""
        result = agent(action="dispatch", role="vision", task="describe this image")
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_ROLE"
        assert "vision_delegate" in result["error"]

    def test_vision_delegate_action_works(self):
        """action='vision_delegate' should be accepted (actual vision tool is mocked)."""
        from unittest.mock import patch
        with patch("tools.vision.vision", return_value={"status": "success", "text": "image description"}):
            result = agent(action="vision_delegate", task="describe", context="test.png")
            assert result["status"] == "success"
