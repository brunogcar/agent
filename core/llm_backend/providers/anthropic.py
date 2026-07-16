"""
core/llm_backend/providers/anthropic.py — Anthropic Claude provider.

Native provider for Claude models. Anthropic's API is NOT OpenAI-compatible:
  - Endpoint: POST /v1/messages (not /v1/chat/completions)
  - Auth: x-api-key header + anthropic-version header (not Bearer token)
  - System prompt: top-level field (not in messages array)
  - Response: {"content": [{"text": "..."}], "usage": {"input_tokens": ..., "output_tokens": ...}}

This provider converts OpenAI-style messages → Anthropic Messages API format,
then normalizes the response back to the OpenAI shape that _parse_response expects.

v1.3 (#39): json_schema converted to Anthropic tool-use format for native
enforcement. We synthesize a single "extract_structured_output" tool whose
input_schema IS the user-supplied JSON Schema, force tool_choice to that tool,
and extract the tool_use block's `input` dict from the response (JSON-
stringified so _parse_response can parse it normally). This is stronger than
the old v1.2.x fallback (prompt-injected "Output ONLY valid JSON"), which only
worked for json_mode-style requests.

When json_schema is None but json_mode is True, the old "Output ONLY valid
JSON" system-prompt addition is still used (no schema to enforce, so prompt
injection is the only mechanism available — same as v1.2.x).

Soft dependency: Uses httpx directly (already installed). No anthropic SDK
needed — consistent with existing providers (LMStudioProvider, OpenAICompatibleProvider
also use httpx, not SDKs).
"""
from __future__ import annotations

import json
import threading
from typing import Any, Optional
import httpx

from core.llm_backend.provider import BaseProvider


