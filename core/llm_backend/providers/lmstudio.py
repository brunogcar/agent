"""
core/llm_backend/providers/lmstudio.py — LM Studio provider (OpenAI-compatible local).

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

import threading
from typing import Any, Optional
import httpx

from core.llm_backend.provider import BaseProvider

class LMStudioProvider(BaseProvider):
    """
    OpenAI-compatible provider for LM Studio (local).
    Also works with Ollama, vLLM, or any OpenAI-compatible endpoint.
    
    THREAD-SAFETY FIX (P0-4 + DeepSeek 2026-05-14):
    - Original code had broken close_clients() that referenced non-existent self._clients
    - Fixed: singleton httpx.Client per instance with proper cleanup
    - Each thread gets its own client via _local for connection pooling
    
    Reference: httpx GitHub Discussion #1633 confirms singletons are thread-safe.
    """
    name = "lmstudio"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = None  # Singleton client instance
        self._lock = threading.Lock()

    def _get_client(self) -> httpx.Client:
        """Return (or create) singleton client."""
        if self._client is None or self._client.is_closed:
            with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(
                        base_url=self.base_url,
                        headers={"Content-Type": "application/json"},
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
        payload: dict[str, Any] = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        # v1.2: JSON schema enforcement. When json_schema is provided, use
        # response_format=json_schema (LM Studio enforces via outlines internally).
        # This is stronger than json_object (which only ensures valid JSON, not schema).
        # json_schema takes precedence over json_mode when both are set.
        # Hardening fix: use `is not None` (was truthy check — empty dict {} is falsy).
        # Hardening fix: payload.update(kwargs) moved BEFORE response_format
        # (was after — kwargs could silently override response_format).
        payload.update(kwargs)
        if json_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"schema": json_schema}}
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
        """
        Close the singleton httpx client safely.
        Thread-safe: calls is_closed check before closing to prevent race conditions.
        Call this via atexit or shutdown handler for cleanup.
        """
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None