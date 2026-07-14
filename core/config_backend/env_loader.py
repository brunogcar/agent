"""core/config_backend/env_loader.py — .env discovery + provider/model resolution helpers.

[v1.0] Extracted from ``core/config.py`` as part of the config_backend split.

These two helpers are dependency-free (only stdlib + ``dotenv`` for type
references in docstrings). They are imported by ``core/config.py`` at module
level for the .env load, and by ``core/config_backend/models.py`` for
``_resolve_role()``.

Why these stay standalone:
    - ``_find_env_file()`` is used by both the module-level .env load in
      ``core/config.py`` AND by ``Config.reload()``.
    - ``_resolve_role()`` is used only inside ``_init_models()``, but keeping
      it next to ``_find_env_file()`` groups all "interpret .env strings"
      logic in one place.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _find_env_file() -> Optional[Path]:
    """Walk up from this file's location until we find .env.

    Starting point is ``core/config_backend/env_loader.py``, so we begin at
    ``core/config_backend/`` and walk up to 5 parents. This still reaches the
    project root (``core/config_backend/`` → ``core/`` → root) within the
    first 2 hops, matching the pre-v1.0 behavior when this lived in
    ``core/config.py``.
    """
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
        env_path = candidate / ".env"
        if env_path.exists():
            return env_path
        candidate = candidate.parent
    return None


def _resolve_role(value: str) -> tuple[str, str]:
    """
    Resolves a single model string into (provider, model) dynamically from .env.
    - "openai" -> ("openai", os.getenv("OPENAI_BASE_MODEL", ""))
    - "qwen-qwen3.5-9b" -> ("qwen", "qwen-qwen3.5-9b")
    - "granite-4.0" -> ("lmstudio", "granite-4.0")
    - "" -> ("lmstudio", "")
    """
    if not value or not value.strip():
        return "lmstudio", ""

    val = value.strip()
    val_lower = val.lower()

    # EXACT MATCH ONLY for cloud providers. Prevents "qwen-3b" from misrouting.
    if val_lower in {"openai", "deepseek", "mistral", "qwen", "kimi"}:
        base_model_env = f"{val_lower.upper()}_BASE_MODEL"
        return val_lower, os.getenv(base_model_env, "")

    # Anything else is treated as a LOCAL model name.
    return "lmstudio", val
