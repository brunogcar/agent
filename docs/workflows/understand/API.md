<- Back to [Understand Overview](../UNDERSTAND.md)

# 📝 API Reference

## 🔧 Tool Signature

The understand workflow is triggered via:

```python
workflow(type="understand", goal="Map the auth module", project_root="D:/projects/myapp")
```

Optional parameters:
- `action` (str, default `"index"`): [v1.5] Routes to one of three modes:
  - `"index"` (default) — runs the full indexing graph (backward compat).
  - `"query"` — search the already-indexed codebase (see Query Interface below).
  - `"health"` — return index stats without running the graph (see Health Check below).
- `skip_embeddings` (bool, default False): v1.4 — Skip vector embedding indexing. Graph edges still stored. Use when LM Studio is slow/unavailable or for fast re-indexing. (action="index" only.)
- `query_type` (str, default `"semantic"`): [v1.5] One of `semantic`, `keyword`, `dependencies`, `callers`. (action="query" only.)
- `file_path` (str, default `""`): [v1.5] Required for `query_type="dependencies"` + `query_type="callers"`. The relative file path to inspect (e.g. `"core/config.py"`). (action="query" only.)
- `top_k` (int, default 10): [v1.5] Max results to return for semantic + keyword queries. (action="query" only.)

Or directly via `base.py`:

```python
from workflows.base import run_workflow

# action="index" (default) — full indexing run
result = run_workflow(
    workflow_type="understand",
    goal="Index codebase",
    project_root="/path/to/project",
    trace_id="abc123",
)

# action="query" — semantic search (goal IS the search query)
result = run_workflow(
    workflow_type="understand",
    goal="how does auth work",
    project_root="/path/to/project",
    action="query",
    query_type="semantic",
    top_k=10,
)

# action="query" — keyword search
result = run_workflow(
    workflow_type="understand",
    goal="auth config",
    project_root="/path/to/project",
    action="query",
    query_type="keyword",
)

# action="query" — dependencies of a file
result = run_workflow(
    workflow_type="understand",
    goal="dependencies of main.py",
    project_root="/path/to/project",
    action="query",
    query_type="dependencies",
    file_path="src/main.py",
)

# action="query" — callers of a file
result = run_workflow(
    workflow_type="understand",
    goal="callers of utils.py",
    project_root="/path/to/project",
    action="query",
    query_type="callers",
    file_path="src/utils.py",
)

# action="health" — index stats
result = run_workflow(
    workflow_type="understand",
    goal="health check",
    project_root="/path/to/project",
    action="health",
)
```

Or via the standalone facade:

```python
from workflows.understand import run_understand_workflow_sync

# action="index" (default) — full indexing run
result = run_understand_workflow_sync("/path/to/project", trace_id="abc123")
# [v1.4.1] Always returns a dict with "status" and "errors" keys.
# Success path: {"status": "completed", "errors": [], ...}
# Failure path: {"status": "failed", "errors": ["..."]}

# [v1.5] action="query" — semantic search
result = run_understand_workflow_sync(
    "/path/to/project",
    action="query",
    question="how does auth work",
    query_type="semantic",
    top_k=10,
    trace_id="abc123",
)

# [v1.5] action="health" — index stats
result = run_understand_workflow_sync(
    "/path/to/project",
    action="health",
    trace_id="abc123",
)
```

Or call the query/health functions directly (bypass both base.py + the facade):

```python
from workflows.understand import query_codebase, health_check
# [v1.5.1] These are re-exported from workflows.understand_impl.query
# (was: workflows.understand_query — moved in v1.5.1).

results = query_codebase(
    project_path="/path/to/project",
    question="how does auth work",
    query_type="semantic",
    top_k=10,
)

stats = health_check(project_path="/path/to/project")
```

---

## ⚡ Nodes

### `node_init_project(state)` — Phase 1: Project Initialization

