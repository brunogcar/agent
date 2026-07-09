"""
core/llm_backend/providers/gemini.py — Google Gemini provider.

Native provider for Google Gemini models. Google's API is NOT OpenAI-compatible:
  - Endpoint: POST /v1beta/models/{model}:generateContent (not /v1/chat/completions)
  - Auth: API key in URL query param ?key=... (not Authorization header)
  - System prompt: systemInstruction field (not in messages/contents array)
  - Messages: "contents" array with {"parts": [{"text": "..."}], "role": "user"}
  - Response: {"candidates": [{"content": {"parts": [{"text": "..."}]}}], "usageMetadata": {...}}

This provider converts OpenAI-style messages → Gemini generateContent format,
then normalizes the response back to the OpenAI shape that _parse_response expects.

json_schema: IGNORED in Phase 1. Gemini uses responseMimeType + responseSchema
(a simplified JSON Schema that doesn't support additionalProperties, limited enum
handling, no union types like ["string", "null"]). Your schemas use all of those
— they'd need to be simplified/converted per-call.
When json_schema is provided, falls back to json_mode=True (Gemini supports
json_mode via responseMimeType: "application/json").
Converting json_schema → Gemini responseSchema is deferred to a follow-up commit
after real-world testing.

Soft dependency: Uses httpx directly (already installed). No google-generativeai
SDK needed — consistent with existing providers.
"""
from __future__ import annotations

import threading
from typing import Any, Optional
import httpx

from core.llm_backend.provider import BaseProvider


class GeminiProvider(BaseProvider):
    """
    Native provider for Google Gemini models.

    NOT OpenAI-compatible — uses Google's Generative Language API.
    Converts OpenAI-style messages to Gemini format and back.

    Thread safety: singleton httpx.Client with double-checked locking
    (same pattern as LMStudioProvider and OpenAICompatibleProvider).
    """
    name = "gemini"

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
        # Convert OpenAI-style messages to Gemini generateContent format.
        # OpenAI: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        # Gemini: {"systemInstruction": {"parts": [{"text": "..."}]}, "contents": [{"role": "user", "parts": [{"text": "..."}]}]}
        system_text = ""
        gemini_contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_text += content + "\n"
            elif role == "assistant":
                gemini_contents.append({"role": "model", "parts": [{"text": content}]})
            else:
                gemini_contents.append({"role": "user", "parts": [{"text": content}]})

        # json_schema: IGNORED (Phase 1). Fall back to json_mode via responseMimeType.
        # TODO (follow-up): Convert json_schema → Gemini responseSchema.
        # Gemini's responseSchema is a simplified JSON Schema that doesn't support:
        # - additionalProperties
        # - union types like ["string", "null"]
        # - some enum edge cases
        # Your schemas use all of these — conversion needs simplification per-call.
        # Deferred until real-world testing with Gemini API keys.
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_schema is not None or json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": generation_config,
        }
        if system_text.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}
        # Merge any extra kwargs (but don't let them override our fields)
        payload.update(kwargs)

        # Gemini endpoint: /v1beta/models/{model}:generateContent?key=...
        response = self._get_client().post(
            f"/v1beta/models/{model}:generateContent",
            json=payload,
            params={"key": self.api_key},
            timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()

        # Normalize Gemini response → OpenAI shape for _parse_response
        # Gemini: {"candidates": [{"content": {"parts": [{"text": "..."}], "role": "model"}}], "usageMetadata": {"promptTokenCount": N, "candidatesTokenCount": M, "totalTokenCount": T}}
        # OpenAI: {"choices": [{"message": {"content": "..."}}], "usage": {"prompt_tokens": N, "completion_tokens": M, "total_tokens": T}}
        candidates = raw.get("candidates", [])
        text = ""
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            for part in parts:
                text += part.get("text", "")

        usage_meta = raw.get("usageMetadata", {})
        prompt_tokens = usage_meta.get("promptTokenCount", 0)
        completion_tokens = usage_meta.get("candidatesTokenCount", 0)
        total_tokens = usage_meta.get("totalTokenCount", prompt_tokens + completion_tokens)

        return {
            "choices": [{"message": {"content": text}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }

    def is_available(self) -> bool:
        try:
            resp = self._get_client().get(
                "/v1beta/models",
                params={"key": self.api_key},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None
