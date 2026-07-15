"""Tests for vision describe action — general image description.

Mirrors the structure of tests/tools/consult/test_advise.py. Covers:
  1. Success path (mock LLM returns ok) via file_path / base64 / url
  2. Disabled path (vision_model empty)
  3. SSRF / validation errors (no source, multiple sources, file not found, file too large)
  4. URL download with retry_sync (success + timeout + HTTP error)
  5. LLM error path
  6. json_mode (uses DESCRIBE_JSON_SYSTEM variant, parsed field in response)
  7. json_schema (forwarded to llm.call as dict; json_mode implied)
  8. format suffix (markdown/json/bullet_points appended to base prompt)
  9. context_type modifier (screenshot/diagram/photo/document appended)
 10. trace_id threading
"""
from __future__ import annotations

import httpx
from unittest.mock import patch, MagicMock

from tools.vision import vision
from tests.tools.vision.conftest import make_mock_response


# =============================================================================
# 1. Success paths
# =============================================================================
class TestDescribeSuccess:
    """describe: general image description via various image sources."""

    def test_describe_success_file_path(self, mock_cfg, mock_llm, temp_image_file):
        """Should return description from vision role via file_path."""
        mock_llm.call.return_value = make_mock_response(text="A red circle on white background.")
        path = temp_image_file()
        result = vision(action="describe", file_path=path, trace_id="trace-1")

        assert result["status"] == "success"
        assert result["action"] == "describe"
        assert result["description"] == "A red circle on white background."
        assert result["model"] == "test-vision-model"
        assert result["trace_id"] == "trace-1"

        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["role"] == "vision"
        assert call_kwargs["json_mode"] is False
        assert call_kwargs["json_schema"] is None
        assert call_kwargs["trace_id"] == "trace-1"

    def test_describe_success_base64(self, mock_cfg, mock_llm):
        """Should accept base64-encoded image data."""
        mock_llm.call.return_value = make_mock_response(text="A blue square.")
        b64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        result = vision(action="describe", base64=b64_data)

        assert result["status"] == "success"
        assert result["description"] == "A blue square."

    def test_describe_success_data_uri(self, mock_cfg, mock_llm):
        """Should accept a full data: URI in the base64 param."""
        mock_llm.call.return_value = make_mock_response(text="A data URI image.")
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        result = vision(action="describe", base64=data_uri)

        assert result["status"] == "success"
        assert result["description"] == "A data URI image."

    def test_describe_success_url(self, mock_cfg, mock_llm, mock_security, mock_retry_sync):
        """Should accept a public URL and download via retry_sync."""
        # Mock the httpx.Client.get path — _do_download creates a real Client.
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"\x89PNG fake bytes"
        with patch("tools.vision_ops.helpers.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            mock_llm.call.return_value = make_mock_response(text="A downloaded image.")
            result = vision(action="describe", url="https://example.com/image.png")

        assert result["status"] == "success"
        assert result["description"] == "A downloaded image."

    def test_describe_default_question_when_empty(self, mock_cfg, mock_llm, temp_image_file):
        """When question is empty, the default instruction should be used."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path)

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        # Last text block should be the default instruction (no question provided).
        assert any("Describe this image in detail." in b["text"] for b in text_blocks)

    def test_describe_with_question(self, mock_cfg, mock_llm, temp_image_file):
        """When question is provided, it should appear in the user content."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, question="Focus on the color scheme")

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Focus on the color scheme" in b["text"] for b in text_blocks)

    def test_describe_with_context(self, mock_cfg, mock_llm, temp_image_file):
        """When context is provided, it should appear before the image block."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context="This is a dashboard screenshot.")

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Context:" in b["text"] and "dashboard" in b["text"] for b in text_blocks)

    def test_describe_image_block_present(self, mock_cfg, mock_llm, temp_image_file):
        """The user content must contain an image_url block."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path)

        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        image_blocks = [b for b in user_content if b.get("type") == "image_url"]
        assert len(image_blocks) == 1
        assert "data:image/png;base64," in image_blocks[0]["image_url"]["url"]


# =============================================================================
# 2. Disabled path
# =============================================================================
class TestDescribeDisabled:
    """describe: kill-switch paths."""

    def test_disabled_when_model_empty(self, mock_cfg, mock_llm, temp_image_file):
        """Should return disabled when VISION_MODEL is empty."""
        mock_cfg.vision_model = ""
        path = temp_image_file()
        result = vision(action="describe", file_path=path)

        assert result["status"] == "disabled"
        assert "VISION_MODEL" in result["error"]
        mock_llm.call.assert_not_called()

    def test_disabled_when_model_none(self, mock_cfg, mock_llm, temp_image_file):
        """Should return disabled when vision_model is None."""
        mock_cfg.vision_model = None
        path = temp_image_file()
        result = vision(action="describe", file_path=path)

        assert result["status"] == "disabled"
        mock_llm.call.assert_not_called()


# =============================================================================
# 3. Validation errors
# =============================================================================
class TestDescribeValidation:
    """describe: input validation."""

    def test_no_sources_provided(self, mock_cfg, mock_llm):
        """Should fail if no image source is provided."""
        result = vision(action="describe")
        assert result["status"] == "error"
        assert "Exactly one image source" in result["error"]
        mock_llm.call.assert_not_called()

    def test_multiple_sources_provided(self, mock_cfg, mock_llm, temp_image_file):
        """Should fail if multiple sources are provided."""
        path = temp_image_file()
        result = vision(action="describe", file_path=path, base64="abc")
        assert result["status"] == "error"
        assert "exactly ONE" in result["error"]
        mock_llm.call.assert_not_called()

    def test_file_not_found(self, mock_cfg, mock_llm):
        """Should fail if file does not exist."""
        result = vision(action="describe", file_path="/nonexistent/path/img.png")
        assert result["status"] == "error"
        assert "File not found" in result["error"]
        mock_llm.call.assert_not_called()

    def test_file_too_large(self, mock_cfg, mock_llm, temp_image_file, monkeypatch):
        """Should fail if file exceeds MAX_IMAGE_BYTES."""
        import tools.vision_ops.helpers as h
        monkeypatch.setattr(h, "MAX_IMAGE_BYTES", 10)
        path = temp_image_file(data=b"x" * 100)  # 100 bytes > 10 byte limit
        result = vision(action="describe", file_path=path)

        assert result["status"] == "error"
        assert "File too large" in result["error"]
        mock_llm.call.assert_not_called()

    def test_ssrf_blocked_url(self, mock_cfg, mock_llm, mock_security):
        """Should fail if URL resolves to a private/internal address."""
        mock_security.return_value = False
        result = vision(action="describe", url="http://192.168.1.10/image.png")
        assert result["status"] == "error"
        assert "SSRF" in result["error"]
        mock_llm.call.assert_not_called()


# =============================================================================
# 4. URL download paths (core/net retry_sync adoption)
# =============================================================================
class TestDescribeURLDownload:
    """describe: URL download with retry_sync."""

    def test_url_download_success(self, mock_cfg, mock_llm, mock_security, mock_retry_sync):
        """Successful download should produce a valid image block."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"\x89PNG fake"
        with patch("tools.vision_ops.helpers.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            mock_llm.call.return_value = make_mock_response(text="OK")
            result = vision(action="describe", url="https://example.com/img.png")

        assert result["status"] == "success"
        # retry_sync should have been called (mock_retry_sync passthrough)
        mock_retry_sync.assert_called_once()

    def test_url_download_timeout(self, mock_cfg, mock_llm, mock_security, mock_retry_sync):
        """Timeout during download should surface as clean error."""
        mock_retry_sync.side_effect = httpx.TimeoutException("Connection timed out")
        result = vision(action="describe", url="https://example.com/slow.png")

        assert result["status"] == "error"
        assert "Timeout" in result["error"]
        mock_llm.call.assert_not_called()

    def test_url_download_http_error(self, mock_cfg, mock_llm, mock_security, mock_retry_sync):
        """HTTPStatusError should surface as clean error with status code."""
        request = httpx.Request("GET", "https://example.com/missing.png")
        response = httpx.Response(status_code=404, request=request)
        mock_retry_sync.side_effect = httpx.HTTPStatusError(
            "Not Found", request=request, response=response
        )
        result = vision(action="describe", url="https://example.com/missing.png")

        assert result["status"] == "error"
        assert "HTTP error 404" in result["error"]
        mock_llm.call.assert_not_called()

    def test_url_download_uses_max_retries_two(self, mock_cfg, mock_llm, mock_security, mock_retry_sync):
        """Vision should pass max_retries=2 to retry_sync (single image, not search)."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"fake"
        with patch("tools.vision_ops.helpers.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            mock_llm.call.return_value = make_mock_response(text="OK")
            vision(action="describe", url="https://example.com/img.png")

        retry_kwargs = mock_retry_sync.call_args[1]
        assert retry_kwargs["max_retries"] == 2
        assert retry_kwargs["jitter"] is True
        # is_retryable should be the function reference (callable), not a bool.
        assert callable(retry_kwargs["is_retryable"])


# =============================================================================
# 5. LLM error path
# =============================================================================
class TestDescribeLLMError:
    """describe: LLM call failure."""

    def test_llm_call_exception(self, mock_cfg, mock_llm, temp_image_file):
        """Should catch exceptions from llm.call and return error."""
        mock_llm.call.side_effect = RuntimeError("model unreachable")
        path = temp_image_file()
        result = vision(action="describe", file_path=path)

        assert result["status"] == "error"
        assert "Vision model call failed" in result["error"]
        assert "model unreachable" in result["error"]

    def test_llm_response_not_ok(self, mock_cfg, mock_llm, temp_image_file):
        """Should return error when result.ok is False."""
        mock_llm.call.return_value = make_mock_response(ok=False, error="context limit exceeded")
        path = temp_image_file()
        result = vision(action="describe", file_path=path)

        assert result["status"] == "error"
        assert result["error"] == "context limit exceeded"
        assert result["model"] == "test-vision-model"


# =============================================================================
# 6. json_mode
# =============================================================================
class TestDescribeJsonMode:
    """describe: JSON output mode."""

    def test_json_mode_uses_json_prompt_variant(self, mock_cfg, mock_llm, temp_image_file):
        """json_mode=True should use DESCRIBE_JSON_SYSTEM (no markdown structure)."""
        mock_llm.call.return_value = make_mock_response(text='{"overview": "x"}', parsed={"overview": "x"})
        path = temp_image_file()
        vision(action="describe", file_path=path, json_mode=True)

        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        # JSON variant should contain the JSON shape guidance.
        assert "valid JSON" in system
        assert "overview" in system
        # Should NOT contain the markdown-style "Overview: one sentence summary"
        assert "Overview: one sentence summary" not in system

    def test_json_mode_includes_parsed_in_response(self, mock_cfg, mock_llm, temp_image_file):
        """json_mode should include parsed field in success response."""
        mock_llm.call.return_value = make_mock_response(
            text='{"overview": "x"}', parsed={"overview": "x"}
        )
        path = temp_image_file()
        result = vision(action="describe", file_path=path, json_mode=True)

        assert result["status"] == "success"
        assert result["parsed"] == {"overview": "x"}
        assert result["description"] == '{"overview": "x"}'

    def test_json_mode_parse_warning_when_not_parsed(self, mock_cfg, mock_llm, temp_image_file):
        """When LLM returns non-JSON in json_mode, parse_warning should be set."""
        mock_llm.call.return_value = make_mock_response(text="not json", parsed=None)
        path = temp_image_file()
        result = vision(action="describe", file_path=path, json_mode=True)

        assert result["status"] == "success"
        assert result["parsed"] == {}
        assert "parse_warning" in result

    def test_json_mode_forwarded_to_llm_call(self, mock_cfg, mock_llm, temp_image_file):
        """json_mode should be forwarded to llm.call()."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, json_mode=True)
        assert mock_llm.call.call_args[1]["json_mode"] is True


# =============================================================================
# 7. json_schema
# =============================================================================
class TestDescribeJsonSchema:
    """describe: structured output via json_schema."""

    def test_json_schema_string_parsed_to_dict(self, mock_cfg, mock_llm, temp_image_file):
        """json_schema string should be parsed and forwarded as a dict to llm.call."""
        mock_llm.call.return_value = make_mock_response(text='{"foo": 1}', parsed={"foo": 1})
        path = temp_image_file()
        schema = '{"type": "object", "properties": {"foo": {"type": "string"}}}'
        vision(action="describe", file_path=path, json_schema=schema)

        call_kwargs = mock_llm.call.call_args[1]
        assert call_kwargs["json_schema"] == {"type": "object", "properties": {"foo": {"type": "string"}}}

    def test_json_schema_uses_json_prompt_variant(self, mock_cfg, mock_llm, temp_image_file):
        """json_schema should also trigger the JSON prompt variant."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        schema = '{"type": "object"}'
        vision(action="describe", file_path=path, json_schema=schema)

        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "valid JSON" in system

    def test_json_schema_malformed_silently_skipped(self, mock_cfg, mock_llm, temp_image_file):
        """Malformed json_schema string should fall through as json_schema=None."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, json_schema="not valid json {")

        # Should not raise; json_schema should be None (helpers fall-back).
        assert mock_llm.call.call_args[1]["json_schema"] is None


# =============================================================================
# 8. format suffix
# =============================================================================
class TestDescribeFormat:
    """describe: format param affects system prompt (non-JSON mode only)."""

    def test_format_markdown_default(self, mock_cfg, mock_llm, temp_image_file):
        """Default format=markdown should not add a format suffix."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path)
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        # Base prompt should be present
        assert "visual analysis specialist" in system.lower()
        # No JSON / bullet_points suffix
        assert "Output your response as valid JSON" not in system
        assert "bullet points only" not in system.lower()

    def test_format_json_suffix(self, mock_cfg, mock_llm, temp_image_file):
        """format=json (without json_mode) should append the JSON format suffix to the base prompt."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, format="json")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        # Base prompt + JSON suffix
        assert "visual analysis specialist" in system.lower()
        assert "Output your response as valid JSON" in system

    def test_format_bullet_points_suffix(self, mock_cfg, mock_llm, temp_image_file):
        """format=bullet_points should append the bullet_points suffix."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, format="bullet_points")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "bullet points only" in system.lower()

    def test_format_ignored_when_json_mode(self, mock_cfg, mock_llm, temp_image_file):
        """When json_mode=True, format suffix should NOT be appended (JSON variant used)."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, json_mode=True, format="bullet_points")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        # The JSON variant should be used; no bullet_points suffix
        assert "bullet points only" not in system.lower()
        assert "valid JSON" in system


# =============================================================================
# 9. context_type modifier
# =============================================================================
class TestDescribeContextType:
    """describe: context_type modifier."""

    def test_context_type_screenshot(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=screenshot should append the screenshot modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context_type="screenshot")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ui screenshot" in system.lower()
        assert "interface elements" in system.lower()

    def test_context_type_diagram(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=diagram should append the diagram modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context_type="diagram")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "diagram" in system.lower()
        assert "data flow" in system.lower()

    def test_context_type_photo(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=photo should append the photo modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context_type="photo")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "photograph" in system.lower()

    def test_context_type_document(self, mock_cfg, mock_llm, temp_image_file):
        """context_type=document should append the document modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context_type="document")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "document" in system.lower()
        assert "scanned text" in system.lower()

    def test_context_type_empty(self, mock_cfg, mock_llm, temp_image_file):
        """context_type='' should not append any modifier."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context_type="")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "ui screenshot" not in system.lower()
        assert "photograph" not in system.lower()
        assert "scanned text" not in system.lower()

    def test_context_type_unknown_silently_ignored(self, mock_cfg, mock_llm, temp_image_file):
        """Unknown context_type should silently degrade (no suffix)."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, context_type="nonexistent")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        assert "nonexistent" not in system.lower()

    def test_context_type_applied_in_json_mode(self, mock_cfg, mock_llm, temp_image_file):
        """context_type modifier should be appended to JSON variant too."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        vision(action="describe", file_path=path, json_mode=True, context_type="screenshot")
        system = mock_llm.call.call_args[1]["messages"][0]["content"]
        # JSON variant + screenshot modifier
        assert "valid JSON" in system
        assert "ui screenshot" in system.lower()


# =============================================================================
# 10. trace_id
# =============================================================================
class TestDescribeTraceID:
    """describe: trace_id threading."""

    def test_trace_id_in_success_response(self, mock_cfg, mock_llm, temp_image_file):
        """trace_id should appear in success response."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="describe", file_path=path, trace_id="trace-123")
        assert result["status"] == "success"
        assert result["trace_id"] == "trace-123"
        assert mock_llm.call.call_args[1]["trace_id"] == "trace-123"

    def test_trace_id_in_error_response(self, mock_cfg, mock_llm, temp_image_file):
        """trace_id should appear in error response."""
        mock_llm.call.return_value = make_mock_response(ok=False, error="boom")
        path = temp_image_file()
        result = vision(action="describe", file_path=path, trace_id="trace-456")
        assert result["status"] == "error"
        assert result["trace_id"] == "trace-456"

    def test_no_trace_id_when_not_provided(self, mock_cfg, mock_llm, temp_image_file):
        """trace_id should NOT be added when not provided."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="describe", file_path=path)
        assert result["status"] == "success"
        assert "trace_id" not in result


# =============================================================================
# 11. Deprecated `task` alias (backward compat with agent vision_delegate)
# =============================================================================
class TestDescribeTaskAlias:
    """describe: deprecated `task` parameter maps to action='describe' + question=task."""

    def test_task_alias_maps_to_describe(self, mock_cfg, mock_llm, temp_image_file):
        """Passing task= without action= should map to describe + question=task."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(task="Describe the colors", file_path=path)

        assert result["status"] == "success"
        assert result["action"] == "describe"

        # The task string should appear as the question text in user content.
        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Describe the colors" in b["text"] for b in text_blocks)

    def test_task_alias_ignored_when_action_set(self, mock_cfg, mock_llm, temp_image_file):
        """If action is set, task should be ignored (action takes priority)."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(action="describe", task="legacy task", file_path=path)

        assert result["status"] == "success"
        assert result["action"] == "describe"
        # When action is set, task is ignored — question defaults to empty
        # → the default instruction "Describe this image in detail." is used.
        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("Describe this image in detail." in b["text"] for b in text_blocks)

    def test_task_alias_with_explicit_question(self, mock_cfg, mock_llm, temp_image_file):
        """If task= and question= are both set, question wins."""
        mock_llm.call.return_value = make_mock_response(text="OK")
        path = temp_image_file()
        result = vision(task="legacy task", question="modern question", file_path=path)

        assert result["status"] == "success"
        user_content = mock_llm.call.call_args[1]["messages"][1]["content"]
        text_blocks = [b for b in user_content if b.get("type") == "text"]
        assert any("modern question" in b["text"] for b in text_blocks)
        # Legacy task should NOT appear
        assert not any("legacy task" in b["text"] for b in text_blocks if "Context:" not in b["text"])
