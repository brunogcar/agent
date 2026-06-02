"""
core/kgraph/storage.py
Hardened SQLite storage for graph topology with WAL mode and write serialization.
"""
from __future__ import annotations
import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

class GraphStore:
    """Thread-safe, WAL-enabled SQLite graph store."""
    
    _instances: Dict[str, "GraphStore"] = {}
    _lock = threading.Lock()

    def __new__(cls, db_path: Path):
        with cls._lock:
            key = str(db_path.resolve())
            if key not in cls._instances:
                cls._instances[key] = super().__new__(cls)
                cls._instances[key]._init(db_path)
            return cls._instances[key]

    def _init(self, db_path: Path) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()
        self._local = threading.local()
        self._write_count = 0
        self._CHECKPOINT_EVERY = 100
        self._repair_wal_on_windows()
        self._init_schema()

    def _repair_wal_on_windows(self) -> None:
        """Delete stale WAL artifacts if the DB was not cleanly closed."""
        if self._db_path.exists():
            wal = self._db_path.with_suffix(".db-wal")
            shm = self._db_path.with_suffix(".db-shm")
            if wal.exists() and (not shm.exists() or shm.stat().st_size == 0):
                try:
                    wal.unlink(missing_ok=True)
                    shm.unlink(missing_ok=True)
                except PermissionError:
                    pass  # Another process is using it

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=30.0,
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn.execute("PRAGMA temp_store=MEMORY")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                type TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                metadata TEXT,
                updated_at REAL DEFAULT (strftime('%s', 'now')),
                UNIQUE(project_id, path)
            );
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_id);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
        """)
        conn.commit()

    def read(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        conn = self._get_conn()
        return conn.execute(sql, params).fetchall()

    def write(self, sql: str, params: tuple = ()) -> None:
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(sql, params)
            conn.commit()
            self._write_count += 1
            if self._write_count >= self._CHECKPOINT_EVERY:
                self._force_checkpoint(conn)
                self._write_count = 0

    def _force_checkpoint(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        wal_path = self._db_path.with_suffix(".db-wal")
        if wal_path.exists() and wal_path.stat().st_size > 50_000_000:  # 50MB
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            conn = self._local.conn
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            self._local.conn = None
