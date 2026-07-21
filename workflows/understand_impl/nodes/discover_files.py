"""Node: discover_files — Discover changed/new files that need parsing.

[#4] Now supports multiple languages: Python (.py), JavaScript (.js/.mjs/.cjs),
TypeScript (.ts/.tsx), Go (.go), Rust (.rs). Uses tree_sitter_parser's
SUPPORTED_EXTENSIONS to filter files during the walk.

[v1.4.1 P1-1] Defensive `status=="failed"` bail at the top of the node.
Belt-and-suspenders alongside route_after_init (P0-1) — if a future graph
refactor accidentally adds a direct init→discover edge, the node itself
short-circuits cleanly instead of running on a half-initialized project.

[v1.4.1 P1-6] Cancellation checks via `workflows.base.is_workflow_cancelled`.
Polled at the start + inside the os.walk loop (every 100 files). Returns
`{"status": "failed", "errors": ["Workflow cancelled"]}` on cancel. The
base.py 600s daemon-thread timeout doesn't kill the thread (Python
limitation) — these checks let the workflow exit cooperatively when the
user requests cancellation.

[v1.4.1 P1-7] GraphStore creation moved INSIDE the try block. Was: created
before try → if the constructor raised, `store` was undefined → `finally:
store.close()` raised NameError, masking the original exception. Now:
`store = None` before try, `if store is not None: store.close()` in finally.

[v1.4.1 P2-2] Uses `ProjectManager.SKIP_DIRS` (was: a local set that drifted
out of sync). The class constant is the single source of truth.

[v1.4.1 P2-13] ProjectManager is re-created here (and in parse_and_store)
rather than passed through state. PM isn't serializable (it caches stats
via _file_count/_total_size_mb). Re-creation is cheap — just path
resolution; the stat walk is cached after the first call, but
discover_files doesn't trigger it (it walks the tree itself).
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

    # [v1.4.1 P1-1] Belt-and-suspenders bail. If init failed and somehow
    # this node was reached anyway (direct edge instead of conditional),
    # don't run on a half-initialized project.
    if state.get("status") == "failed":
        return {}

    # [v1.4.1 P1-6] Cancellation check at node entry.
    if _is_cancelled(tid):
        return {"status": "failed", "errors": ["Workflow cancelled"]}

    tracer.step(tid, "discover", "Scanning for changed files...")

    # [v1.4.1 P2-13] PM re-created here — see module docstring.
    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    # [v1.4.1 P1-4] project_id + artifact_dir are now filled in by init_project,
    # but if init was bypassed (e.g. test fixtures) we still need them for the
    # store.read query below. Mirror init_project's behavior so the node is
    # self-sufficient.
    state.setdefault("project_id", pm.project_id)
    state.setdefault("artifact_dir", str(pm.artifact_root))

    db_path = pm.artifact_root / "kg.db"

    # [v1.4.1 P1-7] GraphStore created INSIDE try; finally checks for None.
    store = None
    # [v1.4.1 P2-2] Use the canonical class constant (was: local frozenset).
    skip_dirs = ProjectManager.SKIP_DIRS

    discovered = []
    files_walked = 0
    try:
        store = GraphStore(db_path)
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

                # [v1.4.1 P1-6] Cooperative cancellation check every 100 files.
                files_walked += 1
                if files_walked % 100 == 0 and _is_cancelled(tid):
                    tracer.step(tid, "discover", "Workflow cancelled mid-walk — aborting.")
                    return {"status": "failed", "errors": ["Workflow cancelled"]}
    finally:
        # [v1.4.1 P1-7] Null check — was bare store.close() that raised NameError
        # when the GraphStore constructor itself raised.
        if store is not None:
            store.close()

    tracer.step(tid, "discover", f"Found {len(discovered)} changed/new files.")
    return {"files_to_parse": discovered}


def _is_cancelled(tid: str) -> bool:
    """[v1.4.1 P1-6] Check the global workflow-cancellation flag.

    Wraps `workflows.base.is_workflow_cancelled` in a try/except so a broken
    base.py import (rare) doesn't crash the node — better to keep indexing
    than to fail on a missing cancellation module. The dispatcher in base.py
    will still short-circuit the result post-hoc when it sees the cancel flag.
    """
    try:
        from workflows.base import is_workflow_cancelled
        return is_workflow_cancelled(tid)
    except Exception:
        return False
