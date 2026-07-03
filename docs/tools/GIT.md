# 🌿 Git Tool

The `git()` tool provides **atomic version control actions** for the MCP Agent Stack. Each action does exactly one thing — no subcommand parsing, no multiplexed behaviors, no `message`-as-DSL.

**Key characteristics:**
- **Atomic actions** — `branch_create`, `tag_delete`, `checkout_new`, etc. One action = one behavior
- **Auto-generated schema** — `@meta_tool` decorator builds `Literal` enum and docstring from DISPATCH
- **Semantic parameter names** — `target` = entity name, `message` = human-readable text
- **Path guard integration** — All operations validate through `core.path_guard`
- **Cancellation guard** — Mutating actions abort if the trace is cancelled
- **Result compression** — Large outputs auto-truncate to prevent MCP context overflow

---

## 🚀 Quick Start

*(Fill this section with relevant info from edits and refactors. Add quick start examples as they are learned.)*

---

## ⚙️ Configuration

No dedicated `.env` variables. Uses:
- `cfg.agent_root` — default repo for `root="agent"`
- `cfg.workspace_root` — default repo for `root="workspace"`

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Check working tree | `git(status)` | Fast, read-only |
| View recent commits | `git(log)` | Structured history |
| See file changes | `git(diff)` | Unified diff, smart truncation |
| Create safe point | `git(snapshot)` | Before automated changes |
| Commit changes | `git(commit)` | After successful changes |
| Create branch | `git(branch_create)` | Atomic, no switch |
| Create + switch branch | `git(checkout_new)` | One action, no subcommand parsing |
| Switch branches | `git(checkout_branch)` | Atomic, clear intent |
| Tag release | `git(tag_create)` | Lightweight tag |
| View commit details | `git(show)` | Capped at 10KB |
| Undo uncommitted changes | `git(rollback)` | Safe stash or force discard |
| Restore file | `git(restore)` | To HEAD or specific commit |
| Init new repo | `git(init)` | With .gitignore + initial commit |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](git/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](git/API.md) | Full tool signature, all actions, security, output format |
| [CHANGELOG.md](git/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](git/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
