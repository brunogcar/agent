"""
core/runtime_providers.py — Provider-agnostic runtime abstraction.
Allows the watchdog to monitor and restart different local LLM servers
(LM Studio, Ollama, vLLM) without hardcoding provider-specific logic.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class RuntimeProvider(ABC):
    """Abstract base class for all runtime providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
        
    @property
    @abstractmethod
    def health_url(self) -> str:
        """The URL to probe for readiness."""
        pass
        
    @property
    @abstractmethod
    def default_restart_cmd(self) -> str:
        """The default CLI command to restart the server."""
        pass
        
    @abstractmethod
    def is_ready(self, json_data: dict) -> bool:
        """Verify the JSON response from health_url indicates models are loaded."""
        pass

class LMStudioProvider(RuntimeProvider):
    @property
    def name(self) -> str:
        return "lmstudio"
        
    @property
    def health_url(self) -> str:
        from core.config import cfg
        return f"{cfg.lm_studio_base_url}/models"
        
    @property
    def default_restart_cmd(self) -> str:
        return "lms server start"
        
    def is_ready(self, json_data: dict) -> bool:
        # LM Studio returns {"data": [{"id": "model_name", ...}]}
        return bool(json_data.get("data"))

class OllamaProvider(RuntimeProvider):
    @property
    def name(self) -> str:
        return "ollama"
        
    @property
    def health_url(self) -> str:
        return "http://localhost:11434/api/tags"
        
    @property
    def default_restart_cmd(self) -> str:
        return "ollama serve"
        
    def is_ready(self, json_data: dict) -> bool:
        # Ollama returns {"models": [{"name": "model_name", ...}]}
        return bool(json_data.get("models"))

class VLLMProvider(RuntimeProvider):
    @property
    def name(self) -> str:
        return "vllm"
        
    @property
    def health_url(self) -> str:
        return "http://localhost:8000/v1/models"
        
    @property
    def default_restart_cmd(self) -> str:
        return "vllm serve"
        
    def is_ready(self, json_data: dict) -> bool:
        return bool(json_data.get("data"))

_PROVIDERS = {
    "lmstudio": LMStudioProvider,
    "ollama": OllamaProvider,
    "vllm": VLLMProvider,
}

def get_provider(name: str) -> RuntimeProvider:
    """Factory function to get a provider instance."""
    provider_cls = _PROVIDERS.get(name.lower())
    if not provider_cls:
        logger.warning(f"Unknown provider '{name}', falling back to lmstudio")
        return LMStudioProvider()
    return provider_cls()