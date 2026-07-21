"""workflows/understand_impl/query.py — Query interface + health check for understand.

[v1.5 Commit 3A] Adds two new entry points that DON'T run the full
understand indexing graph:

  - `query_codebase(...)` — search an already-indexed project by:
      * semantic  → ChromaDB vector search (query_similar_code)
      * keyword   → SQL path match (find_relevant_files)
      * dependencies → outgoing edges (get_dependencies)
      * callers      → incoming edges (get_callers)

  - `health_check(...)` — index stats: file_count, edge_count,
    vector_count, kg.db size, chroma dir size, embedding availability,
    last_indexed timestamp. Returns `indexed=False` (still status="success")
    when kg.db doesn't exist yet.

These are surfaced via `run_workflow(type="understand", action="query"|"health")`
in workflows/base.py — the action param routes BEFORE graph building so
query/health never construct or invoke the LangGraph.

Design:
  - Query functions take `project_path` (string) + `is_agent_root` flag,
    exactly like the existing kgraph query functions. They construct a
    ProjectManager themselves (cheap — no source-tree walk on query paths;
    `find_relevant_files`/`get_dependencies`/`get_callers` already do this).
  - All four query types share a unified return shape: status, action,
    query_type, question/file_path, project_path, results, count, trace_id,
    errors. Callers can rely on `results` always being a list.
  - Semantic results include a `snippet` field — first 5 lines of the
    `source` field with `  N | ` line-number prefixes (grep -n style),
    offset by the result's `line_start`. Capped at 500 chars.
  - Embedding-service failures degrade gracefully — semantic search returns
    `status="success", results=[], errors=["Embedding service unavailable..."]`
    instead of failing hard. Lets callers fall back to keyword search.
  - `indexed=False` (no kg.db) is NOT a failure for health_check — operators
    use health_check to DECIDE whether to index. Query functions DO treat
    "not indexed" as a failure (you can't query an empty graph).

[v1.5] Lazy kgraph imports — like the v1.4.1 facade fix, all `core.kgraph.*`
imports are inside the function bodies. A broken kgraph install (missing
chromadb, broken tree_sitter_languages, etc.) must not cascade to callers
that import this module.
"""
from __future__ import annotations

from pathlib import Path
from core.tracer import tracer
from core.config import cfg


# ─── Snippet formatting ─────────────────────────────────────────────────────

def _format_snippet(source: str, line_start: int, max_lines: int = 5, max_chars: int = 500) -> str:
    """Format a `grep -n`-style snippet from the source code.

    Takes the first `max_lines` lines of `source`, prefixes each with its
    1-based line number (offset by `line_start`), and caps the result at
    `max_chars` characters. Mirrors the output of `grep -n`.

    Args:
        source: The source code text (typically the `source` field from a
            semantic-search result — the matched definition's body).
        line_start: 1-based line number where `source` begins in the original
            file. Used to offset the displayed line numbers. 0 or negative →
            treated as 1 (defensive — should never happen, but a corrupt
            metadata payload shouldn't crash the query).
        max_lines: Max lines to include in the snippet (default 5).
        max_chars: Max characters in the returned string (default 500).
    """
    if not source:
        return ""
    # Defensive — line_start should always be >= 1 from extract_definitions,
    # but metadata payloads from older indexes may carry 0.
    base = max(int(line_start or 0), 1)
    lines = source.splitlines()
    snippet_lines = lines[:max_lines]
    parts = []
    for i, line in enumerate(snippet_lines):
        line_no = base + i
        parts.append(f"{line_no:>3} | {line}")
    out = "\n".join(parts)
    if len(out) > max_chars:
        out = out[:max_chars]
    return out


# ─── query_codebase ────────────────────────────────────────────────────────

_VALID_QUERY_TYPES = ("semantic", "keyword", "dependencies", "callers")