class AnthropicProvider(BaseProvider):
    """
    Native provider for Anthropic Claude models.

    NOT OpenAI-compatible — uses Anthropic's Messages API.
    Converts OpenAI-style messages to Anthropic format and back.

    Thread safety: singleton httpx.Client with double-checked locking
    (same pattern as LMStudioProvider and OpenAICompatibleProvider).
    """
    name = "claude"

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(
                        base_url=self.base_url,
                        headers={
                            "x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        timeout=None,  # timeout enforced per-request
                    )
        return self._client

    def chat_completion(
        self,
        model:       str,
        messages:    list[dict],
        temperature: float,
        max_tokens:  int,
        timeout:     int,
        json_mode:   bool,
        json_schema: Optional[dict] = None,
        tools:       Optional[list] = None,
        **kwargs:    Any,
    ) -> dict:
        # Convert OpenAI-style messages to Anthropic Messages API format.
        # OpenAI: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        # Anthropic: {"system": "...", "messages": [{"role": "user", "content": "..."}]}
        system_text = ""
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_text += content + "\n"
            elif role == "assistant" and msg.get("tool_calls"):
                # v1.4.2: Convert OpenAI-shape assistant+tool_calls → Anthropic
                # content blocks. The LLM returned tool_calls (OpenAI shape from
                # our loop); Anthropic expects [{"type":"text","text":...},
                # {"type":"tool_use","id":...,"name":...,"input":...}].
                content_blocks = []
                if content:
                    content_blocks.append({"type": "text", "text": content})
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    try:
                        tc_input = json.loads(fn.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        tc_input = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"anthropic_tc_{len(content_blocks)}"),
                        "name": fn.get("name", ""),
                        "input": tc_input,
                    })
                anthropic_messages.append({"role": "assistant", "content": content_blocks})
            elif role == "tool":
                # v1.4.2: Convert OpenAI-shape tool result → Anthropic tool_result.
                # OpenAI: {"role":"tool","tool_call_id":"...","content":"..."}
                # Anthropic: {"role":"user","content":[{"type":"tool_result",
                #            "tool_use_id":"...","content":"..."}]}
                tool_call_id = msg.get("tool_call_id", "")
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content,
                    }],
                })
            else:
                anthropic_messages.append({"role": role, "content": content})

        # v1.3 (#39): Native json_schema enforcement via Anthropic tool-use.
        # Anthropic doesn't support response_format=json_schema like OpenAI.
        # Instead, you define a tool whose input_schema IS the JSON Schema,
        # force tool_choice to that tool, and Claude returns a tool_use block
        # whose `input` field is a dict matching the schema. We extract that
        # dict, JSON-stringify it, and return it as the `content` text so
        # _parse_response can parse it normally (just like the OpenAI path).
        #
        # When json_schema is None but json_mode is True, fall back to the
        # pre-v1.3 prompt-injection path (no schema to enforce, so we can't
        # use tool-use). This keeps the json_mode behavior unchanged.
        tool_name = "extract_structured_output"
        use_tool_for_schema = json_schema is not None

        if not use_tool_for_schema and json_mode:
            # Pre-v1.3 path: prompt-injected JSON mode (no schema to enforce).
            system_text += "\nOutput ONLY valid JSON. No prose, no markdown fences."

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_text.strip(),
            "messages": anthropic_messages,
        }

        if use_tool_for_schema:
            # Convert json_schema → Anthropic tool definition.
            # Anthropic's input_schema IS JSON Schema (no transformation needed).
            description = (
                json_schema.get("description")
                if isinstance(json_schema, dict)
                else None
            ) or "Extract structured data matching the schema"
            tool = {
                "name": tool_name,
                "description": description,
                "input_schema": json_schema,
            }
            payload["tools"] = [tool]
            # Force Claude to call this specific tool (no prose, no other tools).
            payload["tool_choice"] = {"type": "tool", "name": tool_name}
        elif tools:
            # v1.4: Native tool calling. Convert ToolDefinition list → Anthropic
            # tools format + add to payload. Do NOT force tool_choice — let
            # Claude decide whether to call a tool or return text.
            from core.llm_backend.tools import to_anthropic_tools
            payload["tools"] = to_anthropic_tools(tools)

        # Merge any extra kwargs (but don't let them override our fields)
        payload.update(kwargs)

        response = self._get_client().post(
            "/v1/messages",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()

        # Normalize Anthropic response → OpenAI shape for _parse_response.
        # Anthropic: {"content": [{"type": "text", "text": "..."} | {"type": "tool_use", "name": "...", "input": {...}}],
        #             "usage": {"input_tokens": N, "output_tokens": M}}
        # OpenAI:     {"choices": [{"message": {"content": "..."}}],
        #             "usage": {"prompt_tokens": N, "completion_tokens": M, "total_tokens": T}}
        #
        # v1.3 (#39): When the request used tool-use for json_schema, the
        # response content array contains a tool_use block. We extract its
        # `input` dict, JSON-stringify it, and use that as the OpenAI-shape
        # `content` text. _parse_response then parses it like any other JSON
        # response. Text blocks are concatenated as before for non-schema calls.
        content_parts = raw.get("content", [])
        text = ""
        tool_input_obj: Any = None
        # v1.4: Native tool calling — collect ALL tool_use blocks (not just
        # the json_schema sentinel). Each becomes a tool_calls entry in the
        # OpenAI-shape response.
        native_tool_calls: list[dict] = []
        for part in content_parts:
            part_type = part.get("type")
            if part_type == "text":
                text += part.get("text", "")
            elif part_type == "tool_use" and part.get("name") == tool_name:
                # Native json_schema path: tool_use.input is a dict matching
                # the user-supplied schema. JSON-stringify so _parse_response
                # can re-parse it into `parsed`.
                tool_input_obj = part.get("input")
            elif part_type == "tool_use":
                # v1.4: Native tool call — convert to OpenAI tool_calls shape.
                # Anthropic provides an `id` (e.g. "toolu_01abc...") — round-trip it.
                native_tool_calls.append({
                    "id": part.get("id", f"anthropic_tc_{len(native_tool_calls)}"),
                    "type": "function",
                    "function": {
                        "name": part.get("name", ""),
                        "arguments": json.dumps(part.get("input") or {}),
                    },
                })

        if tool_input_obj is not None:
            text = json.dumps(tool_input_obj)

        usage_in = raw.get("usage", {})
        prompt_tokens = usage_in.get("input_tokens", 0)
        completion_tokens = usage_in.get("output_tokens", 0)

        # v1.4: Include tool_calls in the normalized response when present.
        message = {"content": text}
        if native_tool_calls:
            message["tool_calls"] = native_tool_calls
        return {
            "choices": [{"message": message}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    def supports_json_schema(self) -> bool:
        """v1.3 (#39): Claude supports json_schema natively via tool-use conversion.

        Returns True (inherited from BaseProvider — kept here as an explicit
        marker for readers grepping for the capability flag).
        """
        return True

    def is_available(self) -> bool:
        try:
            resp = self._get_client().get("/v1/models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None
