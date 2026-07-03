# 🖥️ CLI Tool

The `cli()` tool is a **meta-tool** that routes natural-language commands through a 4-layer dispatch architecture. Unlike `git()` and `file()` — which are **direct action dispatchers** — `cli()` interprets free-form text and decides how to execute it.

**Key characteristics:**
- **Meta-tool routing** — `cli("git status")` → pattern match → `git:status` proxy → `tools/git.py`
- **4-layer dispatch** — Patterns (zero tokens) → Shell (zero tokens) → Router (LLM) → Executor (workflow)
- **Auto-generated schema** — `@meta_tool` builds docstring and `__tool_metadata__` from flattened DISPATCH
- **Path guard integration** — `core.path_guard` validates all filesystem paths in shell execution
- **Security-first** — Shell whitelist, flag blocking, operator rejection, input sanitization
- **Human-readable output** — Proxy handlers format tool responses for CLI consumption

---

## ⚠️ How CLI Differs from Git/File

| Aspect | `git()` / `file()` | `cli()` |
|--------|-------------------|---------|
| **Interface** | `action: Literal[...]` parameter | `command: str` natural language |
| **Dispatch** | Direct — one action = one handler | Routed — 4 layers decide execution path |
| **@meta_tool** | Patches `action: Literal[...]` | Skips `Literal` patch (no `action` param), generates docstring only |
| **Handlers** | One file per action (`branch_create.py`) | One handler per namespace with stacked decorators (`_file`, `_git`, `_web`) |
| **Output** | Structured `dict` | Human-readable `str` (proxy formatting) |
| **Shell access** | None | Layer 2 — whitelisted subprocess with `shell=False` |

**Important:** `cli()` is a **router**, not a direct tool. It does not perform operations itself — it delegates to `git()`, `file()`, `web()`, `python()`, `memory()`, etc.

---

## 🚀 Quick Start

*(Fill this section with relevant info from edits and refactors. Add quick start examples as they are learned.)*

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `cli_max_command_chars` | `cfg.cli_max_command_chars` | 4096 | Max command length |
| `cli_max_arguments` | `cfg.cli_max_arguments` | 50 | Max argument count |
| `workspace_root` | `cfg.workspace_root` | — | Shell `cwd` default |
| `agent_root` | `cfg.agent_root` | — | Path guard boundary |
| `_LMS` | Hardcoded | `http://localhost:1234` | LM Studio API endpoint |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick git status | `cli("git status")` | Zero tokens, instant pattern match |
| Read a file | `cli("read app.py")` | Zero tokens, human-readable output |
| Search code | `cli("grep import os")` | Zero tokens, routes to `file:search_files` |
| Run safe shell | `cli("python --version")` | Zero tokens, real OS output |
| Web search | `cli("search python tutorials")` | Zero tokens, routes to `web:search` |
| Complex multi-step | `cli("refactor the auth module")` | Escalates to Executor — correct tool |
| Direct file edit | `file(action="write_file", ...)` | Use direct tool for programmatic control |
| Direct git commit | `git(action="commit", ...)` | Use direct tool for structured params |
| Unsafe shell | — | Not supported by design |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](cli/ARCHITECTURE.md) | Module tree, 4-layer dispatch flow, design decisions, test coverage, source code reference |
| [API.md](cli/API.md) | Full tool signature, all proxy actions, security model, output format |
| [CHANGELOG.md](cli/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](cli/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
