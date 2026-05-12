"""
core/config.py — Single source of truth for all configuration.

Uses pathlib throughout — works identically on Windows and Linux.
All values come from .env (loaded once at import time).
Nothing is hardcoded except the .env file location discovery.

Other modules import from here:
    from core.config import cfg
    print(cfg.agent_root)
    print(cfg.planner_model)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Locate and load .env ──────────────────────────────────────────────────────
# Walk up from this file's location until we find .env
# This makes it work regardless of working directory
def _find_env_file() -> Optional[Path]:
    candidate = Path(__file__).resolve().parent
    for _ in range(5):  # search up to 5 levels up
        env_path = candidate / ".env"
        if env_path.exists():
            return env_path
        candidate = candidate.parent
    return None

_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file)


# ── Config class ──────────────────────────────────────────────────────────────

class Config:
    """
    Centralised config. All paths are pathlib.Path objects.
    Access via the module-level `cfg` singleton.
    """

    def __init__(self) -> None:
        # ── Paths ─────────────────────────────────────────────────────────────
        # Default paths are relative to agent root so they work on Linux
        # without D:/... paths. Set AGENT_ROOT etc in .env to override.
        _here = Path(__file__).resolve().parent.parent
        self.agent_root    = Path(os.getenv("AGENT_ROOT",     str(_here)))
        self.workspace_root= Path(os.getenv("WORKSPACE_ROOT", str(_here / "workspace")))
        self.memory_root   = Path(os.getenv("MEMORY_ROOT",    str(_here / "memory_db")))

        # Derived paths — never hardcoded anywhere else
        self.memory_chroma_path = self.memory_root / "chroma"
        self.memory_db_path     = self.memory_root / "agent.db"
        self.task_db_path       = self.memory_root / "task.db"
        self.workspace_autocode = self.workspace_root / "autocode"
        self.workspace_index    = self.workspace_root / ".index"  # FTS index (Phase 4)
        self.log_path           = self.agent_root / "logs"

        # ── LM Studio ──────────────────────────────────────────────────────────
        self.lm_studio_base_url = os.getenv(
            "LM_STUDIO_BASE_URL", "http://localhost:1234/v1"
        )

        # ── Model roles ────────────────────────────────────────────────────────
        self.planner_model  = os.getenv("PLANNER_MODEL")
        if not self.planner_model:
            raise RuntimeError("PLANNER_MODEL is required in .env")
        self.executor_model = os.getenv("EXECUTOR_MODEL") or self.planner_model
        self.router_model   = os.getenv("ROUTER_MODEL") or self.planner_model
        self.vision_model   = os.getenv("VISION_MODEL") or self.planner_model

        # Model registry — the single place that maps role → model string.
        # core/llm.py reads this; nothing else should reference model names directly.
        self.model_registry: dict[str, dict] = {
            "planner": {
                "model":    self.planner_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("PLANNER_TIMEOUT", str(90))),
            },
            "executor": {
                "model":    self.executor_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("EXECUTOR_TIMEOUT", str(120))),
            },
            "router": {
                "model":    self.router_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("ROUTER_TIMEOUT", str(15))),
            },
            "vision": {
                "model":    self.vision_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("VISION_TIMEOUT", str(60))),
            },
        }

        # ── External services ───────────────────────────────────────────────────
        self.searxng_url = os.getenv("SEARXNG_URL", "http://192.168.1.10:30053")

        # ── Memory tuning ──────────────────────────────────────────────────────
        self.memory_delete_threshold = float(os.getenv("MEMORY_DELETE_THRESHOLD", "0.4"))
        self.memory_decay_days       = int(os.getenv("MEMORY_DECAY_DAYS", "30"))
        self.memory_top_k            = int(os.getenv("MEMORY_TOP_K", "5"))

        # ── Execution ──────────────────────────────────────────────────────────
        self.execution_timeout = int(os.getenv("EXECUTION_TIMEOUT", "120"))
        self.sandbox_timeout   = int(os.getenv("SANDBOX_TIMEOUT", "30"))

        # ── Autocode ───────────────────────────────────────────────────────────
        self.autocode_max_retries    = int(os.getenv("AUTOCODE_MAX_RETRIES", "3"))
        self.autocode_max_file_chars = int(os.getenv("AUTOCODE_MAX_FILE_CHARS", "6000"))
        self.autocode_debug          = os.getenv("AUTOCODE_DEBUG", "0") == "1"

        # M8: validate tunables -- fail fast at startup rather than silently misbehave
        assert self.autocode_max_retries  > 0,  "AUTOCODE_MAX_RETRIES must be > 0"
        assert self.autocode_max_file_chars > 0, "AUTOCODE_MAX_FILE_CHARS must be > 0"

        # Protected files — autocode will never touch these
        self.protected_files: frozenset[str] = frozenset({
            "server.py", "registry.py",
            "core/config.py", "core/tracer.py",
            "core/llm.py",       # model dispatch -- corruption breaks all AI calls
            "memory/store.py",   # memory backend -- corruption breaks all recall
            "gateway/app.py",    # contains auth logic and secrets handling
        })

        # ── Gateway ────────────────────────────────────────────────────────────
        self.gateway_host   = os.getenv("GATEWAY_HOST", "127.0.0.1")
        self.gateway_port   = int(os.getenv("GATEWAY_PORT", "8000"))
        self.gateway_secret = os.getenv("GATEWAY_SECRET", "changeme")

        # ── Environment ────────────────────────────────────────────────────────
        self.env        = os.getenv("ENV", "development")
        self.is_dev     = self.env == "development"
        self.is_windows = os.name == "nt"

    def ensure_dirs(self) -> None:
        """Create all required directories if they don't exist. Call once at startup."""
        dirs = [
            self.memory_root,
            self.memory_chroma_path,
            self.workspace_root,
            self.workspace_autocode,
            self.workspace_index,
            self.log_path,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def resolve_agent_path(self, relative: str) -> Path:
        """
        Resolve a path relative to agent_root.
        Handles both forward and back slashes safely.
        Returns an absolute pathlib.Path.

        Example:
            cfg.resolve_agent_path("tools/memory.py")
            → Path("D:/mcp/agent/tools/memory.py")
        """
        # Normalise separators
        clean = relative.replace("\\", "/").lstrip("/")
        result = self.agent_root / clean
        return result.resolve()

    def resolve_workspace_path(self, relative: str) -> Path:
        """Resolve a path relative to workspace_root."""
        clean = relative.replace("\\", "/").lstrip("/")
        result = self.workspace_root / clean
        return result.resolve()

    def is_protected(self, path: str | Path) -> bool:
        """Check whether a file path is in the protected set."""
        name = Path(path).name
        # Also check relative path e.g. "core/config.py"
        rel = str(path).replace("\\", "/").lstrip("/")
        return name in self.protected_files or rel in self.protected_files

    def __repr__(self) -> str:
        return (
            f"Config(env={self.env!r}, agent_root={self.agent_root}, "
            f"planner={self.planner_model!r}, executor={self.executor_model!r})"
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
cfg = Config()
