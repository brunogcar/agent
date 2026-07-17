"""Node: discover_files — Discover changed/new files that need parsing.

[#4] Now supports multiple languages: Python (.py), JavaScript (.js/.mjs/.cjs),
TypeScript (.ts/.tsx), Go (.go), Rust (.rs). Uses tree_sitter_parser's
SUPPORTED_EXTENSIONS to filter files during the walk.
"""
from __future__ import annotations

import os
import math
from pathlib import Path

from workflows.understand_impl.state import UnderstandState
from workflows.understand_impl.helpers import _chunked_md5
from core.tracer import tracer
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from core.kgraph.tree_sitter_parser import ALL_SUPPORTED_EXTENSIONS


def node_discover_files(state: UnderstandState) -> dict:
    """Discover changed/new files that need parsing."""
    tid = state.get("trace_id", "understand")
    tracer.step(tid, "discover", "Scanning for changed files...")

    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    db_path = pm.artifact_root / "kg.db"
    store = GraphStore(db_path)

    skip_dirs = frozenset({"node_modules", "__pycache__", ".git", ".venv", "venv", ".understand", "dist", "build", ".pytest_cache"})

    discovered = []
    try:
        for root, dirs, files in os.walk(pm.source_root):
            dirs[:] = sorted(set(dirs) - skip_dirs)
            for f in files:
                # v1.3: Use ALL_SUPPORTED_EXTENSIONS (code + docs)
                if Path(f).suffix.lower() not in ALL_SUPPORTED_EXTENSIONS:
                    continue
                full_path = Path(root) / f
                try:
                    stat = full_path.stat()
                    if stat.st_size > ProjectManager.MAX_FILE_SIZE_BYTES:
                        continue
                except OSError:
                    continue

                # v1.3.1: Resolve full_path before relative_to() — pm.source_root
                # is already resolved (ProjectManager.__init__ does .resolve()), but
                # full_path comes from os.walk which returns the OS's raw path.
                # On Windows, resolve() normalizes drive letter case + expands short
                # names + resolves symlinks. Without resolving full_path too,
                # relative_to() raises ValueError when the casings don't match.
                # Also wrapped in try/except with logging — was unhandled (would
                # crash the entire file discovery walk on a single bad path).
                try:
                    rel_path = full_path.resolve().relative_to(pm.source_root).as_posix()
                except (ValueError, OSError) as e:
                    tracer.warning(tid, "discover",
                                   f"Skipping {full_path}: relative_to failed: {e}")
                    continue

                node = store.read(
                    "SELECT content_hash, last_modified, file_size FROM nodes WHERE project_id = ? AND path = ?",
                    (state["project_id"], rel_path)
                )

                if node:
                    row = node[0]
                    if math.isclose(row["last_modified"], stat.st_mtime, abs_tol=0.001) and row["file_size"] == stat.st_size:
                        continue

                current_hash = _chunked_md5(full_path)
                stored_hash = store.get_file_hash(state["project_id"], rel_path)

                if current_hash != stored_hash:
                    discovered.append((str(full_path), rel_path, current_hash, stat.st_mtime, stat.st_size))
    finally:
        store.close()

    tracer.step(tid, "discover", f"Found {len(discovered)} changed/new files.")
    return {"files_to_parse": discovered}
