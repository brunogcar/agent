<- Back to [Python Overview](../PYTHON.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never bypass `@meta_tool` for action dispatch** — the v1.0 refactor reversed the Pre-v1 layout. Every action MUST be registered via `@register_action("python", "<name>", ...)` in `python_ops/actions/<name>.py`. The `action: Literal[...]` annotation and docstring action list are auto-generated from `DISPATCH` — do not hand-write them in `tools/python.py`.
2. **Never call `exec()` / `eval()` directly from an action handler** — always go through the executors (`_run_inprocess`, `_run_subprocess`) for code that needs imports, or use the `SAFE_BUILTINS` + `_STDOUT_LOCK` pattern from `actions/run.py` for sandboxed execution. The executors centralize temp-file cleanup, timeout enforcement, and stdout capture. Bypassing them creates resource leaks and testability holes.
3. **Never bypass sandbox validation** — `_validate_sandbox_ast()` (for `run`) and `_validate_eval_ast()` (for `eval`) are the authoritative security checks. The `FORBIDDEN_IN_SANDBOX` fast-path is supplementary. New actions that execute user code MUST call one of these validators first.
4. **Never bypass import validation** — `run_data` MUST run `_parse_imports(code)`, reject `BLOCKED_IMPORTS` first, then reject anything not in `ALL_ALLOWED`. Skipping any step breaks the security boundary.
5. **Never remove `hash` from `SAFE_BUILTINS`** — DoS risk via collision attacks (Pre-v1 invariant).
6. **Never remove `_STDOUT_LOCK`** — Cross-thread stdout clobbering is a real bug (BUGFIX-2). The lock must wrap every `contextlib.redirect_stdout` call from any action that captures stdout in-process.
7. **Never add modules to `BLOCKED_IMPORTS` or remove them from `SAFE_BUILTINS` without adding tests** — security boundary changes need coverage. Add a test in `test_sandbox_security.py` (for `SAFE_BUILTINS` changes) or `test_run_data.py` (for `BLOCKED_IMPORTS` changes).
8. **Never add `os`, `sys`, `subprocess` to allowed lists** — These are the core security boundary. Use dedicated tools (`file`, `git`, `web`) instead.
9. **Never remove temp file cleanup** — The `finally` block in `_run_subprocess()` (executors.py) and `_run_lint()` (actions/lint.py) MUST always delete the temp file. Leaked temp files accumulate in `cfg.workspace_root`.
10. **Never hardcode timeout values** — Always use `cfg.execution_timeout` (default) or the `timeout` param override. The 10-second `_LINT_TIMEOUT` in `actions/lint.py` is the only intentional hardcoded timeout — linting should be fast and the cap is documented.
11. **Never add a new action without `@register_action`** — dropping a `.py` file in `python_ops/actions/` without the decorator is a silent no-op: the file is auto-imported by `__init__.py`, but the handler is never registered in `DISPATCH`, so callers get `Unknown action`. The decorator is the contract.
12. **Never hand-write the `action: Literal[...]` annotation in the facade** — `@meta_tool` generates it from `DISPATCH.get("python", {})` keys. Adding a new action = drop a file in `python_ops/actions/`. The facade updates itself. (See Anti-Pattern #2 below.)
13. **Never print to stdout** — MCP stdio corruption. Return dicts only. Use `sys.stderr` for debug logs only.
14. **Never create `.bak` files** — forbidden by project rules.
15. **Never rewrite the entire facade (`tools/python.py`) or an action handler for a small fix** — surgical edits only. New actions go in `python_ops/actions/<name>.py`; the facade's `action: Literal[...]` and docstring update themselves via `@meta_tool`.
16. **Never add `**kwargs` to the `@tool @meta_tool` facade** — FastMCP schema breaks. All params must be explicit named kwargs (`action`, `code`, `trace_id`, `timeout`, `json_schema`).
17. **Never skip `compileall` before `pytest`** — catches syntax errors early across the 11-file subpackage.
18. **Never expose the python tool to untrusted multi-tenant input** — The sandbox is defense-in-depth against LLM mistakes, not a security boundary against determined adversaries. The `profile` action is NOT sandboxed at all.
19. **Never run `profile` on untrusted code** — `profile` is NOT sandboxed (it needs full builtins for `cProfile`/`pstats`/`io`). Always run `lint` or `run` first to validate the code's structure, OR document that the caller accepts the risk.
20. **Never collapse the `eval` strict-schema semantics into graceful** — `eval`'s `json_schema` mismatch MUST return `fail`. The expression value IS a structured object; collapsing to a warning would hide real bugs. The asymmetry between `eval` (strict) and `run`/`run_data` (graceful) is deliberate.

## ✅ ALWAYS DO

21. **Always include `mode` in handler-level error and success responses** — consumers need to know which executor path was taken. Facade-level errors (bad `action`, empty `code`, handler exception, non-dict return) do NOT have `mode` because the handler never ran.
22. **Always include `trace_id` in every return path** — when the caller passed a non-empty `trace_id`, every response (success, error) MUST echo it back. Workflow tracing depends on this. The facade handles facade-level errors and threading; handlers must include `trace_id` in their own returns when non-empty.
23. **Always set `duration_ms` on the response** — the facade does this unconditionally after the handler returns. Do not override it in handlers. Even error returns carry timing.
24. **Always use `compileall` before `pytest`** — catches syntax errors early across the 11-file subpackage.
25. **Always test AST bypass vectors** — `__builtins__`, `__subclasses__`, `__class__`, `__base__`, `__mro__`, `__dict__`, `getattr`, dynamic subscripts, metaclass attacks, async functions, context managers. The `test_sandbox_ast_bypass.py` file (15 tests) is the contract.
26. **Always test thread safety** — Concurrent `python(action="run")` calls with `_STDOUT_LOCK`. The `test_python_exec_thread_safety.py` file (3 tests) is the contract.
27. **Always test import blocking** — `os`, `sys`, `subprocess`, `socket`, `pickle`, `shutil` must be rejected in `run_data`. The `TestRunDataBlockedImports` class in `test_run_data.py` is the contract.
28. **Always test subprocess timeout** — Patch `tools.python_ops.executors.cfg.execution_timeout` to a small value, or pass `timeout=<small int>` and assert the error message reports the right value.
29. **Always test temp file cleanup** — Assert temp file is deleted after subprocess execution. Use the `temp_workspace` fixture from `conftest.py` to assert directory contents before/after.
30. **Always add a test class for any new action** — mirror the existing structure (`Success` / `Error` / `EmptyCode` / `TraceID` / `Timeout` / `JSONSchema` as applicable). Skipping any class leaves a coverage hole.
31. **Always register new actions with help text + examples** — `@register_action("python", "<name>", help_text=..., examples=[...])`. The help text feeds the auto-generated docstring; the examples show up in the `@meta_tool` doc_sections.
32. **Always preserve the handler signature `(code, trace_id, timeout, json_schema, **kwargs)`** — the facade calls every handler with these exact kwargs. Adding handler-specific params requires either extending the facade (rare) or using `**kwargs` to absorb extras. Never break the shared signature.
33. **Always patch `prune_text` on BOTH action modules** — `tools.python_ops.actions.run.prune_text` AND `tools.python_ops.actions.run_data.prune_text`. Both modules `from ... import prune_text` at the top, so the patch must target each binding site individually (see Anti-Pattern #1 below).
34. **Always document `timeout` and `json_schema` behavior in the handler docstring** — the help_text passed to `@register_action` is shown in the auto-generated docstring. State whether `timeout` is honored or ignored, and whether `json_schema` is graceful/strict/ignored.
35. **Always update this doc** when adding actions, changing allowlists, modifying security rules, or discovering a new anti-pattern.

---

## 🚫 Anti-Patterns & Lessons Learned

### #1 — Direct imports of `prune_text` in action handlers (import-time-binding lesson)

> - **What happened:** The `conftest.py` fixture `mock_pruner` originally patched `core.memory_backend.pruner.prune_text`. Both `actions/run.py` and `actions/run_data.py` do `from core.memory_backend.pruner import prune_text` at the top of their files. The patch had **no effect** on the handlers' local `prune_text` binding — they kept calling the real `prune_text`.
> - **Why it matters:** Python's `from X import Y` creates a local binding at import time. Patching `X.Y` later has no effect on already-imported local references. Tests appear to "pass" the patch but the handler bypasses it silently — leading to mysterious failures that look like config issues but are actually import-binding issues.
> - **Fix:** The `mock_pruner` fixture patches BOTH `tools.python_ops.actions.run.prune_text` AND `tools.python_ops.actions.run_data.prune_text` directly. Each action module's local `prune_text` symbol is replaced with the mock. This is the same lesson discovered during `consult-v1.0-code` (cross-referenced there as Anti-Pattern #1) — it applies to *every* external dependency accessed from action handlers via `from X import Y`.
> - **Generalization:** For any helper used by multiple action modules (e.g. `prune_text`, the schema validators, `_run_subprocess`), either centralize access in a single module (like `helpers.py` in `consult_ops/`) OR document the multi-patch requirement in `conftest.py`. The current `python_ops/` design uses the latter — `conftest.py` is the authoritative patch-surface reference.

### #2 — Hand-writing the `action: Literal[...]` annotation in the facade

> - **What happened:** (Hypothetical — caught during review.) A maintainer adds a 6th action `format` and manually edits `tools/python.py` to add `"format"` to the `Literal`. The next session adds a 7th action and forgets to update the facade — callers get `Unknown action 'format'` even though the handler is registered.
> - **Why it matters:** The facade annotation is the LLM's schema. If it drifts from `DISPATCH`, the LLM is told an action exists that the runtime can't dispatch (or vice versa).
> - **Fix:** Never hand-write the `Literal`. `@meta_tool` generates it from `DISPATCH.get("python", {})` keys. Adding a new action = drop a file in `python_ops/actions/` with `@register_action`. The facade updates itself.

### #3 — Skipping the FORBIDDEN_IN_SANDBOX fast-path check in `run`

> - **What happened:** (Hypothetical.) A maintainer removes the fast-path check from `run.py` because "the AST validator catches everything anyway". The AST validator is now invoked on `__import__('os').system('rm -rf /')` — which parses fine syntactically — but the expensive walk runs unnecessarily on obvious violations.
> - **Why it matters:** The fast-path is cheap (5 substring checks) and catches the most common LLM mistakes (`eval(`, `exec(`, `open(`, `__import__`, `compile(`) before the AST parser even runs. Removing it makes the common case slower without improving security.
> - **Fix:** Keep both layers. Fast-path catches the obvious; AST validator catches the obfuscated. The error messages differ slightly ("Forbidden token 'eval('" vs "Blocked dangerous call: eval()") which is also useful for debugging — the fast-path error tells the LLM "you typed eval(" while the AST error tells it "you obfuscated eval()".

### #4 — Calling `eval()` directly in `actions/eval.py` instead of using `SAFE_BUILTINS`

> - **What happened:** (Hypothetical.) A maintainer simplifies the `eval` handler to just `result = eval(code)` without restricting `__builtins__`. Now `eval("__import__('os').system('rm -rf /')")` executes the import.
> - **Why it matters:** The `_validate_eval_ast` validator rejects `__import__` at the AST level, but defense-in-depth means the runtime should ALSO restrict builtins. If the validator ever has a bug (or a new bypass is discovered), the `SAFE_BUILTINS` restriction is the fallback.
> - **Fix:** Always pass `{"__builtins__": SAFE_BUILTINS}` as the globals dict to `eval()` (and `exec()` in `run`). Two independent layers must both fail for a bypass to succeed.

### #5 — Adding `provider` / `model` to facade-level error responses

> - **What happened:** (Hypothetical.) A maintainer adds `"mode": "unknown"` to the empty-action error response "for consistency". This pollutes the error schema and breaks callers that branch on `if "mode" in result`.
> - **Why it matters:** Facade-level errors (bad `action`, empty `code`, exception in handler, non-dict return) happen *before* any handler runs. There is no `mode` to report — the action never dispatched. Handlers add `mode` only on responses that they themselves construct.
> - **Fix:** Facade errors carry `status`, `error`, `trace_id`, `duration_ms`. Handler responses (success and error alike) carry `status`, `mode`, `data`/`error`, `trace_id`, `duration_ms`, optionally `warnings`. Do not unify the schemas.

### #6 — Forgetting to force `mode="profile"` on subprocess-routed profile results

> - **What happened:** (Caught during v1.0 implementation.) `_profile_subprocess` calls `_run_subprocess(wrapped_code, ...)`. The `_run_subprocess` helper returns `ok(output, mode="subprocess")`. Without a force-override, the profile result reports `mode="subprocess"` instead of `mode="profile"`, which breaks callers that branch on the mode field.
> - **Why it matters:** The `mode` field tells the consumer which executor ran. For `profile`, the consumer expects `"profile"` regardless of whether it ran in-process or in a subprocess.
> - **Fix:** `_profile_subprocess` explicitly sets `result["mode"] = "profile"` after the `_run_subprocess` call. The in-process path (`_profile_inprocess`) already returns `mode="profile"` from its own `ok()` call.

### #7 — Letting `lint` exit code 1 surface as a tool failure

> - **What happened:** (Caught during v1.0 implementation.) Initial `lint` implementation returned `fail` on any non-zero exit code. But `ruff` / `flake8` use exit code 1 to signal "lint issues found" — which is the *normal* output, not a tool failure.
> - **Why it matters:** Treating exit code 1 as a failure would hide the lint findings from the caller — they'd see `status=error` instead of the actual lint output (unused imports, undefined names, syntax errors, etc.).
> - **Fix:** Exit code 0 = clean (success with "no issues" message); exit code 1 = lint issues found (still success — the issues are the content of the lint output); exit code >1 = tool error (e.g. `ruff` crashed, bad CLI args). Documented in the handler docstring.

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