def query_codebase(
    project_path: str,
    question: str,
    query_type: str = "semantic",
    file_path: str = "",
    top_k: int = 10,
    is_agent_root: bool = False,
    trace_id: str = "",
) -> dict:
    """Query an already-indexed codebase. Does NOT run the indexing graph.

    Routes to the appropriate kgraph query function based on `query_type`:

      * "semantic"     → core.kgraph.vectors.query_similar_code(pm, question, ...)
      * "keyword"      → core.kgraph.queries.find_relevant_files(project_path, question, ...)
      * "dependencies" → core.kgraph.queries.get_dependencies(project_path, file_path)
      * "callers"      → core.kgraph.queries.get_callers(project_path, file_path)

    Args:
        project_path: Absolute path to the project root (the same path that
            was passed to `action="index"`).
        question: The search query (semantic / keyword). For dependencies +
            callers this field is ignored — `file_path` is the query target.
            It's still echoed back in the response as `question` for
            caller-side tracing consistency.
        query_type: One of "semantic", "keyword", "dependencies", "callers".
        file_path: REQUIRED for "dependencies" + "callers" — the relative
            file path to inspect (e.g. "core/config.py"). Ignored for
            semantic + keyword.
        top_k: Max results to return (semantic + keyword only). Default 10.
        is_agent_root: Pass-through to ProjectManager — affects source_root
            resolution (agent_root → path itself, workspace → path/code).
            The kg.db is always at {path}/.understand/kg.db regardless.
        trace_id: For trace correlation. Empty → a new trace is created.

    Returns:
        dict with shape:
          {
            "status": "success" | "failed",
            "action": "query",
            "query_type": query_type,
            "question": question,
            "project_path": project_path,
            "results": [...],   # list (shape depends on query_type)
            "count": int,
            "trace_id": str,
            "errors": [str, ...],
          }

    Error handling:
      * Invalid query_type → status="failed" + descriptive error.
      * file_path missing for dependencies/callers → status="failed".
      * Project not indexed (kg.db missing) → status="failed" with hint to
        run `action="index"` first.
      * Embedding service unavailable for semantic search → status="success"
        with empty results + graceful-degradation error message (NOT a hard
        failure — lets callers fall back to keyword search).
    """
    tid = trace_id or tracer.new_trace(
        "understand", goal=f"Query codebase at {project_path} ({query_type})"
    )

    # Validate query_type BEFORE touching kgraph — fail fast + clear message.
    if query_type not in _VALID_QUERY_TYPES:
        msg = (
            f"Invalid query_type: {query_type}. "
            f"Use: {', '.join(_VALID_QUERY_TYPES)}"
        )
        tracer.error(tid, "query", msg)
        tracer.finish(tid, success=False, result=msg)
        return {
            "status": "failed",
            "action": "query",
            "query_type": query_type,
            "question": question,
            "project_path": project_path,
            "results": [],
            "count": 0,
            "trace_id": tid,
            "errors": [msg],
        }

    # file_path required for dependencies + callers.
    if query_type in ("dependencies", "callers") and not file_path:
        msg = "file_path is required for dependencies/callers queries"
        tracer.error(tid, "query", msg)
        tracer.finish(tid, success=False, result=msg)
        return {
            "status": "failed",
            "action": "query",
            "query_type": query_type,
            "question": question,
            "project_path": project_path,
            "results": [],
            "count": 0,
            "trace_id": tid,
            "errors": [msg],
        }

    # Lazy kgraph imports — keep this module importable even if kgraph is
    # broken at import time (mirrors the v1.4.1 facade fix).
    from core.kgraph.project import ProjectManager
    from core.kgraph.vectors import query_similar_code
    from core.kgraph.queries import find_relevant_files, get_dependencies, get_callers
    from core.kgraph.embeddings import is_embedding_available

    pm = ProjectManager(project_path, is_agent_root=is_agent_root)
    kg_db_path = pm.artifact_root / "kg.db"

    # "Not indexed" is a HARD failure for query (you can't query an empty graph).
    # health_check treats it as success-with-indexed=False instead.
    if not kg_db_path.exists():
        msg = (
            f"Project not indexed. Run understand(action='index') first. "
            f"Expected: {kg_db_path}"
        )
        tracer.error(tid, "query", msg)
        tracer.finish(tid, success=False, result=msg)
        return {
            "status": "failed",
            "action": "query",
            "query_type": query_type,
            "question": question,
            "project_path": project_path,
            "results": [],
            "count": 0,
            "trace_id": tid,
            "errors": [msg],
        }

    errors: list[str] = []

    try:
        if query_type == "semantic":
            # Graceful degradation — if LM Studio is down, return success with
            # empty results + an explanatory error. Lets callers fall back to
            # keyword search without an extra round-trip.
            if not is_embedding_available():
                msg = (
                    "Embedding service unavailable — semantic search requires "
                    "LM Studio running"
                )
                tracer.warning(tid, "query", msg)
                tracer.finish(tid, success=True, result="semantic: degraded (no embeddings)")
                return {
                    "status": "success",
                    "action": "query",
                    "query_type": query_type,
                    "question": question,
                    "project_path": project_path,
                    "results": [],
                    "count": 0,
                    "trace_id": tid,
                    "errors": [msg],
                }

            raw_results = query_similar_code(
                pm, question, n_results=top_k, trace_id=tid
            )
            # [v1.7] Per-project embedding model: query_similar_code internally
            # calls pm.get_embedding_model() + passes it to embed_texts().
            # The query text is embedded with the project's configured model,
            # matching the model used at index time (so cosine distances
            # remain meaningful when the project overrides the global default).
            #
            # Augment each result with a line-numbered snippet for display.
            results = []
            for r in raw_results:
                r_copy = dict(r)
                r_copy["snippet"] = _format_snippet(
                    r.get("source", ""), r.get("line_start", 0)
                )
                results.append(r_copy)

        elif query_type == "keyword":
            file_paths = find_relevant_files(project_path, question, top_k=top_k)
            # Wrap as list of dicts for a uniform results shape (callers that
            # iterate results don't need to branch on query_type).
            results = [{"file_path": p} for p in file_paths]

        elif query_type == "dependencies":
            deps = get_dependencies(project_path, file_path)
            results = [{"target": d} for d in deps]

        elif query_type == "callers":
            callers = get_callers(project_path, file_path)
            results = [{"caller": c} for c in callers]

        else:
            # Unreachable — validated above. Defensive.
            results = []

        tracer.step(
            tid, "query",
            f"query_type={query_type} → {len(results)} results",
        )
        tracer.finish(tid, success=True, result=f"{len(results)} results")
        return {
            "status": "success",
            "action": "query",
            "query_type": query_type,
            "question": question,
            "project_path": project_path,
            "results": results,
            "count": len(results),
            "trace_id": tid,
            "errors": errors,
        }
    except Exception as e:
        msg = f"Query failed: {type(e).__name__}: {e}"
        tracer.error(tid, "query", msg)
        tracer.finish(tid, success=False, result=msg)
        return {
            "status": "failed",
            "action": "query",
            "query_type": query_type,
            "question": question,
            "project_path": project_path,
            "results": [],
            "count": 0,
            "trace_id": tid,
            "errors": [msg],
        }


