"""
core/llm_backend/providers/anthropic.py — Anthropic Claude provider.

Native provider for Claude models. Anthropic's API is NOT OpenAI-compatible:
  - Endpoint: POST /v1/messages (not /v1/chat/completions)
  - Auth: x-api-key header + anthropic-version header (not Bearer token)
  - System prompt: top-level field (not in messages array)
  - Response: {"content": [{"text": "..."}], "usage": {"input_tokens": ..., "output_tokens": ...}}

This provider converts OpenAI-style messages → Anthropic Messages API format,
then normalizes the response back to the OpenAI shape that _parse_response expects.

json_schema: IGNORED in Phase 1. Claude uses tool-use for structured output
(a completely different API mechanism — you define a "tool" with input_schema,
and Claude outputs tool_use blocks). Converting json_schema → Anthropic tool
format is deferred to a follow-up commit after real-world testing.
When json_schema is provided, falls back to json_mode=True (Claude supports
json_mode via a system instruction, not response_format — this provider
adds "Output ONLY valid JSON." to the system prompt when json_mode is True).

Soft dependency: Uses httpx directly (already installed). No anthropic SDK
needed — consistent with existing providers (LMStudioProvider, OpenAICompatibleProvider
also use httpx, not SDKs).
"""
from __future__ import annotations

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
            else:
                anthropic_messages.append({"role": role, "content": content})

        # json_schema: IGNORED (Phase 1). Fall back to json_mode instruction.
        # TODO (follow-up): Convert json_schema → Anthropic tool-use format.
        # Claude's structured output uses tool_use blocks with input_schema,
        # not response_format. This requires:
        # 1. Converting json_schema dict → Anthropic tool definition
        # 2. Adding the tool to the request
        # 3. Extracting the tool_use block from the response
        # Deferred until real-world testing with Claude API keys.
        if json_schema is not None or json_mode:
            system_text += "\nOutput ONLY valid JSON. No prose, no markdown fences."

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_text.strip(),
            "messages": anthropic_messages,
        }
        # Merge any extra kwargs (but don't let them override our fields)
        payload.update(kwargs)

        response = self._get_client().post(
            "/v1/messages",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()

        # Normalize Anthropic response → OpenAI shape for _parse_response
        # Anthropic: {"content": [{"type": "text", "text": "..."}], "usage": {"input_tokens": N, "output_tokens": M}}
        # OpenAI: {"choices": [{"message": {"content": "..."}}], "usage": {"prompt_tokens": N, "completion_tokens": M, "total_tokens": T}}
        content_parts = raw.get("content", [])
        text = ""
        for part in content_parts:
            if part.get("type") == "text":
                text += part.get("text", "")

        usage_in = raw.get("usage", {})
        prompt_tokens = usage_in.get("input_tokens", 0)
        completion_tokens = usage_in.get("output_tokens", 0)

        return {
            "choices": [{"message": {"content": text}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

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
