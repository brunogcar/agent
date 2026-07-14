# 🧠 Workflow

The `understand` workflow analyzes a **project's codebase** to build a dependency graph, map file relationships, and identify architectural patterns. It is the foundation for intelligent code navigation, impact analysis, and automated refactoring suggestions.

**Key characteristics:**
- **Multi-language static analysis** — Tree-sitter parser supports Python, JavaScript/TypeScript, Go, and Rust (v1.2). Extracts imports, class hierarchies, and function calls.
- **Dependency graph** — Builds a graph in SQLite (via `GraphStore`) for fast querying
- **Incremental updates** — Only re-parses changed files (MD5 hash comparison)
- **Project isolation** — Each project gets its own graph database and artifact directory
- **Semantic search** — Per-definition code embeddings in ChromaDB via LM Studio `/v1/embeddings` (v1.1). Graceful degradation if embedding model is unavailable.
- **LangGraph StateGraph** — Sync nodes, routed through `base.py`'s `graph.invoke()`. Supports checkpoint/resume.

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
| Generate report | `report` tool | 11 atomic report actions — charts, maps, dashboards, export to PDF/PNG |

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

*Architecture: 4-node sync LangGraph StateGraph (init → discover → parse+store → report) with GraphStore dependency graph, incremental updates, batch processing, and ChromaDB vector indexing. Routed through base.py's `graph.invoke()`.*
