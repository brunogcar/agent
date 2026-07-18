<- Back to [Understand Overview](../UNDERSTAND.md)

# 📝 API Reference

## 🔧 Tool Signature

The understand workflow is triggered via:

```python
workflow(type="understand", goal="Map the auth module", project_root
- `skip_embeddings` (bool, default False): v1.4 — Skip vector embedding indexing. Graph edges still stored. Use when LM Studio is slow/unavailable or for fast re-indexing.="D:/projects/myapp")
```

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

**Output:** Partial dict with `status` ("running" or "failed").

**Error handling:** Returns `{"status": "failed", "errors": [...]}` if source root missing, project too large, or GraphStore init fails.

---

### `node_discover_files(state)` — Phase 2: File Discovery

**Purpose:** Scan the project for changed/new files that need indexing.

**Logic:**
1. Walk the source tree with `os.walk()`, skipping common directories
2. For each file with a supported extension (`.py`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.go`, `.rs`), check if it changed since last index (mtime + size)
3. If changed, compute chunked MD5 hash and compare with stored hash
4. Collect all changed files as `(full_path, rel_path, hash, mtime, size)` tuples

**Output:** Partial dict with `files_to_parse` (list of tuples).

**Performance:** Uses `_chunked_md5()` (8KB chunks) instead of `read_bytes()` to avoid memory spikes on large files.

**[#4] Multi-language:** Supported extensions are defined in `core/kgraph/tree_sitter_parser.SUPPORTED_EXTENSIONS`. Adding a new language is a 3-line change there.

---

### `node_parse_and_store(state)` — Phase 3: Tree-sitter Parsing + Graph Storage + Vector Embeddings

**Purpose:** Parse changed files, store dependency edges in the knowledge graph, and populate code embeddings for semantic search.

**Logic:**
1. Process files in batches (configurable via `UNDERSTAND_BATCH_SIZE`, default 10)
2. For each file, detect the language from the extension and parse imports via tree-sitter `extract_imports(content, language)`
3. Deduplicate target paths (for Python, both `dep` and `dep.replace(".", "/") + ".py"`)
4. Upsert file graph node + dependency edges via `GraphStore.upsert_file_graph()`
5. **[v1.1]** Extract top-level definitions via `extract_definitions(content, language)` (tree-sitter)
6. **[v1.1]** Embed each definition via LM Studio's `/v1/embeddings` endpoint and upsert into ChromaDB via `upsert_file_vectors()`
7. Close GraphStore connection when done

**Output:** Partial dict with `files_parsed`, `edges_created`, `vectors_created`, `errors`, `status`.

**Status values:** `"completed"` (no errors) or `"completed_with_errors"` (some files failed but workflow succeeded).

**[#4] Multi-language:** Language is detected per file via `get_language_for_file(rel_path)`. Tree-sitter handles Python, JavaScript/TypeScript, Go, and Rust through one API.

**Graceful degradation:** If LM Studio is unavailable or the embedding model isn't loaded, `upsert_file_vectors()` returns 0 and logs a `tracer.warning`. The workflow continues — graph edges are still stored, but semantic search won't work until LM Studio is running.

---

### `node_report(state)` — Phase 4: Report Generation

**Purpose:** Generate a codebase overview report.

**Logic:**
1. Build report sections (project path, indexing summary, errors)
2. Call `report(action="report", ...)` tool
3. Log any report generation failures via `tracer.error()`

**Output:** Empty dict `{}` (report is a side effect).

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
  "status": "completed",
  "project_path": "/path/to/project",
  "files_parsed": 42,
  "edges_created": 156,
  "vectors_created": 0,
  "errors": [],
  "trace_id": "abc123"
}
```
> When `vectors_created` is 0 but `files_parsed` > 0, LM Studio was unavailable. Graph edges are stored; semantic search won't work until LM Studio is running with the embedding model loaded.

### Failure
```json
{
  "status": "failed",
  "errors": ["Source root does not exist: /path/to/project/code"],
  "trace_id": "abc123"
}
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `UNDERSTAND_BATCH_SIZE` | `.env` | `10` | Number of files to parse per batch |
| `skip_dirs` | Hardcoded | `node_modules`, `__pycache__`, `.git`, etc. | Directories to skip during file discovery |
| `EMBEDDING_MODEL` | `.env` | `all-MiniLM-L6-v2-GGUF` | LM Studio embedding model name (set to match what LM Studio shows) |
| `EMBEDDING_BASE_URL` | `.env` | same as `LM_STUDIO_BASE_URL` | OpenAI-compatible embeddings endpoint |
| `EMBEDDING_ENABLED` | `.env` | `true` | Set to `false` to disable vector indexing entirely |

**Recommended embedding model:** [All-MiniLM-L6-v2-Embedding-GGUF](https://huggingface.co/second-state/All-MiniLM-L6-v2-Embedding-GGUF) (q8 = 25MB). Download in LM Studio under Models → Embeddings.

---

*Last updated: 2026-07-13 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
