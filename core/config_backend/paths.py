"""core/config_backend/paths.py — Initialize all filesystem path attributes.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.
All path attributes are set on the ``Config`` instance via this function.

Env vars read:
    AGENT_ROOT      — project root (default: project root discovered from this file)
    WORKSPACE_ROOT  — workspace dir (default: <agent_root>/workspace)
    MEMORY_ROOT     — memory DB dir (default: <agent_root>/memory_db)

Derived paths (computed from the above):
    memory_chroma_path, memory_db_path, task_db_path,
    workspace_autocode, workspace_index,
    log_path, agent_log_path, sleep_learn_log_path

Range/existence checks on ``agent_root`` live in ``validators.py``.
"""

from __future__ import annotations

import os
from pathlib import Path


def _init_paths(cfg) -> None:
    """Initialize all filesystem path attributes from environment variables."""

    # -- Paths -------------------------------------------------------------
    # NOTE: __file__ here is core/config_backend/paths.py.
    # parent          -> core/config_backend/
    # parent.parent   -> core/
    # parent.parent.parent -> project root (matches the pre-v1.0 _here in
    # core/config.py where _here = Path(__file__).resolve().parent.parent)
    _here = Path(__file__).resolve().parent.parent.parent

    cfg.agent_root = Path(os.getenv("AGENT_ROOT", str(_here)))
    cfg.workspace_root = Path(os.getenv("WORKSPACE_ROOT", str(_here / "workspace")))
    cfg.memory_root = Path(os.getenv("MEMORY_ROOT", str(_here / "memory_db")))

    cfg.memory_chroma_path = cfg.memory_root / "chroma"
    cfg.memory_db_path = cfg.memory_root / "agent.db"
    cfg.task_db_path = cfg.memory_root / "task.db"
    cfg.workspace_autocode = cfg.workspace_root / "autocode"
    cfg.workspace_index = cfg.workspace_root / ".index"
    cfg.log_path = cfg.agent_root / "logs"
    cfg.agent_log_path = cfg.log_path / "agent"
    cfg.sleep_learn_log_path = cfg.log_path / "sleep_learn"
