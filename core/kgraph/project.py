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
    SKIP_DIRS: frozenset[str] = frozenset({
        "node_modules", "__pycache__", ".git", ".venv", "venv",
        ".understand", "dist", "build", ".pytest_cache",
        # v1.4.1 additions (P2-2):
        ".mypy_cache", ".ruff_cache", ".tox", "htmlcov",
        # .eggs + .egg-info dirs (legacy Python packaging) — common clutter.
        ".eggs",
    })

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
        skip_dirs = ProjectManager.SKIP_DIRS

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