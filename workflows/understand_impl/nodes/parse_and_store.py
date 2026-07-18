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
    """Parse changed files, store dependency edges + code embeddings.

    v1.4: Two-phase approach:
      Phase 1: Parse all files + store graph edges (fast, no LLM)
      Phase 2: If embeddings enabled, batch-embed ALL definitions in one pass
               (was: per-file HTTP calls → 965 requests → timeout on large projects)

    v1.4: skip_embeddings parameter — when True, skip Phase 2 entirely.
    Lets understand run in ~5s (graph only) when LM Studio is slow/unavailable.
    """
    tid = state.get("trace_id", "understand")
    files_to_parse = state.get("files_to_parse", [])
    skip_embeddings = state.get("skip_embeddings", False)

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

    # v1.4: Collect all definitions for batched embedding (Phase 2)
    all_definitions: list[tuple[str, dict]] = []  # [(rel_path, def_dict), ...]
    all_doc_chunks: list[tuple[str, dict]] = []   # [(rel_path, chunk_dict), ...]

    batch_size = getattr(cfg, "understand_batch_size", 10)
    try:
        # ── Phase 1: Parse files + store graph edges ────────────────────
        for i in range(0, len(files_to_parse), batch_size):
            batch = files_to_parse[i:i + batch_size]

            for full_path, rel_path, current_hash, mtime, size in batch:
                try:
                    content = Path(full_path).read_text(encoding="utf-8", errors="replace")

                    if is_doc_file(rel_path):
                        # Doc path: no graph edges, just collect chunks for Phase 2
                        store.upsert_file_graph(
                            state["project_id"], rel_path, current_hash,
                            [], mtime, size
                        )
                        parsed += 1

                        if not skip_embeddings:
                            doc_chunks = extract_doc_chunks(content, rel_path, tid)
                            for chunk in doc_chunks:
                                all_doc_chunks.append((rel_path, chunk))
                    else:
                        # Code path: tree-sitter imports + definitions
                        language = get_language_for_file(rel_path) or "python"
                        deps = extract_imports(content, language)

                        target_paths = set()
                        for dep in deps:
                            target_paths.add(dep)
                            if language == "python":
                                target_paths.add(dep.replace(".", "/") + ".py")

                        store.upsert_file_graph(
                            state["project_id"], rel_path, current_hash,
                            list(target_paths), mtime, size
                        )
                        parsed += 1
                        edges += len(target_paths)

                        # v1.4: Collect definitions for batched embedding (Phase 2)
                        if not skip_embeddings:
                            definitions = extract_definitions(content, language)
                            for d in definitions:
                                all_definitions.append((rel_path, d))
                except Exception as e:
                    errors.append(f"Failed to parse {rel_path}: {e}")
    finally:
        store.close()

    # ── Phase 2: Batched embedding (v1.4 — was per-file, now batched) ────
    if not skip_embeddings and (all_definitions or all_doc_chunks):
        from core.kgraph.embeddings import is_embedding_available, embed_texts
        from core.kgraph.vectors import get_project_vector_collection

        if not is_embedding_available():
            tracer.step(tid, "parse",
                        "Embedding service unavailable — skipping vector indexing. "
                        "Graph edges stored successfully.")
        else:
            collection = get_project_vector_collection(state["project_id"])
            vectors = _batch_embed_and_store(
                collection, state["project_id"],
                all_definitions, all_doc_chunks, tid
            )
            tracer.step(tid, "parse",
                        f"Embedded {vectors} definitions/chunks in batched mode.")
    elif skip_embeddings:
        tracer.step(tid, "parse", "skip_embeddings=True — vector indexing skipped.")

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


def _batch_embed_and_store(
    collection,
    project_id: str,
    definitions: list[tuple[str, dict]],
    doc_chunks: list[tuple[str, dict]],
    trace_id: str,
) -> int:
    """v1.4: Batch-embed all definitions + doc chunks in groups of 100.

    Replaces the per-file embed_texts() calls (965 HTTP requests) with
    ~55 batched calls (5500 definitions / 100 per batch). 10x speedup.

    Also handles per-file deletion of old vectors before inserting new ones.
    """
    from core.kgraph.embeddings import embed_texts

    # Group by file for deletion (delete old vectors per file before inserting)
    files_touched: set[str] = set()
    for rel_path, _ in definitions:
        files_touched.add(rel_path)
    for rel_path, _ in doc_chunks:
        files_touched.add(rel_path)

    for file_path in files_touched:
        try:
            collection.delete(where={"file_path": file_path})
        except Exception:
            pass

    vectors_stored = 0

    # Batch embed definitions
    all_items = [(rp, d) for rp, d in definitions] + [(rp, d) for rp, d in doc_chunks]
    batch_size = 100

    for i in range(0, len(all_items), batch_size):
        batch = all_items[i:i + batch_size]
        texts = [d["source"] for _, d in batch]
        embeddings = embed_texts(texts, trace_id=trace_id)

        if embeddings is None:
            tracer.warning(trace_id, "parse",
                           f"Embedding batch {i//batch_size + 1} failed — skipping {len(batch)} items")
            continue

        if len(embeddings) != len(batch):
            tracer.warning(trace_id, "parse",
                           f"Embedding count mismatch in batch {i//batch_size + 1}")
            continue

        ids = []
        metadatas = []
        for (rel_path, d), emb in zip(batch, embeddings):
            item_id = f"{project_id}:{rel_path}:{d['name']}"
            ids.append(item_id)
            metadatas.append({
                "project_id": project_id,
                "file_path": rel_path,
                "name": d["name"],
                "type": d["type"],
                "line_start": d.get("line_start", 0),
                "line_end": d.get("line_end", 0),
            })

        try:
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            vectors_stored += len(batch)
        except Exception as e:
            tracer.warning(trace_id, "parse",
                           f"ChromaDB upsert failed for batch {i//batch_size + 1}: {e}")

    return vectors_stored
