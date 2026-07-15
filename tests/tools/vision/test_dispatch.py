"""Tests for vision facade dispatch and registry.

Mirrors the structure of tests/tools/consult/test_dispatch.py. Covers:
  - Unknown action → error listing valid actions
  - Empty action → error explaining action is required
  - Case insensitivity (DESCRIBE / Describe / describe all dispatch the same handler)
  - All 3 actions present in DISPATCH with full metadata
  - Deprecated task alias compatibility
"""
from __future__ import annotations

from tools.vision import vision


class TestDispatch:
    """Dispatcher routes actions and handles unknown/empty actions."""

    def test_unknown_action(self):
        """Unknown action should list valid actions."""
        result = vision(action="nonexistent")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]
        assert "describe" in result["error"]
        assert "extract_text" in result["error"]
        assert "analyse_ui" in result["error"]

    def test_empty_action(self):
        """Empty action should return clear 'action is required' error."""
        result = vision(action="")
        assert result["status"] == "error"
        assert "action is required" in result["error"].lower()

    def test_action_case_insensitive(self, mock_cfg, mock_llm, temp_image_file):
        """Action should be case-insensitive (uppercase/lowercase both dispatch)."""
        # The mock_llm fixture already returns a default successful response.
        path = temp_image_file()

        # Uppercase
        result_upper = vision(action="DESCRIBE", file_path=path)
        assert result_upper["status"] == "success", f"DESCRIBE failed: {result_upper}"
        assert result_upper["action"] == "describe"

        # Mixed case
        result_mixed = vision(action="Describe", file_path=path)
        assert result_mixed["status"] == "success", f"Describe failed: {result_mixed}"
        assert result_mixed["action"] == "describe"

        # Lowercase with underscores
        result_underscore = vision(action="Extract_Text", file_path=path)
        assert result_underscore["status"] == "success", f"Extract_Text failed: {result_underscore}"
        assert result_underscore["action"] == "extract_text"

    def test_duration_ms_always_present(self, mock_cfg, mock_llm, temp_image_file):
        """duration_ms should be present on every handler-returned result."""
        path = temp_image_file()
        result = vision(action="describe", file_path=path)
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))
        assert result["duration_ms"] >= 0

    def test_handler_exception_caught(self, mock_cfg, mock_llm, temp_image_file):
        """If the LLM raises inside the handler, the result should be a graceful error.

        The handler catches LLM exceptions and returns status=error with
        'Vision model call failed: ...'. The facade's outer catch
        ('Vision action failed: ...') only fires for non-LLM exceptions in
        handler logic itself.
        """
        mock_llm.call.side_effect = RuntimeError("boom")
        path = temp_image_file()
        result = vision(action="describe", file_path=path)
        assert result["status"] == "error"
        assert "Vision model call failed" in result["error"]
        assert "boom" in result["error"]

    def test_trace_id_threaded_through_dispatch(self):
        """trace_id should be present in error responses from dispatch layer."""
        result = vision(action="nonexistent", trace_id="trace-dispatch-1")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-1"

        result = vision(action="", trace_id="trace-dispatch-2")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-dispatch-2"


class TestRegistry:
    """Verify all 3 vision actions are registered in DISPATCH."""

    def test_dispatch_has_3_actions(self):
        from tools.vision_ops._registry import DISPATCH
        actions = DISPATCH.get("vision", {})
        assert len(actions) == 3
        expected = {"describe", "extract_text", "analyse_ui"}
        assert set(actions.keys()) == expected

    def test_all_actions_have_metadata(self):
        from tools.vision_ops._registry import DISPATCH
        for name, info in DISPATCH["vision"].items():
            assert "func" in info, f"{name} missing func"
            assert "help" in info, f"{name} missing help"
            assert "examples" in info, f"{name} missing examples"
            assert callable(info["func"]), f"{name} func not callable"
            assert isinstance(info["help"], str) and info["help"], f"{name} help empty"
            assert isinstance(info["examples"], list) and info["examples"], f"{name} examples empty"

    def test_action_names_match_pattern(self):
        """All action names must match ^[a-z][a-z0-9_]*$ (validated by @meta_tool)."""
        import re
        from tools.vision_ops._registry import DISPATCH
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for name in DISPATCH["vision"]:
            assert pattern.match(name), f"{name!r} does not match required pattern"

    def test_facade_action_literal_generated(self):
        """The @meta_tool decorator should have replaced `action: str` with a Literal."""
        from typing import get_args, get_type_hints
        from tools.vision import vision as vision_fn
        hints = get_type_hints(vision_fn)
        action_hint = hints.get("action")
        # Literal[...] args should be exactly {"describe", "extract_text", "analyse_ui"} (sorted).
        args = set(get_args(action_hint))
        assert args == {"describe", "extract_text", "analyse_ui"}, f"Got: {args}"

    def test_facade_docstring_has_action_list(self):
        """The @meta_tool decorator should have generated a docstring with action list."""
        from tools.vision import vision as vision_fn
        assert vision_fn.__doc__ is not None
        doc = vision_fn.__doc__
        assert "describe" in doc
        assert "extract_text" in doc
        assert "analyse_ui" in doc
        assert "vision meta-tool" in doc.lower()

    def test_facade_docstring_has_doc_sections(self):
        """The doc_sections passed to @meta_tool should be present in the docstring."""
        from tools.vision import vision as vision_fn
        doc = vision_fn.__doc__
        # Spot-check a few doc_sections strings
        assert "VISION TOOL" in doc
        assert "Multimodal image analysis" in doc
        assert "DEPRECATED" in doc
        assert "NOT parallel-safe" in doc
