"""core/config.py — Single source of truth for all configuration.

[v1.0] Split: the monolithic ~430-line ``Config.__init__`` is now a thin
dispatcher that calls builder functions in ``core/config_backend/``. The
public surface (``Config`` class + ``cfg`` singleton) is unchanged — all
213 callers that do ``from core.config import cfg`` continue to work.

Uses pathlib throughout — works identically on Windows and Linux.
All values come from .env (loaded once at import time, BEFORE ``Config()``
is constructed).
Nothing is hardcoded except the .env file location discovery.

Other modules import from here:
    from core.config import cfg
    print(cfg.agent_root)
    print(cfg.planner_model)

The actual config-building logic lives in:
    core/config_backend/paths.py        — _init_paths(cfg)
    core/config_backend/providers.py    — _init_providers(cfg)
    core/config_backend/models.py       — _init_models(cfg)
    core/config_backend/services.py     — _init_services(cfg)
    core/config_backend/memory.py       — _init_memory(cfg)
    core/config_backend/execution.py    — _init_execution(cfg)
    core/config_backend/limits.py       — _init_limits(cfg)
    core/config_backend/security.py     — _init_security(cfg)
    core/config_backend/validators.py   — _validate_config(cfg)  (range checks)
    core/config_backend/validation.py   — validate_config()       (startup)
    core/config_backend/env_loader.py   — _find_env_file(), _resolve_role()
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from core.config_backend.env_loader import _find_env_file

# -- Locate and load .env ------------------------------------------------------
# MUST happen at module import time, BEFORE Config() is constructed, so the
# env vars are visible to the builders. load_dotenv(override=True) is the
# [BUGFIX-CONFIG] fix for Windows env var shadowing — .env wins over OS env.
_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file, override=True)


# -- Config class --------------------------------------------------------------
class Config:
    """
    Centralised config. All paths are pathlib.Path objects.
    Access via the module-level `cfg` singleton.

    [v1.0] __init__ is a thin dispatcher — actual attribute setup lives in
    the per-section builders under core/config_backend/. The builders are
    imported lazily inside __init__ to avoid a circular import
    (config_backend.validation imports core.config for the cfg singleton).
    """
    def __init__(self) -> None:
        # Lazy imports inside __init__ avoid the circular dependency between
        # core.config (this module) and core.config_backend.validation (which
        # imports `cfg` from core.config at module load time). They also keep
        # the import cost out of module-import time — only paid when Config()
        # is actually instantiated.
        from core.config_backend.paths import _init_paths
        from core.config_backend.providers import _init_providers
        from core.config_backend.models import _init_models
        from core.config_backend.services import _init_services
        from core.config_backend.memory import _init_memory
        from core.config_backend.execution import _init_execution
        from core.config_backend.limits import _init_limits
        from core.config_backend.security import _init_security
        from core.config_backend.validators import _validate_config

        # Builders set attributes on self in section order. The order matters:
        # models.py reads cfg.lm_studio_base_url set by providers.py, and
        # validators.py reads attributes set by every prior builder.
        _init_paths(self)
        _init_providers(self)
        _init_models(self)
        _init_services(self)
        _init_memory(self)
        _init_execution(self)
        _init_limits(self)
        _init_security(self)
        _validate_config(self)

    def ensure_dirs(self) -> None:
        """Create all required directories if they don't exist."""
        dirs = [
            self.memory_root, self.memory_chroma_path, self.workspace_root,
            self.workspace_autocode, self.workspace_index, self.log_path, self.agent_log_path, self.sleep_learn_log_path,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def resolve_agent_path(self, relative: str) -> Path:
        clean = relative.replace("\\", "/").lstrip("/")
        target = (self.agent_root / clean).resolve()
        try:
            target.relative_to(self.agent_root.resolve())
        except ValueError as e:
            raise PermissionError(f"Path '{relative}' resolves outside AGENT_ROOT") from e
        return target

    def resolve_workspace_path(self, relative: str) -> Path:
        # [Bug #1] Path traversal guard — mirrors resolve_agent_path.
        # Without this, a path like '../../secrets.txt' escapes the workspace
        # sandbox. The agent_root version (above) has this check; the workspace
        # version was missing it.
        clean = relative.replace("\\", "/").lstrip("/")
        target = (self.workspace_root / clean).resolve()
        try:
            target.relative_to(self.workspace_root.resolve())
        except ValueError as e:
            raise PermissionError(
                f"Path '{relative}' resolves outside WORKSPACE_ROOT"
            ) from e
        return target

    def is_protected(self, path: str | Path) -> bool:
        """Check if path matches protected file list (Cross-platform, bulletproof)."""
        try:
            target = Path(path).resolve()
            agent_root_resolved = self.agent_root.resolve()

            # 1. Check absolute path match (Handles OS-specific case sensitivity natively)
            for pf in self.protected_files:
                protected_path = (agent_root_resolved / pf).resolve()
                if target == protected_path:
                    return True

            # 2. Fallback: Check if target matches the protected file anywhere (e.g., symlinks)
            # Use os.path.normcase for cross-platform safety (lowercases on Windows, no-op on Linux)
            target_name = os.path.normcase(target.name)
            for pf in self.protected_files:
                if target_name == os.path.normcase(Path(pf).name):
                    if target == (agent_root_resolved / pf).resolve():
                        return True
        except (ValueError, OSError, RuntimeError):
            pass

        return False

    def reload(self) -> None:
        """Re-read .env and rebuild model_registry. Call after changing .env.

        NOTE: This is NOT atomic. Concurrent reads during reload may see
        a partially-updated config (e.g., new planner_model but old executor_model).
        This is acceptable for a single-operator local agent where reloads happen
        at controlled times, not mid-request. Do not call during active inference.
        """
        _env_file = _find_env_file()
        if _env_file:
            load_dotenv(_env_file, override=True)
        self.__init__()

    def __repr__(self) -> str:
        return (
            f"Config(env={self.env!r}, agent_root={self.agent_root}, "
            f"planner={self.planner_model!r}, executor={self.executor_model!r})"
        )

# -- Singleton -----------------------------------------------------------------
cfg = Config()
