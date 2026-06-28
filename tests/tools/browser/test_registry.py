"""Browser tool tests — registry auto-registration."""
from __future__ import annotations

import pytest

from tools.browser_core._registry import DISPATCH, register_action


class TestBrowserRegistry:
    """Test browser action registry."""

    def test_dispatch_not_empty(self):
        """After auto-discovery, DISPATCH must have all actions."""
        actions = DISPATCH.get("browser", {})
        expected = {
            "navigate", "click", "fill", "type", "screenshot",
            "text_content", "evaluate", "select_option", "keyboard_press",
            "get_url", "close", "wait_for_selector", "scroll", "wait_for_url",
            "hover", "cookies", "set_viewport", "extract_html",
            "extract_links", "extract_tables",
        }
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        """Every action must have func, help, examples."""
        for name, info in DISPATCH["browser"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert callable(info["func"]), f"{name} func not callable"

    def test_duplicate_action_raises(self):
        """Registering the same action twice should raise ValueError."""
        with pytest.raises(ValueError, match="already exists"):
            @register_action("browser", "navigate", help_text="dup")
            def dup(): pass
