<- Back to [Python Overview](../PYTHON.md)

# 🗺️ Changelog

## 📝 Version History

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes recorded for pre-v1. Add here as they occur.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Dual-mode execution | ✅ Pre-v1 | `run` (sandbox) and `run_data` (controlled imports) |
| AST-based sandbox validation | ✅ Pre-v1 | `_validate_sandbox_ast()` blocks imports, dangerous builtins, MRO traversal, metaclass attacks |
| Fast-path + AST two-layer defense | ✅ Pre-v1 | `FORBIDDEN_IN_SANDBOX` string check + `_validate_sandbox_ast()` |
| Thread-safe stdout capture | ✅ Pre-v1 | `_STDOUT_LOCK` prevents cross-thread clobbering (BUGFIX-2) |
| Import allowlisting | ✅ Pre-v1 | `STDLIB_IMPORTS` + `HEAVY_IMPORTS` + `CORE_ALLOWED` with `BLOCKED_IMPORTS` boundary |
| Subprocess isolation | ✅ Pre-v1 | Heavy libs run in subprocess with timeout and temp file cleanup |
| Result pruning | ✅ Pre-v1 | `prune_text()` prevents MCP context overflow |
| Clean error messages | ✅ Pre-v1 | Errors tell the model exactly what went wrong and which mode to use |
| Granular core allowlist | ✅ Pre-v1 | Only `core.br_validator` allowed from project codebase |
| Temp file cleanup | ✅ Pre-v1 | `finally` block ensures deletion even on exception |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `@meta_tool` refactor | Add `action` param with `Literal["run", "run_data"]` validation and auto-generated schema | P0 |
| Un-multiplex | Extract `_do_run`, `_do_run_data` into atomic handlers under `python_ops/actions/` (follow `browser_ops/actions/` pattern) | P0 |
| Test restructure | Add `conftest.py`, split existing tests into per-concern files: validation, sandbox, sandbox_ast_bypass, run_data_imports, run_data_execution, thread_safety, subprocess, output, integration | P1 |
| Per-mode timeout | `timeout` parameter override for `cfg.execution_timeout` | P2 |
| Memory limit | Cap memory usage for subprocess heavy-lib execution | P2 |
| Result caching | Cache identical code executions to avoid redundant computation | P3 |
| Jupyter kernel mode | Optional Jupyter kernel backend for persistent state across calls | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Arbitrary code execution** | Security boundary. Use `file()`, `git()`, `web()` for FS/network access. | Skip |
| 2 | **Persistent state between calls** | Stateless by design. Use `memory` tool for persistence. | Skip |
| 3 | **Async/await support** | `async` functions blocked in sandbox. Use `run_data` with explicit event loop if needed. | Skip |
| 4 | **Interactive REPL mode** | MCP stdio doesn't support interactive sessions. | Skip |
| 5 | **Custom module installation** | `pip install` is blocked. Pre-install required packages in environment. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
