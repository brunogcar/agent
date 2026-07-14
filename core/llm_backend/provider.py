"""
core/llm_backend/provider.py — Provider abstraction and registry.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

class BaseProvider(ABC):
    """
    Abstract LLM provider. Implement this to add a new backend.
    Subclass, implement chat_completion(), register in ProviderRegistry.
    """
    name: str = "base"

    @abstractmethod
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
    ) -> dict: ...

    def is_available(self) -> bool:
        return True

    def supports_json_schema(self) -> bool:
        """[v1.3 #41] Return True if this provider natively supports json_schema enforcement.

        All providers now support json_schema natively (v1.3):
        - OpenAI-compatible: response_format with json_schema (v1.2)
        - Claude: Anthropic tool-use conversion (v1.3 #39)
        - Gemini: responseSchema conversion (v1.3 #40)
        - LM Studio: outlines-based enforcement (v1.2)

        Callers can check this before passing json_schema to gracefully
        degrade when a future provider doesn't support it.
        """
        return True

class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> BaseProvider:
        if name not in self._providers:
            raise KeyError(
                f"Provider '{name}' not registered. "
                f"Available: {list(self._providers.keys())}"
            )
        return self._providers[name]

    def available(self) -> list[str]:
        return list(self._providers.keys())
