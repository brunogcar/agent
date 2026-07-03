# 🧠 Workflow

The `understand` workflow analyzes a **project's codebase** to build a dependency graph, map file relationships, and identify architectural patterns. It is the foundation for intelligent code navigation, impact analysis, and automated refactoring suggestions.

**Key characteristics:**
- **Static analysis** — Parses Python AST to extract imports, class hierarchies, and function calls
- **Dependency graph** — Builds a graph in SQLite (via `GraphStore`) for fast querying
- **Incremental updates** — Only re-parses changed files (MD5 hash comparison)
- **Project isolation** — Each project gets its own graph database and artifact directory
- **Async I/O** — All file I/O uses `asyncio.to_thread()` to prevent blocking the event loop
- **Memory integration** — Stores project metadata in procedural memory for future recall

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Analyze a project
result = run_workflow(
    workflow_type="understand",
    goal="Analyze the codebase structure",
    project_root="/path/to/project",
    trace_id="understand_001",
)

print(result["status"])  # "success" | "failed"
print(result["result"])  # "Project analysis complete: 42 files, 156 dependencies"
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Analyze codebase | `understand` workflow | Static analysis, dependency graph, incremental updates |
| Research a topic | `research` workflow | Web search + synthesis, no code analysis |
| Fix code | `autocode` workflow | Targeted code changes with test verification |
| Deep research | `deep_research` workflow | Iterative search with convergence detection |
| Analyze data | `data` workflow | Code generation + execution, data analysis |
| Generate report | `report` workflow | Structured report generation |

---

## ⚙️ Configuration

```ini
# .env
UNDERSTAND_MAX_FILE_SIZE_MB=1          # Max file size to parse (MB)
UNDERSTAND_BATCH_SIZE=10               # Files per batch
UNDERSTAND_TIMEOUT_SECONDS=300         # Workflow timeout (seconds)
```

```python
# core/config.py
cfg.understand_max_file_size_mb = 1    # Max file size to parse (MB)
cfg.understand_batch_size = 10          # Files per batch
cfg.understand_timeout_seconds = 300    # Workflow timeout (seconds)
```

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [Architecture](understand/ARCHITECTURE.md) | File maps, design decisions, mermaid diagrams, source code reference |
| [API](understand/API.md) | Node reference, output, configuration details |
| [Changelog](understand/CHANGELOG.md) | Version history, breaking changes, completed, roadmap |
| [Instructions](understand/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Architecture: 4-phase async orchestrator (init -> discover -> parse + store -> report) with GraphStore dependency graph, incremental updates, batch processing, and memory integration. Not a LangGraph StateGraph — direct async function calls.*
