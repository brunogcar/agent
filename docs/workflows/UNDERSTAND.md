# 🧠 Workflow

The `understand` workflow analyzes a **project's codebase** to build a dependency graph, map file relationships, and identify architectural patterns. It is the foundation for intelligent code navigation, impact analysis, and automated refactoring suggestions.

**Key characteristics:**
- **Multi-language static analysis** — Tree-sitter parser supports Python, JavaScript/TypeScript, Go, Rust, Java, C/C++, Ruby, Lua, PHP, Scala, Swift, Kotlin (v1.2 + v1.4). Extracts imports, class hierarchies, and function calls.
- **Document indexing** — `.md`/`.txt`/`.rst` files indexed via chonkie sentence chunking (v1.3). Doc chunks get vector embeddings with `type: "doc"` metadata — searchable alongside code definitions.
- **Dependency graph** — Builds a graph in SQLite (via `GraphStore`) for fast querying
- **Incremental updates** — Only re-parses changed files (MD5 hash comparison)
- **Project isolation** — Each project gets its own graph database and artifact directory; [v1.4.1] ChromaDB vectors are project-scoped (`{project}/.understand/chroma/` for projects, `memory_root/understand/chroma/` for agent root)
- **Semantic search** — Per-definition code embeddings + doc chunk embeddings in ChromaDB via LM Studio `/v1/embeddings` (v1.1). Graceful degradation if embedding model is unavailable.
- **LangGraph StateGraph** — Sync nodes, routed through `base.py`'s `graph.invoke()`. [v1.4.1] Checkpoints saved on crash/cancel/timeout by `base.py`'s exception handler (mid-execution node-level resume is NOT supported — see ARCHITECTURE.md § "Checkpoint/resume").

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
UNDERSTAND_BATCH_SIZE=10               # [v1.4.1 P2-14] Unused in Phase 1 (batch loop removed). Kept for backward compat.
UNDERSTAND_EMBED_BATCH_SIZE=100         # [v1.4.1 P2-8] Phase-2 embedding batch size — definitions per HTTP call to LM Studio.
UNDERSTAND_SKIP_DIRS=vendor,third_party # [v1.7] Comma-separated extra dirs to skip during discovery (merged with _DEFAULT_SKIP_DIRS).
UNDERSTAND_TIMEOUT_SECONDS=600          # [v1.7] Understand dispatch timeout in seconds. Was hardcoded 600 in base.py.
```

```python
# core/config.py
cfg.understand_batch_size = 10          # [v1.4.1 P2-14] Unused in Phase 1 (kept for backward compat).
cfg.understand_embed_batch_size = 100   # [v1.4.1 P2-8] Phase-2 embedding batch size.
cfg.understand_skip_dirs = ""           # [v1.7] Extra skip-dirs (comma-separated; merged with _DEFAULT_SKIP_DIRS via get_skip_dirs()).
cfg.understand_timeout_seconds = 600    # [v1.7] Dispatch timeout (was hardcoded in base.py).
```

Other relevant env vars: `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_ENABLED` (see kgraph [API.md](kgraph/API.md)).
Hard limits are in code: `MAX_FILES_FOR_FOREGROUND=5000`, `MAX_FILE_SIZE_BYTES=1MB`, `MAX_TOTAL_PROJECT_SIZE_MB=500` (see `core/kgraph/project.py`).

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [Architecture](understand/ARCHITECTURE.md) | File maps, design decisions, mermaid diagrams, source code reference |
| [API](understand/API.md) | Node reference, output, configuration details |
| [Changelog](understand/CHANGELOG.md) | Version history, breaking changes, completed, roadmap |
| [Instructions](understand/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Architecture: 4-node sync LangGraph StateGraph (init → discover → parse+store → report) with GraphStore dependency graph, incremental updates, batch processing, and ChromaDB vector indexing. Routed through base.py's `graph.invoke()`. [v1.4.1] Conditional init edge via `route_after_init` short-circuits to END on init failure.*
