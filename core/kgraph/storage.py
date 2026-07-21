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
    """
    Thread-safe, WAL-enabled SQLite graph store.
    
    P2 Optimization Note: This implementation uses thread-local connections 
    (`self._local.conn`) combined with a single `_write_lock`. This is the 
    canonical, safest, and most performant pattern for local SQLite concurrency 
    in Python. It prevents database corruption while avoiding the overhead of 
    heavy external connection pooling libraries (like aiosqlite) for a local-first agent.
    """
    
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
                last_modified REAL,
                file_size INTEGER,
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
            CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);
            CREATE INDEX IF NOT EXISTS idx_nodes_project_path ON nodes(project_id, path);
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
    # TRUNCATE forces SQLite to checkpoint AND shrink the WAL file to 0 bytes.
    # This prevents the "30-day disk exhaustion" bug on Windows.
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            # Fallback to PASSIVE if TRUNCATE fails (e.g., database is locked)
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def get_file_hash(self, project_id: str, path: str) -> str | None:
        """Get the stored content hash for a specific file node."""
        rows = self.read("SELECT content_hash FROM nodes WHERE project_id = ? AND path = ? AND type = 'file'", (project_id, path))
        return rows[0]["content_hash"] if rows else None

    # [v1.6] Stale-index cleanup support — discover_files uses these two
    # methods to detect files indexed-but-deleted-from-disk and remove their
    # graph nodes + edges (orphans that would otherwise accumulate forever).
    def get_all_file_paths(self, project_id: str) -> list[str]:
        """Return all file paths currently stored for this project.

        Used by node_discover_files' stale-cleanup phase to compute the
        set difference `stored_paths - disk_paths` → orphan paths whose
        nodes + edges + vectors should be removed.

        Args:
            project_id: The 16-char hex project_id (sha256 of resolved
                absolute path, taken by ProjectManager.project_id).

        Returns:
            List of relative file paths (e.g. ["core/config.py",
            "src/utils.py"]). Empty list if no files indexed yet.
        """
        rows = self.read(
            "SELECT path FROM nodes WHERE project_id = ? AND type = 'file'",
            (project_id,)
        )
        return [row["path"] for row in rows]

    def delete_file_entry(self, project_id: str, path: str) -> None:
        """Delete a file's node + all its edges (outgoing + incoming).

        [v1.6] Used by the stale-cleanup phase in node_discover_files to
        remove orphaned graph entries for files that were indexed but have
        since been deleted from disk.

        Outgoing edges: source_id = `file:{path}`.
        Incoming edges: target_id may be ANY of three forms, depending on
        the importer's language:
          - the file_path verbatim (Python file-path form, JS/TS relative)
          - `file:{path}` (the node id stored by `upsert_file_graph`)
          - the Python module-name form (e.g. `core.config` for
            `core/config.py`)

        We delete ALL three forms to be safe — DELETEs that match nothing
        are no-ops, so over-deletion is harmless. Under-deletion would
        leave orphaned edges whose target no longer resolves.

        Args:
            project_id: The project_id from ProjectManager.
            path: Relative file path (e.g. `core/config.py`).
        """
        node_id = f"file:{path}"
        # Python-style module-name form: "core/config.py" → "core.config".
        # Other languages won't match this form (harmless — DELETE no-op).
        # Strip any supported code extension, then convert `/` → `.`.
        module_name = path
        for ext in (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".go",
                    ".rs", ".java", ".c", ".h", ".cpp", ".cc", ".cxx",
                    ".hpp", ".rb", ".lua", ".php", ".scala", ".swift", ".kt",
                    ".md", ".txt", ".rst"):
            if module_name.endswith(ext):
                module_name = module_name[: -len(ext)]
                break
        module_name = module_name.replace("/", ".").lstrip(".")
        with self._write_lock:
            conn = self._get_conn()
            # 1. Delete the file node itself.
            conn.execute(
                "DELETE FROM nodes WHERE project_id = ? AND path = ?",
                (project_id, path)
            )
            # 2. Delete outgoing edges (source_id = file:{path}).
            conn.execute(
                "DELETE FROM edges WHERE project_id = ? AND source_id = ?",
                (project_id, node_id)
            )
            # 3. Delete incoming edges — try all 3 target_id forms.
            conn.execute(
                "DELETE FROM edges WHERE project_id = ? AND target_id = ?",
                (project_id, path)
            )
            conn.execute(
                "DELETE FROM edges WHERE project_id = ? AND target_id = ?",
                (project_id, node_id)
            )
            conn.execute(
                "DELETE FROM edges WHERE project_id = ? AND target_id = ?",
                (project_id, module_name)
            )
            conn.commit()
            self._write_count += 1
            if self._write_count >= self._CHECKPOINT_EVERY:
                self._force_checkpoint(conn)
                self._write_count = 0

    def upsert_file_graph(self, project_id: str, path: str, content_hash: str, dependencies: list[str], last_modified: float = 0.0, file_size: int = 0) -> None:
        """Atomically update a file's node and its dependency edges."""
        node_id = f"file:{path}"
        with self._write_lock:
            conn = self._get_conn()
            # 1. Delete old edges originating from this file
            conn.execute("DELETE FROM edges WHERE project_id = ? AND source_id = ?", (project_id, node_id))
            # 2. Upsert the file node with mtime and size for fast-path validation
            conn.execute("""
                INSERT OR REPLACE INTO nodes (id, project_id, path, type, content_hash, last_modified, file_size, metadata)
                VALUES (?, ?, ?, 'file', ?, ?, ?, '{}')
            """, (node_id, project_id, path, content_hash, last_modified, file_size))
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

    @classmethod
    def close_all(cls) -> None:
        """v1.0: Close ALL GraphStore instances (singleton cleanup).

        Called via atexit in server.py to ensure WAL checkpoints are flushed
        before the process dies. Without this, SQLite WAL files may not be
        checkpointed → potential data loss on crash/kill.

        Thread-safe: acquires _lock to prevent new instances during cleanup.
        """
        with cls._lock:
            for key, instance in list(cls._instances.items()):
                try:
                    instance.close()
                except Exception:
                    pass  # Best-effort — don't crash on shutdown
            cls._instances.clear()