**Purpose:** Initialize ProjectManager and verify GraphStore can be created.

**Logic:**
1. Create `ProjectManager` for the project path
2. Check source root exists (for non-agent projects)
3. Check indexing mode (reject if too large)
4. Initialize project artifacts
5. Verify GraphStore creation (create + close immediately)

**Output:** Partial dict with `status` ("running" or "failed"), `project_id`, `artifact_dir`, `project_path` (resolved).

**Error handling:** Returns `{"status": "failed", "errors": [...]}` if source root missing, project too large, or GraphStore init fails. [v1.4.1 P0-1] The graph's `route_after_init` conditional edge short-circuits to END on failure — discover/parse/report don't run on a half-initialized project.

---

### `node_discover_files(state)` — Phase 2: File Discovery

**Purpose:** Scan the project for changed/new files that need indexing.
**[v1.5.1]** Also detect files that were indexed but have since been deleted
from disk, and remove their graph nodes + edges + ChromaDB vectors.

**Logic:**
1. [v1.4.1 P1-1] Bail early if `status == "failed"` (belt-and-suspenders alongside `route_after_init`).
2. [v1.4.1 P1-6] Check `is_workflow_cancelled(trace_id)` at start + every 100 files.
3. **Phase 1 (existing behavior — disk walk + change detection):**
   - Walk the source tree with `os.walk()`, skipping `ProjectManager.SKIP_DIRS`.
   - For each file with a supported extension, check if it changed since last index (mtime + size fast path, then chunked MD5).
   - Collect changed files as `(full_path, rel_path, hash, mtime, size)` tuples.
   - [v1.5.1] Collect every walked rel_path into a `disk_paths` set for Phase 2.
4. **[v1.5.1] Phase 2 (stale cleanup):**
   - Query `GraphStore.get_all_file_paths(project_id)` for stored paths.
   - Compute `orphans = stored_paths - disk_paths` (set difference).
   - For each orphan: `GraphStore.delete_file_entry(project_id, orphan_path)`
     (deletes the node + all outgoing/incoming edges).
   - Unless `skip_embeddings=True`: `collection.delete(where={"file_path": orphan_path})`
     for each orphan (wrapped in try/except — ChromaDB may be unavailable).
   - Trace: `Cleaned up N stale files from index` (or `No stale files detected` if empty).

**Output:** Partial dict with `files_to_parse` (list of tuples), or `{"status": "failed", "errors": ["Workflow cancelled"]}` on cancel.

**Performance:** Uses `_chunked_md5()` (8KB chunks) instead of `read_bytes()` to avoid memory spikes on large files. Phase 2 is O(stored_paths) — a single SQL SELECT + one DELETE per orphan (cheap).

**[v1.4.1 P1-7]** GraphStore is created INSIDE the `try` block; `finally` checks `if store is not None` before calling `close()`. Was: bare `store.close()` in finally that raised `NameError` when the constructor itself raised.

**[v1.4.1 P2-2]** Uses `ProjectManager.SKIP_DIRS` (class constant) instead of a local set. Includes `.mypy_cache`, `.ruff_cache`, `.tox`, `htmlcov` (new in v1.4.1).

**[v1.5.1] ChromaDB cleanup skipped when `skip_embeddings=True`** — we never indexed vectors in the first place, so there's nothing to clean up. (And the ChromaDB collection may not even exist.)

---

### `node_parse_and_store(state)` — Phase 3: Tree-sitter Parsing + Graph Storage + Vector Embeddings

**Purpose:** Parse changed files, store dependency edges in the knowledge graph, and populate code embeddings for semantic search.

