<- Back to [Understand Overview](../UNDERSTAND.md)

# 📝 API Reference

## 🔧 Node Reference

### `node_init_project(state)` — Phase 1: Initialize Project

**Purpose:** Initialize the project structure and GraphStore.

**Logic:**
1. Resolve `project_root` via `ProjectManager`
2. Create `GraphStore` instance (lazy init)
3. Log trace step

**Output:** Partial dict with `project_id`, `project_path`, `is_agent_root`, `db_path`.

**Note:** The `GraphStore` instance is created but discarded. Later nodes create their own instances. This is wasteful but not broken.

---

### `node_discover_files(state)` — Phase 2: File Discovery

**Purpose:** Discover all Python files in the project and check for changes.

**Logic:**
1. Walk the project directory tree (excluding skip directories)
2. For each `.py` file: compute MD5 hash, compare with stored hash
3. Collect files that are new or changed

**Output:** Partial dict with `files_to_parse` (list of changed file paths).

**Error handling:**
- File read errors are logged but don't fail the workflow
- Permission errors are logged but don't fail the workflow

**Note:** `os.walk` mutates `dirs` in-place to prune the walk. This is fragile — if `os.walk` implementation changes, it may silently fail.

**Note:** MD5 hash is computed by reading the entire file into memory (`read_bytes()`). For large files, this is memory-intensive.

---

### `node_parse_and_store(state)` — Phase 3: AST Parsing + Graph Storage

**Purpose:** Parse changed files and store dependencies in the graph.

**Logic:**
1. For each changed file (in batches of 10):
   - Parse AST to extract imports
   - Resolve imports to file paths
   - Store file node and dependency edges in GraphStore
2. Update `seen_urls` (actually `seen_files` — naming is from research workflow)

**Output:** Partial dict with `files_parsed`, `edges_created`, `errors`, `status`.

**Error handling:**
- Parse errors are collected in `errors` list
- `status` is `"completed"` if no errors, `"completed_with_errors"` if some errors

**Note:** `asyncio.gather` is used for batch processing, but `parse_file_dependencies` is CPU-bound (AST parsing). Running it in `asyncio.gather` without `asyncio.to_thread()` blocks the event loop.

**Note:** Duplicate target paths are created for each dependency: both `dep.replace(".", "/") + ".py"` and `dep` itself. This creates duplicate edges.

---

### `node_report(state)` — Phase 4: Generate Report

**Purpose:** Generate a report of the analysis results.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with analysis results
2. Return the report

**Output:** Partial dict with `report_html` and `report_path`.

**Note:** The `report` tool's `action="report"` is the report action name (generates a single-scroll HTML report), not a mistake.

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "Project analysis complete: 42 files, 156 dependencies",
  "error": "",
  "artifacts": ["report.html"]
}
```

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Project analysis failed: timeout",
  "artifacts": []
}
```

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
