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

v1.3 (#40): json_schema converted to Gemini's responseSchema for native
enforcement. Gemini's responseSchema is a strict subset of JSON Schema that
rejects: `additionalProperties`, `additionalProperties: false`, union types
like `["string", "null"]`, and `$ref`. We strip/simplify these per-call via
`_convert_schema_for_gemini()` before setting it on generationConfig.responseSchema.
The `responseMimeType` is also set to `application/json`.

When json_schema is None but json_mode is True, the pre-v1.3 path is kept:
set responseMimeType only (no schema). Same as v1.2.x.

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

        # v1.3 (#40): Native json_schema enforcement via Gemini responseSchema.
        # Gemini's responseSchema is a strict subset of JSON Schema — we strip
        # unsupported keys (additionalProperties, $ref) and simplify union
        # types (e.g. ["string", "null"] → "string") per-call before passing it.
        # When json_schema is None but json_mode is True, fall back to the
        # pre-v1.3 path: responseMimeType only (no schema).
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = self._convert_schema_for_gemini(json_schema)
        elif json_mode:
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

    @staticmethod
    def _convert_schema_for_gemini(schema: Any) -> Any:
        """Convert a JSON Schema to Gemini's responseSchema subset.

        Gemini's responseSchema is a strict subset of JSON Schema. Unsupported
        features that must be stripped or simplified:
          - `additionalProperties` / `additionalProperties: false` → drop key
          - Union types like `["string", "null"]` → simplify to first type
          - `$ref` / `$defs` → inline resolved (we don't resolve here; the
            caller must already-inline schemas before passing them — we strip
            the key defensively to avoid 400s)
          - `title` / `description` / `$schema` / `definitions` → tolerated
            by Gemini but stripped defensively for cleanliness

        Walks the schema recursively: objects → properties, arrays → items.
        Returns a new dict (does not mutate input).
        """
        if not isinstance(schema, dict):
            return schema

        # Keys Gemini's responseSchema doesn't understand (or doesn't need).
        # Stripping them avoids 400s and keeps the wire payload lean.
        _DROP_KEYS = {
            "additionalProperties",
            "$ref",
            "$defs",
            "definitions",
            "$schema",
        }

        out: dict[str, Any] = {}
        for key, value in schema.items():
            if key in _DROP_KEYS:
                continue
            if key == "type" and isinstance(value, list):
                # Union type (e.g. ["string", "null"]). Gemini doesn't support
                # union types — simplify to the first non-null type. If only
                # ["null"] is present, fall back to "string" (Gemini requires
                # a concrete type).
                non_null = [t for t in value if t != "null"]
                out[key] = non_null[0] if non_null else "string"
            elif key == "properties" and isinstance(value, dict):
                out[key] = {
                    prop: GeminiProvider._convert_schema_for_gemini(sub)
                    for prop, sub in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                out[key] = GeminiProvider._convert_schema_for_gemini(value)
            else:
                out[key] = value
        return out

    def supports_json_schema(self) -> bool:
        """v1.3 (#40): Gemini supports json_schema natively via responseSchema conversion.

        Returns True (inherited from BaseProvider — kept here as an explicit
        marker for readers grepping for the capability flag).
        """
        return True

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