**Logic:**
1. [v1.4.1 P1-1] Bail early if `status == "failed"`.
2. [v1.4.1 P1-6] Check `is_workflow_cancelled(trace_id)` at start + every 10 files + per embedding batch.
3. **Phase 1 (graph edges):** For each file:
   - [v1.4.1 P3-1] Re-check file size before `read_text` (handles files that grew between discover + parse).
   - [v1.4.1 P3-3] Log progress every 50 files.
   - If doc file (`.md`/`.txt`/`.rst`): collect chonkie chunks for Phase 2 (no graph edges).
   - If code file: detect language, extract imports via tree-sitter `extract_imports(content, language, errors=errors)` [v1.4.1 P3-4], deduplicate target paths, upsert file graph node + edges.
   - [v1.4.1 P2-10] Errors appended via `_append_capped()` — list capped at 100 entries.
4. **Phase 2 (embeddings):** If `skip_embeddings=False` and definitions exist:
   - Check `is_embedding_available()` (cached).
   - [v1.4.1 P1-5] `_batch_embed_and_store()` returns `tuple[int, list[str]]` — failed batches append to the errors list (was: only `tracer.warning`-logged).
   - [v1.4.1 P2-8] Batch size from `cfg.understand_embed_batch_size` (env: `UNDERSTAND_EMBED_BATCH_SIZE`, default 100).
5. [v1.4.1 P2-10] If errors were capped, append `"... and N more errors (capped at 100)"` summary entry.

**Output:** Partial dict with `files_parsed`, `edges_created`, `vectors_created`, `errors`, `status`.

**Status values:** `"completed"` (no errors) or `"completed_with_errors"` (some files failed but workflow succeeded), or `"failed"` (cancelled).

**[v1.4.1 P2-14]** The outer Phase-1 batch loop was removed. Was: `for i in range(0, len(files), batch_size):` — each file is processed one at a time, so the batching added no value. `cfg.understand_batch_size` is kept for backward compat (unused in Phase 1; Phase 2 uses `cfg.understand_embed_batch_size`).

**Graceful degradation:** If LM Studio is unavailable or the embedding model isn't loaded, `embed_texts()` returns `None` and the batch is skipped with an error entry. The workflow continues — graph edges are still stored.

---

### `node_report(state)` — Phase 4: Report Generation

**Purpose:** Generate a codebase overview report.

