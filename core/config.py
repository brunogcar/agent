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
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# -- Locate and load .env ------------------------------------------------------
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


# -- Intelligent Provider & Model Resolution -----------------------------
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


# -- Config class --------------------------------------------------------------
class Config:
    """
    Centralised config. All paths are pathlib.Path objects.
    Access via the module-level `cfg` singleton.
    """
    def __init__(self) -> None:
        # -- Paths -------------------------------------------------------------
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
        self.agent_log_path     = self.log_path / "agent"
        self.sleep_learn_log_path = self.log_path / "sleep_learn"

        # -- Runtime Provider (LM Studio, Ollama, vLLM) ------------------------
        self.runtime_provider = os.getenv("RUNTIME_PROVIDER", "lmstudio").lower()
        self.lm_studio_base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        self.lm_studio_restart_cmd = os.getenv("LM_STUDIO_RESTART_CMD", "")

        # -- Cloud Advisory Providers (OpenAI-Compatible APIs) -----------------
        # If the API key is present in .env, the provider is registered and available.
        # Comment out the key in .env to disable the provider.
        self.openai_api_key   = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url  = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
        self.deepseek_api_key  = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    
        self.mistral_api_key   = os.getenv("MISTRAL_API_KEY", "")
        self.mistral_base_url  = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    
        self.qwen_api_key      = os.getenv("QWEN_API_KEY", "")
        self.qwen_base_url     = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
        self.kimi_api_key      = os.getenv("KIMI_API_KEY", "")
        self.kimi_base_url     = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

        # -- Model roles -------------------------------------------------------
        planner_raw = os.getenv("PLANNER_MODEL")
        if not planner_raw:
            raise RuntimeError("PLANNER_MODEL is required in .env")

        executor_raw = os.getenv("EXECUTOR_MODEL") or planner_raw
        router_raw   = os.getenv("ROUTER_MODEL") or planner_raw
        vision_raw   = os.getenv("VISION_MODEL") or planner_raw
        consultor_raw = os.getenv("CONSULTOR_MODEL", "").strip()

        # Resolve provider and model automatically for each role
        planner_prov, planner_mod   = _resolve_role(planner_raw)
        executor_prov, executor_mod = _resolve_role(executor_raw)
        router_prov, router_mod     = _resolve_role(router_raw)
        vision_prov, vision_mod     = _resolve_role(vision_raw)
        consultor_prov, consultor_mod = _resolve_role(consultor_raw)

        self.planner_model   = planner_mod
        self.executor_model  = executor_mod
        self.router_model    = router_mod
        self.vision_model    = vision_mod
        self.consultor_model = consultor_mod

        self.model_registry: dict[str, dict] = {
            "planner": {
                "model":    planner_mod,
                "provider": planner_prov,
                "base_url": self.lm_studio_base_url if planner_prov == "lmstudio" else os.getenv(f"{planner_prov.upper()}_BASE_URL", ""),
                "timeout":  int(os.getenv("PLANNER_TIMEOUT", "180")),
            },
            "executor": {
                "model":    executor_mod,
                "provider": executor_prov,
                "base_url": self.lm_studio_base_url if executor_prov == "lmstudio" else os.getenv(f"{executor_prov.upper()}_BASE_URL", ""),
                "timeout":  int(os.getenv("EXECUTOR_TIMEOUT", "120")),
            },
            "router": {
                "model":    router_mod,
                "provider": router_prov,
                "base_url": self.lm_studio_base_url if router_prov == "lmstudio" else os.getenv(f"{router_prov.upper()}_BASE_URL", ""),
                "timeout":  int(os.getenv("ROUTER_TIMEOUT", "15")),
            },
            "vision": {
                "model":    vision_mod,
                "provider": vision_prov,
                "base_url": self.lm_studio_base_url if vision_prov == "lmstudio" else os.getenv(f"{vision_prov.upper()}_BASE_URL", ""),
                "timeout":  int(os.getenv("VISION_TIMEOUT", "60")),
            },
        }

        # Add consultor to registry ONLY if a model is explicitly resolved
        if consultor_mod:
            self.model_registry["consultor"] = {
                "model":    consultor_mod,
                "provider": consultor_prov,
                "base_url": self.lm_studio_base_url if consultor_prov == "lmstudio" else os.getenv(f"{consultor_prov.upper()}_BASE_URL", ""),
                "timeout":  int(os.getenv("CONSULTOR_TIMEOUT", "60")),
            }

        # -- External services -------------------------------------------------
        self.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")

        # -- Memory tuning -----------------------------------------------------
        self.memory_delete_threshold = float(os.getenv("MEMORY_DELETE_THRESHOLD", "0.4"))
        self.memory_decay_days       = int(os.getenv("MEMORY_DECAY_DAYS", "30"))
        self.memory_top_k            = int(os.getenv("MEMORY_TOP_K", "5"))

        # -- Memory Diversity (Phase 6) ----------------------------------------
        self.diversity_distance_threshold = float(os.getenv("DIVERSITY_DISTANCE_THRESHOLD", "0.12"))
        self.archive_age_days             = int(os.getenv("ARCHIVE_AGE_DAYS", "30"))
        self.purge_age_days               = int(os.getenv("PURGE_AGE_DAYS", "90"))

        # -- Context Budgeting (Phase 5) ---------------------------------------
        # Max tokens for the input context window (leaves room for output)
        self.max_context_tokens  = int(os.getenv("MAX_CONTEXT_TOKENS", "8000"))

        # -- Parallel Execution (Phase 7) --------------------------------------
        self.max_concurrent_workers = int(os.getenv("MAX_CONCURRENT_WORKERS", "3"))
        self.max_concurrent_inferences = int(os.getenv("MAX_CONCURRENT_INFERENCES", "2"))
        self.worker_timeout = int(os.getenv("WORKER_TIMEOUT", "60"))
        self.worker_max_tokens = int(os.getenv("WORKER_MAX_TOKENS", "250"))
    
        # -- Tool  & System Limits (P2: Centralized Magic Numbers) --------------
        
        # Memory Tool Limits
        # Renamed from max_memory_bytes to memory_max_entry_bytes (D1 Option B consensus)
        # to clarify this is per-entry, not total storage limit
        self.memory_max_entry_bytes = int(os.getenv("MAX_MEMORY_BYTES", "50000"))  # 50KB per entry
        self.max_tags_per_entry     = int(os.getenv("MAX_TAGS_PER_ENTRY", "6"))
        self.max_tag_length         = int(os.getenv("MAX_TAG_LENGTH", "50"))
        
        # Web Tool Limits
        # NOTE: 8000 chars (~2-3k tokens) is a conservative default to prevent
        # context overflow in existing workflows that depend on this value.
        # Override in .env if you need larger pages.
        self.web_max_text_chars      = int(os.getenv("WEB_MAX_TEXT_CHARS", "8000"))
        self.web_snippet_chars      = int(os.getenv("WEB_SNIPPET_CHARS", "300"))
        self.web_max_search_results = int(os.getenv("WEB_MAX_SEARCH_RESULTS", "10"))
        
        # CLI Tool Limits
        # 4096 matches typical terminal buffer sizes; 1024 was too restrictive
        # for real-world commands like `git log --oneline` or complex pipelines.
        self.cli_max_command_chars = int(os.getenv("CLI_MAX_COMMAND_LENGTH", "4096"))
        self.cli_max_arguments     = int(os.getenv("CLI_MAX_ARGUMENTS", "20"))
        
        # File Tool Limits
        self.file_max_read_chars = int(os.getenv("FILE_MAX_READ_CHARS", "50000"))

        # -- Execution & Autocode ----------------------------------------------
        self.execution_timeout = int(os.getenv("EXECUTOR_TIMEOUT", "120"))
        self.sandbox_timeout   = int(os.getenv("SANDBOX_TIMEOUT", "30"))
        self.autocode_max_retries    = int(os.getenv("AUTOCODE_MAX_RETRIES", "3"))
        self.autocode_max_file_chars = int(os.getenv("AUTOCODE_MAX_FILE_CHARS", "6000"))
        self.autocode_debug          = os.getenv("AUTOCODE_DEBUG", "0") == "1"

        # -- Timeouts ----------------------------------------------------------
        self.planner_timeout = int(os.getenv("PLANNER_TIMEOUT", "180"))
        self.router_timeout = int(os.getenv("ROUTER_TIMEOUT", "15"))
        self.autocode_graph_timeout = int(os.getenv("AUTOCODE_GRAPH_TIMEOUT", "300"))
        self.max_retries = int(os.getenv("AUTOCODE_MAX_RETRIES", "3"))

        # -- Validations -------------------------------------------------------
        # Existing validations (survive python -O via explicit raise)
        if self.autocode_max_retries <= 0:
            raise ValueError("AUTOCODE_MAX_RETRIES must be > 0")
        if self.autocode_max_file_chars <= 0:
            raise ValueError("AUTOCODE_MAX_FILE_CHARS must be > 0")

        _node_timeouts = [self.planner_timeout, self.execution_timeout, self.router_timeout]
        if self.autocode_graph_timeout < max(_node_timeouts):
            raise ValueError("AUTOCODE_GRAPH_TIMEOUT must be >= max(node timeouts)")

        if not self.agent_root.is_absolute():
            raise ValueError("AGENT_ROOT must be an absolute path")
        if not self.agent_root.exists():
            raise FileNotFoundError(f"AGENT_ROOT not found: {self.agent_root}")

        # P2: Validate all new tool limits
        if not (1 <= self.memory_max_entry_bytes <= 10_000_000):
            raise ValueError(f"MAX_MEMORY_BYTES must be 1-10000000, got {self.memory_max_entry_bytes}")
        if not (1 <= self.max_tags_per_entry <= 50):
            raise ValueError(f"MAX_TAGS_PER_ENTRY must be 1-50, got {self.max_tags_per_entry}")
        if not (1 <= self.max_tag_length <= 200):
            raise ValueError(f"MAX_TAG_LENGTH must be 1-200, got {self.max_tag_length}")
        if not (1 <= self.web_max_text_chars <= 100_000):
            raise ValueError(f"WEB_MAX_TEXT_CHARS must be 1-100000, got {self.web_max_text_chars}")
        if not (1 <= self.web_snippet_chars <= 5000):
            raise ValueError(f"WEB_SNIPPET_CHARS must be 1-5000, got {self.web_snippet_chars}")
        if not (1 <= self.web_max_search_results <= 50):
            raise ValueError(f"WEB_MAX_SEARCH_RESULTS must be 1-50, got {self.web_max_search_results}")
        if not (1 <= self.cli_max_command_chars < 50_000):
            raise ValueError(f"CLI_MAX_COMMAND_LENGTH must be 1-49999, got {self.cli_max_command_chars}")
        if not (1 <= self.cli_max_arguments <= 100):
            raise ValueError(f"CLI_MAX_ARGUMENTS must be 1-100, got {self.cli_max_arguments}")
        if not (1 <= self.file_max_read_chars <= 1_000_000):
            raise ValueError(f"FILE_MAX_READ_CHARS must be 1-1000000, got {self.file_max_read_chars}")

        # -- Protected files ---------------------------------------------------
        self.protected_files: frozenset[str] = frozenset({
            "server.py", "registry.py",
            "core/config.py", "core/tracer.py",
            "core/llm.py", "core/memory.py", "core/gateway.py",
        })

        # -- SSRF Protection ---------------------------------------------------
        # Allowlist for trusted internal services (comma-separated hostnames)
        # Default: permissive for development (localhost, LM Studio, SearXNG)
        # Production: set ALLOWED_INTERNAL_HOSTS="" to block ALL private/localhost
        self.allowed_internal_hosts: frozenset[str] = frozenset(
            h.strip().lower()
            for h in os.getenv("ALLOWED_INTERNAL_HOSTS", "localhost,127.0.0.1,::1").split(",")
            if h.strip()
        )

        # -- Gateway -----------------------------------------------------------
        self.gateway_host   = os.getenv("GATEWAY_HOST", "127.0.0.1")
        self.gateway_port   = int(os.getenv("GATEWAY_PORT", "8000"))
        self.gateway_secret = os.getenv("GATEWAY_SECRET", "changeme")

        # -- Environment -------------------------------------------------------
        self.env        = os.getenv("ENV", "development")
        self.is_dev     = self.env == "development"
        self.is_windows = os.name == "nt"

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
        clean = relative.replace("\\", "/").lstrip("/")
        return (self.workspace_root / clean).resolve()

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
                    if target == Path(pf).resolve():
                        return True
        except (ValueError, OSError, RuntimeError):
            pass
            
        return False

    def __repr__(self) -> str:
        return (
            f"Config(env={self.env!r}, agent_root={self.agent_root}, "
            f"planner={self.planner_model!r}, executor={self.executor_model!r})"
        )


# -- Singleton -----------------------------------------------------------------
cfg = Config()