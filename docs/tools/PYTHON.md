# 🐍 Python Tool

The `python()` tool executes Python code with **security layers** via a `@meta_tool` facade. It exposes **5 actions** — `run` (strict sandbox), `run_data` (controlled imports), `eval` (pure expression), `profile` (cProfile), and `lint` (ruff/flake8) — all routed through the `python_ops/` subpackage.

**Key characteristics:**
- **`@meta_tool` facade** — 5 actions (`run` / `run_data` / `eval` / `profile` / `lint`) auto-discovered from `python_ops/actions/` via the `DISPATCH` registry. Adding a new action = drop a file; the `action: Literal[...]` annotation and docstring update themselves.
- **11-file `python_ops/` subpackage** — `_registry.py` (DISPATCH + `register_action`), `__init__.py` (auto-discovery), `sandbox.py` (security Layer 1: `SAFE_BUILTINS` + AST validators), `imports.py` (Layer 2: import allowlists), `executors.py` (Layer 3: in-process + subprocess + JSON-schema validators), `actions/{__init__,run,run_data,eval,profile,lint}.py`.
- **Three-layer security** — Sandbox (AST validation + `SAFE_BUILTINS`) → Imports (`BLOCKED_IMPORTS` + `ALL_ALLOWED`) → Executors (`_STDOUT_LOCK` + subprocess isolation). Each layer owned by a separate module and fails independently.
- **`json_schema` validation** — NEW in v1.0. Graceful for `run`/`run_data` (warnings on mismatch); strict for `eval` (`fail` on mismatch — the expression value is a structured object); ignored by `profile`/`lint`. Best-effort, no `jsonschema` dependency.
- **`timeout` override** — NEW in v1.0. `-1` → `cfg.execution_timeout`; any non-negative int → overrides. Honored by `run_data`/`profile` (subprocess); ignored by `run`/`eval` (in-process); fixed 10s hard cap for `lint`.
- **Thread-safe stdout** — Module-level `_STDOUT_LOCK` prevents cross-thread clobbering when used in `parallel()`.
- **Result pruning** — `prune_text()` prevents MCP context overflow on large outputs (e.g., pandas DataFrame dumps).
- **Kill-switch ready** — Clear error messages tell the model exactly what went wrong and which action to use.
- **145 tests across 10 files** — `conftest.py` + 5 action tests + `test_dispatch.py` + 3 existing security/safety tests updated for the breaking `mode`→`action` rename.

---

## 🚀 Quick Start

```python
# run — strict sandbox, pure logic, no imports
python(action="run", code="print(sum(range(100)))")

# run_data — stdlib imports, in-process
python(action="run_data", code="import json; print(json.dumps({'a': 1}))")

# run_data — heavy libs, subprocess isolation
python(action="run_data", code="import pandas as pd; print(pd.DataFrame({'x': [1,2,3]}).to_string())")

# eval — pure expression (NEW in v1.0); the value IS the output (no print() needed)
python(action="eval", code="[x**2 for x in range(5)]")

# profile — cProfile top-20 cumulative (NEW in v1.0); NOT sandboxed
python(action="profile", code="print(sum(range(10000)))")

# lint — ruff/flake8 pre-check (NEW in v1.0); 10s hard cap
python(action="lint", code="import os\nprint(os.getcwd())")

# With new v1.0 params: trace_id (observability), timeout (override), json_schema (validation)
python(
    action="run_data",
    code="import json; print(json.dumps({'a': 1, 'b': 2}))",
    timeout=60,                                              # overrides cfg.execution_timeout
    json_schema='{"type":"object","required":["a","b"],"properties":{"a":{"type":"integer"},"b":{"type":"integer"}}}',
    trace_id="wf-1234",
)

# Always use print() to return results (except in eval)
python(action="run", code="x = 42")                  # Returns env dump, not 42
python(action="run", code="x = 42; print(x)")        # Returns "42"
python(action="eval", code="42")                     # Returns "42" — no print() needed
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `execution_timeout` | `cfg.execution_timeout` | — | Subprocess timeout for heavy-lib execution (used when `timeout=-1`) |
| `workspace_root` | `cfg.workspace_root` | — | Temp file directory for subprocess mode |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Action | Why |
|------|------|--------|-----|
| Pure logic, math, string ops | `python` | `run` | Fast, in-process, no imports, sandboxed |
| Data analysis with pandas/numpy | `python` | `run_data` | Controlled imports, subprocess isolation for heavy libs |
| JSON parsing, regex, datetime | `python` | `run_data` | Stdlib imports, in-process |
| Quick expression evaluation | `python` | `eval` | Pure expression, value returned directly, no `print()` needed |
| Performance profiling | `python` | `profile` | cProfile top-20 cumulative — NOT sandboxed, use only on trusted code |
| Code quality check | `python` | `lint` | ruff/flake8 pre-check, 10s hard cap |
| File system operations | `file` | — | Direct, no code execution |
| Git operations | `git` | — | Atomic, safe |
| Web requests | `web` | — | Dedicated tool with SSRF protection |
| Arbitrary code execution | ❌ not supported | — | Security boundary — `os`, `sys`, `subprocess` never allowed |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](python/ARCHITECTURE.md) | Source code reference (11-file subpackage), module tree, dispatch flow + per-action flows, three-layer security model, 5-action pattern, JSON schema validation, design decisions, test coverage (145 tests / 10 files) |
| [API.md](python/API.md) | Full `@meta_tool` signature, 5 action sections (run/run_data/eval/profile/lint) with params/returns/examples, new params (`timeout`/`json_schema`), error handling table, JSON Schema validation, security section |
| [CHANGELOG.md](python/CHANGELOG.md) | v1.0 entry, breaking changes (`mode`→`action`), completed table, in-progress + roadmap (10 suggested items), deferred |
| [INSTRUCTIONS.md](python/INSTRUCTIONS.md) | AI editing rules — NEVER DO (20 rules), ALWAYS DO (15 rules), anti-patterns (7 lessons from v1.0 refactor) |

---

*Last updated: 2026-07-15 (v1.0). See subfiles for detailed documentation.*
