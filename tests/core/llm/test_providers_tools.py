"""Provider-level tests for native tool calling (v1.5).

THESE ARE THE TESTS THAT SHOULD HAVE CAUGHT THE lmstudio.py BUG.

Unlike test_complete_with_tools.py (which mocks LLMClient.call — the provider
code never runs), these tests mock at the HTTP layer (httpx.MockTransport).
The provider code actually executes: builds the payload, converts ToolDefinition
to the provider's native format, calls json.dumps, and sends to the (faked)
HTTP endpoint. This catches:
- Missing tools parameter (the lmstudio.py bug)
- Serialization errors (ToolDefinition not JSON-serializable)
- Incorrect format conversion (wrong key names, wrong nesting)
- Response-side tool_calls extraction

The mock handler intercepts the HTTP request, inspects the payload, and returns
a canned response in the provider's native format. The test then verifies:
1. The payload has tools in the correct format
2. The response's tool_calls are correctly extracted
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.llm_backend.tools import ToolDefinition, tool_def_from_meta_tool
from core.llm_backend.providers.openai_compat import OpenAICompatibleProvider
from core.llm_backend.providers.lmstudio import LMStudioProvider
from core.llm_backend.providers.anthropic import AnthropicProvider
from core.llm_backend.providers.gemini import GeminiProvider


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_tool_def():
    """Build a simple ToolDefinition for testing."""
    fn = MagicMock()
    fn.__tool_metadata__ = {
        "actions": ["read_file", "list_directory"],
        "dispatch": {
            "read_file": {"help": "Read a file", "examples": []},
            "list_directory": {"help": "List a directory", "examples": []},
        },
    }
    return tool_def_from_meta_tool("file", fn)


def _mock_httpx_handler(response_json: dict, captured: dict):
    """Build an httpx.MockTransport handler that captures the request + returns canned response."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Capture the request payload for assertions
        captured["payload"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json=response_json)
    return handler


def _make_provider_with_mock(provider_class, response_json, captured, base_url="https://api.test.com", api_key="test-key", **kwargs):
    """Create a provider with its httpx client patched to use MockTransport."""
    handler = _mock_httpx_handler(response_json, captured)
    transport = httpx.MockTransport(handler)
    # Create the provider, then replace its _get_client to return a mock client
    if provider_class == OpenAICompatibleProvider:
        provider = provider_class(base_url, api_key, provider_name="test")
    elif provider_class == LMStudioProvider:
        provider = provider_class(base_url)  # LMStudioProvider takes only base_url
    elif provider_class == AnthropicProvider:
        provider = provider_class(base_url, api_key)
    elif provider_class == GeminiProvider:
        provider = provider_class(base_url, api_key)
    else:
        provider = provider_class(base_url, api_key, **kwargs)

    mock_client = MagicMock()
    mock_client.post = lambda url, **kw: httpx.Response(200, json=response_json, request=httpx.Request("POST", url))
    # Actually use the transport-based client
    mock_client = httpx.Client(transport=transport, base_url=base_url)
    provider._get_client = lambda: mock_client
    provider._client = mock_client
    return provider


# ── OpenAI-compatible provider (also covers LM Studio — same format) ─────────

