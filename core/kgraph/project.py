"""
core/kgraph/project.py
Manages physical isolation and project-level statistics.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Literal, Tuple

class ProjectManager:
    """Manages the .understand/ workspace for a specific project."""
    
    # Hard limits for local-first execution
    MAX_FILES_FOR_FOREGROUND = 5000
    MAX_FILE_SIZE_BYTES = 1_048_576  # 1MB
    MAX_TOTAL_PROJECT_SIZE_MB = 500

    def __init__(self, project_path: str | Path):
        self.path = Path(project_path).resolve()
        self.understand_dir = self.path / ".understand"
        self._file_count: int | None = None
        self._total_size_mb: float | None = None

    @property
    def project_id(self) -> str:
        """Unique ID based on absolute path hash."""
        return hashlib.sha256(str(self.path).encode("utf-8")).hexdigest()[:16]

    def ensure_initialized(self) -> None:
        """Create the .understand directory structure if it doesn't exist."""
        self.understand_dir.mkdir(parents=True, exist_ok=True)
        (self.understand_dir / "cache").mkdir(exist_ok=True)

    def get_indexing_mode(self) -> Literal["foreground", "background", "reject"]:
        """Determine if the project is safe to index in the foreground."""
        count, size_mb = self._get_project_stats()
        
        if size_mb > self.MAX_TOTAL_PROJECT_SIZE_MB:
            return "reject"
        if count > self.MAX_FILES_FOR_FOREGROUND:
            return "background"
        return "foreground"

    def _get_project_stats(self) -> Tuple[int, float]:
        """Fast stat walk, skipping known junk directories."""
        if self._file_count is not None:
            return self._file_count, self._total_size_mb
        
        count = 0
        total_bytes = 0
        skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", ".understand", "dist", "build", ".pytest_cache"}
        
        for root, dirs, files in os.walk(self.path):
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
