<- Back to [Understand Overview](../UNDERSTAND.md)

# 📝 API Reference

## 🔧 Tool Signature

The understand workflow is triggered via:

```python
workflow(type="understand", goal="Map the auth module", project_root="D:/projects/myapp")
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

**Purpose:** Scan the project for changed/new Python files that need indexing.

**Logic:**
1. Walk the source tree with `os.walk()`, skipping common directories
2. For each `.py` file, check if it changed since last index (mtime + size)
3. If changed, compute chunked MD5 hash and compare with stored hash
4. Collect all changed files as `(full_path, rel_path, hash, mtime, size)` tuples

**Output:** Partial dict with `files_to_parse` (list of tuples).

**Performance:** Uses `_chunked_md5()` (8KB chunks) instead of `read_bytes()` to avoid memory spikes on large files.

---

### `node_parse_and_store(state)` — Phase 3: AST Parsing + Graph Storage

**Purpose:** Parse changed files and store dependency edges in the knowledge graph.

**Logic:**
1. Process files in batches (configurable via `UNDERSTAND_BATCH_SIZE`, default 10)
2. For each file, read content and parse imports via `_parse_dependencies_sync_from_string()`
3. Deduplicate target paths (both `dep` and `dep.replace(".", "/") + ".py"`)
4. Upsert file graph node + dependency edges via `GraphStore.upsert_file_graph()`
5. Close GraphStore connection when done

**Output:** Partial dict with `files_parsed`, `edges_created`, `errors`, `status`.

**Status values:** `"completed"` (no errors) or `"completed_with_errors"` (some files failed but workflow succeeded).

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
  "errors": ["Failed to parse broken.py: SyntaxError: ..."],
  "trace_id": "abc123"
}
```

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

---

*Last updated: 2026-07-05 (v1.0 split). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
