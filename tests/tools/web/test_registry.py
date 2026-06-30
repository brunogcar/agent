"""Web tool tests — registry auto-registration."""
from __future__ import annotations

import pytest

from tools.web_ops._registry import DISPATCH, register_action


class TestWebRegistry:
    """Test web action registry."""

    def test_dispatch_not_empty(self):
        """After auto-discovery, DISPATCH must have all actions."""
        actions = DISPATCH.get("web", {})
        expected = {"search", "scrape", "read", "search_and_read"}
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        """Every action must have func, help, examples."""
        for name, info in DISPATCH["web"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert callable(info["func"]), f"{name} func not callable"

    def test_duplicate_action_raises(self):
        """Registering the same action twice should raise ValueError."""
        with pytest.raises(ValueError, match="already exists"):
            @register_action("web", "search", help_text="dup")
            def dup(): pass
