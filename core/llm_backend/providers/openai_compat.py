"""
core/llm_backend/providers/openai_compat.py — Generic OpenAI-compatible provider.

EXTRACTION NOTE (LLM Phase 1): Used for cloud APIs that implement the OpenAI spec
(OpenAI, DeepSeek, Mistral, Qwen, Kimi/Moonshot, Groq, etc.).
"""
from __future__ import annotations

import threading
from typing import Any, Optional
import httpx

from core.llm_backend.provider import BaseProvider

class OpenAICompatibleProvider(BaseProvider):
    """
    Generic OpenAI-compatible provider for cloud APIs.
    Supports API key authentication and custom base URLs.
    """
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, provider_name: str = "openai_compat") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = provider_name
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self) -> httpx.Client:
        """Return (or create) singleton client with API key auth."""
        if self._client is None or self._client.is_closed:
            with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(
                        base_url=self.base_url,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self.api_key}"
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
        payload: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        # v1.4: Native tool calling. Convert ToolDefinition list → OpenAI
        # tools format + add to payload. The response's tool_calls (if any)
        # are already in OpenAI shape (choices[0].message.tool_calls) — no
        # response-side conversion needed for OpenAI-compatible providers.
        if tools:
            from core.llm_backend.tools import to_openai_tools
            payload["tools"] = to_openai_tools(tools)
        # v1.2: JSON schema enforcement. Some cloud providers (OpenAI, DeepSeek)
        # support json_schema response_format. Others may not — they'll ignore
        # or error. Callers should use json_mode (not json_schema) for providers
        # with unknown schema support.
        # json_schema takes precedence over json_mode when both are set.
        # Hardening fix: use `is not None` (was truthy check — empty dict {} is falsy).
        # Hardening fix: payload.update(kwargs) moved BEFORE response_format
        # (was after — kwargs could silently override response_format).
        payload.update(kwargs)
        if json_schema is not None:
            # v1.3 (#42): Add `name` field to response_format for tracing.
            # OpenAI uses the name to identify structured-output requests in
            # their dashboard/tracing. Optional but recommended. Falls back to
            # the schema's `title` field, then to "structured_output".
            # Also set `strict: True` — OpenAI's strict mode guarantees the
            # response matches the schema (no extra keys, all required keys
            # present, no unsupported fields). DeepSeek/Mistral/Qwen ignore
            # `strict` but accept it without error.
            schema_name = (
                json_schema.get("title")
                if isinstance(json_schema, dict)
                else None
            ) or "structured_output"
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            }
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = self._get_client().post(
            "/chat/completions",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def is_available(self) -> bool:
        try:
            resp = self._get_client().get("/models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        """Close the singleton httpx client safely."""
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None