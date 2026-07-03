# 🐍 Python Tool

The `python()` tool executes Python code with **two execution modes**: a strict sandbox for pure logic, and a data mode with controlled imports for data analysis. It replaces the old `run_python` and `run_python_data` flat tools.

**Key characteristics:**
- **Dual-mode execution** — `run` (strict sandbox, no imports) and `run_data` (controlled imports, stdlib in-process, heavy libs subprocess)
- **AST-based sandbox validation** — `validate_sandbox_ast()` blocks imports, dangerous builtins, MRO traversal vectors, and metaclass attacks
- **Thread-safe stdout capture** — Module-level `_STDOUT_LOCK` prevents cross-thread clobbering when used in `parallel()`
- **Import allowlisting** — `STDLIB_IMPORTS` + `HEAVY_IMPORTS` + `CORE_ALLOWED` with `BLOCKED_IMPORTS` security boundary
- **Result pruning** — `prune_text()` prevents MCP context overflow on large outputs
- **Kill-switch ready** — Clear error messages tell the model exactly what went wrong and how to fix it

---

## 🚀 Quick Start

```python
# Sandbox mode — pure logic, no imports
python(mode="run", code="print(sum(range(100)))")

# Data mode — stdlib imports, in-process
python(mode="run_data", code="import json; print(json.dumps({'a': 1}))")

# Data mode — heavy libs, subprocess isolation
python(mode="run_data", code="import pandas as pd; print(pd.DataFrame({'x': [1,2,3]}).to_string())")

# Always use print() to return results
python(mode="run", code="x = 42")  # Returns env dump, not 42
python(mode="run", code="x = 42; print(x)")  # Returns "42"
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `execution_timeout` | `cfg.execution_timeout` | — | Subprocess timeout for heavy-lib execution |
| `workspace_root` | `cfg.workspace_root` | — | Temp file directory for subprocess mode |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Mode | Why |
|------|------|------|-----|
| Pure logic, math, string ops | `python` | `run` | Fast, in-process, no imports |
| Data analysis with pandas/numpy | `python` | `run_data` | Controlled imports, subprocess isolation for heavy libs |
| JSON parsing, regex, datetime | `python` | `run_data` | Stdlib imports, in-process |
| File system operations | `file` | — | Direct, no code execution |
| Git operations | `git` | — | Atomic, safe |
| Web requests | `web` | — | Dedicated tool with SSRF protection |
| Arbitrary code execution | ❌ not supported | — | Security boundary |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](python/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](python/API.md) | Full tool signature, modes, sandbox rules, import allowlists, output format |
| [CHANGELOG.md](python/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](python/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
