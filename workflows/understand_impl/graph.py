"""Graph builder and metadata for the understand workflow.

[Decision] This is the v1.0 split — the previous version (async nodes in a
monolithic file) is now Pre-v1.0 in the CHANGELOG. The async→sync conversion
and 16 bug fixes were done in the Pre-v1.0 → v1.0 transition.

[Decision] Uses UnderstandState (not WorkflowState from base.py) because
understand has unique fields: project_path, is_agent_root, project_id,
artifact_dir, files_to_parse, files_parsed, edges_created. These don't
exist in the shared WorkflowState and adding them would bloat it.

[Decision] base.py imports build_understand_graph() and _default_state()
from the thin facade (workflows/understand.py), which re-exports from here.
This is the same pattern as research_impl, autocode_impl, deep_research_impl.

[v1.4.1 P0-1] The init → discover edge is now CONDITIONAL via
`route_after_init` (workflows/understand_impl/routes.py). On init failure
(missing source root, project too large, GraphStore init crash), the graph
short-circuits to END instead of running discover_files on a half-initialized
project (which would create an empty kg.db and report "✅ up to date").

[v1.4.1 P2-1] Version bumped 1.3 → 1.4 (catching up — the code already had
v1.4 features: skip_embeddings + two-phase batched embedding). 1.4.1 is
the hardening pass (2 P0 + 7 P1 + 14 P2 + 4 P3 from a 7-reviewer collective
audit).
"""
from __future__ import annotations

from pathlib import Path
from langgraph.graph import StateGraph, END
from workflows.understand_impl.state import UnderstandState
from workflows.understand_impl.nodes.init_project import node_init_project
from workflows.understand_impl.nodes.discover_files import node_discover_files
from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store
from workflows.understand_impl.nodes.report import node_report
from workflows.understand_impl.routes import route_after_init


