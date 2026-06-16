"""Unit tests for robust JSON extraction in _parse_response."""
from __future__ import annotations

import pytest
from core.llm_backend.client import LLMClient


class TestJSONExtraction:
    """Test the robust regex-based JSON parsing in _parse_response."""

    def test_clean_json(self):
        """Test parsing clean JSON without any wrapping."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value", "number": 42}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value", "number": 42}

    def test_json_in_markdown_fence(self):
        """Test parsing JSON wrapped in ```json code blocks."""
        raw = {
            "choices": [{"message": {"content": '```json\n{"key": "value"}\n```'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_in_generic_fence(self):
        """Test parsing JSON wrapped in ``` code blocks."""
        raw = {
            "choices": [{"message": {"content": '```\n{"key": "value"}\n```'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_with_conversational_prefix(self):
        """Test parsing JSON with text before it."""
        raw = {
            "choices": [{"message": {"content": 'Here is the result:\n{"key": "value"}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_with_conversational_suffix(self):
        """Test parsing JSON with text after it."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value"}\n\nHope this helps!'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"key": "value"}

    def test_json_with_surrounding_text(self):
        """Test parsing JSON with text before and after."""
        raw = {
            "choices": [{"message": {"content": 'Sure! Here you go:\n\n{"status": "success", "data": [1, 2, 3]}\n\nLet me know if you need anything else.'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == {"status": "success", "data": [1, 2, 3]}

    def test_nested_json_object(self):
        """Test parsing nested JSON structures."""
        raw = {
            "choices": [{"message": {"content": '{"outer": {"inner": "value"}, "array": [1, 2, {"nested": true}]}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed["outer"]["inner"] == "value"
        assert resp.parsed["array"][2]["nested"] is True

    def test_json_array(self):
        """Test parsing JSON arrays."""
        raw = {
            "choices": [{"message": {"content": '[1, 2, 3, {"key": "value"}]'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed == [1, 2, 3, {"key": "value"}]

    def test_malformed_json_graceful_failure(self):
        """Test that malformed JSON doesn't crash, just returns None."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value"'}}],  # Missing closing brace
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed is None  # Graceful degradation

    def test_no_json_in_response(self):
        """Test response with no JSON at all."""
        raw = {
            "choices": [{"message": {"content": 'This is just plain text with no JSON.'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert resp.parsed is None

    def test_json_mode_false_skips_parsing(self):
        """Test that json_mode=False skips JSON parsing entirely."""
        raw = {
            "choices": [{"message": {"content": '{"key": "value"}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=False)
        assert resp.ok is True
        assert resp.parsed is None  # Not parsed because json_mode=False
        assert resp.text == '{"key": "value"}'

    def test_json_with_backticks_in_string(self):
        """Test JSON containing backticks in string values."""
        raw = {
            "choices": [{"message": {"content": '{"code": "```python\\nprint(\\"hello\\")\\n```"}'}}],
            "usage": {}
        }
        resp = LLMClient._parse_response(raw, "executor", "test-model", 1.0, json_mode=True)
        assert resp.ok is True
        assert "```python" in resp.parsed["code"]
