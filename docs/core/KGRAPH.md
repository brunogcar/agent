# 🕸️ Knowledge Graph

The Knowledge Graph (`core/kgraph/`) is a **deterministic AST-based codebase analysis system** that builds a dependency graph of Python projects. It provides fast file-to-test mapping, dependency resolution, and project-level isolation for the autocode workflow.

**Key characteristics:**
- **Deterministic AST parsing** — No LLM calls; pure Python `ast` module for import extraction
- **SQLite graph storage** — WAL-enabled, thread-safe, with automatic checkpoint management
- **Hybrid validation** — mtime + size (fast path) then MD5 (authoritative slow path) for cache invalidation
- **Test targeting** — Maps source files to their test files via AST dependency analysis
- **Project isolation** — Each project gets its own `.understand/` artifact directory
- **Physical isolation** — Project-specific ChromaDB collections separate from main memory

---

## 🚀 Quick Start

*(Fill this section with relevant info from edits and refactors. Add quick start examples as they are learned.)*

---

## ⚙️ Configuration

The kgraph module uses no dedicated `.env` variables. It derives all configuration from:

| Source | Used For |
|--------|----------|
| `cfg.memory_chroma_path` | ChromaDB storage for project vectors |
| `cfg.agent_root` | Agent root project detection |
| `cfg.workspace_root` | Workspace project discovery |

### Hard Limits (in code)

| Setting | Value | Location |
|---------|-------|----------|
| AST cache size | 512 entries | `ast_parser.py` `@lru_cache` |
| AST thread pool | 2 workers | `ast_parser.py` `ThreadPoolExecutor` |
| Max files for foreground | 5,000 | `project.py` `MAX_FILES_FOR_FOREGROUND` |
| Max file size | 1MB | `project.py` `MAX_FILE_SIZE_BYTES` |
| Max project size | 500MB | `project.py` `MAX_TOTAL_PROJECT_SIZE_MB` |
| Checkpoint frequency | 100 writes | `storage.py` `_CHECKPOINT_EVERY` |
| Cleanup max age | 30 days | `cleanup.py` default parameter |
| Cleanup max size | 5GB | `cleanup.py` default parameter |
| SQLite busy timeout | 30s | `storage.py` `PRAGMA busy_timeout` |
| SQLite connection timeout | 30s | `storage.py` `sqlite3.connect(timeout)` |

---

## 🔄 When to Use

*(Fill this section with relevant info from edits and refactors. Add usage scenarios as they are learned.)*

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](kgraph/ARCHITECTURE.md) | Component map, stack integration, artifact directory, design decisions, known concerns, testing |
| [API.md](kgraph/API.md) | Public API exports, usage patterns, all components (Project Manager, AST Parser, Graph Store, Queries, Test Index, Test Mapper, Vectors, Cleanup) |
| [CHANGELOG.md](kgraph/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](kgraph/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-04. See subfiles for detailed documentation.*