# [WORKFLOW_METADATA] Structured metadata for MCP client introspection.
# Allows clients (and humans) to render the workflow structure without
# reading source code. Mirrors the schema used by research / autocode /
# deep_research / autoresearch / data.
#
# [v1.4.1 P2-1] Version "1.4" — catching up. The shipped code already had
# v1.4 features (skip_embeddings + two-phase batched embedding) but the
# WORKFLOW_METADATA.version field was still "1.3". v1.4.1 is the hardening
# pass; we keep the version label at "1.4" (the feature release) and
# document the hardening in CHANGELOG.md (v1.4.1 row).
#
# [v1.5] Version bumped 1.4 → 1.5. Adds the query interface + health
# check via the `action` parameter on run_workflow(type='understand').
# New module: workflows/understand_query.py (query_codebase +
# health_check). No changes to the indexing graph itself — v1.5 is purely
# additive (new entry points that bypass the graph for query/health).
#
# [v1.6] Version bumped 1.5 → 1.6. Two changes: (1) module move —
# workflows/understand_query.py → workflows/understand_impl/query.py
# (matches the user's `<workflow>_impl/` pattern; the facade only
# re-exports). (2) Stale index cleanup — node_discover_files now detects
# files indexed-but-deleted-from-disk and removes their graph nodes +
# edges + vectors (was: orphans accumulated forever). New GraphStore
# methods: get_all_file_paths() + delete_file_entry().
#
# [v1.7] Configurability bundle. Five features: (1) UNDERSTAND_SKIP_DIRS
# env var — comma-separated extra dirs merged with _DEFAULT_SKIP_DIRS via
# ProjectManager.get_skip_dirs(). (2) UNDERSTAND_TIMEOUT_SECONDS env var
# (default 600) — was hardcoded in base.py. (3) Embedding cache in
# embeddings.py — md5(text)-keyed, 10000-entry cap, clear_embedding_cache()
# for testing. (4) Discover progress reporting — every 1000 files a
# tracer.step with count. (5) Per-project embedding model —
# .understand/config.json can specify {"embedding_model": "..."} to
# override the global cfg.embedding_model. embed_texts() gained an optional
# `model` parameter.
#
# [v1.4.1 P2-11] safety_features list added — mirrors the autoresearch pattern
# for clients that surface "what guarantees does this workflow give me?".
WORKFLOW_METADATA = {
    "name": "understand",
    # v1.4: skip_embeddings + two-phase batched embedding were already in the
    # code; the version field just hadn't been bumped. v1.4.1 is the hardening.
    # v1.5: query interface + health check (action parameter).
    # v1.6: stale index cleanup + module move (understand_query.py → understand_impl/query.py).
    # v1.7: configurability bundle — skip_dirs + timeout + embedding cache +
    #       progress reporting + per-project embedding model.
    "version": "1.7",
    "description": "Build codebase knowledge graph + doc embeddings: init → discover → parse → report",
    "entry_point": "node_init_project",
    "nodes": [
        {"name": "node_init_project", "description": "Initialize ProjectManager and verify GraphStore"},
        {"name": "node_discover_files", "description": "Scan for changed/new code + doc files via chunked MD5"},
        {"name": "node_parse_and_store", "description": "Parse imports via AST (code) or chonkie (docs), store edges + embeddings"},
        {"name": "node_report", "description": "Generate codebase overview report"},
    ],
    "edges": [
        # [v1.4.1 P0-1] Conditional edge — routes to END on init failure.
        {
            "from": "node_init_project",
            "to": "node_discover_files",
            "condition": (
                "route_after_init: status != 'failed' → discover, "
                "status == 'failed' → END (short-circuits half-init state)"
            ),
            "conditional": True,
        },
        {"from": "node_discover_files", "to": "node_parse_and_store"},
        {"from": "node_parse_and_store", "to": "node_report"},
        {"from": "node_report", "to": "END"},
    ],
    "loops": [],
    "branches": [],
    "safety_features": [
        "incremental_indexing",       # MD5 + mtime fast-path; only changed files re-parsed
        "chunked_md5",                # 8KB chunks instead of read_bytes() — no memory spikes on large files
        "graphstore_wal",             # SQLite WAL mode + thread-local conns + write serialization
        "skip_embeddings_mode",       # v1.4: graph-only mode (~5s) when LM Studio is slow/unavailable
        "graceful_embedding_degradation",  # embed_texts() None → vectors skipped, graph edges still stored
        "multi_language_support",     # v1.2: tree-sitter (Python, JS/TS, Go, Rust + 9 more in v1.4)
        "doc_indexing",               # v1.3: .md/.txt/.rst via chonkie sentence chunking
        "cancellation_checks",        # v1.4.1 P1-6: is_workflow_cancelled() polled in discover + parse loops
        "route_after_init",           # v1.4.1 P0-1: init failure short-circuits to END (was: ran discover anyway)
        "embedding_batch_errors",     # v1.4.1 P1-5: failed batches appended to errors list (was: only warned)
        "graphstore_in_try",          # v1.4.1 P1-7: GraphStore created inside try; finally checks for None
        "errors_capped_at_100",       # v1.4.1 P2-10: parse loop caps errors list (was: unbounded)
        "file_size_recheck",          # v1.4.1 P3-1: parse re-checks size before read_text (handles files that grew)
        "project_scoped_vectors",     # v1.4.1 P1-3: ChromaDB path is per-project (was: always agent_root)
        "query_interface",           # v1.5: action="query" routes to query_codebase (semantic/keyword/deps/callers) without running the graph
        "health_check",              # v1.5: action="health" returns index stats (file/edge/vector counts, sizes, embedding availability) without running the graph
        "stale_index_cleanup",       # v1.6: discover_files detects files indexed-but-deleted-from-disk and removes their graph nodes + edges + vectors
        "configurable_skip_dirs",    # v1.7: UNDERSTAND_SKIP_DIRS env var — comma-separated extra dirs merged with _DEFAULT_SKIP_DIRS
        "configurable_timeout",      # v1.7: UNDERSTAND_TIMEOUT_SECONDS env var (default 600) — was hardcoded in base.py
        "embedding_cache",           # v1.7: embed_texts() caches by md5(text); cache hits skip the HTTP call. Cap 10000 entries.
        "per_project_embedding_model",  # v1.7: .understand/config.json can override cfg.embedding_model per-project
    ],
}


def build_understand_graph():
    """Build and compile the understand LangGraph StateGraph.

    [v1.4.1 P0-1] The init → discover edge is now CONDITIONAL.
    `route_after_init` (workflows/understand_impl/routes.py) returns:
      - "discover" when init succeeded (status != "failed")
      - "end"      when init failed (status == "failed")

    This mirrors the autoresearch `route_after_setup` pattern. Without it,
    a failed init (missing source root, oversized project, GraphStore
    constructor crash) was followed by `node_discover_files` running on a
    half-initialized project, finding 0 files, and the report saying
    "✅ up to date" — silently masking the init failure.
    """
    workflow = StateGraph(UnderstandState)
    workflow.add_node("node_init_project", node_init_project)
    workflow.add_node("node_discover_files", node_discover_files)
    workflow.add_node("node_parse_and_store", node_parse_and_store)
    workflow.add_node("node_report", node_report)
    workflow.set_entry_point("node_init_project")
    # [v1.4.1 P0-1] Conditional edge — was: workflow.add_edge("node_init_project", "node_discover_files")
    workflow.add_conditional_edges(
        "node_init_project",
        route_after_init,
        {"discover": "node_discover_files", "end": END},
    )
    workflow.add_edge("node_discover_files", "node_parse_and_store")
    workflow.add_edge("node_parse_and_store", "node_report")
    workflow.add_edge("node_report", END)
    return workflow.compile()
