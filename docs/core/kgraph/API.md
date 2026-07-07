<- Back to [Knowledge Graph Overview](../KGRAPH.md)

# 📝 API Reference

## 🔧 API Overview

The Knowledge Graph exposes a public API through `core/kgraph/__init__.py` for project isolation, AST parsing, graph storage, dependency queries, test mapping, and vector collections.

---

## 📦 Public API

### From `__init__.py`

```python
from core.kgraph import (
    ProjectManager,              # Project isolation and configuration
    GraphStore,                  # SQLite graph storage
    get_project_vector_collection,  # Project-specific ChromaDB
    parse_file_dependencies,     # Async AST parsing
    clear_ast_cache,             # Clear LRU cache
    load_test_index,             # Load persistent test index
    save_test_index,             # Save persistent test index
    get_targeted_tests,          # Source → test mapping (main entry point)
    rebuild_test_index,          # Force full index rebuild
    CRITICAL_PATHS,              # Files that trigger full test suite
    get_dependencies,            # Outgoing edge query
    get_callers,                 # Incoming edge query
)
```

---

## 💡 Common Usage Patterns

### Find tests for modified files (autocode workflow)

```python
from core.kgraph import get_targeted_tests, ProjectManager

pm = ProjectManager("/path/to/project")
result = await get_targeted_tests(
    project_path=pm.path,
    modified_files=["core/llm.py", "core/config.py"],
    project_id=pm.project_id,
)

if result["fallback"]:
    # Run full test suite
    run_all_tests()
else:
    # Run only targeted tests
    for test in result["tests"]:
        run_test(test)
```

### Find relevant files for a goal

```python
from core.kgraph import find_relevant_files

files = find_relevant_files("/path/to/project", "fix timeout in web scraper", top_k=5)
# Returns: ["tools/web.py", "tools/browser_ops/actions.py", ...]
```

### Query dependency graph

```python
from core.kgraph import get_dependencies, get_callers

# What does core/llm.py import?
deps = get_dependencies("/project", "core/llm.py")

# What imports core/config.py?
callers = get_callers("/project", "core/config.py")
```

---

## ⚡ Components

### 1. Project Manager (`project.py`)

Manages physical isolation and project-level configuration. Each project has a unique `project_id` derived from its absolute path hash.

#### Project Types

| Type | `source_root` | `artifact_root` | Use Case |
|------|---------------|-----------------|----------|
| **Agent root** | `agent_root` | `agent_root/.understand` | Indexing the agent's own codebase |
| **Workspace project** | `project/code` | `project/.understand` | Indexing user projects in workspace |

#### Indexing Modes

The `get_indexing_mode()` method determines how to handle a project based on its size:

```mermaid
graph TD
    A["Project stats<br/>(file count, total size)"] --> B{Size > 500MB?}
    B -->|Yes| C["reject<br/>Refuse to index"]
    B -->|No| D{Files > 5000?}
    D -->|Yes| E["background<br/>Index in background thread"]
    D -->|No| F["foreground<br/>Index immediately"]
```

| Mode | Condition | Behavior |
|------|-----------|----------|
| `foreground` | ≤ 5,000 files AND ≤ 500MB | Index synchronously (fast enough) |
| `background` | > 5,000 files AND ≤ 5000MB | Index in background thread |
| `reject` | > 500MB | Refuse to index (too large) |

#### Hard Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| `MAX_FILES_FOR_FOREGROUND` | 5,000 | Prevent blocking on large projects |
| `MAX_FILE_SIZE_BYTES` | 1MB | Skip oversized files during indexing |
| `MAX_TOTAL_PROJECT_SIZE_MB` | 500 | Reject projects that are too large |

#### Startup Cleanup

On `ensure_initialized()`, the project manager runs `KGCleanup.cleanup_project()` to:
- Delete cache files older than 30 days
- Force SQLite WAL checkpoint to prevent unbounded growth

---

### 2. AST Parser (`ast_parser.py`)

Dedicated, bounded AST parsing to prevent event loop blocking and memory leaks.

#### Design

