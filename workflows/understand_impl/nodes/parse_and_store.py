"""Node: parse_and_store — Parse changed files, store dependency edges + code embeddings.

[#3] Populates ChromaDB vector embeddings for each file's top-level definitions.
[#4] Multi-language support via tree-sitter (Python, JS/TS, Go, Rust).

If the embedding service (LM Studio) is unavailable, vector indexing is skipped
gracefully — the graph edges in SQLite are still stored.
"""
from __future__ import annotations

from pathlib import Path

from workflows.understand_impl.state import UnderstandState
from core.tracer import tracer
from core.config import cfg
from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from core.kgraph.tree_sitter_parser import extract_imports, get_language_for_file, is_supported, is_doc_file
from core.kgraph.embeddings import extract_definitions, extract_doc_chunks
from core.kgraph.vectors import upsert_file_vectors


def node_parse_and_store(state: UnderstandState) -> dict:
    """Parse changed files, store dependency edges + code embeddings."""
    tid = state.get("trace_id", "understand")
    files_to_parse = state.get("files_to_parse", [])
    if not files_to_parse:
        tracer.step(tid, "parse", "No changed files — codebase is up to date.")
        return {
            "status": "completed",
            "files_parsed": 0,
            "edges_created": 0,
            "vectors_created": 0,
            "errors": [],
            "note": "No changed files — codebase is up to date.",
        }

    tracer.step(tid, "parse", f"Parsing {len(files_to_parse)} changed files...")

    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    db_path = pm.artifact_root / "kg.db"
    store = GraphStore(db_path)

    parsed = 0
    edges = 0
    vectors = 0
    errors = []

    batch_size = getattr(cfg, "understand_batch_size", 10)
    # v1.2.1 (P1-1): Wrap in try/finally — was: store.close() outside finally.
    # If an exception escaped the per-file try/except (e.g., batch boundary
    # error), the SQLite connection leaked. INSTRUCTIONS #3: always close in finally.
    try:
        for i in range(0, len(files_to_parse), batch_size):
            batch = files_to_parse[i:i + batch_size]

            for full_path, rel_path, current_hash, mtime, size in batch:
                try:
                    content = Path(full_path).read_text(encoding="utf-8", errors="replace")

                    # v1.3: Branch — doc files (.md/.txt/.rst) vs code files
                    if is_doc_file(rel_path):
                        # Doc path: chonkie sentence chunking, no graph edges
                        store.upsert_file_graph(
                            state["project_id"], rel_path, current_hash,
                            [], mtime, size  # no target_paths — docs don't have imports
                        )
                        parsed += 1
                        # No edges for docs

                        # v1.3: Use chonkie for doc chunking (tree-sitter can't parse prose)
                        doc_chunks = extract_doc_chunks(content, rel_path, tid)
                        vectors += upsert_file_vectors(
                            state["project_id"], rel_path, doc_chunks, trace_id=tid,
                        )
                    else:
                        # Code path: tree-sitter imports + definitions (existing v1.2 logic)
                        language = get_language_for_file(rel_path) or "python"
                        deps = extract_imports(content, language)

                        target_paths = set()
                        for dep in deps:
                            target_paths.add(dep)
                            # For Python, also add the path-form (dotted → slashes)
                            if language == "python":
                                target_paths.add(dep.replace(".", "/") + ".py")

                        store.upsert_file_graph(
                            state["project_id"], rel_path, current_hash,
                            list(target_paths), mtime, size
                        )
                        parsed += 1
                        edges += len(target_paths)

                        # [#3] Populate code embeddings for semantic search.
                        # [#4] Pass the detected language for multi-language chunking.
                        # Graceful: if LM Studio is unavailable, this returns 0.
                        definitions = extract_definitions(content, language)
                        vectors += upsert_file_vectors(
                            state["project_id"], rel_path, definitions, trace_id=tid,
                        )
                except Exception as e:
                    errors.append(f"Failed to parse {rel_path}: {e}")
    finally:
        store.close()

    tracer.step(
        tid, "parse",
        f"Completed. Parsed {parsed} files, {edges} edges, {vectors} vectors."
    )
    return {
        "files_parsed": parsed,
        "edges_created": edges,
        "vectors_created": vectors,
        "errors": errors,
        "status": "completed" if not errors else "completed_with_errors"
    }
