"""Tests for the memory action registry."""
from __future__ import annotations

import pytest

from tools.memory_ops._registry import DISPATCH, register_action


class TestRegistry:
    def test_dispatch_populated(self):
        assert "memory" in DISPATCH
        assert len(DISPATCH["memory"]) == 12  # v1.4: +update, +export, +import; v1.5: +extract

    def test_all_actions_have_func(self):
        for name, info in DISPATCH["memory"].items():
            assert callable(info["func"]), f"Action '{name}' has no func"

    def test_all_actions_have_help(self):
        for name, info in DISPATCH["memory"].items():
            assert info.get("help"), f"Action '{name}' has no help text"

    def test_duplicate_action_raises(self):
        with pytest.raises(ValueError, match="Duplicate action"):
            @register_action("memory", "store", help_text="duplicate")
            def fake_store(**kwargs):
                pass