```mermaid
graph TD
    A["Caller<br/>(test_mapper, queries)"] --> B["parse_file_dependencies()"]
    B --> C["Read file bytes<br/>Compute MD5 hash"]
    C --> D["run_in_executor()<br/>_AST_EXECUTOR (2 workers)"]
    D --> E["_parse_file_dependencies_sync()"]
    E --> F{LRU cache hit?<br/>key=(project_id, path, md5)}
    F -->|Yes| G["Return cached frozenset"]
    F -->|No| H["ast.parse(source)"]
    H --> I["ast.walk(tree)<br/>Extract Import + ImportFrom"]
    I --> J["Return frozenset of deps"]
    J --> K["Cache result<br/>maxsize=512"]
```

#### Key Properties

| Property | Value | Rationale |
|----------|-------|-----------|
| Thread pool | `ThreadPoolExecutor(max_workers=2)` | CPU-bound work, doesn't block event loop |
| Cache | `@lru_cache(maxsize=512)` | Prevent re-parsing unchanged files |
| Cache key | `(project_id, file_path, md5_hash)` | Cross-project safe + content invalidation |
| Return type | `frozenset[str]` | Lightweight, immutable, hashable |
| Error handling | Returns `frozenset()` on `SyntaxError`, `RecursionError`, `MemoryError` | Graceful fallback for broken files |

#### Two Parsing Modes

| Mode | Function | Input | Use Case |
|------|----------|-------|----------|
| **File-based** | `parse_file_dependencies(project_id, file_path)` | File path on disk | Full project indexing |
| **String-based** | `parse_dependencies_from_string(project_id, content)` | Raw source string | Micro-updates from workflow state |

---

### 3. Graph Store (`storage.py`)

Thread-safe, WAL-enabled SQLite graph store for dependency topology.

#### Schema

```sql
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,              -- "file:core/config.py"
    project_id TEXT NOT NULL,
    path TEXT NOT NULL,
    type TEXT NOT NULL,               -- "file", "module", "class", "function"
    content_hash TEXT NOT NULL,       -- MD5 of file content
    last_modified REAL,               -- File mtime for fast-path validation
    file_size INTEGER,                -- File size for fast-path validation
    metadata TEXT,                    -- JSON metadata
    updated_at REAL,
    UNIQUE(project_id, path)
);

CREATE TABLE edges (
    id TEXT PRIMARY KEY,              -- MD5 of "source->target"
    project_id TEXT NOT NULL,
    source_id TEXT NOT NULL,          -- "file:core/llm.py"
    target_id TEXT NOT NULL           -- "core.config" or "file:core/config.py"
);
```

#### Indexes

| Index | Purpose |
|-------|---------|
| `idx_nodes_project` | Fast project-scoped node lookups |
| `idx_nodes_path` | Fast path-based node lookups |
| `idx_nodes_project_path` | Compound: project + path (unique constraint) |
| `idx_edges_source` | Fast dependency lookups (outgoing edges) |
| `idx_edges_target` | Fast caller lookups (incoming edges) |

#### Thread Safety Model

```mermaid
graph TD
    A["Thread 1<br/>read()"] --> B["thread-local conn<br/>No lock needed"]
    C["Thread 2<br/>read()"] --> D["thread-local conn<br/>No lock needed"]
    E["Thread 3<br/>write()"] --> F["_write_lock<br/>Serialize writes"]
    F --> G["thread-local conn<br/>conn.execute() + conn.commit()"]
    G --> H["_write_count++<br/>Checkpoint every 100 writes"]
```

| Operation | Lock | Connection | Notes |
|-----------|------|------------|-------|
| `read()` | None | Thread-local | Concurrent reads are safe |
| `write()` | `_write_lock` | Thread-local | Serialized writes |
| `upsert_file_graph()` | `_write_lock` | Thread-local | Atomic node + edge update |

#### WAL Management

| Setting | Value | Purpose |
|---------|-------|---------|
| `journal_mode` | WAL | Write-ahead logging for concurrency |
| `synchronous` | NORMAL | Balance safety and performance |
| `busy_timeout` | 30000ms | Wait before SQLITE_BUSY error |
| `temp_store` | MEMORY | Fast temporary tables |
| Checkpoint frequency | Every 100 writes | Prevent WAL file bloat |
| Checkpoint mode | TRUNCATE (fallback PASSIVE) | Shrink WAL to 0 bytes |

