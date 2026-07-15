"""Tests for vision extract_text action — OCR-style text extraction.

Mirrors the structure of test_describe.py. Covers:
  1. Success path with text_extracted field
  2. Disabled path (vision_model empty)
  3. Validation errors
  4. LLM error path
  5. json_mode (uses EXTRACT_TEXT_JSON_SYSTEM variant)
  6. json_schema forwarding
  7. format suffix
  8. context_type modifier
  9. trace_id threading
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.vision import vision
from tests.tools.vision.conftest import make_mock_response


class TestExtractTextSuccess:
    """extract_text: OCR-style text extraction."""

    def test_extract_text_success(self, mock_cfg, mock_llm, temp_image_file):
        """Should return text_extracted from vision role."""
        mock_llm.call.return_value = make_mock_response(text="Hello\nWorld")
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path)

        assert result["status"] == "success"
        assert result["action"] == "extract_text"
        assert result["text_extracted"] == "Hello\nWorld"
        assert result["model"] == "test-vision-model"

        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["role"] == "vision"

    def test_extract_text_default_instruction(self, mock_cfg, mock_llm, temp_image_file):
        """When question is empty, default instruction should be used."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path)

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Extract all visible text" in b["text"] for b in text_blocks)

    def test_extract_text_with_question(self, mock_cfg, mock_llm, temp_image_file):
        """When question is provided, it should appear in user content."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path, question="Focus on the header text")

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Focus on the header text" in b["text"] for b in text_blocks)


class TestExtractTextDisabled:
    """extract_text: kill-switch paths."""

    def test_disabled_when_model_empty(self, mock_cfg, mock_llm, temp_image_file):
        """Should return disabled when VISION_MODEL is empty."""
        mock_cfg.vision_model = ""
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path)

        assert result["status"] == "disabled"
        assert "VISION_MODEL" in result["error"]
        mock_llm.call.assert_not_called()


class TestExtractTextValidation:
    """extract_text: input validation."""

    def test_no_sources_provided(self, mock_cfg, mock_llm):
        result = vision(action="extract_text")
        assert result["status"] == "error"
        assert "Exactly one image source" in result["error"]
        mock_llm.call.assert_not_called()

    def test_multiple_sources_provided(self, mock_cfg, mock_llm, temp_image_file):
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path, url="https://example.com/x.png")
        assert result["status"] == "error"
        assert "exactly ONE" in result["error"]

    def test_file_not_found(self, mock_cfg, mock_llm):
        result = vision(action="extract_text", file_path="/nonexistent.png")
        assert result["status"] == "error"
        assert "File not found" in result["error"]


class TestExtractTextLLMError:
    """extract_text: LLM call failure."""

    def test_llm_response_not_ok(self, mock_cfg, mock_llm, temp_image_file):
        """Should return error when result.ok is False."""
        mock_llm.call.return_value = make_mock_response(ok=False, error="rate limited")
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path)

        assert result["status"] == "error"
        assert result["error"] == "rate limited"

    def test_llm_call_exception(self, mock_cfg, mock_llm, temp_image_file):
        """Should catch exceptions from llm.call."""
        mock_llm.call.side_effect = RuntimeError("boom")
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path)

        assert result["status"] == "error"
        assert "Vision model call failed" in result["error"]


class TestExtractTextJsonMode:
    """extract_text: JSON output mode."""

    def test_json_mode_uses_json_prompt_variant(self, mock_cfg, mock_llm, temp_image_file):
        """json_mode=True should use EXTRACT_TEXT_JSON_SYSTEM."""
        mock_llm.call.return_value = make_mock_response(
            text='{"has_text": true}', parsed={"has_text": True}
        )
        path = temp_image_file()
        vision(action="extract_text", file_path=path, json_mode=True)

        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "valid JSON" in system
        assert "blocks" in system
        assert "source_type" in system

    def test_json_mode_includes_parsed(self, mock_cfg, mock_llm, temp_image_file):
        """json_mode should include parsed field in success response."""
        mock_llm.call.return_value = make_mock_response(
            text='{"has_text": true}', parsed={"has_text": True}
        )
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path, json_mode=True)

        assert result["parsed"] == {"has_text": True}

    def test_json_mode_parse_warning(self, mock_cfg, mock_llm, temp_image_file):
        """When LLM returns non-JSON in json_mode, parse_warning should be set."""
        mock_llm.call.return_value = make_mock_response(text="not json", parsed=None)
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path, json_mode=True)

        assert result["parsed"] == {}
        assert "parse_warning" in result
        # The warning should reference the text_extracted field
        assert "text_extracted" in result["parse_warning"]


class TestExtractTextJsonSchema:
    """extract_text: structured output via json_schema."""

    def test_json_schema_forwarded_to_llm_call(self, mock_cfg, mock_llm, temp_image_file):
        """json_schema string should be parsed and forwarded as a dict."""
        mock_llm.call.return_value = make_mock_response(text='{"has_text": true}', parsed={"has_text": True})
        path = temp_image_file()
        schema = '{"type": "object", "properties": {"has_text": {"type": "boolean"}}}'
        vision(action="extract_text", file_path=path, json_schema=schema)

        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] == {
            "type": "object",
            "properties": {"has_text": {"type": "boolean"}},
        }


class TestExtractTextFormat:
    """extract_text: format suffix."""

    def test_format_markdown_default(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path)
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ocr specialist" in system.lower()
        assert "Output your response as valid JSON" not in system

    def test_format_json_suffix(self, mock_cfg, mock_llm, temp_image_file):
        """format=json (without json_mode) should append the JSON suffix to base prompt."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path, format="json")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ocr specialist" in system.lower()
        assert "Output your response as valid JSON" in system

    def test_format_bullet_points_suffix(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path, format="bullet_points")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "bullet points only" in system.lower()


class TestExtractTextContextType:
    """extract_text: context_type modifier."""

    def test_context_type_document(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=document should append the document modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path, context_type="document")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "document" in system.lower()
        assert "scanned text" in system.lower()

    def test_context_type_screenshot(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=screenshot should append the screenshot modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="extract_text", file_path=path, context_type="screenshot")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ui screenshot" in system.lower()


class TestExtractTextTraceID:
    """extract_text: trace_id threading."""

    def test_trace_id_in_success(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path, trace_id="trace-789")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-789"
        assert mock_llm.call.call_args[1]["trace_id"] == "trace-789"

    def test_no_trace_id_when_not_provided(self, mock_cfg, mock_llm, temp_image_file):
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="extract_text", file_path=path)
        assert result["status"] == "success"
        assert "trace_id" not in result