# ─── health_check ──────────────────────────────────────────────────────────

# Cap the chroma-dir walk at 1000 files — ChromaDB can produce many small
# vector files in long-running indexes, and we don't want a stat() storm
# on huge stores. The size is approximate (truncated walk); operators who
# need exact sizes can `du -sh` directly.
_CHROMA_WALK_CAP = 1000


def _dir_size_bytes(path: Path, cap_files: int = _CHROMA_WALK_CAP) -> int:
    """Walk `path` and sum file sizes. Caps at `cap_files` entries.

    Used for the chroma dir size — ChromaDB produces many small files
    (one per HNSW segment) and walking all of them on a huge store is
    wasteful for a health-check API.
    """
    if not path.exists():
        return 0
    total = 0
    count = 0
    try:
        for root, _dirs, files in _os_walk_safe(path):
            for f in files:
                if count >= cap_files:
                    return total
                try:
                    total += (Path(root) / f).stat().st_size
                    count += 1
                except OSError:
                    pass
    except Exception:
        pass
    return total


def _os_walk_safe(path: Path):
    """Wrap os.walk so a permission error doesn't crash the whole walk.

    Returns an empty iterator on error — _dir_size_bytes will just see 0
    additional bytes from the failed subtree.
    """
    import os
    try:
        yield from os.walk(path)
    except (OSError, PermissionError):
        return


