"""
core/kgraph/storage.py
Hardened SQLite storage for graph topology with WAL mode and write serialization.
"""
from __future__ import annotations
import sqlite3
import hashlib
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


    def get_file_hash(self, project_id: str, path: str) -> str | None:
        """Get the stored content hash for a specific file node."""
        rows = self.read("SELECT content_hash FROM nodes WHERE project_id = ? AND path = ? AND type = 'file'", (project_id, path))
        return rows[0]["content_hash"] if rows else None

    def upsert_file_graph(self, project_id: str, path: str, content_hash: str, dependencies: list[str]) -> None:
        """Atomically update a file's node and its dependency edges."""
        node_id = f"file:{path}"
        with self._write_lock:
            conn = self._get_conn()
            # 1. Delete old edges originating from this file
            conn.execute("DELETE FROM edges WHERE project_id = ? AND source_id = ?", (project_id, node_id))
            # 2. Upsert the file node
            conn.execute("""
                INSERT OR REPLACE INTO nodes (id, project_id, path, type, content_hash, metadata)
                VALUES (?, ?, ?, 'file', ?, '{}')
            """, (node_id, project_id, path, content_hash))
            # 3. Insert new edges
            for dep in dependencies:
                edge_id = hashlib.md5(f"{node_id}->{dep}".encode()).hexdigest()
                conn.execute("""
                    INSERT OR IGNORE INTO edges (id, project_id, source_id, target_id)
                    VALUES (?, ?, ?, ?)
                """, (edge_id, project_id, node_id, dep))
            conn.commit()
            
            self._write_count += 1
            if self._write_count >= self._CHECKPOINT_EVERY:
                self._force_checkpoint(conn)
                self._write_count = 0

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            conn = self._local.conn
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            self._local.conn = None
