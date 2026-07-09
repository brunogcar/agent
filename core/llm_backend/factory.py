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
    
    # 1. Register default local provider
    client.register_provider(
        "lmstudio",
        LMStudioProvider(cfg.lm_studio_base_url),
    )
    
    # 2. Dynamically register Cloud Advisory Providers based on .env keys
    from core.llm_backend.providers.openai_compat import OpenAICompatibleProvider

    # OpenAI-compatible providers (same provider class, different base URLs)
    cloud_providers = [
        ("openai",   cfg.openai_api_key,   cfg.openai_base_url),
        ("deepseek", cfg.deepseek_api_key, cfg.deepseek_base_url),
        ("mistral",  cfg.mistral_api_key,  cfg.mistral_base_url),
        ("qwen",     cfg.qwen_api_key,     cfg.qwen_base_url),
        ("kimi",     cfg.kimi_api_key,     cfg.kimi_base_url),
        # v1.2.1: Additional OpenAI-compatible providers
        ("zai",      cfg.zai_api_key,      cfg.zai_base_url),
        ("mimo",     cfg.mimo_api_key,     cfg.mimo_base_url),
    ]

    for name, api_key, base_url in cloud_providers:
        if api_key:  # Only register if the key is present and not empty
            client.register_provider(
                name,
                OpenAICompatibleProvider(base_url=base_url, api_key=api_key, provider_name=name)
            )

    # v1.2.1: Native providers (NOT OpenAI-compatible — need dedicated provider classes)
    # Claude (Anthropic) — uses Anthropic Messages API
    if cfg.claude_api_key:
        from core.llm_backend.providers.anthropic import AnthropicProvider
        client.register_provider(
            "claude",
            AnthropicProvider(base_url=cfg.claude_base_url, api_key=cfg.claude_api_key)
        )

    # Gemini (Google) — uses Google Generative Language API
    if cfg.gemini_api_key:
        from core.llm_backend.providers.gemini import GeminiProvider
        client.register_provider(
            "gemini",
            GeminiProvider(base_url=cfg.gemini_base_url, api_key=cfg.gemini_api_key)
        )

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