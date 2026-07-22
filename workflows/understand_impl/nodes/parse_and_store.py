"""Node: parse_and_store — Parse changed files, store dependency edges + code embeddings.

[#3] Populates ChromaDB vector embeddings for each file's top-level definitions.
[#4] Multi-language support via tree-sitter (Python, JS/TS, Go, Rust).

If the embedding service (LM Studio) is unavailable, vector indexing is skipped
gracefully — the graph edges in SQLite are still stored.

[v1.8] Cross-language import resolution. JS/TS relative imports (`./foo`,
`../utils`) now resolve to candidate file paths (up to 13 candidates per
import: 1 raw + 6 extension variants + 6 index-file variants) via
`_resolve_import_to_file_paths()`. Go package imports store the package
short-name as a derivative (`github.com/foo/bar` → also `bar`). Rust
`use` declarations store each `::`-separated path segment except the
last item name. Python unchanged (already resolved in v1.4 via
`dep.replace(".", "/") + ".py"`). Non-relative JS/TS imports (`react`,
`@scope/pkg`) are stored raw only — they're in node_modules, not project
source. Candidates are stored as edge targets — the query layer dedupes.

[v1.4.1 P1-1] Defensive `status=="failed"` bail at the top of the node.
Belt-and-suspenders alongside route_after_init (P0-1) — if a future graph
refactor accidentally adds a direct init→parse edge, the node itself
short-circuits cleanly instead of running on a half-initialized project.

[v1.4.1 P1-5] _batch_embed_and_store now returns `tuple[int, list[str]]`
(vectors_stored, errors). Failed batches (None embeddings, count mismatch,
ChromaDB upsert exception) are appended to the errors list — was: only
`tracer.warning`-logged, so operators saw `vectors_created=5000` with no
indication that 100 items were skipped. The errors are merged into the
node's main errors list.

[v1.4.1 P1-6] Cancellation checks via `workflows.base.is_workflow_cancelled`.
Polled at the start + inside the file-parsing loop (every 10 files) + inside
the embedding batch loop (every batch). Returns
`{"status": "failed", "errors": ["Workflow cancelled"]}` on cancel.

[v1.4.1 P1-7] GraphStore creation moved INSIDE the try block. Was: created
before try → if the constructor raised, `store` was undefined → `finally:
store.close()` raised NameError, masking the original exception.

[v1.4.1 P2-8] Embedding batch size now read from cfg.understand_embed_batch_size
(was: hardcoded 100). Default 100; override via UNDERSTAND_EMBED_BATCH_SIZE env var.

[v1.4.1 P2-10] Errors list capped at 100 entries. Was: unbounded — a project
with 1000 broken files would produce a 1000-entry errors list that bloats
the final state dict + the report. Now: appends stop at 100, and a final
"... and N more errors (capped at 100)" entry is added.

[v1.4.1 P2-13] ProjectManager is re-created here (and in discover_files)
rather than passed through state. PM isn't serializable (caches stats).

[v1.4.1 P2-14] Removed the outer Phase-1 batch loop. Was:
`for i in range(0, len(files_to_parse), batch_size): batch = ...; for f in batch: ...`
The batching added no value (each file is processed one at a time). Now:
iterate directly over `files_to_parse`. `cfg.understand_batch_size` is
kept for backward compatibility but is unused in Phase 1; Phase 2 uses
`cfg.understand_embed_batch_size` (P2-8) for the embedding batch size.

[v1.4.1 P3-1] File size re-check before read_text. The discover node already
filters by MAX_FILE_SIZE_BYTES, but a file can grow between discover and
parse (especially on long-running understand invocations). Re-check guards
against loading a now-oversized file into memory.

[v1.4.1 P3-3] Progress reporting every 50 files via tracer.step.

[v1.4.1 P3-4] Passes the local `errors` list into extract_imports +
extract_definitions_ts so tree-sitter parse failures are surfaced instead
of silently swallowed.
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


# [v1.4.1 P2-10] Hard cap on the errors list. A project with 1000 broken
# files would otherwise produce a 1000-entry list that bloats the final
# state dict + the report. The final "... and N more" entry preserves
# the count for the operator.
_ERRORS_CAP = 100


# [v1.8] Candidate file extensions for JS/TS relative-import resolution.
# Stored as a module-level constant so tests can reference the same list
# (and a future change only touches one place). The set is the union of:
#   - TypeScript file extensions (.ts, .tsx)
#   - JavaScript file extensions (.js, .mjs, .cjs, .jsx)
# We always include BOTH the TS + JS variants for any JS/TS import — a
# .ts file can import a .js file (typed wrappers around legacy JS), and
# vice versa. Resolving to the "wrong" extension is harmless because the
# query layer dedupes; the candidates that don't exist on disk simply
# never match a stored node.
_JS_TS_EXTENSIONS = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx")


def _resolve_import_to_file_paths(dep: str, rel_path: str, language: str) -> list[str]:
    """[v1.8] Resolve an import string to candidate file paths.

    Returns a list of relative file paths (POSIX-style) that the import
    COULD resolve to. The caller stores ALL candidates as edge targets —
    edges are cheap (strings in SQLite), and the query layer dedupes.

    For languages where file-path resolution isn't possible (Go packages,
    Rust crates), returns ``[dep]`` (the raw import string) + any useful
    derivatives (package name, module name).

    Resolution rules per language:

    - **python** (unchanged from v1.4): ``import core.config`` → also
      stores ``core/config.py`` (file-path form). Raw module name kept.
    - **javascript / typescript** (NEW): relative imports (``./foo``,
      ``../utils``) resolve to up to 13 candidate file paths
      (1 raw + 6 extension variants + 6 index-file variants). The
      candidate list is built from the importing file's directory
      (``Path(rel_path).parent``), stripped of leading ``./`` /
      ``../`` segments (each ``../`` walks one parent dir).
      Non-relative imports (``react``, ``lodash``, ``@scope/pkg``) are
      stored raw only — they're in ``node_modules``, not project source.
    - **go**: ``import "github.com/foo/bar"`` → stores raw
      ``github.com/foo/bar`` + ``bar`` (the package name, useful for
      queries). No file-path resolution (would need GOPATH).
    - **rust**: ``use std::collections::HashMap`` → stores raw
      ``std::collections::HashMap`` + each ``::``-separated path segment
      except the last item name (so ``std::collections::HashMap`` →
      also stores ``std`` and ``collections``). No file-path resolution.

    Args:
        dep: The raw import string from tree-sitter (e.g. "core.config",
            "./foo", "../utils", "react", "fmt", "std::collections::HashMap").
        rel_path: The relative path of the importing file
            (e.g. "src/app.ts").
        language: The tree-sitter language name ("python", "javascript",
            "typescript", "go", "rust").

    Returns:
        List of candidate target paths/strings to store as edge targets.
        Always includes the raw ``dep`` as the first element (when dep
        is non-empty). Returns ``[]`` for empty ``dep``.
    """
    if not dep:
        return []

    candidates: list[str] = [dep]  # Always store the raw import string.

    if language == "python":
        # import core.config → also core/config.py
        candidates.append(dep.replace(".", "/") + ".py")

    elif language in ("javascript", "typescript"):
        # Only resolve RELATIVE imports (./ or ../). Non-relative
        # imports (react, lodash, @scope/pkg) are node_modules packages
        # — not project source. Storing file-path candidates for them
        # would pollute the edge table with phantom paths.
        if dep.startswith("./") or dep.startswith("../"):
            importing_dir = Path(rel_path).parent
            stripped = dep
            parent_depth = 0
            max_depth = len(Path(rel_path).parts)  # can't go above project root
            # Strip each leading ./ or ../ — one parent dir per ../
            while stripped.startswith("./") or stripped.startswith("../"):
                if stripped.startswith("../"):
                    stripped = stripped[3:]
                    parent_depth += 1
                    if parent_depth > max_depth:
                        # [v1.9.2] Import escapes above project root — can't resolve.
                        # Was: Path('.').parent clamps silently to root (false-positive edges).
                        # Now: bail with just [dep] (raw only).
                        return [dep]
                    importing_dir = importing_dir.parent
                else:
                    stripped = stripped[2:]
            # Join the resolved dir with the stripped import path.
            # Path("./foo").as_posix() collapses to "foo".
            resolved_base_str = (importing_dir / stripped).as_posix()
            # Candidate extension variants — both TS + JS so a .ts file
            # importing a .js file (or vice versa) resolves correctly.
            for ext in _JS_TS_EXTENSIONS:
                candidates.append(resolved_base_str + ext)
            # Index file variants — `./foo` may resolve to `foo/index.ts`
            # etc. (CommonJS / ES module folder convention).
            for ext in _JS_TS_EXTENSIONS:
                candidates.append(resolved_base_str + "/index" + ext)
        # Non-relative imports: fall through with just [dep].

    elif language == "go":
        # import "github.com/foo/bar" → also store "bar" (package name).
        # The raw package path is kept; the package name is a useful
        # derivative for query-side impact analysis (callers searching
        # for "who imports the bar package" match by short name too).
        if "/" in dep:
            pkg_name = dep.rsplit("/", 1)[-1]
            if pkg_name and pkg_name not in candidates:
                candidates.append(pkg_name)
        # No file-path resolution — Go packages don't map 1:1 to files
        # without GOPATH/module info, which we don't have at parse time.

    elif language == "rust":
        # use std::collections::HashMap → store each ::-separated path
        # segment except the last (which is the item name like HashMap).
        # use crate::models::User → also store "crate" + "models".
        if "::" in dep:
            parts = dep.split("::")
            # parts[:-1] = crate + each intermediate module name.
            for part in parts[:-1]:
                if part and part not in candidates:
                    candidates.append(part)
        # No file-path resolution — Rust modules map to files via
        # `mod` declarations, not import paths.

    return candidates


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

    # [v1.4.1 P1-1] Belt-and-suspenders bail.
    if state.get("status") == "failed":
        return {}

    # [v1.4.1 P1-6] Cancellation check at node entry.
    if _is_cancelled(tid):
        return {"status": "failed", "errors": ["Workflow cancelled"]}

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

    # [v1.4.1 P2-13] PM re-created here — see module docstring.
    pm = ProjectManager(state["project_path"], is_agent_root=state["is_agent_root"])
    # [v1.9.1 P2-4] Removed state.setdefault — violates no-mutation convention.

    db_path = pm.artifact_root / "kg.db"

    # [v1.4.1 P1-7] GraphStore created INSIDE try; finally checks for None.
    store = None

    parsed = 0
    edges = 0
    vectors = 0
    errors: list[str] = []

    # [v1.4.1 P2-10] Reset the dropped-counter at the start of each node
    # invocation so a previous run's cap count doesn't bleed into this one.
    dropped = 0  # [v1.9.1 P2-6] local counter (was module-global _DROPPED)

    # v1.4: Collect all definitions for batched embedding (Phase 2)
    all_definitions: list[tuple[str, dict]] = []  # [(rel_path, def_dict), ...]
    all_doc_chunks: list[tuple[str, dict]] = []   # [(rel_path, chunk_dict), ...]

    try:
        store = GraphStore(db_path)

        # [v1.4.1 P2-14] Removed the outer `for i in range(0, len(files_to_parse),
        # batch_size):` loop. Each file is processed one at a time — the batching
        # added no value. cfg.understand_batch_size is preserved for backward
        # compat (Phase 2 now uses cfg.understand_embed_batch_size instead).
        for idx, (full_path, rel_path, current_hash, mtime, size) in enumerate(files_to_parse):
            # [v1.4.1 P1-6] Cooperative cancellation check every 10 files.
            if idx % 10 == 0 and idx > 0 and _is_cancelled(tid):
                tracer.step(tid, "parse", "Workflow cancelled mid-parse — aborting.")
                if not _append_capped(errors, "Workflow cancelled", _ERRORS_CAP): dropped += 1
                return {
                    "status": "failed",
                    "errors": errors,
                    "files_parsed": parsed,
                    "edges_created": edges,
                    "vectors_created": 0,
                }

            # [v1.4.1 P3-3] Progress reporting every 50 files.
            if idx > 0 and idx % 50 == 0:
                tracer.step(tid, "parse", f"Progress: {idx}/{len(files_to_parse)} files parsed")

            try:
                # [v1.4.1 P3-1] Re-check file size before read_text. The file may
                # have grown between discover_files and parse_and_store.
                full_path_obj = Path(full_path)
                try:
                    if full_path_obj.stat().st_size > ProjectManager.MAX_FILE_SIZE_BYTES:
                        if not _append_capped(errors, f"File too large (>{ProjectManager.MAX_FILE_SIZE_BYTES} bytes): {rel_path}", _ERRORS_CAP): dropped += 1
                        continue
                except OSError as size_err:
                    if not _append_capped(errors, f"Stat failed for {rel_path}: {size_err}", _ERRORS_CAP): dropped += 1
                    continue

                content = full_path_obj.read_text(encoding="utf-8", errors="replace")

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
                    # [v1.4.1 P3-4] Pass errors list so tree-sitter parse failures
                    # are surfaced instead of silently swallowed.
                    deps = extract_imports(content, language, errors=errors)

                    target_paths = set()
                    for dep in deps:
                        # [v1.8] Cross-language import resolution — JS/TS
                        # relative imports now resolve to candidate file
                        # paths (up to 13 candidates per import: 1 raw +
                        # 6 extension variants + 6 index-file variants).
                        # Go/Rust store raw + package/module-name
                        # derivatives. Python unchanged.
                        for candidate in _resolve_import_to_file_paths(
                            dep, rel_path, language
                        ):
                            target_paths.add(candidate)

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
                if not _append_capped(errors, f"Failed to parse {rel_path}: {e}", _ERRORS_CAP): dropped += 1
    finally:
        # [v1.4.1 P1-7] Null check — was bare store.close() that raised NameError.
        if store is not None:
            store.close()

    # [v1.4.1 P2-10] Append a "... and N more" summary entry if we dropped
    # error messages during the cap. Placed AFTER the merge so the cap entry
    # itself isn't dropped.
    # [v1.9.1 P2-6] dropped tracked locally via _append_capped return values
    if dropped > 0:
        # The cap entry counts toward the cap+1 slot — that's fine, the final
        # list will be at most _ERRORS_CAP + 1 entries (the summary).
        errors.append(f"... and {dropped} more errors (capped at {_ERRORS_CAP})")

    # ── Phase 2: Batched embedding (v1.4 — was per-file, now batched) ────
    embed_errors: list[str] = []
    # [v1.9.1 P1-3] Reset embedding availability check each run
    if not skip_embeddings and (all_definitions or all_doc_chunks):
        try:
            from core.kgraph.embeddings import reset_embedding_check
            reset_embedding_check()
        except Exception:
            pass  # Non-fatal
        from core.kgraph.embeddings import is_embedding_available
        from core.kgraph.vectors import get_project_vector_collection

        if not is_embedding_available():
            tracer.step(tid, "parse",
                        "Embedding service unavailable — skipping vector indexing. "
                        "Graph edges stored successfully.")
        else:
            # [v1.4.1 P1-3] Pass pm (not project_id) — get_project_vector_collection
            # now expects a ProjectManager so it can compute the project-scoped path.
            collection = get_project_vector_collection(pm)
            vectors, embed_errors = _batch_embed_and_store(
                collection, pm, all_definitions, all_doc_chunks, tid
            )
            tracer.step(tid, "parse",
                        f"Embedded {vectors} definitions/chunks in batched mode.")
    elif skip_embeddings:
        tracer.step(tid, "parse", "skip_embeddings=True — vector indexing skipped.")

    # [v1.4.1 P1-5] Merge embedding batch errors into the main errors list.
    for e in embed_errors:
        if not _append_capped(errors, e, _ERRORS_CAP): dropped += 1

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


def _append_capped(errors: list[str], message: str, cap: int) -> bool:
    """Append to errors, respecting the cap.

    [v1.9.1 P2-6] Returns True if appended, False if dropped.
    Was: module-global _DROPPED counter (shared across concurrent runs).
    """
    if len(errors) < cap:
        errors.append(message)
        return True
    return False


# [v1.9.1 P2-6] _DROPPED module-global + _dropped_count + _reset_dropped_counter
# removed. _append_capped now returns bool; caller tracks `dropped` locally.


def _batch_embed_and_store(
    collection,
    pm,
    definitions: list[tuple[str, dict]],
    doc_chunks: list[tuple[str, dict]],
    trace_id: str,
) -> tuple[int, list[str]]:
    """v1.4: Batch-embed all definitions + doc chunks in groups.

    [v1.4.1 P1-3] Signature: `pm` (was: `project_id`). Used to look up
    the project ID for the ChromaDB metadata.

    [v1.4.1 P1-5] Returns `tuple[int, list[str]]` (vectors_stored, errors).
    Failed batches (None embeddings, count mismatch, ChromaDB upsert
    exception) append an error string instead of only warning.

    [v1.4.1 P2-8] Batch size now from cfg.understand_embed_batch_size
    (was: hardcoded 100).

    Replaces the per-file embed_texts() calls (965 HTTP requests) with
    ~55 batched calls (5500 definitions / 100 per batch). 10x speedup.

    Also handles per-file deletion of old vectors before inserting new ones.
    """
    from core.kgraph.embeddings import embed_texts

    errors: list[str] = []
    project_id = pm.project_id
    # [v1.7] Per-project embedding model. Was: cfg.embedding_model (global).
    # Now: pm.get_embedding_model() reads .understand/config.json override.
    model = pm.get_embedding_model() if hasattr(pm, "get_embedding_model") else ""

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
    # [v1.4.1 P2-8] Configurable batch size — was hardcoded `batch_size = 100`.
    batch_size = getattr(cfg, "understand_embed_batch_size", 100)

    for i in range(0, len(all_items), batch_size):
        # [v1.4.1 P1-6] Cooperative cancellation check between batches.
        if _is_cancelled(trace_id):
            errors.append("Workflow cancelled during embedding phase")
            break

        batch = all_items[i:i + batch_size]
        batch_num = i // batch_size + 1
        texts = [d["source"] for _, d in batch]
        # [v1.7] Pass per-project model to embed_texts.
        embeddings = embed_texts(texts, trace_id=trace_id, model=model)

        if embeddings is None:
            msg = f"Embedding batch {batch_num} failed — skipped {len(batch)} items (LM Studio unavailable or error)"
            tracer.warning(trace_id, "parse", msg)
            errors.append(msg)
            continue

        if len(embeddings) != len(batch):
            msg = f"Embedding count mismatch in batch {batch_num} — got {len(embeddings)} for {len(batch)} items"
            tracer.warning(trace_id, "parse", msg)
            errors.append(msg)
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
            msg = f"ChromaDB upsert failed for batch {batch_num}: {e}"
            tracer.warning(trace_id, "parse", msg)
            errors.append(msg)

    # [v1.4.1 P2-10] Append a cap-summary entry if we hit the limit.
    # The embedding errors list is small (bounded by # of batches), so the
    # cap rarely triggers here — but the main node loop will still respect
    # _ERRORS_CAP when merging.
    return vectors_stored, errors


def _is_cancelled(tid: str) -> bool:
    """[v1.4.1 P1-6] Check the global workflow-cancellation flag.

    Wraps `workflows.base.is_workflow_cancelled` in a try/except so a broken
    base.py import doesn't crash the node.
    """
    try:
        from workflows.base import is_workflow_cancelled
        return is_workflow_cancelled(tid)
    except Exception:
        return False
