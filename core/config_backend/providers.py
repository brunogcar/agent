"""core/config_backend/providers.py — Initialize API keys, base URLs, embeddings, runtime.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

Env vars read:
    Runtime (LM Studio / Ollama / vLLM):
        RUNTIME_PROVIDER         — default "lmstudio"
        LM_STUDIO_BASE_URL       — default http://localhost:1234/v1
        LM_STUDIO_RESTART_CMD    — default "" (empty)

    Embeddings (LM Studio /v1/embeddings endpoint):
        EMBEDDING_MODEL          — default "all-MiniLM-L6-v2-GGUF"
        EMBEDDING_BASE_URL       — default = LM_STUDIO_BASE_URL
        EMBEDDING_ENABLED        — default "true" (truthy: true/1/yes)

    Cloud advisory providers (OpenAI-compatible unless noted):
        OPENAI_API_KEY / OPENAI_BASE_URL
        DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL
        MISTRAL_API_KEY / MISTRAL_BASE_URL
        QWEN_API_KEY / QWEN_BASE_URL
        KIMI_API_KEY / KIMI_BASE_URL

    v1.2.1 additional providers:
        CLAUDE_API_KEY / CLAUDE_BASE_URL      — Anthropic (NOT OpenAI-compatible)
        GEMINI_API_KEY / GEMINI_BASE_URL      — Google (NOT OpenAI-compatible)
        ZAI_API_KEY / ZAI_BASE_URL            — Z.ai (OpenAI-compatible)
        MIMO_API_KEY / MIMO_BASE_URL          — MiMo (OpenAI-compatible)

    GitHub (for github tool):
        GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO
"""

from __future__ import annotations

import os


def _init_providers(cfg) -> None:
    """Initialize runtime provider, embeddings, cloud API keys, and GitHub config."""

    # -- Runtime Provider (LM Studio, Ollama, vLLM) ------------------------
    cfg.runtime_provider = os.getenv("RUNTIME_PROVIDER", "lmstudio").lower()
    cfg.lm_studio_base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    cfg.lm_studio_restart_cmd = os.getenv("LM_STUDIO_RESTART_CMD", "")

    # -- Embedding Model (for codebase vector indexing in understand workflow) --
    # Uses the LM Studio /v1/embeddings endpoint (OpenAI-compatible).
    # Download a GGUF embedding model (e.g. All-MiniLM-L6-v2-Embedding-GGUF)
    # in LM Studio, then set EMBEDDING_MODEL to the model name LM Studio shows.
    # Set EMBEDDING_ENABLED=false to disable vector indexing entirely.
    cfg.embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2-GGUF")
    cfg.embedding_base_url = os.getenv("EMBEDDING_BASE_URL", cfg.lm_studio_base_url)
    cfg.embedding_enabled = os.getenv("EMBEDDING_ENABLED", "true").lower() in ("true", "1", "yes")

    # -- Cloud Advisory Providers (OpenAI-Compatible APIs) -----------------
    # If the API key is present in .env, the provider is registered and available.
    # Comment out the key in .env to disable the provider.
    cfg.openai_api_key = os.getenv("OPENAI_API_KEY", "")
    cfg.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    cfg.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    cfg.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    cfg.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")
    cfg.mistral_base_url = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    cfg.qwen_api_key = os.getenv("QWEN_API_KEY", "")
    cfg.qwen_base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    cfg.kimi_api_key = os.getenv("KIMI_API_KEY", "")
    cfg.kimi_base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

    # v1.2.1: Additional cloud providers (Claude, Gemini, Z.ai, MiMo)
    # Claude (Anthropic) — NOT OpenAI-compatible, needs AnthropicProvider
    cfg.claude_api_key = os.getenv("CLAUDE_API_KEY", "")
    cfg.claude_base_url = os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com")

    # Gemini (Google) — NOT OpenAI-compatible, needs GeminiProvider
    cfg.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    cfg.gemini_base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")

    # Z.ai (GLM) — OpenAI-compatible, uses OpenAICompatibleProvider
    cfg.zai_api_key = os.getenv("ZAI_API_KEY", "")
    cfg.zai_base_url = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")

    # MiMo (Xiaomi AI Studio) — OpenAI-compatible, uses OpenAICompatibleProvider
    cfg.mimo_api_key = os.getenv("MIMO_API_KEY", "")
    cfg.mimo_base_url = os.getenv("MIMO_BASE_URL", "https://aistudio.xiaomimimo.com/v1")

    # GitHub API (for github tool — PR operations, push, issues, releases)
    cfg.github_token = os.getenv("GITHUB_TOKEN", "")
    cfg.github_owner = os.getenv("GITHUB_OWNER", "")
    cfg.github_repo = os.getenv("GITHUB_REPO", "")