**Logic:**
1. Build report sections (project path, indexing summary, errors).
2. [v1.4.1 P2-4] Summary includes `vectors_created` when `skip_embeddings=False`. Omits the Vectors line when `skip_embeddings=True` (avoids misleading "0 vectors" when we didn't even try).
3. Call `report(action="report", ...)` tool.
4. Log any report generation failures via `tracer.error()`.

**Output:** Empty dict `{}` or `{"note": "..."}` (report is a side effect).

---

## 📤 Output

### Success
```json
{
  "status": "completed",
  "project_path": "/path/to/project",
  "files_parsed": 42,
  "edges_created": 156,
  "vectors_created": 128,
  "errors": [],
  "trace_id": "abc123"
}
```

### Success with errors
```json
{
  "status": "completed_with_errors",
  "project_path": "/path/to/project",
  "files_parsed": 40,
  "edges_created": 150,
  "vectors_created": 120,
  "errors": ["Failed to parse broken.py: SyntaxError: ..."],
  "trace_id": "abc123"
}
```

### Success (LM Studio unavailable — vectors skipped)
```json
{
  "status": "completed_with_errors",
  "project_path": "/path/to/project",
  "files_parsed": 42,
  "edges_created": 156,
  "vectors_created": 0,
  "errors": ["Embedding batch 1 failed — skipped 100 items (LM Studio unavailable or error)"],
  "trace_id": "abc123"
}
```
> When `vectors_created` is 0 but `files_parsed` > 0, LM Studio was unavailable. Graph edges are stored; semantic search won't work until LM Studio is running with the embedding model loaded. [v1.4.1 P1-5] The errors list now includes the batch-failure message (was: only warned).

### Failure (init failed — short-circuited by route_after_init)
```json
{
  "status": "failed",
  "errors": ["Source root does not exist: /path/to/project/code"],
  "trace_id": "abc123"
}
```
> [v1.4.1 P0-1] When `node_init_project` fails, `route_after_init` routes directly to END — discover/parse/report don't run. Was: they ran anyway, creating an empty kg.db and reporting "✅ up to date".

---

## 🔍 Query Interface (v1.5)

`action="query"` searches an already-indexed codebase WITHOUT running the
indexing graph. The `goal` parameter is the search query (for semantic +
keyword) or a description (for dependencies + callers — `file_path` is the
actual query target).

### `query_type="semantic"` — vector search via ChromaDB

Finds code definitions whose embeddings are closest to the query string.
Requires LM Studio running with the embedding model loaded.

```python
result = run_workflow(
    workflow_type="understand",
    goal="how does the auth token validation work",
    project_root="/path/to/project",
    action="query",
    query_type="semantic",
    top_k=10,
)
```

**Result shape:**
```json
{
  "status": "success",
  "action": "query",
  "query_type": "semantic",
  "question": "how does the auth token validation work",
  "project_path": "/path/to/project",
  "results": [
    {
      "file_path": "src/auth/tokens.py",
      "name": "validate_token",
      "type": "function",
      "line_start": 42,
      "line_end": 58,
      "distance": 0.123,
      "source": "def validate_token(token):\n    ...",
      "snippet": " 42 | def validate_token(token):\n 43 |     if not token:\n 44 |         return False\n 45 |     ..."
    }
  ],
  "count": 1,
  "trace_id": "abc123",
  "errors": []
}
```

**Snippet format:** `grep -n`-style line-numbered prefix (`  N | <code>`),
offset by `line_start`. First 5 lines of `source`, capped at 500 chars.

**Graceful degradation:** If LM Studio is unavailable, returns:
```json
{
  "status": "success",
  "results": [],
  "count": 0,
  "errors": ["Embedding service unavailable — semantic search requires LM Studio running"]
}
```
Callers can fall back to `query_type="keyword"` without an extra round-trip.

### `query_type="keyword"` — SQL path match

Finds files whose paths contain keywords from the query. No LM Studio
required — pure SQL on the kg.db.

```python
result = run_workflow(
    workflow_type="understand",
    goal="auth config",
    project_root="/path/to/project",
    action="query",
    query_type="keyword",
    top_k=5,
)
```

**Result shape:**
```json
{
  "status": "success",
  "action": "query",
  "query_type": "keyword",
  "results": [
    {"file_path": "src/auth.py"},
    {"file_path": "core/config.py"}
  ],
  "count": 2,
  "errors": []
}
```

### `query_type="dependencies"` — outgoing edges

Returns the files that a given file imports. **Requires `file_path`.**

```python
result = run_workflow(
    workflow_type="understand",
    goal="dependencies of main.py",
    project_root="/path/to/project",
    action="query",
    query_type="dependencies",
    file_path="src/main.py",
)
```

**Result shape:**
```json
{
  "status": "success",
  "action": "query",
  "query_type": "dependencies",
  "results": [
    {"target": "src/utils.py"},
    {"target": "src/auth.py"}
  ],
  "count": 2,
  "errors": []
}
```

### `query_type="callers"` — incoming edges

Returns the files that import a given file. **Requires `file_path`.**

```python
result = run_workflow(
    workflow_type="understand",
    goal="callers of utils.py",
    project_root="/path/to/project",
    action="query",
    query_type="callers",
    file_path="src/utils.py",
)
```

**Result shape:**
```json
{
  "status": "success",
  "action": "query",
  "query_type": "callers",
  "results": [
    {"caller": "src/main.py"},
    {"caller": "src/auth.py"}
  ],
  "count": 2,
  "errors": []
}
```

### Query error cases

| Case | status | errors |
|------|--------|--------|
| Invalid `query_type` | `failed` | `["Invalid query_type: <x>. Use: semantic, keyword, dependencies, callers"]` |
| `file_path` missing for dependencies/callers | `failed` | `["file_path is required for dependencies/callers queries"]` |
| Project not indexed (no kg.db) | `failed` | `["Project not indexed. Run understand(action='index') first. Expected: <path>/kg.db"]` |
| Embedding service unavailable (semantic only) | `success` | `["Embedding service unavailable — semantic search requires LM Studio running"]` (results=[], count=0) |

---

## 🩺 Health Check (v1.5)

`action="health"` returns index stats WITHOUT running the graph. Operators
use it to decide whether to index — `indexed=False` is NOT a failure (it's
the natural state of a project that hasn't been indexed yet).

```python
result = run_workflow(
    workflow_type="understand",
    goal="health check",
    project_root="/path/to/project",
    action="health",
)
```

**Result shape:**
```json
{
  "status": "success",
  "action": "health",
  "project_path": "/path/to/project",
  "project_id": "abc123def456ghij",
  "indexed": true,
  "last_indexed": 1721606400.0,
  "file_count": 42,
  "edge_count": 156,
  "vector_count": 128,
  "kg_db_size_bytes": 524288,
  "chroma_dir_size_bytes": 1048576,
  "embedding_available": true,
  "trace_id": "abc123",
  "errors": []
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `indexed` | bool | True if kg.db exists at `{project}/.understand/kg.db`. |
| `last_indexed` | float | kg.db mtime (unix timestamp). 0.0 if not indexed. |
| `file_count` | int | `COUNT(*) FROM nodes WHERE project_id=? AND type='file'`. |
| `edge_count` | int | `COUNT(*) FROM edges WHERE project_id=?`. |
| `vector_count` | int | `collection.count()` from ChromaDB. 0 if ChromaDB unavailable. |
| `kg_db_size_bytes` | int | kg.db file size. 0 if not indexed. |
| `chroma_dir_size_bytes` | int | Sum of file sizes under chroma/ dir (capped at 1000 files). |
| `embedding_available` | bool | `is_embedding_available()` — True if LM Studio is reachable. |

**Not-indexed response** (still `status="success"`):
```json
{
  "status": "success",
  "action": "health",
  "indexed": false,
  "last_indexed": 0.0,
  "file_count": 0,
  "edge_count": 0,
  "vector_count": 0,
  "kg_db_size_bytes": 0,
  "chroma_dir_size_bytes": 0,
  "embedding_available": false,
  "errors": []
}
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `UNDERSTAND_BATCH_SIZE` | `.env` | `10` | [v1.4.1 P2-14] Unused in Phase 1 (batch loop removed). Kept for backward compat. |
| `UNDERSTAND_EMBED_BATCH_SIZE` | `.env` | `100` | [v1.4.1 P2-8] Phase-2 embedding batch size — definitions per HTTP call to LM Studio. |
| `skip_dirs` | `ProjectManager.SKIP_DIRS` | `node_modules`, `__pycache__`, `.git`, `.venv`, `venv`, `.understand`, `dist`, `build`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `htmlcov`, `.eggs` | [v1.4.1 P2-2] Directories to skip during file discovery. Canonical class constant. |
| `EMBEDDING_MODEL` | `.env` | `all-MiniLM-L6-v2-GGUF` | LM Studio embedding model name (set to match what LM Studio shows) |
| `EMBEDDING_BASE_URL` | `.env` | same as `LM_STUDIO_BASE_URL` | OpenAI-compatible embeddings endpoint |
| `EMBEDDING_ENABLED` | `.env` | `true` | Set to `false` to disable vector indexing entirely |

**Recommended embedding model:** [All-MiniLM-L6-v2-Embedding-GGUF](https://huggingface.co/second-state/All-MiniLM-L6-v2-Embedding-GGUF) (q8 = 25MB). Download in LM Studio under Models → Embeddings.

---

*Last updated: 2026-07-22 (v1.5.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