def health_check(
    project_path: str,
    is_agent_root: bool = False,
    trace_id: str = "",
) -> dict:
    """Return index health stats. Does NOT run the graph.

    Reports:
      * indexed: bool       — kg.db exists?
      * last_indexed: float — kg.db mtime (unix timestamp), 0.0 if not indexed.
      * file_count: int     — COUNT(*) FROM nodes WHERE project_id=? AND type='file'
      * edge_count: int     — COUNT(*) FROM edges WHERE project_id=?
      * vector_count: int   — collection.count() (0 if ChromaDB unavailable)
      * kg_db_size_bytes: int — kg.db file size (0 if not exists)
      * chroma_dir_size_bytes: int — sum of file sizes under chroma/ (capped)
      * embedding_available: bool — is_embedding_available()

    `indexed=False` is NOT a failure — it's the natural state of a project
    that hasn't been indexed yet. Operators call health_check to DECIDE
    whether to index. Returns status="success" with all counts at 0.

    Args:
        project_path: Absolute path to the project root.
        is_agent_root: Pass-through to ProjectManager — affects chroma dir
            location (workspace → {project}/.understand/chroma, agent root
            → cfg.memory_root/understand/chroma).
        trace_id: For trace correlation.

    Returns:
        dict (see fields above).
    """
    tid = trace_id or tracer.new_trace(
        "understand", goal=f"Health check at {project_path}"
    )

    from core.kgraph.project import ProjectManager
    from core.kgraph.embeddings import is_embedding_available

    pm = ProjectManager(project_path, is_agent_root=is_agent_root)
    kg_db_path = pm.artifact_root / "kg.db"

    # Embedding availability — safe to call regardless of indexed state.
    try:
        emb_available = bool(is_embedding_available())
    except Exception:
        emb_available = False

    # If not indexed, return success with indexed=False + zeroed counts.
    # This is the documented behavior — operators use health_check to decide
    # whether to index, not as a failure indicator.
    if not kg_db_path.exists():
        tracer.step(tid, "understand_health", "Project not indexed (kg.db missing)")
        tracer.finish(tid, success=True, result="not indexed")
        return {
            "status": "success",
            "action": "health",
            "project_path": project_path,
            "project_id": pm.project_id,
            "indexed": False,
            "last_indexed": 0.0,
            "file_count": 0,
            "edge_count": 0,
            "vector_count": 0,
            "kg_db_size_bytes": 0,
            "chroma_dir_size_bytes": 0,
            "embedding_available": emb_available,
            "trace_id": tid,
            "errors": [],
        }

    # kg.db exists — gather stats.
    try:
        kg_db_size = kg_db_path.stat().st_size
    except OSError:
        kg_db_size = 0
    try:
        last_indexed = float(kg_db_path.stat().st_mtime)
    except OSError:
        last_indexed = 0.0

    # File + edge counts via direct SQL (cheaper than walking nodes).
    file_count = 0
    edge_count = 0
    store = None
    try:
        from core.kgraph.storage import GraphStore
        store = GraphStore(kg_db_path)
        rows = store.read(
            "SELECT COUNT(*) AS n FROM nodes WHERE project_id = ? AND type = 'file'",
            (pm.project_id,),
        )
        if rows:
            file_count = int(rows[0]["n"])
        rows = store.read(
            "SELECT COUNT(*) AS n FROM edges WHERE project_id = ?",
            (pm.project_id,),
        )
        if rows:
            edge_count = int(rows[0]["n"])
    except Exception as e:
        tracer.warning(tid, "understand_health", f"SQL count failed: {e}")
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass

    # Vector count — ChromaDB may not be available. Wrap in try/except.
    vector_count = 0
    try:
        from core.kgraph.vectors import get_project_vector_collection
        collection = get_project_vector_collection(pm)
        vector_count = int(collection.count())
    except Exception as e:
        tracer.warning(tid, "understand_health", f"Vector count failed: {e}")

    # Chroma dir size — walk + sum. Path depends on is_agent_root.
    if is_agent_root:
        chroma_dir = cfg.memory_root / "understand" / "chroma"
    else:
        chroma_dir = pm.artifact_root / "chroma"
    chroma_size = _dir_size_bytes(chroma_dir)

    tracer.step(
        tid, "understand_health",
        f"indexed=True, files={file_count}, edges={edge_count}, vectors={vector_count}",
    )
    tracer.finish(tid, success=True, result=f"indexed, {file_count} files")
    return {
        "status": "success",
        "action": "health",
        "project_path": project_path,
        "project_id": pm.project_id,
        "indexed": True,
        "last_indexed": last_indexed,
        "file_count": file_count,
        "edge_count": edge_count,
        "vector_count": vector_count,
        "kg_db_size_bytes": kg_db_size,
        "chroma_dir_size_bytes": chroma_size,
        "embedding_available": emb_available,
        "trace_id": tid,
        "errors": [],
    }


__all__ = [
    "query_codebase",
    "health_check",
]
