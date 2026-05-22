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
def _find_env_file() -> Optional[Path]:
    """Walk up from this file's location until we find .env"""
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
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
        _here = Path(__file__).resolve().parent.parent
        self.agent_root     = Path(os.getenv("AGENT_ROOT",     str(_here)))
        self.workspace_root = Path(os.getenv("WORKSPACE_ROOT", str(_here / "workspace")))
        self.memory_root    = Path(os.getenv("MEMORY_ROOT",    str(_here / "memory_db")))

        self.memory_chroma_path = self.memory_root / "chroma"
        self.memory_db_path     = self.memory_root / "agent.db"
        self.task_db_path       = self.memory_root / "task.db"
        self.workspace_autocode = self.workspace_root / "autocode"
        self.workspace_index    = self.workspace_root / ".index"
        self.log_path           = self.agent_root / "logs"

        # ── LM Studio ─────────────────────────────────────────────────────────
        self.lm_studio_base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")

        # ── Model roles ───────────────────────────────────────────────────────
        self.planner_model  = os.getenv("PLANNER_MODEL")
        if not self.planner_model:
            raise RuntimeError("PLANNER_MODEL is required in .env")
        self.executor_model = os.getenv("EXECUTOR_MODEL") or self.planner_model
        self.router_model   = os.getenv("ROUTER_MODEL") or self.planner_model
        self.vision_model   = os.getenv("VISION_MODEL") or self.planner_model

        self.model_registry: dict[str, dict] = {
            "planner": {
                "model":    self.planner_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("PLANNER_TIMEOUT", "90")),
            },
            "executor": {
                "model":    self.executor_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("EXECUTOR_TIMEOUT", "120")),
            },
            "router": {
                "model":    self.router_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("ROUTER_TIMEOUT", "15")),
            },
            "vision": {
                "model":    self.vision_model,
                "base_url": self.lm_studio_base_url,
                "timeout":  int(os.getenv("VISION_TIMEOUT", "60")),
            },
        }

        # ── External services ─────────────────────────────────────────────────
        self.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")

        # ── Memory tuning ─────────────────────────────────────────────────────
        self.memory_delete_threshold = float(os.getenv("MEMORY_DELETE_THRESHOLD", "0.4"))
        self.memory_decay_days       = int(os.getenv("MEMORY_DECAY_DAYS", "30"))
        self.memory_top_k            = int(os.getenv("MEMORY_TOP_K", "5"))

        # ── Tool & System Limits (P2: Centralized Magic Numbers) ──────────────
        # Memory Tool Limits
        self.max_memory_bytes  = int(os.getenv("MAX_MEMORY_BYTES", "50000"))  # 50KB
        self.max_tags_per_entry = int(os.getenv("MAX_TAGS_PER_ENTRY", "6"))
        self.max_tag_length    = int(os.getenv("MAX_TAG_LENGTH", "50"))
        
        # Web Tool Limits
        self.web_max_text_chars    = int(os.getenv("WEB_MAX_TEXT_CHARS", "8000"))
        self.web_snippet_chars    = int(os.getenv("WEB_SNIPPET_CHARS", "300"))
        self.web_max_search_results = int(os.getenv("WEB_MAX_SEARCH_RESULTS", "10"))
        
        # CLI Tool Limits
        self.cli_max_command_length = int(os.getenv("CLI_MAX_COMMAND_LENGTH", "1024"))
        self.cli_max_arguments      = int(os.getenv("CLI_MAX_ARGUMENTS", "20"))
        
        # File Tool Limits
        self.file_max_read_chars = int(os.getenv("FILE_MAX_READ_CHARS", "50000"))

        # ── Execution & Autocode ──────────────────────────────────────────────
        self.execution_timeout = int(os.getenv("EXECUTOR_TIMEOUT", "120"))
        self.sandbox_timeout   = int(os.getenv("SANDBOX_TIMEOUT", "30"))
        self.autocode_max_retries    = int(os.getenv("AUTOCODE_MAX_RETRIES", "3"))
        self.autocode_max_file_chars = int(os.getenv("AUTOCODE_MAX_FILE_CHARS", "6000"))
        self.autocode_debug          = os.getenv("AUTOCODE_DEBUG", "0") == "1"

        # ── Timeouts ──────────────────────────────────────────────────────────
        self.planner_timeout = int(os.getenv("PLANNER_TIMEOUT", "180"))
        self.router_timeout = int(os.getenv("ROUTER_TIMEOUT", "60"))
        self.autocode_graph_timeout = int(os.getenv("AUTOCODE_GRAPH_TIMEOUT", "300"))
        self.max_retries = int(os.getenv("AUTOCODE_MAX_RETRIES", "3"))

        # Validations
        assert self.autocode_max_retries > 0, "AUTOCODE_MAX_RETRIES must be > 0"
        assert self.autocode_max_file_chars > 0, "AUTOCODE_MAX_FILE_CHARS must be > 0"

        _node_timeouts = [self.planner_timeout, self.execution_timeout, self.router_timeout]
        if self.autocode_graph_timeout < max(_node_timeouts):
            raise ValueError("AUTOCODE_GRAPH_TIMEOUT must be >= max(node timeouts)")

        if not self.agent_root.is_absolute():
            raise ValueError("AGENT_ROOT must be an absolute path")
        if not self.agent_root.exists():
            raise FileNotFoundError(f"AGENT_ROOT not found: {self.agent_root}")

        # ── Protected files ───────────────────────────────────────────────────
        self.protected_files: frozenset[str] = frozenset({
            "server.py", "registry.py",
            "core/config.py", "core/tracer.py",
            "core/llm.py", "core/memory.py", "core/gateway.py",
        })

        # ── Gateway ───────────────────────────────────────────────────────────
        self.gateway_host   = os.getenv("GATEWAY_HOST", "127.0.0.1")
        self.gateway_port   = int(os.getenv("GATEWAY_PORT", "8000"))
        self.gateway_secret = os.getenv("GATEWAY_SECRET", "changeme")

        # ── Environment ───────────────────────────────────────────────────────
        self.env        = os.getenv("ENV", "development")
        self.is_dev     = self.env == "development"
        self.is_windows = os.name == "nt"

    def ensure_dirs(self) -> None:
        """Create all required directories if they don't exist."""
        dirs = [
            self.memory_root, self.memory_chroma_path, self.workspace_root,
            self.workspace_autocode, self.workspace_index, self.log_path,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def resolve_agent_path(self, relative: str) -> Path:
        clean = relative.replace("\\", "/").lstrip("/")
        return (self.agent_root / clean).resolve()

    def resolve_workspace_path(self, relative: str) -> Path:
        clean = relative.replace("\\", "/").lstrip("/")
        return (self.workspace_root / clean).resolve()

    def is_protected(self, path: str | Path) -> bool:
        name = Path(path).name
        rel = str(path).replace("\\", "/").lstrip("/")
        return name in self.protected_files or rel in self.protected_files

    def __repr__(self) -> str:
        return (
            f"Config(env={self.env!r}, agent_root={self.agent_root}, "
            f"planner={self.planner_model!r}, executor={self.executor_model!r})"
        )

# ── Singleton ─────────────────────────────────────────────────────────────────
cfg = Config()