#### Windows WAL Repair

On startup, `_repair_wal_on_windows()` checks for stale WAL artifacts (`.db-wal` exists but `.db-shm` is empty/missing) and deletes them to prevent corruption from unclean shutdowns.

#### Singleton Pattern

`GraphStore` uses `__new__` with a class-level lock to ensure one instance per database path:

```python
store1 = GraphStore(Path("project/.understand/kg.db"))
store2 = GraphStore(Path("project/.understand/kg.db"))
assert store1 is store2  # Same instance
```

---

### 4. Graph Queries (`queries.py`)

Read-only queries for the knowledge graph.

#### `find_relevant_files(project_path, query, top_k=5)`

Finds files whose paths match keywords in a natural language query.

```python
files = find_relevant_files("/project", "fix the timeout in web scraper")
# Returns: ["tools/web.py", "tools/browser_ops/actions.py", "tests/tools/web/test_web_scrape.py"]
```

**How it works:**
1. Extract meaningful keywords (≥3 chars, skip stop words)
2. SQL `LIKE` query against node paths
3. Score by keyword match count
4. Return top-K by relevance

**Stop words filtered:** `the, a, an, and, or, for, in, on, at, to, of, is, it, this, that, fix, bug, issue, add, create, implement, write, update, change, modify, refactor, code`

#### `get_dependencies(project_path, file_path)`

Returns files that the given file imports (outgoing edges).

```python
deps = get_dependencies("/project", "core/llm.py")
# Returns: ["core/config.py", "core/tracer.py", "core/llm_backend/client.py"]
```

#### `get_callers(project_path, file_path)`

Returns files that import the given file (incoming edges).

```python
callers = get_callers("/project", "core/config.py")
# Returns: ["core/llm.py", "core/memory.py", "server.py"]
```

---

### 5. Test Index (`test_index.py`)

Persistent storage for the source → test file mapping index with hybrid validation.

#### Hybrid Validation (mtime + size + MD5)

```mermaid
graph TD
    A["Cached entry<br/>(mtime, size, md5)"] --> B{mtime + size<br/>match?}
    B -->|Yes| C["Valid<br/>Content unchanged<br/>Skip MD5 check"]
    B -->|No| D["Compute MD5<br/>Slow path"]
    D --> E{md5<br/>matches?}
    E -->|Yes| F["Valid<br/>Content same, mtime changed<br/>(e.g., git checkout)"]
    E -->|No| G["Invalid<br/>Content changed<br/>Re-parse AST"]
```

| Path | Cost | When | Result |
|------|------|------|--------|
| **Fast** | O(1) stat call | mtime + size unchanged | Skip re-parsing |
| **Slow** | O(n) MD5 hash | mtime or size changed | Check if content actually changed |
| **Full** | O(n) AST parse | MD5 changed | Re-extract dependencies |

#### Atomic Writes

Test index is saved atomically to prevent corruption on crash:

1. Write to `.tmp` file
2. Replace original with `.tmp` (atomic on NTFS + ext4)

---

### 6. Test Mapper (`test_mapper.py`)

Maps source files to their targeted tests using persistent AST indexing. This is the primary interface used by the autocode workflow.

#### `get_targeted_tests(project_path, modified_files, project_id)`

The main entry point. Determines which tests to run for a set of modified files.

```mermaid
graph TD
    A["Modified files<br/>e.g., ['core/llm.py']"] --> B{Any file in<br/>CRITICAL_PATHS?}
    B -->|Yes| C["Return fallback=True<br/>Run full test suite"]
    B -->|No| D["Load test index"]
    D --> E{Index<br/>empty?}
    E -->|Yes| F["rebuild_test_index()<br/>Scan + parse all test files"]
    E -->|No| G["Build reverse map<br/>source → [tests]"]
    F --> G
    G --> H["For each modified file:<br/>Look up mapped tests"]
    H --> I{All files<br/>have tests?}
    I -->|No| J["Return fallback=True<br/>Missing mapping"]
    I -->|Yes| K["Validate tests exist<br/>Zombie cleanup"]
    K --> L{Valid<br/>tests found?}
    L -->|No| M["Return fallback=True"]
    L -->|Yes| N["Return targeted tests<br/>fallback=False"]
```

