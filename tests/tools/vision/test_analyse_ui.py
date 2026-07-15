"""Tests for vision analyse_ui action — UI/UX analysis.

Mirrors the structure of test_describe.py. Covers:
  1. Success path with analysis field
  2. Disabled path
  3. Validation errors
  4. LLM error path
  5. json_mode (uses ANALYSE_UI_JSON_SYSTEM variant)
  6. json_schema forwarding
  7. format suffix
  8. context_type modifier (screenshot is the typical use case)
  9. trace_id threading
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tools.vision import vision
from tests.tools.vision.conftest import make_mock_response


class TestAnalyseUISuccess:
    """analyse_ui: UI/UX analysis."""

    def test_analyse_ui_success(self, mock_cfg, mock_llm, temp_image_file):
        """Should return analysis from vision role."""
        mock_llm.call.return_value = make_mock_response(text="Components: nav, hero, footer...")
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path)

        assert result["status"] == "success"
        assert result["action"] == "analyse_ui"
        assert result["analysis"] == "Components: nav, hero, footer..."
        assert result["model"] == "test-vision-model"

        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["role"] == "vision"

    def test_analyse_ui_default_instruction(self, mock_cfg, mock_llm, temp_image_file):
        """When question is empty, default instruction should be used."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path)

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Analyse this UI" in b["text"] for b in text_blocks)

    def test_analyse_ui_with_question(self, mock_cfg, mock_llm, temp_image_file):
        """When question is provided, it should appear in user content."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path, question="Focus on the navigation bar")

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Focus on the navigation bar" in b["text"] for b in text_blocks)


class TestAnalyseUIDisabled:
    """analyse_ui: kill-switch paths."""

    def test_disabled_when_model_empty(self, mock_cfg, mock_llm, temp_image_file):
        mock_cfg.vision_model = ""
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path)

        assert result["status"] == "disabled"
        assert "VISION_MODEL" in result["error"]
        mock_llm.call.assert_not_called()


class TestAnalyseUIValidation:
    """analyse_ui: input validation."""

    def test_no_sources_provided(self, mock_cfg, mock_llm):
        result = vision(action="analyse_ui")
        assert result["status"] == "error"
        assert "Exactly one image source" in result["error"]
        mock_llm.call.assert_not_called()

    def test_file_not_found(self, mock_cfg, mock_llm):
        result = vision(action="analyse_ui", file_path="/nonexistent.png")
        assert result["status"] == "error"
        assert "File not found" in result["error"]


class TestAnalyseUILLMError:
    """analyse_ui: LLM call failure."""

    def test_llm_response_not_ok(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(ok=False, error="500 server error")
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path)

        assert result["status"] == "error"
        assert result["error"] == "500 server error"

    def test_llm_call_exception(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.side_effect = RuntimeError("model down")
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path)

        assert result["status"] == "error"
        assert "Vision model call failed" in result["error"]
        assert "model down" in result["error"]


class TestAnalyseUIJsonMode:
    """analyse_ui: JSON output mode."""

    def test_json_mode_uses_json_prompt_variant(self, mock_cfg, mock_llm, temp_image_file):
        """json_mode=True should use ANALYSE_UI_JSON_SYSTEM."""
        mock_llm.call.return_value = make_mock_response(
            text='{"components": ["nav"]}', parsed={"components": ["nav"]}
        )
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path, json_mode=True)

        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "valid JSON" in system
        assert "components" in system
        assert "layout" in system
        assert "accessibility" in system

    def test_json_mode_includes_parsed(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(
            text='{"components": ["nav"]}', parsed={"components": ["nav"]}
        )
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path, json_mode=True)

        assert result["parsed"] == {"components": ["nav"]}

    def test_json_mode_parse_warning(self, mock_cfg, mock_llm, temp_image_file):
        """parse_warning should reference the analysis field."""
        mock_llm.call.return_value = make_mock_response(text="not json", parsed=None)
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path, json_mode=True)

        assert result["parsed"] == {}
        assert "parse_warning" in result
        assert "analysis" in result["parse_warning"]


class TestAnalyseUIJsonSchema:
    """analyse_ui: structured output via json_schema."""

    def test_json_schema_forwarded_to_llm_call(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(
            text='{"components": ["nav"]}', parsed={"components": ["nav"]}
        )
        path = temp_image_file()
        schema = '{"type": "object", "properties": {"components": {"type": "array"}}}'
        vision(action="analyse_ui", file_path=path, json_schema=schema)

        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] == {
            "type": "object",
            "properties": {"components": {"type": "array"}},
        }


class TestAnalyseUIFormat:
    """analyse_ui: format suffix."""

    def test_format_markdown_default(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path)
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ui/ux designer" in system.lower()
        assert "Output your response as valid JSON" not in system

    def test_format_bullet_points_suffix(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path, format="bullet_points")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "bullet points only" in system.lower()


class TestAnalyseUIContextType:
    """analyse_ui: context_type modifier (screenshot is the typical case)."""

    def test_context_type_screenshot(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=screenshot is the canonical use case for analyse_ui."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path, context_type="screenshot")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ui screenshot" in system.lower()
        assert "interface elements" in system.lower()

    def test_context_type_empty(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="analyse_ui", file_path=path, context_type="")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ui screenshot" not in system.lower()


class TestAnalyseUITraceID:
    """analyse_ui: trace_id threading."""

    def test_trace_id_in_success(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path, trace_id="trace-ui-1")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-ui-1"
        assert mock_llm.call.call_args[1]["trace_id"] == "trace-ui-1"

    def test_no_trace_id_when_not_provided(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="analyse_ui", file_path=path)
        assert result["status"] == "success"
        assert "trace_id" not in result
