<- Back to [Python Overview](../PYTHON.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
from registry import tool
from tools._meta_tool import meta_tool
from tools.python_ops._registry import DISPATCH

@tool
@meta_tool(
    DISPATCH.get("python", {}),
    doc_sections=[
        "PYTHON TOOL — Code execution with security layers:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Pure logic, no imports | python(run) | Strict sandbox, whitelisted builtins only |",
        " | Data analysis with imports | python(run_data) | Controlled imports (stdlib in-process, heavy in subprocess) |",
        " | Quick expression eval | python(eval) | Expressions only (no statements), even more restrictive than run |",
        " | Performance profiling | python(profile) | cProfile timing breakdown |",
        " | Code quality check | python(lint) | ruff --select E,F (syntax + lint) before execution |",
        "",
        "NOT parallel-safe for run_data (subprocess), but run/eval/lint are safe.",
        "ALWAYS use print() to return output — variables are not captured (except in eval).",
    ],
)
def python(
    action: str = "",            # Literal["eval","lint","profile","run","run_data"] (auto-generated)
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
) -> dict:
    """Python code execution meta-tool — run | run_data | eval | profile | lint."""
```

> The `action: Literal[...]` annotation and the action list in the docstring are **auto-generated** by `@meta_tool` from `DISPATCH["python"]` keys at import time. Adding a new action file in `python_ops/actions/` automatically extends the `Literal` and the docstring — no facade edits required.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | `str` (`Literal["eval","lint","profile","run","run_data"]`) | **Yes** | `""` | Which execution mode to invoke. Empty / unknown values return `status=error`. Case-insensitive (lowercased internally); leading/trailing whitespace stripped. |
| `code` | `str` | **Yes** | `""` | Python source code to execute. Empty / whitespace → `status=error` with `"No code provided"`. |
| `trace_id` | `str` | No | `""` | Observability trace ID. Forwarded to `tracer.step()` by the facade and included in the response **only when non-empty**. |
| `timeout` | `int` | No | `-1` | Subprocess timeout override (seconds). `-1` → use `cfg.execution_timeout`. Any non-negative int → override. **Honored by:** `run_data`, `profile` (when subprocess-routed). **Ignored by:** `run` (in-process), `eval` (in-process), `lint` (fixed 10s hard cap). |
| `json_schema` | `str` | No | `""` | JSON Schema string for output validation. **Graceful** for `run`/`run_data` (warnings on mismatch, output returned as-is). **Strict** for `eval` (`fail` on mismatch — the expression value is a structured object). **Ignored** by `profile`/`lint`. Supports `type`, `enum`, `required`, `properties`, `items` keywords (no `jsonschema` dependency). |

---

## 🎬 Actions

### `python(action="run", ...)` — Strict Sandbox

**Purpose:** Pure-logic execution with no imports and a whitelisted-builtin environment. Fast — runs in the current process.

**Required:** `code`
**Optional:** `trace_id`, `json_schema` (graceful). `timeout` is accepted but ignored (in-process).

**Allowed builtins:** `print`, `range`, `len`, `int`, `float`, `str`, `bool`, `list`, `dict`, `set`, `tuple`, `sum`, `min`, `max`, `abs`, `round`, `enumerate`, `zip`, `map`, `filter`, `sorted`, `reversed`, `isinstance`, `issubclass`, `type`, `repr`, `any`, `all`, `chr`, `ord`, `hex`, `oct`, `bin`, `divmod`, `pow`, `True`, `False`, `None`. (`hash` deliberately removed — DoS risk via collision attacks.)

**Blocked:** All imports, `eval()`, `exec()`, `compile()`, `open()`, `__import__`, `input()`, `breakpoint()`, `globals()`, `locals()`, `vars()`, `dir()`, `getattr()`, `setattr()`, `delattr()`, class definitions, async functions, context managers (`with`), `__builtins__` access, MRO traversal (`__class__`, `__subclasses__`, `__mro__`, `__dict__`).

**Fast-path check:** `FORBIDDEN_IN_SANDBOX` tokens: `__import__`, `eval(`, `exec(`, `open(`, `compile(`.

**AST validation:** `_validate_sandbox_ast()` blocks obfuscated bypasses via syntax-tree analysis.

**Execution:** In-process with `SAFE_BUILTINS` as `__builtins__`. Stdout captured via `contextlib.redirect_stdout` with `_STDOUT_LOCK`.

**Output:** If no stdout, returns env dump `{k: str(v) for k, v in local_env.items()}`. If stdout present, pruned via `prune_text()`.

**Example:**
```python
# Pure logic — no imports
python(action="run", code="print(sum(range(100)))")
# → {"status": "success", "data": "4950", "mode": "sandbox"}

# Math + string ops
python(action="run", code="x = [1,2,3]; print(sum(x) * 2)")
# → {"status": "success", "data": "12", "mode": "sandbox"}

# With json_schema (graceful — output not JSON, warning appended)
python(action="run", code="print(42)", json_schema='{"type":"integer"}')
# → {"status": "success", "data": "42", "mode": "sandbox",
#    "warnings": ["json_schema was provided but output is not valid JSON — schema check skipped."]}

# Forbidden token — fast-path rejection
python(action="run", code="open('/etc/passwd')")
# → {"status": "error", "error": "Forbidden token 'open(' in sandbox mode. Use action='run_data' for code that needs imports or file access.", "mode": "sandbox"}
```

---

### `python(action="run_data", ...)` — Controlled Imports

**Purpose:** Data analysis / file processing / calculations requiring imports. Stdlib modules run in-process; heavy libs run in a subprocess with timeout.

**Required:** `code`
**Optional:** `trace_id`, `timeout` (forwards to subprocess), `json_schema` (graceful).

**Allowed stdlib (in-process):** `random`, `json`, `math`, `statistics`, `datetime`, `calendar`, `collections`, `itertools`, `functools`, `re`, `csv`, `io`, `textwrap`, `string`, `decimal`, `fractions`, `heapq`, `bisect`, `pprint`, `copy`, `time`, `uuid`, `hashlib`, `base64`, `struct`, `dataclasses`, `typing`, `enum`, `abc`.

**Allowed heavy libs (subprocess):** `pandas`, `numpy`, `matplotlib`, `scipy`, `sklearn`, `seaborn`, `plotly`, `PIL`, `cv2`, `torch`, `tensorflow`.

**Allowed core:** `core.br_validator` (granular — no arbitrary `core.*` access).

**Blocked (never allowed):** `os`, `sys`, `subprocess`, `shutil`, `socket`, `pickle`, `multiprocessing`, `ctypes`, `importlib`, `builtins`, `signal`, `pty`, `tty`, `termios`, `fcntl`, `resource`.

**Execution path:**
- Stdlib-only imports → `_run_inprocess()` (fast, no subprocess overhead)
- Heavy lib imports → `_run_subprocess()` (isolated, timeout-enforced, temp file in `cfg.workspace_root`)

**Output:** Stdout from `print()`, pruned via `prune_text()`.

**Example:**
```python
# Stdlib — in-process
python(action="run_data", code="import json; print(json.dumps({'a': 1}))")
# → {"status": "success", "data": "{\"a\": 1}", "mode": "in_process"}

# Heavy lib — subprocess
python(action="run_data", code="import pandas as pd; print(pd.DataFrame({'x': [1,2,3]}).to_string())")
# → {"status": "success", "data": "   x\n0  1\n1  2\n2  3", "mode": "subprocess"}

# With timeout override (60s instead of cfg.execution_timeout)
python(action="run_data", code="import pandas as pd; ...", timeout=60)

# Blocked import — security boundary
python(action="run_data", code="import os; print(os.getcwd())")
# → {"status": "error", "error": "Import(s) blocked for security: ['os']. These modules can access filesystem, processes, or network. Use the file(), git(), or web() tools instead.", "mode": "run_data"}

# With json_schema (graceful — validates parsed JSON)
python(action="run_data", code="import json; print(json.dumps({'a': 1, 'b': 2}))",
       json_schema='{"type":"object","required":["a","b"],"properties":{"a":{"type":"integer"},"b":{"type":"integer"}}}')
# → {"status": "success", "data": "{\"a\": 1, \"b\": 2}", "mode": "in_process"}  (no warnings — schema matched)
```

---

### `python(action="eval", ...)` — Pure Expression (NEW in v1.0)

**Purpose:** Quick evaluation of a single Python expression. **Stricter than `run`** — rejects ALL statements (assignments, loops, ifs, defs, with). The expression value IS the output (no `print()` needed).

**Required:** `code` (must be a single expression — `ast.parse(code, mode='eval')` must succeed)
**Optional:** `trace_id`, `json_schema` (**strict** — fails on mismatch). `timeout` accepted but ignored (in-process).

**Validation:** `_validate_eval_ast(code)` — first parses in `mode='eval'` (rejects all statements), then composes `_validate_sandbox_ast` for the same security boundary as `run`.

**Execution:** `eval()` with `SAFE_BUILTINS` only.

**Output:** The expression value, stringified via `_stringify()`:
- `str` → returned as-is
- `dict` / `list` / `tuple` / `None` / `int` / `float` / `bool` → `json.dumps(value, default=str)`
- Anything else → `repr(value)`

**Example:**
```python
# Arithmetic
python(action="eval", code="2 + 2")
# → {"status": "success", "data": "4", "mode": "eval"}

# List comprehension
python(action="eval", code="[x**2 for x in range(5)]")
# → {"status": "success", "data": "[0, 1, 4, 9, 16]", "mode": "eval"}

# Generator expression
python(action="eval", code="sum(x for x in range(10) if x % 2 == 0)")
# → {"status": "success", "data": "20", "mode": "eval"}

# Dict literal
python(action="eval", code="{'a': [1,2], 'b': [3,4]}")
# → {"status": "success", "data": "{\"a\": [1, 2], \"b\": [3, 4]}", "mode": "eval"}

# With json_schema (STRICT — fails on mismatch)
python(action="eval", code="{'a': 1}", json_schema='{"type":"object","required":["a","b"],"properties":{"a":{"type":"integer"},"b":{"type":"integer"}}}')
# → {"status": "error", "error": "Output does not match schema: missing required field: b", "mode": "eval"}

# Statement rejected (must be a single expression)
python(action="eval", code="x = 42")
# → {"status": "error", "error": "eval mode only accepts expressions, not statements. (line 1: invalid syntax)", "mode": "eval"}

# Imports rejected (same security boundary as run)
python(action="eval", code="__import__('os').getcwd()")
# → {"status": "error", "error": "Forbidden token '__import__' ...", "mode": "eval"}
# (NOTE: eval does NOT use the FORBIDDEN_IN_SANDBOX fast-path; the AST validator catches it.)
```

---

### `python(action="profile", ...)` — cProfile Timing Breakdown (NEW in v1.0)

**Purpose:** Profile code with `cProfile` and return the top-20 cumulative-time functions via `pstats`. Useful for identifying bottlenecks in LLM-generated code before committing to `run_data` execution.

**Required:** `code`
**Optional:** `trace_id`, `timeout` (forwards to subprocess when code has imports). `json_schema` ignored (output is profiling data, not user data).

**⚠️ NOT SANDBOXED.** Profiling requires full builtins access (`cProfile`, `pstats`, `io`) and the profiled code may need imports. Restricting builtins would defeat the purpose. **Use only on trusted code** — code that has already passed `lint` or `run`/`run_data` validation.

**Execution path:**
- Code declares imports (any kind) → `_profile_subprocess` (wraps code in `cProfile.Profile().enable()` / `.disable()` template, runs via `_run_subprocess`)
- No imports → `_profile_inprocess` (cProfile directly in current process)

**Output:** `pstats`-formatted output, sorted by `cumulative`, top-20 functions via `ps.print_stats(20)`. `mode` is always `"profile"` regardless of executor path.

**Example:**
```python
# Simple — no imports, in-process
python(action="profile", code="print(sum(range(10000)))")
# → {"status": "success", "data": "         10005 function calls in 0.005 seconds\n\n   Ordered by: cumulative time\n\n   ncalls  tottime  percall  cumtime  percall filename:lineno(function)\n        1    0.000    0.000    0.005    0.005 ...", "mode": "profile"}

# With imports — subprocess
python(action="profile", code="import json; [json.dumps({i: i}) for i in range(100)]", timeout=60)
# → {"status": "success", "data": "<pstats output>", "mode": "profile"}

# Syntax error surfaced cleanly
python(action="profile", code="def f(x)\n  return x")
# → {"status": "error", "error": "SyntaxError line 1: invalid syntax", "mode": "profile"}
```

---

### `python(action="lint", ...)` — ruff/flake8 Pre-Check (NEW in v1.0)

**Purpose:** Surface syntax errors (E) and pyflakes errors (F) before code execution. Use as a pre-flight gate before `run_data` on complex scripts.

**Required:** `code`
**Optional:** `trace_id`. `timeout` ignored (fixed 10s hard cap). `json_schema` ignored.

**Linter selection:**
1. `shutil.which("ruff")` → if present, run `ruff check --select E,F --no-cache <tmp>`
2. elif `shutil.which("flake8")` → run `flake8 <tmp>`
3. else → `fail("Neither ruff nor flake8 is installed. Install with: pip install ruff")`

**Execution:** Writes code to a temp `.py` file, runs the linter via `subprocess.run(timeout=10)`, combines stdout+stderr, deletes temp file in `finally` block.

**Exit codes:**
- `0` = clean (no issues)
- `1` = lint issues found (still a successful run — issues are content of the lint output)
- `>1` = tool error → `fail`

**Output:** Linter output (combined stdout+stderr), or `"(ruff|flake8) reported no issues — clean"` if empty.

**Example:**
```python
# Clean code
python(action="lint", code="def f(x):\n    return x * 2")
# → {"status": "success", "data": "(ruff reported no issues — clean)", "mode": "lint"}

# Lint issues found (still success)
python(action="lint", code="import os\nprint(os.getcwd())")
# → {"status": "success", "data": "<path>:1:8: F401 [*] `os` imported but unused\n...", "mode": "lint"}

# Syntax error caught
python(action="lint", code="def f(x)\n  return x")
# → {"status": "success", "data": "<path>:1:9: E999 SyntaxError: expected ':'", "mode": "lint"}
# (NOTE: syntax errors are reported as lint content, not as a tool failure — exit code 1, not >1)

# Neither linter installed
python(action="lint", code="print('hello')")
# → {"status": "error", "error": "Neither ruff nor flake8 is installed. Install with: pip install ruff", "mode": "lint"}

# Linter timeout (10s hard cap)
# → {"status": "error", "error": "ruff timed out after 10s.", "mode": "lint"}
```

---

## 📤 Output Schema

Every response is a flat `dict` with a `status` key. The `mode` field reports which executor path was taken.

### Success

```json
{
  "status": "success",
  "data": "4950",
  "mode": "sandbox",
  "trace_id": "wf-1234",
  "warnings": ["json_schema validation failed: ..."],
  "duration_ms": 12
}
```
> `trace_id` is omitted when the caller didn't pass one. `warnings` is omitted when no validation issues occurred. `duration_ms` is always present, set by the facade.

### Error (forbidden token)

```json
{
  "status": "error",
  "error": "Forbidden token '__import__' in sandbox mode. Use action='run_data' for code that needs imports or file access.",
  "mode": "sandbox",
  "trace_id": "wf-1234",
  "duration_ms": 2
}
```

### Error (AST blocked)

```json
{
  "status": "error",
  "error": "Blocked sandbox escape vector: attribute '__subclasses__' is not allowed in sandbox mode.",
  "mode": "sandbox",
  "duration_ms": 3
}
```

### Error (blocked import)

```json
{
  "status": "error",
  "error": "Import(s) blocked for security: ['os']. These modules can access filesystem, processes, or network. Use the file(), git(), or web() tools instead.",
  "mode": "run_data",
  "duration_ms": 1
}
```

### Error (not in allowed list)

```json
{
  "status": "error",
  "error": "Import(s) not in allowed list: ['django']. Allowed stdlib: [...]. Allowed heavy: [...].",
  "mode": "run_data",
  "duration_ms": 1
}
```

### Error (subprocess timeout)

```json
{
  "status": "error",
  "error": "Timed out after 60s. Simplify or reduce data size.",
  "mode": "subprocess",
  "duration_ms": 60123
}
```

### Error (syntax)

```json
{
  "status": "error",
  "error": "SyntaxError line 3: invalid syntax",
  "mode": "run_data",
  "duration_ms": 1
}
```

### Error (eval schema mismatch — STRICT)

```json
{
  "status": "error",
  "error": "Output does not match schema: missing required field: b",
  "mode": "eval",
  "duration_ms": 4
}
```

### Facade-Level Errors

| Trigger | Response |
|---------|----------|
| `action` empty / whitespace | `{"status": "error", "error": "action is required (run \| run_data \| eval \| profile \| lint)", "trace_id": ..., "duration_ms": ...}` |
| `action` not in `DISPATCH` | `{"status": "error", "error": "Unknown action '<x>'. Use: eval \| lint \| profile \| run \| run_data", "trace_id": ..., "duration_ms": ...}` |
| `code` empty / whitespace | `{"status": "error", "error": "No code provided", "trace_id": ..., "duration_ms": ...}` |
| Handler raises exception | `{"status": "error", "error": "Python action failed: <exc>", "trace_id": ..., "duration_ms": ...}` |
| Handler returns non-dict | `{"status": "error", "error": "Handler returned <type>, expected dict.", "trace_id": ..., "duration_ms": ...}` |

---

## ⚠️ Error Handling

| Condition | `status` | `mode` | Returned by | `trace_id` | `warnings` | `duration_ms` |
|-----------|----------|--------|-------------|------------|------------|---------------|
| `action` empty | `error` | ❌ | Facade | ✅ (if passed) | ❌ | ✅ |
| `action` unknown | `error` | ❌ | Facade | ✅ (if passed) | ❌ | ✅ |
| `code` empty | `error` | (per-action) | Facade | ✅ (if passed) | ❌ | ✅ |
| Forbidden token (run) | `error` | `sandbox` | Handler (fast-path) | ✅ (if passed) | ❌ | ✅ |
| AST blocked (run/eval) | `error` | `sandbox` / `eval` | Handler (`_validate_*_ast`) | ✅ (if passed) | ❌ | ✅ |
| Blocked import (run_data) | `error` | `run_data` | Handler (imports check) | ✅ (if passed) | ❌ | ✅ |
| Unknown import (run_data) | `error` | `run_data` | Handler (imports check) | ✅ (if passed) | ❌ | ✅ |
| SyntaxError (run_data/profile) | `error` | `run_data` / `profile` | Handler (`ast.parse`) | ✅ (if passed) | ❌ | ✅ |
| Subprocess timeout (run_data/profile) | `error` | `subprocess` / `profile` | Handler (`_run_subprocess`) | ✅ (if passed) | ❌ | ✅ |
| Subprocess non-zero exit (run_data/profile) | `error` | `subprocess` / `profile` | Handler (`_run_subprocess`) | ✅ (if passed) | ❌ | ✅ |
| Lint tool not installed (lint) | `error` | `lint` | Handler (`_has_executable`) | ✅ (if passed) | ❌ | ✅ |
| Lint timeout (lint, 10s hard cap) | `error` | `lint` | Handler (`subprocess.run`) | ✅ (if passed) | ❌ | ✅ |
| Lint tool error (exit >1) | `error` | `lint` | Handler | ✅ (if passed) | ❌ | ✅ |
| eval schema mismatch (STRICT) | `error` | `eval` | Handler (`_validate_against_schema`) | ✅ (if passed) | ❌ | ✅ |
| eval invalid json_schema string (STRICT) | `error` | `eval` | Handler | ✅ (if passed) | ❌ | ✅ |
| Handler raises exception | `error` | ❌ | Facade (try/except) | ✅ (if passed) | ❌ | ✅ |
| Handler returns non-dict | `error` | ❌ | Facade (isinstance check) | ✅ (if passed) | ❌ | ✅ |
| Success (no schema, no truncation) | `success` | (per-action) | Handler | ✅ (if passed) | ❌ | ✅ |
| Success with json_schema match (run/run_data/eval) | `success` | (per-action) | Handler | ✅ (if passed) | ❌ | ✅ |
| Success with json_schema mismatch (run/run_data, GRACEFUL) | `success` | `sandbox` / `in_process` / `subprocess` | Handler | ✅ (if passed) | ✅ (1 warning) | ✅ |
| Success with invalid json_schema string (run/run_data, GRACEFUL) | `success` | `sandbox` / `in_process` / `subprocess` | Handler | ✅ (if passed) | ✅ (1 warning) | ✅ |
| Success (profile/lint — json_schema ignored) | `success` | `profile` / `lint` | Handler | ✅ (if passed) | ❌ | ✅ |

**Notes:**
- `mode` is **always present on handler-level errors and successes** — it identifies which executor path was attempted. Facade-level errors (bad `action`, empty `code`, handler exception, non-dict return) do NOT have a `mode` field because the handler never ran.
- `trace_id` is **always** included when the caller passed one — even on facade-level validation errors. This ensures workflow tracing can correlate a failed `python` call to its trace.
- `warnings` is only present on `success` responses when `json_schema` validation failed gracefully (run/run_data). It is never present on error responses or on `eval` successes (eval is strict — it fails instead of warning).
- `duration_ms` is added by the facade on **every** return path (including facade-level errors) — useful for SLO monitoring without separate instrumentation.

---

## 📐 JSON Schema Validation

The `json_schema` param (NEW in v1.0) accepts a JSON Schema string. Behavior is per-action:

| Action | Semantics | Why |
|--------|-----------|-----|
| `run` | **Graceful** — parse output as JSON, validate, append warning on mismatch, return output as-is | Output is arbitrary stdout text; JSON-ness isn't guaranteed |
| `run_data` | **Graceful** — same as `run` | Same rationale |
| `eval` | **Strict** — validate the expression value against schema, `fail` on mismatch | The value IS a structured object; mismatch is a real bug |
| `profile` | **Ignored** | Output is `pstats` data, not user data |
| `lint` | **Ignored** | Output is linter text, not user data |

**Supported JSON Schema keywords** (best-effort, no `jsonschema` package dependency):
- `type` — One of `string`, `integer`, `number`, `boolean`, `array`, `object`, `null`. **Bool-vs-int disambiguation:** `bool` is a subclass of `int` in Python; the validator explicitly rejects boolean values when the schema declares `integer` or `number` to avoid silent type confusion.
- `enum` — Value must be in the enum list.
- `required` — For `object` types: every key in `required[]` must be present.
- `properties` — For `object` types: validate each present key's value against its sub-schema (recursive).
- `items` — For `array` types: validate each element against the items schema (recursive).

**Unsupported keywords** (would require `jsonschema` dependency): `$ref`, `allOf`, `anyOf`, `oneOf`, `not`, `format`, `pattern`, `minimum`/`maximum`, `minLength`/`maxLength`, `minItems`/`maxItems`. If a caller needs these, add `jsonschema` to `requirements.txt` and swap `_validate_against_schema` for `jsonschema.validate()` — the call signature is compatible.

**Example schemas:**
```json
// Object with required integer fields
{"type":"object","required":["a","b"],"properties":{"a":{"type":"integer"},"b":{"type":"integer"}}}

// Array of strings
{"type":"array","items":{"type":"string"}}

// Enum-constrained string
{"type":"string","enum":["low","medium","high"]}

// Nested object
{"type":"object","required":["name","scores"],"properties":{"name":{"type":"string"},"scores":{"type":"array","items":{"type":"number"}}}}
```

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **Sandbox builtins** | `SAFE_BUILTINS` dict replaces `__builtins__` for `run`/`eval`. Only 30+ safe functions. `hash` deliberately removed (DoS risk via collision attacks). |
| **AST validation (run/eval)** | `_validate_sandbox_ast()` / `_validate_eval_ast()` block imports, dangerous calls, MRO traversal, metaclass attacks, dynamic subscripts, context managers. See [ARCHITECTURE.md § Security Layers](ARCHITECTURE.md#-security-layers). |
| **Fast-path tokens (run only)** | `FORBIDDEN_IN_SANDBOX` catches obvious violations before AST parsing. (`eval` skips this — relies purely on AST validation, which is safer.) |
| **Import allowlisting (run_data)** | `ALL_ALLOWED = STDLIB_IMPORTS \| HEAVY_IMPORTS \| CORE_ALLOWED`. Everything else rejected. `_parse_imports` preserves `core.*` dotted path for granular `CORE_ALLOWED` check. |
| **Blocked imports (run_data)** | `BLOCKED_IMPORTS` frozenset: `os`, `sys`, `subprocess`, `shutil`, `socket`, `pickle`, `ctypes`, `multiprocessing`, `importlib`, `builtins`, `signal`, `pty`, `tty`, `termios`, `fcntl`, `resource`. Never allowed. |
| **Subprocess isolation** | Heavy libs run in `subprocess.run()` with timeout (overridable via `timeout` param) and temp file cleanup in `finally` block. |
| **Thread-safe stdout** | `_STDOUT_LOCK` prevents concurrent `redirect_stdout` clobbering in `parallel()`. |
| **No `hash` in `SAFE_BUILTINS`** | Removed in Pre-v1 — DoS risk via collision attacks. Never re-add. |
| **Temp file cleanup** | `finally` block ensures temp file deletion even on exception (in `_run_subprocess` and `_run_lint`). |
| **Lint subprocess isolation** | `lint` writes code to a temp file and runs `ruff`/`flake8` in a subprocess with a 10-second hard timeout. The linter never has access to the agent's Python process. |
| **Action allowlist via `DISPATCH`** | The facade only invokes handlers registered through `@register_action`. Unknown `action` values return `error` before any handler runs — no eval, no string-to-function mapping. |
| **`trace_id` is caller-supplied** | The tool never generates its own `trace_id`. Prevents log-injection via fabricated trace IDs. |
| **`profile` NOT sandboxed** | Documented prominently — profiling needs full builtins. Use only on trusted code. |

> **Warning:** The sandbox is defense-in-depth against LLM mistakes and prompt injection. It is NOT a security boundary against determined adversarial code. Do not expose to untrusted multi-tenant input without OS-level sandboxing.

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
