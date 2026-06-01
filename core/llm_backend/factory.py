"""
core/llm_backend/factory.py — LLMClient composition root and lifecycle.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

import atexit

from core.config import cfg
from core.llm_backend.client import LLMClient
from core.llm_backend.providers.lmstudio import LMStudioProvider

def create_llm_client() -> LLMClient:
    """Instantiate and configure the global LLMClient."""
    client = LLMClient()
    
    # Register default local provider
    client.register_provider(
        "lmstudio",
        LMStudioProvider(cfg.lm_studio_base_url),
    )
    
    # TODO: Phase 2 will dynamically register OpenAI, DeepSeek, Mistral, etc. here
    # based on .env API keys.
    
    return client

def _cleanup_providers(client: LLMClient) -> None:
    """
    DeepSeek fix 2026-05-14: Proper atexit cleanup via llm singleton (not class method).
    Close all registered provider clients.
    """
    for provider in client._registry._providers.values():
        if hasattr(provider, 'close'):
            provider.close()

# We will wire the atexit registration in the facade once the singleton is created.