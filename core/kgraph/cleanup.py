"""
core/kgraph/cleanup.py
Prevents disk space exhaustion and WAL file bloat over long-term unattended operation.
"""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from core.tracer import tracer

class KGCleanup:
    @staticmethod
    def cleanup_project(project_path: Path, max_age_days: int = 30, max_size_gb: int = 5) -> None:
        """
        Clean up old KG artifacts to prevent disk space exhaustion.
        Runs on startup or periodically.
        """
        understand_dir = project_path / ".understand"
        if not understand_dir.exists():
            return
            
        # 1. Clean up cache/ directory
        cache_dir = understand_dir / "cache"
        if cache_dir.exists():
            KGCleanup._cleanup_dir(cache_dir, max_age_days, max_size_gb)

        # 2. Force SQLite WAL checkpoint to prevent unbounded growth
        kg_db = understand_dir / "kg.db"
        if kg_db.exists():
            try:
                with sqlite3.connect(str(kg_db)) as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception as e:
                tracer.warning("kg_cleanup", f"Failed to checkpoint {kg_db}: {e}")

    @staticmethod
    def _cleanup_dir(dir_path: Path, max_age_days: int, max_size_gb: int) -> None:
        """Clean up old or large files in a directory."""
        now = time.time()
        max_age_seconds = max_age_days * 86400
        max_size_bytes = max_size_gb * (1024 ** 3)
        
        # Delete files older than max_age_days
        for file_path in dir_path.glob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < (now - max_age_seconds):
                try:
                    file_path.unlink()
                except OSError:
                    pass
                    
        # Calculate total size and delete oldest files if over limit
        files = sorted(
            [f for f in dir_path.glob("*") if f.is_file()],
            key=lambda f: f.stat().st_mtime
        )
        total_size = sum(f.stat().st_size for f in files)
        
        for file_path in files:
            if total_size <= max_size_bytes:
                break
            try:
                total_size -= file_path.stat().st_size
                file_path.unlink()
            except OSError:
                pass