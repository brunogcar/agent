<- Back to [Python Overview](../PYTHON.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
def python(
    mode: str,
    code: str,
    trace_id: str = "",
) -> dict:
    """Execute Python code.

    mode: "run" | "run_data"

    run
      Strict sandbox — no imports allowed.
      Only whitelisted built-ins: print, range, len, int, float, str,
      list, dict, set, sum, min, max, abs, round, sorted, zip, etc.
      Use for: math, string ops, list/dict manipulation, pure logic.
      Fast — runs in the current process.

    run_data
      Unrestricted imports from allowed module list.
      Stdlib modules (json, math, datetime, re, csv, etc.) → in-process, fast.
      Heavy libs (pandas, numpy, matplotlib, sklearn) → subprocess, isolated.
      ALWAYS use print() to return output — variables are not captured.
      Use for: data analysis, file processing, calculations with libraries.
    """
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `mode` | `str` | **Yes** | — | Execution mode: `run` (sandbox) or `run_data` (controlled imports) |
| `code` | `str` | **Yes** | — | Python code to execute. Must use `print()` to return results. |
| `trace_id` | `str` | No | `""` | Trace identifier for observability |

---

## ⚡ Modes

### `run` — Strict Sandbox

**Allowed builtins:** `print`, `range`, `len`, `int`, `float`, `str`, `bool`, `list`, `dict`, `set`, `tuple`, `sum`, `min`, `max`, `abs`, `round`, `enumerate`, `zip`, `map`, `filter`, `sorted`, `reversed`, `isinstance`, `issubclass`, `type`, `repr`, `any`, `all`, `chr`, `ord`, `hex`, `oct`, `bin`, `divmod`, `pow`, `True`, `False`, `None`

**Blocked:** All imports, `eval()`, `exec()`, `compile()`, `open()`, `__import__`, `input()`, `breakpoint()`, `globals()`, `locals()`, `vars()`, `dir()`, `getattr()`, `setattr()`, `delattr()`, class definitions, async functions, context managers (`with`), `__builtins__` access, MRO traversal (`__class__`, `__subclasses__`, `__mro__`, `__dict__`)

**Fast-path check:** `FORBIDDEN_IN_SANDBOX` tokens: `__import__`, `eval(`, `exec(`, `open(`, `compile(`

**AST validation:** `_validate_sandbox_ast()` blocks obfuscated bypasses via syntax-tree analysis.

**Execution:** In-process with `SAFE_BUILTINS` as `__builtins__`. Stdout captured via `contextlib.redirect_stdout` with `_STDOUT_LOCK`.

**Output:** If no stdout, returns env dump `{k: str(v) for k, v in local_env.items()}`. If stdout present, pruned via `prune_text()`.

### `run_data` — Controlled Imports

**Allowed stdlib:** `random`, `json`, `math`, `statistics`, `datetime`, `calendar`, `collections`, `itertools`, `functools`, `re`, `csv`, `io`, `textwrap`, `string`, `decimal`, `fractions`, `heapq`, `bisect`, `pprint`, `copy`, `time`, `uuid`, `hashlib`, `base64`, `struct`, `dataclasses`, `typing`, `enum`, `abc`

**Allowed heavy libs:** `pandas`, `numpy`, `matplotlib`, `scipy`, `sklearn`, `seaborn`, `plotly`, `PIL`, `cv2`, `torch`, `tensorflow`

**Allowed core:** `core.br_validator`

**Blocked (never allowed):** `os`, `sys`, `subprocess`, `shutil`, `socket`, `pickle`, `multiprocessing`, `ctypes`, `importlib`, `builtins`, `signal`, `pty`, `tty`, `termios`, `fcntl`, `resource`

**Execution path:**
- Stdlib-only imports → `_run_inprocess()` (fast, no subprocess overhead)
- Heavy lib imports → `_run_subprocess()` (isolated, timeout-enforced)

**Subprocess:** Temp file in `cfg.workspace_root`, `subprocess.run()` with `cfg.execution_timeout`, auto-cleanup on completion/error.

---

## 📤 Output

### Success (sandbox)
```json
{
  "status": "success",
  "data": "4950",
  "mode": "sandbox"
}
```

### Success (run_data, in-process)
```json
{
  "status": "success",
  "data": "{\"a\": 1}",
  "mode": "in_process"
}
```

### Success (run_data, subprocess)
```json
{
  "status": "success",
  "data": "   x\n0  1\n1  2\n2  3",
  "mode": "subprocess"
}
```

### Error (forbidden token)
```json
{
  "status": "error",
  "error": "Forbidden token '__import__' in sandbox mode. Use mode='run_data' for code that needs imports or file access.",
  "mode": "sandbox"
}
```

### Error (AST blocked)
```json
{
  "status": "error",
  "error": "Blocked sandbox escape vector: attribute '__subclasses__' is not allowed in sandbox mode.",
  "mode": "sandbox"
}
```

### Error (blocked import)
```json
{
  "status": "error",
  "error": "Import(s) blocked for security: ['os']. These modules can access filesystem, processes, or network. Use the file(), git(), or web() tools instead.",
  "mode": "run_data"
}
```

### Error (not in allowed list)
```json
{
  "status": "error",
  "error": "Import(s) not in allowed list: ['django']. Allowed stdlib: [...]. Allowed heavy: [...].",
  "mode": "run_data"
}
```

### Error (subprocess timeout)
```json
{
  "status": "error",
  "error": "Timed out after 60s. Simplify or reduce data size.",
  "mode": "subprocess"
}
```

### Error (syntax)
```json
{
  "status": "error",
  "error": "SyntaxError line 3: invalid syntax",
  "mode": "run_data"
}
```

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **Sandbox builtins** | `SAFE_BUILTINS` dict replaces `__builtins__`. Only 30+ safe functions. |
| **AST validation** | `_validate_sandbox_ast()` blocks imports, dangerous calls, MRO traversal, metaclass attacks, dynamic subscripts. |
| **Fast-path tokens** | `FORBIDDEN_IN_SANDBOX` catches obvious violations before AST parsing. |
| **Import allowlisting** | `ALL_ALLOWED = STDLIB_IMPORTS | HEAVY_IMPORTS | CORE_ALLOWED`. Everything else rejected. |
| **Blocked imports** | `BLOCKED_IMPORTS` frozenset: `os`, `sys`, `subprocess`, `shutil`, `socket`, `pickle`, `ctypes`, etc. Never allowed. |
| **Subprocess isolation** | Heavy libs run in `subprocess.run()` with timeout and temp file cleanup. |
| **Thread-safe stdout** | `_STDOUT_LOCK` prevents concurrent `redirect_stdout` clobbering. |
| **No `hash`** | Removed from `SAFE_BUILTINS` — DoS risk via collision attacks. |
| **Temp file cleanup** | `finally` block ensures temp file deletion even on exception. |

> **Warning:** The sandbox is defense-in-depth against LLM mistakes and prompt injection. It is NOT a security boundary against determined adversarial code. Do not expose to untrusted multi-tenant input without OS-level sandboxing.

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
