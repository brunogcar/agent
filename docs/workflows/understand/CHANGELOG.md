<- Back to [Understand Overview](../UNDERSTAND.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.7 | 2026-07-22 | **Configurability bundle.** (1) `UNDERSTAND_SKIP_DIRS` env var — comma-separated extra dirs to skip during file discovery (merged with `ProjectManager._DEFAULT_SKIP_DIRS`). (2) `UNDERSTAND_TIMEOUT_SECONDS` env var (default 600) — was hardcoded in base.py. (3) Embedding cache — `embed_texts()` caches by md5(text); cache hits skip the HTTP call. Cap 10000 entries. `clear_embedding_cache()` for testing. (4) Discover progress reporting — every 1000 files, a `tracer.step` with count. (5) Per-project embedding model — `.understand/config.json` can specify `{"embedding_model": "..."}` to override the global `cfg.embedding_model`. |
| v1.6 | 2026-07-22 | **Stale index cleanup + 3A fixes.** (1) `node_discover_files` now detects files that were indexed but deleted from disk, and removes their graph nodes + edges + vectors (was: orphans accumulated forever). New `GraphStore.get_all_file_paths()` + `GraphStore.delete_file_entry()` methods. (2) **Module move:** `workflows/understand_query.py` → `workflows/understand_impl/query.py` (was: sibling of facade — violated the `<workflow>_impl/` pattern). (3) **Base docs updated:** base.py was modified in v1.5 (action routing) but base docs weren't — now all 4 base docs reflect the understand action parameter. |
| v1.5 | 2026-07-22 | **Query interface + health check.** New `action` parameter routes to: `index` (default, runs the graph — backward compat), `query` (semantic/keyword/dependencies/callers search), `health` (index stats). New `workflows/understand_query.py` module. Exposes `query_similar_code` + `find_relevant_files` + `get_dependencies` + `get_callers` via a unified entry point. Semantic results include `grep -n`-style line-numbered snippets. Embedding-service failures degrade gracefully (empty results + error, not a hard failure). Health check returns `indexed=False` (still success) when kg.db missing — operators use it to decide whether to index. `WORKFLOW_METADATA.safety_features` adds `query_interface` + `health_check`. No changes to the indexing graph itself — v1.5 is purely additive. |
| v1.4.1 | 2026-07-21 | **Phase 1 hardening.** 2 P0 + 7 P1 + 14 P2 + 4 P3 from a 7-reviewer collective audit (mine + mimo + deepseek + mistral; qwen discarded as hallucinated). P0: `route_after_init` conditional edge (init failure no longer silently masks as "✅ up to date"); lazy `is_same_path` import in facade (kgraph import failure no longer cascades). P1: defensive `status=="failed"` bail in discover+parse; `queries.py` multi-language fix (was `.py`-only); ChromaDB project-scoped path (was always agent_root); PM removed from `_default_state`; embedding batch errors accumulated; cancellation checks in loops; GraphStore created inside `try`. P2: version bumped 1.3→1.4; consolidated `SKIP_DIRS`; doc chunk line numbers; report shows `vectors_created`; `skip_embeddings` in default state; `note` field in TypedDict; facade return shape normalized; configurable `UNDERSTAND_EMBED_BATCH_SIZE`; `project_path` validation; errors capped at 100; `safety_features` list; checkpoint/resume claim corrected; Phase-1 batch loop removed. P3: file size re-check; progress reporting; tree-sitter syntax errors surfaced. |
| v1.4 | 2026-07-15 | **skip_embeddings + two-phase batched embedding.** `skip_embeddings=True` runs graph-only mode (~5s) when LM Studio is slow/unavailable. Two-phase parse: Phase 1 parses all files + stores edges (no LLM); Phase 2 batch-embeds ALL definitions in one pass (was: per-file HTTP calls → 965 requests → timeout). `UNDERSTAND_EMBED_BATCH_SIZE` env var (default 100). v1.4.1 note: the WORKFLOW_METADATA.version field wasn't bumped to 1.4 at the time — fixed in v1.4.1. |
| v1.3 | 2026-07-13 | **Doc indexing (.md/.txt/.rst).** `discover_files` now finds doc files alongside code. `parse_and_store` branches: code → tree-sitter; docs → chonkie sentence chunking. New `extract_doc_chunks()` in `embeddings.py`. Chonkie is a soft dependency. |
| v1.2.1 | 2026-07-13 | **Bugfix + doc drift.** P1: `parse_and_store` `store.close()` wrapped in `finally` (was leaking SQLite connection). P2: WORKFLOW_METADATA version "1.0" → "1.2". UNDERSTAND.md rewritten — was describing Pre-v1.0 architecture. |
| v1.2 | 2026-07-06 | **Multi-language support (tree-sitter).** Tree-sitter replaces `ast` parser. Supports Python, JavaScript/TypeScript, Go, Rust through one unified API. |
| v1.1 | 2026-07-06 | **ChromaDB vector indexing (#3).** Per-definition code embeddings (functions, classes, module docstrings) via LM Studio `/v1/embeddings`. Graceful degradation when LM Studio is down. |
| v1.0 | 2026-07-05 | **Subpackage split.** Split monolithic `workflows/understand.py` (326 lines) into `workflows/understand_impl/` subpackage. Added `WORKFLOW_METADATA`. Fixed 16 bugs. |
| Pre-v1.0 | 2026-07-05 | **Architecture conversion (pre-split).** All nodes converted from `async def` to `def` (sync). Routed through `base.py`'s standard `graph.invoke()`. Fixed 16 bugs: trace_id propagation, GraphStore lifecycle, os.walk mutation, chunked MD5, duplicate edges, etc. |

---

### ⚠️ Breaking Changes

#### v1.4.1 — 2026-07-21

| Change | Impact | Migration |
|--------|--------|-----------|
| ChromaDB path moved for agent_root | Agent-root vectors now live at `memory_db/understand/chroma/` (was: `agent_root/.understand/chroma/`). | Delete the old `agent_root/.understand/chroma/` directory and re-run understand. We do NOT auto-migrate (would be a surprise move of multi-GB vector stores). |
| `get_project_vector_collection` signature changed | Was `project_id: str`, now `pm: ProjectManager`. | Pass `pm` (the ProjectManager instance) instead of `project_id`. Internal callers updated. |
| `upsert_file_vectors` + `query_similar_code` signatures changed | Same: `project_id: str` → `pm: ProjectManager`. | Pass `pm` instead of `project_id`. |
| `_default_state` no longer sets `project_id` / `artifact_dir` | They start as empty strings; `node_init_project` fills them in. | No migration — `node_init_project` always runs before any node that needs these fields. |
| `extract_imports` + `extract_definitions_ts` new optional `errors` param | New keyword-only param. | No migration — defaults to `None` (old behavior). |

#### v1.2 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| Tree-sitter replaces `ast` parser | Multi-language support (Python, JS/TS, Go, Rust). `ast`-specific behavior no longer available. | No migration — tree-sitter is a superset. If external code imported `ast`-based parsing, switch to `tree_sitter_parser.py`. |

#### v1.0 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| All nodes converted from `async def` to `def` | Nodes are now sync. `graph.ainvoke()` no longer works — use `graph.invoke()`. | No migration — `base.py` already uses `graph.invoke()`. |
| `run_understand_workflow()` (async) removed | Was the async orchestrator. Replaced by `run_understand_workflow_sync()`. | Use `run_understand_workflow_sync()` or route through `base.py`'s `run_workflow()`. |
| `ThreadPoolExecutor` + `new_event_loop()` removed | The sync facade no longer creates threads or event loops. | No migration — callers see the same sync API. |
| `trace_id` added to `UnderstandState` | State now includes `trace_id` field. | No migration — `base.py` injects it automatically. |
| `_default_state()` accepts `trace_id` parameter | New optional parameter. | No migration — defaults to `""`. |
| New env var: `UNDERSTAND_BATCH_SIZE` | Configurable batch size for AST parsing. Default: 10. | Optional — add to `.env` to customize. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Configurable `skip_dirs`** | Currently `ProjectManager.SKIP_DIRS` class constant (v1.4.1 consolidated). Should be `.env`-configurable for project-specific overrides. | P3 |
| 5 | **Additional languages** | Java, C/C++, Ruby via tree-sitter (tree-sitter-languages already bundles these — just add to LANGUAGE_MAP). [v1.4: .rb, .java, .c, .cpp, .lua, .php, .scala, .swift, .kt already added.] | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **Remove GraphStore** | GraphStore is essential for dependency querying. Removing it would break impact analysis. | Skip |
| 2 | **Remove incremental updates** | Full re-parse on every run would be too slow for large projects. | Skip |
| 3 | **Remove batch processing** | Processing all files at once would cause memory spikes. | Skip |
| 4 | **Real-time file watching** | File watching would require additional infrastructure (e.g., watchdog). | Skip |
| 5 | **IDE integration** | IDE plugins would require LSP or VS Code extension development. | Skip |

---

*Last updated: 2026-07-22 (v1.7). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