class TestOpenAICompatProviderTools:
    """Tests that OpenAI-compatible provider converts tools + extracts tool_calls."""

    def test_tools_in_payload(self):
        """Provider should add tools to the payload in OpenAI format."""
        captured = {}
        response = {"choices": [{"message": {"content": "Done"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        provider = _make_provider_with_mock(OpenAICompatibleProvider, response, captured)

        provider.chat_completion(
            model="test-model", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False,
            tools=[_make_tool_def()],
        )
        assert "tools" in captured["payload"]
        assert captured["payload"]["tools"][0]["type"] == "function"
        assert captured["payload"]["tools"][0]["function"]["name"] == "file"
        assert "action" in captured["payload"]["tools"][0]["function"]["parameters"]["properties"]

    def test_tool_calls_extracted_from_response(self):
        """Provider should extract tool_calls from the response (OpenAI shape)."""
        captured = {}
        response = {
            "choices": [{"message": {
                "content": "",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "file", "arguments": '{"action": "read_file", "path": "x.py"}'}}],
            }}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        provider = _make_provider_with_mock(OpenAICompatibleProvider, response, captured)
        result = provider.chat_completion(
            model="test-model", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False, tools=[_make_tool_def()],
        )
        msg = result["choices"][0]["message"]
        assert "tool_calls" in msg
        assert msg["tool_calls"][0]["function"]["name"] == "file"

    def test_no_tools_no_crash(self):
        """Provider works fine without tools (normal text completion)."""
        captured = {}
        response = {"choices": [{"message": {"content": "hello"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}}
        provider = _make_provider_with_mock(OpenAICompatibleProvider, response, captured)
        result = provider.chat_completion(
            model="test-model", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False,
        )
        assert "tools" not in captured["payload"]


class TestLMStudioProviderTools:
    """THE TEST THAT WOULD HAVE CAUGHT THE lmstudio.py BUG.

    LM Studio is OpenAI-compatible and is the default provider. Before v1.4.2,
    it didn't have a tools parameter, causing TypeError: ToolDefinition not
    JSON serializable.
    """

    def test_tools_in_payload(self):
        """LM Studio provider should add tools to the payload (same as OpenAI)."""
        captured = {}
        response = {"choices": [{"message": {"content": "Done"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        provider = _make_provider_with_mock(LMStudioProvider, response, captured)

        provider.chat_completion(
            model="test-model", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False,
            tools=[_make_tool_def()],
        )
        # If this assert passes, the lmstudio.py bug is fixed (tools are serialized)
        assert "tools" in captured["payload"]
        assert captured["payload"]["tools"][0]["type"] == "function"


# ── Anthropic provider ───────────────────────────────────────────────────────

class TestAnthropicProviderTools:
    """Tests that Anthropic provider converts tools + extracts tool_use + converts messages."""

    def test_tools_in_anthropic_format(self):
        """Anthropic uses input_schema (not parameters) + no type:function wrapper."""
        captured = {}
        response = {"content": [{"type": "text", "text": "Done"}], "usage": {"input_tokens": 10, "output_tokens": 5}}
        provider = _make_provider_with_mock(AnthropicProvider, response, captured)

        provider.chat_completion(
            model="claude-3-test", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False,
            tools=[_make_tool_def()],
        )
        assert "tools" in captured["payload"]
        assert captured["payload"]["tools"][0]["name"] == "file"
        assert "input_schema" in captured["payload"]["tools"][0]

    def test_tool_use_extracted(self):
        """Anthropic tool_use blocks → OpenAI-shape tool_calls."""
        captured = {}
        response = {
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "file", "input": {"action": "read_file", "path": "x.py"}},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        provider = _make_provider_with_mock(AnthropicProvider, response, captured)
        result = provider.chat_completion(
            model="claude-3-test", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False, tools=[_make_tool_def()],
        )
        msg = result["choices"][0]["message"]
        assert "tool_calls" in msg
        assert msg["tool_calls"][0]["function"]["name"] == "file"

    def test_assistant_tool_calls_message_conversion(self):
        """v1.4.2: assistant message with tool_calls → Anthropic tool_use content blocks."""
        captured = {}
        response = {"content": [{"type": "text", "text": "Done"}], "usage": {"input_tokens": 10, "output_tokens": 5}}
        provider = _make_provider_with_mock(AnthropicProvider, response, captured)

        provider.chat_completion(
            model="claude-3-test",
            messages=[
                {"role": "user", "content": "read x.py"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "file", "arguments": '{"action": "read_file"}'}}
                ]},
                {"role": "tool", "tool_call_id": "call_1", "content": '{"result": "file contents"}'},
            ],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False, tools=[_make_tool_def()],
        )
        # The assistant message should be converted to tool_use content blocks
        msgs = captured["payload"]["messages"]
        assistant_msg = next(m for m in msgs if m["role"] == "assistant")
        assert isinstance(assistant_msg["content"], list)
        tool_use_block = next(b for b in assistant_msg["content"] if b.get("type") == "tool_use")
        assert tool_use_block["name"] == "file"

        # The tool result should be converted to tool_result content block
        tool_msg = next(m for m in msgs if m["role"] == "user" and isinstance(m["content"], list))
        tool_result = next(b for b in tool_msg["content"] if b.get("type") == "tool_result")
        assert tool_result["tool_use_id"] == "call_1"


# ── Gemini provider ──────────────────────────────────────────────────────────

class TestGeminiProviderTools:
    """Tests that Gemini provider converts tools + extracts functionCall + converts messages."""

    def test_tools_in_gemini_format(self):
        """Gemini wraps in functionDeclarations."""
        captured = {}
        response = {"candidates": [{"content": {"parts": [{"text": "Done"}], "role": "model"}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}}
        provider = _make_provider_with_mock(GeminiProvider, response, captured)

        provider.chat_completion(
            model="gemini-test", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False,
            tools=[_make_tool_def()],
        )
        assert "tools" in captured["payload"]
        assert "functionDeclarations" in captured["payload"]["tools"][0]
        assert captured["payload"]["tools"][0]["functionDeclarations"][0]["name"] == "file"

    def test_function_call_extracted(self):
        """Gemini functionCall parts → OpenAI-shape tool_calls with synthetic IDs."""
        captured = {}
        response = {
            "candidates": [{"content": {"parts": [
                {"functionCall": {"name": "file", "args": {"action": "read_file", "path": "x.py"}}}
            ], "role": "model"}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
        }
        provider = _make_provider_with_mock(GeminiProvider, response, captured)
        result = provider.chat_completion(
            model="gemini-test", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False, tools=[_make_tool_def()],
        )
        msg = result["choices"][0]["message"]
        assert "tool_calls" in msg
        assert msg["tool_calls"][0]["function"]["name"] == "file"
        # Synthetic ID should start with gemini_tc_
        assert msg["tool_calls"][0]["id"].startswith("gemini_tc_")

    def test_tool_result_message_conversion(self):
        """v1.4: tool result → Gemini functionResponse with name lookup."""
        captured = {}
        response = {"candidates": [{"content": {"parts": [{"text": "Done"}], "role": "model"}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}}
        provider = _make_provider_with_mock(GeminiProvider, response, captured)

        provider.chat_completion(
            model="gemini-test",
            messages=[
                {"role": "user", "content": "read x.py"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "gemini_tc_0", "type": "function", "function": {"name": "file", "arguments": '{"action": "read_file"}'}}
                ]},
                {"role": "tool", "tool_call_id": "gemini_tc_0", "content": '{"result": "file contents"}'},
            ],
            temperature=0.5, max_tokens=100, timeout=30, json_mode=False, tools=[_make_tool_def()],
        )
        # The tool result should be converted to functionResponse
        contents = captured["payload"]["contents"]
        func_msg = next(c for c in contents if c.get("role") == "function")
        fr = func_msg["parts"][0]["functionResponse"]
        assert fr["name"] == "file"  # looked up from the preceding assistant message
        assert "result" in fr["response"]
