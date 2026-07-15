<- Back to [Python Overview](../PYTHON.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.0** | 2026-07-15 | `@meta_tool` refactor: 5 actions (`run` / `run_data` / `eval` / `profile` / `lint`), `python_ops/` subpackage (11 files), **breaking `mode`→`action` rename**, new params (`timeout`, `json_schema`), 145 tests across 10 files. Original 367-line `tools/python.py` collapsed to a 111-line facade. |
| Pre-v1 | 2026-07-03 | Initial dual-mode tool: single `python(mode, code, trace_id)` facade with `run` (sandbox) + `run_data` (controlled imports). AST-based sandbox (`_validate_sandbox_ast`), thread-safe stdout (`_STDOUT_LOCK`), import allowlists, subprocess isolation for heavy libs. 34 tests across 3 files. |

---

## ⚠️ Breaking Changes

| Version | Change | Migration |
|---------|--------|-----------|
| **v1.0** | `mode` parameter renamed to `action`. Legacy `python(mode="run", code="...")` returns `{"status": "error", "error": "action is required (run \| run_data \| eval \| profile \| lint)"}`. | Update all callers to `python(action="run", code="...")`. The `run` and `run_data` behaviors are otherwise unchanged — error messages that previously said "Use mode='run_data'" now say "Use action='run_data'". The router's `_RE_DIRECT_PYTHON` heuristic already routes to `python`; no router changes were needed. |
| **v1.0** | `_validate_sandbox_ast()` moved from `tools/python.py` to `tools/python_ops/sandbox.py`. Tests that did `from tools.python import _validate_sandbox_ast` must be updated to `from tools.python_ops.sandbox import _validate_sandbox_ast`. | Update import paths. The function signature is unchanged. (Only `test_sandbox_ast_bypass.py` was affected.) |
| **v1.0** | All other previously module-level constants (`SAFE_BUILTINS`, `FORBIDDEN_IN_SANDBOX`, `STDLIB_IMPORTS`, `HEAVY_IMPORTS`, `CORE_ALLOWED`, `BLOCKED_IMPORTS`, `ALL_ALLOWED`, `_run_inprocess`, `_run_subprocess`, `_STDOUT_LOCK`) moved into the `python_ops/` subpackage. | Update any external references to import from the new locations (`python_ops.sandbox`, `python_ops.imports`, `python_ops.executors`). Internal callers were updated in-place. |

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
| Clean error messages | ✅ Pre-v1 | Errors tell the model exactly what went wrong and which action to use |
| Granular core allowlist | ✅ Pre-v1 | Only `core.br_validator` allowed from project codebase |
| Temp file cleanup | ✅ Pre-v1 | `finally` block ensures deletion even on exception |
| `@meta_tool` refactor | ✅ v1.0 | Facade is now a thin dispatch wrapper; `action: Literal["eval","lint","profile","run","run_data"]` auto-generated from `DISPATCH` |
| Un-multiplex into `python_ops/` | ✅ v1.0 | 11-file subpackage: `_registry.py`, `__init__.py`, `sandbox.py`, `imports.py`, `executors.py`, `actions/{__init__,run,run_data,eval,profile,lint}.py` |
| 5 actions (`run` / `run_data` / `eval` / `profile` / `lint`) | ✅ v1.0 | `run` and `run_data` preserve Pre-v1 behavior; `eval` (pure-expression), `profile` (cProfile top-20), and `lint` (ruff/flake8 pre-check) are new |
| `eval` action | ✅ v1.0 | Pure-expression evaluation via `ast.parse(code, mode='eval')` + `_validate_eval_ast` + `eval()` with `SAFE_BUILTINS`. The expression value IS the output (no `print()` needed). Strict `json_schema` enforcement. |
| `profile` action | ✅ v1.0 | `cProfile` timing breakdown, top-20 cumulative functions via `pstats`. Routes to subprocess if code has imports. **NOT sandboxed** — profiling needs full builtins. |
| `lint` action | ✅ v1.0 | `ruff check --select E,F --no-cache` (preferred) or `flake8` fallback. 10-second hard timeout. Temp-file based with `finally` cleanup. |
| `timeout` param | ✅ v1.0 | `-1` (default) → `cfg.execution_timeout`; any non-negative int → overrides. Honored by `run_data` (subprocess), `profile` (subprocess). Ignored by `run` (in-process), `eval` (in-process), `lint` (fixed 10s). |
| `json_schema` param | ✅ v1.0 | JSON Schema string for output validation. **Graceful** for `run`/`run_data` (warnings on mismatch, output returned as-is). **Strict** for `eval` (`fail` on mismatch — the expression value is a structured object). Ignored by `profile`/`lint` (output is tool data, not user data). Best-effort validation (no `jsonschema` dependency): supports `type`, `enum`, `required`, `properties`, `items` keywords. Bool-vs-int disambiguation (bool is subclass of int in Python). |
| `trace_id` support | ✅ v1.0 | Threaded through every return path (success + all error states when present); forwarded to `tracer.step()` by the facade |
| Test restructure | ✅ v1.0 | 145 tests across 10 files (`conftest.py` + 5 action tests + `test_dispatch.py` + 3 existing tests updated for the `mode`→`action` rename + import-path move). Old layout had 3 files / 34 tests. |
| `conftest.py` shared fixtures | ✅ v1.0 | `mock_cfg`, `mock_pruner` (patches both `actions.run.prune_text` AND `actions.run_data.prune_text` — see INSTRUCTIONS.md Anti-Pattern #1), `temp_workspace`, `mock_tracer`, `make_subprocess_result()` factory |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Result caching | Cache identical code executions to avoid redundant computation (key = `(action, code, json_schema)` hash) | P3 |
| Jupyter kernel mode | Optional Jupyter kernel backend for persistent state across calls | P3 |

### 💡 Suggested Roadmap (Future Sessions)

The following items are **proposed** for future python roadmap sessions. They are not yet committed — list them here so the next maintainer can pick the highest-value ones.

| Feature | Notes | Priority |
|---------|-------|----------|
| `python(action="format")` | Auto-format code with `ruff format` (preferred) or `black` before execution. Returns the formatted source as the result `data`. Pairs naturally with `lint` — `lint` reports issues, `format` fixes them. | P2 |
| `python(action="typecheck")` | Run `mypy` on the code before execution. Surfaces type errors without running the code. Useful as a pre-flight gate for `run_data` on complex scripts. | P2 |
| `python(action="test")` | Run `pytest` on a specific test file or test function (e.g. `python(action="test", code="tests/test_foo.py::test_bar")`). Wraps `pytest --tb=short -v` in a subprocess with the existing `timeout` override. | P2 |
| `matplotlib_output` | Auto-capture matplotlib figures as base64-encoded PNG images and return them alongside (or instead of) stdout text. Detect `plt.figure()` / `plt.savefig()` patterns. Most-requested UX improvement for data-science flows. | P2 |
| `pandas_dataframe_output` | Auto-render pandas DataFrames as markdown tables in the result `data`. Detects `print(df)` or final-expression DataFrames. Cleaner than `df.to_string()` for LLM consumption. | P2 |
| `conda_env` support | Execute in a specific conda environment via `conda run -n <env> python <tmp>`. Resolves the "pandas isn't installed in the agent's venv" problem without forcing the user to install heavy libs in the agent environment. | P3 |
| `persistent_session` | Optional stateful mode with variable persistence across calls within a trace. Implementation likely via per-`trace_id` `exec_globals` dict cached in `python_ops/state.py`. Reverses a deliberate Pre-v1 design decision — see Deferred #2. | P3 |
| `streaming` support | Stream stdout line-by-line when `complete_with_tools()` is implemented in `core/llm_backend/`. MCP stdio transport can't stream today — this would require gateway-only mode. | P3 |
| `security_audit` | Run `bandit` (security linter) and `safety` (vulnerability scanner) on the code before execution. Returns findings as structured JSON. Stronger than `lint` for untrusted code paths. | P3 |
| `memory_limit` | Cap memory usage for subprocess heavy-lib execution via `resource.setrlimit(RLIMIT_AS, ...)` in the subprocess wrapper. Prevents OOM crashes from runaway pandas/numpy allocations. | P3 |

> **Note for future maintainers:** items in the table above are *suggestions* gathered during v1.0 docs work. Before implementing any of them, re-check the current source (`tools/python_ops/`) and `core/llm_backend/` to confirm prerequisites (e.g. `complete_with_tools()` for streaming, `subprocess` wrappers for `memory_limit`) are in place. Several overlap (e.g. `format` + `typecheck` + `test` would together form a full dev-loop trio) and should be designed as a coherent set, not one-offs.

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Arbitrary code execution** | Security boundary. Use `file()`, `git()`, `web()` for FS/network access. | Skip |
| 2 | **Persistent state between calls** | Stateless by design. The Roadmap `persistent_session` item revisits this with an opt-in per-trace variant. Use `memory` tool for cross-call persistence. | Skip (until opt-in variant) |
| 3 | **Async/await support** | `async` functions blocked in sandbox. Use `run_data` with explicit event loop if needed. | Skip |
| 4 | **Interactive REPL mode** | MCP stdio doesn't support interactive sessions. The Roadmap `persistent_session` is a non-interactive alternative. | Skip |
| 5 | **Custom module installation** | `pip install` is blocked. Pre-install required packages in environment. | Skip |
| 6 | **`hash` in `SAFE_BUILTINS`** | Removed in Pre-v1 — DoS risk via collision attacks. Never re-add. | Skip |

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
