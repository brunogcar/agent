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

[v1.5.1] STALE INDEX CLEANUP. The walk now has two phases:
  Phase 1 — walk disk + detect changed files (existing behavior).
  Phase 2 — query GraphStore for all stored file paths, compute
    `orphans = stored_paths - disk_paths`, and delete each orphan's
    graph node + edges (via GraphStore.delete_file_entry) and its
    ChromaDB vectors (via collection.delete(where={"file_path": ...})).

  Was: files indexed-but-deleted-from-disk left orphaned nodes + edges +
  vectors in the store forever, compounding over time. Now: each
  discover_files invocation prunes the index to match the current disk
  state, so the index stays consistent with the codebase.

  ChromaDB cleanup is skipped when `state["skip_embeddings"]` is True —
  skip_embeddings means we didn't index vectors in the first place, so
  there's nothing to clean up. (And the ChromaDB collection may not
  even exist.)
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
    """Discover changed/new files that need parsing.

    [v1.5.1] Two phases:
      Phase 1: walk disk + detect changed files (existing behavior —
        unchanged from v1.4.1).
      Phase 2: stale cleanup — query GraphStore for stored file paths,
        compute orphans (stored - disk), delete their graph entries +
        ChromaDB vectors.
    """
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
    # [v1.5.1] Collect disk paths during the walk — needed for Phase 2
    # stale cleanup (orphans = stored_paths - disk_paths). Pre-allocated
    # as a set for O(1) lookup during the set-difference computation.
    disk_paths: set[str] = set()
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

                # [v1.5.1] Record this path as seen-on-disk for Phase 2.
                disk_paths.add(rel_path)

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

        # [v1.5.1] Phase 2 — stale cleanup. Done INSIDE the try block so
        # the GraphStore is still open + can be queried. ChromaDB cleanup
        # is deferred to a helper that handles the optional-skip case.
        skip_embeddings = bool(state.get("skip_embeddings", False))
        _cleanup_stale_entries(
            store=store,
            project_id=state["project_id"],
            disk_paths=disk_paths,
            pm=pm,
            tid=tid,
            skip_embeddings=skip_embeddings,
        )
    finally:
        # [v1.4.1 P1-7] Null check — was bare store.close() that raised NameError
        # when the GraphStore constructor itself raised.
        if store is not None:
            store.close()

    tracer.step(tid, "discover", f"Found {len(discovered)} changed/new files.")
    return {"files_to_parse": discovered}


def _cleanup_stale_entries(
    store: GraphStore,
    project_id: str,
    disk_paths: set[str],
    pm: ProjectManager,
    tid: str,
    skip_embeddings: bool,
) -> None:
    """[v1.5.1] Phase 2 of node_discover_files — prune orphaned index entries.

    Computes `orphans = stored_paths - disk_paths` and, for each orphan:
      1. Deletes its graph node + all edges (GraphStore.delete_file_entry).
      2. Deletes its ChromaDB vectors (collection.delete) — UNLESS
         `skip_embeddings=True` (we never indexed vectors in the first
         place, so there's nothing to clean).

    ChromaDB cleanup is wrapped in try/except so a broken ChromaDB install
    (missing dependency, locked SQLite, etc.) doesn't crash the discover
    node — the GraphStore cleanup still ran, which is the most important
    part. The orphan count is logged via tracer.step.

    Args:
        store: Open GraphStore instance (caller owns lifecycle).
        project_id: The 16-char hex project_id.
        disk_paths: Set of relative paths currently on disk (collected
            during Phase 1 walk).
        pm: ProjectManager (needed for ChromaDB collection lookup).
        tid: Trace ID for tracer.step / tracer.warning logging.
        skip_embeddings: If True, skip ChromaDB cleanup entirely.
    """
    # Query the store for ALL file paths currently indexed.
    try:
        stored_paths = set(store.get_all_file_paths(project_id))
    except Exception as e:
        tracer.warning(tid, "discover",
                       f"Stale cleanup: get_all_file_paths failed: {e}")
        return

    orphans = stored_paths - disk_paths
    if not orphans:
        tracer.step(tid, "discover", "No stale files detected.")
        return

    # Delete each orphan's graph entries (node + edges).
    for orphan_path in orphans:
        try:
            store.delete_file_entry(project_id, orphan_path)
        except Exception as e:
            tracer.warning(tid, "discover",
                           f"Stale cleanup: delete_file_entry failed for "
                           f"{orphan_path}: {e}")

    # Delete each orphan's ChromaDB vectors — only if embeddings were used.
    if not skip_embeddings:
        try:
            from core.kgraph.vectors import get_project_vector_collection
            collection = get_project_vector_collection(pm)
            for orphan_path in orphans:
                try:
                    collection.delete(where={"file_path": orphan_path})
                except Exception as e:
                    tracer.warning(tid, "discover",
                                   f"Stale cleanup: ChromaDB delete failed for "
                                   f"{orphan_path}: {e}")
        except Exception as e:
            # ChromaDB unavailable — graceful degradation. GraphStore
            # cleanup already ran (the more important part).
            tracer.warning(tid, "discover",
                           f"Stale cleanup: ChromaDB collection unavailable — "
                           f"vector cleanup skipped: {e}")

    tracer.step(tid, "discover",
                f"Cleaned up {len(orphans)} stale files from index")


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