#### Critical Paths (Always Full Suite)

These files have global impact — modifying any of them triggers the full test suite:

| Path | Reason |
|------|--------|
| `core/config.py` | Global configuration affects everything |
| `core/llm.py` | All LLM interactions |
| `core/memory.py` | All memory operations |
| `server.py` | MCP server entry point |
| `registry.py` | MCP tool registration |
| `core/gateway.py` | HTTP gateway |
| `core/tracer.py` | All logging and tracing |
| `main.py`, `app.py`, `manage.py`, `settings.py` | Common framework entry points |

#### Test Index Rebuild

`rebuild_test_index()` scans the test directory and builds the mapping:

1. Find all `test_*.py` and `*_test.py` files
2. For each, check if cached entry is valid (hybrid validation)
3. If invalid, parse AST to extract imports
4. Convert module imports to file paths (`core.config` → `core/config.py`)
5. Add heuristic: `test_foo.py` probably tests `foo.py`
6. Remove stale entries for deleted test files
7. Save index atomically

#### Manual Override (test_mapping.yaml)

Users can override AST-based mapping with manual rules:

```yaml
# .understand/test_mapping.yaml
core/config.py:
  - tests/test_config_edge_cases.py
  - tests/test_config_migration.py
```

Manual mappings take priority over AST-derived mappings.

---

### 7. Embeddings (`embeddings.py`) — v1.1

AST-based code chunking + LM Studio embedding client for semantic code search.

```python
from core.kgraph.embeddings import extract_definitions, embed_texts

# Split Python source into top-level definitions for embedding
definitions = extract_definitions(source_code)
# → [{"name": "foo", "type": "function", "source": "def foo(): ...", "line_start": 1, "line_end": 5}, ...]

# Embed texts via LM Studio /v1/embeddings (OpenAI-compatible)
vectors = embed_texts(["def foo(): pass", "class Bar: pass"])
# → [[0.1, 0.2, ...], [0.3, 0.4, ...]]  or None if LM Studio unavailable
```

**Config:** `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_ENABLED` (in `.env`).
**Recommended model:** All-MiniLM-L6-v2-Embedding-GGUF (q8, 25MB) in LM Studio.
**Graceful degradation:** Returns `None` on failure — callers must handle this.

---

### 8. Vectors (`vectors.py`) — v1.1

Project-specific ChromaDB collections for code embeddings, physically isolated from the main memory system.

```python
from core.kgraph.vectors import upsert_file_vectors, query_similar_code

# Store embeddings for a file's definitions (delete old, insert new)
count = upsert_file_vectors("abc123def456", "core/config.py", definitions, trace_id="t1")
# → 5  (number of vectors stored; 0 if LM Studio unavailable)

# Semantic search: find code similar to a query
results = query_similar_code("abc123def456", "how does config loading work?", n_results=10)
# → [{"file_path": "core/config.py", "name": "Config.__init__", "type": "function",
#     "line_start": 50, "line_end": 120, "distance": 0.23, "source": "..."}, ...]
```

**Collection naming:** `kg_{project_id}_embeddings` (cosine similarity, stored in main ChromaDB path).
**Delete-then-insert:** `upsert_file_vectors` deletes old vectors for the file before inserting, so renamed/deleted definitions don't leave stale vectors.

---

### 9. Cleanup (`cleanup.py`)

Prevents disk space exhaustion and WAL file bloat during long-term unattended operation.

| Operation | Default | Action |
|-----------|---------|--------|
| Cache cleanup | 30 days | Delete files older than threshold in `.understand/cache/` |
| Size enforcement | 5GB | Delete oldest files if total exceeds limit |
| WAL checkpoint | On startup | `PRAGMA wal_checkpoint(TRUNCATE)` to shrink WAL to 0 bytes |

---

*Last updated: 2026-07-06 (v1.1 — embeddings + vectors). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
