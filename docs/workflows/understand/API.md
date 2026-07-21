<- Back to [Understand Overview](../UNDERSTAND.md)

# 📝 API Reference

## 🔧 Tool Signature

The understand workflow is triggered via:

```python
workflow(type="understand", goal="Map the auth module", project_root="D:/projects/myapp")
```

Optional parameter:
- `skip_embeddings` (bool, default False): v1.4 — Skip vector embedding indexing. Graph edges still stored. Use when LM Studio is slow/unavailable or for fast re-indexing.

Or directly via `base.py`:

```python
from workflows.base import run_workflow
result = run_workflow(
    workflow_type="understand",
    goal="Index codebase",
    project_root="/path/to/project",
    trace_id="abc123",
)
```

Or via the standalone facade:

```python
from workflows.understand import run_understand_workflow_sync
result = run_understand_workflow_sync("/path/to/project", trace_id="abc123")
# [v1.4.1] Always returns a dict with "status" and "errors" keys.
# Success path: {"status": "completed", "errors": [], ...}
# Failure path: {"status": "failed", "errors": ["..."]}
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

**Logic:**
1. [v1.4.1 P1-1] Bail early if `status == "failed"` (belt-and-suspenders alongside `route_after_init`).
2. [v1.4.1 P1-6] Check `is_workflow_cancelled(trace_id)` at start + every 100 files.
3. Walk the source tree with `os.walk()`, skipping `ProjectManager.SKIP_DIRS` directories.
4. For each file with a supported extension (`.py`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.go`, `.rs` + 9 more + `.md`/`.txt`/`.rst`), check if it changed since last index (mtime + size).
5. If changed, compute chunked MD5 hash and compare with stored hash.
6. Collect all changed files as `(full_path, rel_path, hash, mtime, size)` tuples.

**Output:** Partial dict with `files_to_parse` (list of tuples), or `{"status": "failed", "errors": ["Workflow cancelled"]}` on cancel.

**Performance:** Uses `_chunked_md5()` (8KB chunks) instead of `read_bytes()` to avoid memory spikes on large files.

**[v1.4.1 P1-7]** GraphStore is created INSIDE the `try` block; `finally` checks `if store is not None` before calling `close()`. Was: bare `store.close()` in finally that raised `NameError` when the constructor itself raised.

**[v1.4.1 P2-2]** Uses `ProjectManager.SKIP_DIRS` (class constant) instead of a local set. Includes `.mypy_cache`, `.ruff_cache`, `.tox`, `htmlcov` (new in v1.4.1).

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

*Last updated: 2026-07-21 (v1.4.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
