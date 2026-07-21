"""
core/kgraph/project.py
Manages physical isolation and project-level statistics.
Supports both agent_root (source=root, artifacts=.understand)
and workspace projects (source=code, artifacts=.understand).
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Literal, Tuple
from core.config import cfg
from core.kgraph.cleanup import KGCleanup

def is_same_path(a: str | Path, b: str | Path) -> bool:
    """
    Cross-platform, bulletproof path comparison.
    Uses os.path.normcase which handles Windows case-insensitivity 
    and slash normalization, while remaining strictly case-sensitive on Linux/macOS.
    """
    try:
        # 1. OS-level check (handles symlinks perfectly)
        return Path(a).resolve().samefile(Path(b).resolve())
    except (OSError, ValueError, FileNotFoundError):
        # 2. Fallback: normcase + abspath
        # On Windows: lowercases and converts / to \
        # On Linux/macOS: does nothing (preserves case-sensitivity)
        norm_a = os.path.normcase(os.path.abspath(str(a).strip()))
        norm_b = os.path.normcase(os.path.abspath(str(b).strip()))
        return norm_a == norm_b


class ProjectManager:
    """Manages the .understand/ workspace for a specific project."""
    # Hard limits for local-first execution
    MAX_FILES_FOR_FOREGROUND = 5000
    MAX_FILE_SIZE_BYTES = 1_048_576  # 1MB
    MAX_TOTAL_PROJECT_SIZE_MB = 500

    # [v1.4.1 P2-2] Canonical skip-dirs set, used by both _get_project_stats()
    # here and node_discover_files (which previously had its own local copy
    # that drifted out of sync). Frozen so callers can't mutate it. os.walk's
    # `dirs[:] =` filtering uses exact-name matching (no globs), so we list
    # the literal directory names. Includes the v1.4.1 additions: .mypy_cache,
    # .ruff_cache, .tox, htmlcov (was missing — coverage HTML reports were
    # being walked). `.pytest_cache` was already here; `__pycache__`,
    # `node_modules`, `.git`, `.venv`, `venv`, `.understand`, `dist`, `build`
    # carried over from the v1.3 local set.
    #
    # [v1.7] Renamed from SKIP_DIRS → _DEFAULT_SKIP_DIRS. The runtime
    # skip-dirs set is now obtained via get_skip_dirs() which merges this
    # default with the UNDERSTAND_SKIP_DIRS env var (comma-separated extras).
    # The class constant stays as the immutable default; callers should use
    # get_skip_dirs() (or ProjectManager.SKIP_DIRS for backward compat —
    # kept as a property aliasing the default).
    _DEFAULT_SKIP_DIRS: frozenset[str] = frozenset({
        "node_modules", "__pycache__", ".git", ".venv", "venv",
        ".understand", "dist", "build", ".pytest_cache",
        # v1.4.1 additions (P2-2):
        ".mypy_cache", ".ruff_cache", ".tox", "htmlcov",
        # .eggs + .egg-info dirs (legacy Python packaging) — common clutter.
        ".eggs",
    })

    # [v1.7] Backward-compat alias. Existing tests + callers that read
    # ProjectManager.SKIP_DIRS still work — they get the default set.
    # Callers that want the env-merged set should use get_skip_dirs().
    SKIP_DIRS = _DEFAULT_SKIP_DIRS

    @classmethod
    def get_skip_dirs(cls) -> frozenset[str]:
        """[v1.7] Return the skip_dirs set, merged with UNDERSTAND_SKIP_DIRS.

        The base set is the immutable _DEFAULT_SKIP_DIRS class constant
        (consolidated in v1.4.1 P2-2). The UNDERSTAND_SKIP_DIRS env var
        (comma-separated) adds project-specific extras at runtime — e.g.
        `UNDERSTAND_SKIP_DIRS=vendor,third_party` adds those two dirs.

        Returns a NEW frozenset on each call (base | extra) so callers can
        safely mutate the result without affecting the class constant.

        Was: callers read cls.SKIP_DIRS directly. The env var had no effect.
        Now: callers that want env overrides should call get_skip_dirs().
        The class constant is still available for callers that want the
        pure default (e.g. tests asserting the default set contents).
        """
        base = cls._DEFAULT_SKIP_DIRS
        env_extra = getattr(cfg, "understand_skip_dirs", "")
        if env_extra:
            extra = frozenset(d.strip() for d in env_extra.split(",") if d.strip())
            return base | extra
        return base

    def get_embedding_model(self) -> str:
        """[v1.7] Return the embedding model for this project.

        Resolution order:
          1. Project-specific override in .understand/config.json
             (key: "embedding_model"). Lets different projects use different
             embedding models without changing the global default.
          2. cfg.embedding_model (the global default, set by EMBEDDING_MODEL
             env var).

        Returns the model name as a string (e.g. "all-MiniLM-L6-v2-GGUF").

        Failures (missing config.json, JSON parse error, missing key) fall
        through to the global default — a corrupt project config must NOT
        crash embedding calls.
        """
        config_path = self.artifact_root / "config.json"
        if config_path.exists():
            try:
                import json
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if "embedding_model" in config:
                    return config["embedding_model"]
            except Exception:
                pass  # Fall through to global default.
        return getattr(cfg, "embedding_model", "all-MiniLM-L6-v2-GGUF")

    def __init__(self, project_path: str | Path, is_agent_root: bool = False):
        self.path = Path(project_path).resolve()
        self.is_agent_root = is_agent_root
        
        if self.is_agent_root:
            # Agent root: source is the root itself, artifacts are in .understand
            self.source_root = self.path
            self.artifact_root = self.path / ".understand"
        else:
            # Workspace project: source is in 'code', artifacts are in '.understand'
            self.source_root = self.path / "code"
            self.artifact_root = self.path / ".understand"
            
        self._file_count: int | None = None
        self._total_size_mb: float | None = None

    @property
    def project_id(self) -> str:
        """Unique ID based on absolute path hash."""
        return hashlib.sha256(str(self.path).encode("utf-8")).hexdigest()[:16]

    def ensure_initialized(self) -> None:
        """Create the artifact directory structure if it doesn't exist and run cleanup."""
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        (self.artifact_root / "cache").mkdir(exist_ok=True)
        self.source_root.mkdir(parents=True, exist_ok=True)
        
        # NOTE: source_root is created here so tests and init_project can rely on it.
        # For workspace projects, this is the 'code/' subdirectory.
         
        # 🔴 Phase 7 Step 3: Run cleanup on startup to prevent WAL/cache bloat
        try:
            KGCleanup.cleanup_project(self.path, max_age_days=30, max_size_gb=5)
        except Exception:
            pass  # Fail silently, cleanup is best-effort

    def get_indexing_mode(self) -> Literal["foreground", "background", "reject"]:
        """Determine if the project is safe to index in the foreground."""
        count, size_mb = self._get_project_stats()
        
        if size_mb > self.MAX_TOTAL_PROJECT_SIZE_MB:
            return "reject"
        if count > self.MAX_FILES_FOR_FOREGROUND:
            return "background"
        return "foreground"

    def _get_project_stats(self) -> Tuple[int, float]:
        """Fast stat walk of the SOURCE root, skipping known junk directories."""
        if self._file_count is not None:
            return self._file_count, self._total_size_mb
        
        count = 0
        total_bytes = 0
        # [v1.4.1 P2-2] Use the canonical SKIP_DIRS class constant (was: a
        # local set that drifted out of sync with node_discover_files).
        # [v1.7] Use get_skip_dirs() so UNDERSTAND_SKIP_DIRS env var is
        # respected (was: cls.SKIP_DIRS which doesn't read the env var).
        skip_dirs = ProjectManager.get_skip_dirs()

        for root, dirs, files in os.walk(self.source_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                count += 1
                try:
                    total_bytes += (Path(root) / f).stat().st_size
                except OSError:
                    pass
        
        self._file_count = count
        self._total_size_mb = total_bytes / (1024 * 1024)
        return self._file_count, self._total_size_mb