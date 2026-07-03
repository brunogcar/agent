# 📁 File Tool

The `file()` tool provides **atomic file system actions** for the MCP Agent Stack. Each action does exactly one thing — no subcommand parsing, no overloaded behaviors.

**Key characteristics:**
- **Atomic actions** — `read_file`, `write_file`, `create_directory`, `directory_tree`, etc. One action = one behavior
- **Auto-generated schema** — `@meta_tool` decorator builds `Literal` enum and docstring from DISPATCH
- **Semantic parameter names** — `path` = file path, `source`/`destination` = move/copy paths, `query` = search text
- **Path guard integration** — All operations validate through `core.path_guard`
- **Cancellation guard** — Mutating actions abort if the trace is cancelled
- **Result compression** — Large outputs auto-truncate to prevent MCP context overflow

---

## 🚀 Quick Start

*(Fill this section with relevant info from edits and refactors. Add quick start examples as they are learned.)*

---

## ⚙️ Configuration

No dedicated `.env` variables. Uses:
- `cfg.agent_root` — default root for relative paths
- `cfg.workspace_root` — workspace root for relative paths
- `cfg.is_protected()` — blocks edits to sensitive files

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Read a file | `file(read_file)` | Line/char truncation, 10MB size limit |
| Write a file | `file(write_file)` | Auto-creates parents, no .bak garbage |
| Append to file | `file(append_file)` | No read-before-write, no .bak |
| List a directory | `file(list_directory)` | Structured metadata |
| Project structure | `file(directory_tree)` | Recursive JSON tree, cycle guard |
| Search code | `file(search_files)` | SQLite FTS across workspace |
| Find files | `file(find_files)` | Glob patterns, 1000 result limit |
| Move/rename | `file(move_file)` | Cross-directory, force overwrite |
| Copy | `file(copy_file)` | Cross-directory, force overwrite |
| Delete | `file(delete_file)` | Explicit force required |
| File metadata | `file(get_file_info)` | Size, mode, times |
| Check existence | `file(exists)` | Boolean, fast |
| Patch a file | `file(patch_file)` | Single str_replace |
| Multi-edit preview | `file(edit_file)` | Diff preview, dry_run |
| Read binary | `file(read_media_file)` | Base64 + MIME type, 5MB limit |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](file/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](file/API.md) | Full tool signature, all actions, security, output format |
| [CHANGELOG.md](file/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](file/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
