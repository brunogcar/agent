<- Back to [Parallel Overview](../PARALLEL.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add runtime tool discovery** — `_TOOL_MAP` is explicit (17 hardcoded keys). Dynamic loading risks circular imports and non-deterministic behavior. Add new tools by editing the dict + the `_get_tool_fn` lazy-import chain in `tools/parallel_ops/tool_map.py`.
2. **Never add a tool to `PARALLEL_SAFE` without thread-safety analysis** — Adding `git`, `memory`, `cli`, `browser`, `tavily`, `swarm`, or `workflow` causes real-world lock collisions, state corruption, or thread-pool exhaustion. Document the analysis in the docstring + the API.md table when adding a tool.
3. **Never remove the nested-call guard** — `threading.local()` (`_parallel_depth` in `tools/parallel_ops/executor.py`) is the only protection against `parallel → parallel` deadlock. All three engines must increment it.
4. **Never call `dispatch_run` / `dispatch_race` / `dispatch_pipeline` directly from the facade** — The facade invokes action handlers via `DISPATCH["parallel"][action]["func"]`. Bypassing the dispatch table breaks `@meta_tool` introspection and the action-name validation flow.
5. **Never add a tool to `_TOOL_MAP` without adding the matching lazy-import branch in `_get_tool_fn`** — A new key with `None` value that has no `elif name == "X":` branch returns `None` silently, surfacing as `"Tool 'X' not found"` at runtime.
6. **Never use `as_completed()` for the `run` action's timeout** — It blocks indefinitely. `dispatch_run` uses `concurrent.futures.wait()`. (`dispatch_race` legitimately uses `as_completed()` — it needs to react to completion order.)
7. **Never hardcode timeout values** — Always route through `_resolve_timeout()` (which falls back to `cfg.worker_timeout`). The `.env` is the single source of truth.
8. **Never create `.bak` files** — forbidden by project rules.
9. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
10. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks. (Action handlers may accept `**kwargs` to swallow forward-compat params — the facade must not.)
11. **Never print to stdout** — MCP stdio corruption. Return dicts only.
12. **Never skip `compileall` before `pytest`** — catches syntax errors early.
13. **Never import `parallel` into `_TOOL_MAP`** — Nested parallel calls are blocked by `_parallel_depth`; the tool name is omitted from `_TOOL_MAP` entirely so attempting to dispatch returns `"Tool 'parallel' not found"` cleanly (instead of dispatching then failing on the nested guard).
14. **Never remove the `core/parallel_executor.py` shim** — Existing imports (`from core.parallel_executor import dispatch_parallel, PARALLEL_SAFE, ...`) continue to work via the 37-line re-export. New code should import from `tools.parallel_ops.*` directly, but the shim must remain.
15. **Never expand `parallel` beyond `run`/`race`/`pipeline` without a dispatch engine** — A new action requires (a) a new file in `tools/parallel_ops/actions/`, (b) `@register_action("parallel", "<name>", ...)` on the handler, (c) if the action has novel execution semantics, a new `dispatch_<name>` function in `tools/parallel_ops/executor.py`. Auto-discovery picks up (a) + (b); (c) is manual.

## ✅ ALWAYS DO

16. **Always follow the `@meta_tool` pattern** — The facade is decorated with `@tool` + `@meta_tool(DISPATCH.get("parallel", {}), doc_sections=[...])`. The `action: Literal[...]` type and the docstring are auto-generated from `DISPATCH`. Adding a new action = drop a file in `actions/` — no edits to the facade needed.
17. **Always import `tools.parallel_ops` in the facade BEFORE reading `DISPATCH`** — The auto-discovery in `parallel_ops/__init__.py` must run before `@meta_tool` reads `DISPATCH` for `Literal` generation. The facade does `from tools import parallel_ops  # noqa: F401` for this side effect.
18. **Always use `_get_tool_fn` for lazy tool imports** — Never `from tools.web import web` at module load in `parallel_ops/`. Lazy imports keep startup fast, avoid circular imports (parallel is itself a tool), and defer optional dependencies (Playwright, ChromaDB, tavily async client).
19. **Always clamp `max_workers` to 1–8** — Both in the action handlers (where applicable) and the executor. Defense in depth.
20. **Always include `trace_id` in `fail()` and `ok()` calls** — Observability requires trace correlation. Thread `trace_id` into every per-task result and every error entry.
21. **Always test the kill-switch paths** — Empty `tasks`, bad types, missing `name`, unknown tool, unsafe tool (run/race only), invalid `feed` type (pipeline only), empty `action`, unknown `action`.
22. **Always test the nested-call guard** — Patch `_parallel_depth.value` and assert the error message. Test that `pipeline` also increments the guard (a pipeline stage that calls `parallel()` is also blocked).
23. **Always test timeout behavior** — Mock `cfg.worker_timeout` to a small value (via `mock_cfg` fixture patching `tools.parallel_ops.executor.cfg`) and verify `not_done` futures are marked timed out.
24. **Always add `duration_ms` to the response** — The facade does this post-handler via `result["duration_ms"] = round((time.time() - start) * 1000)`. Do not duplicate this in handlers.
25. **Always update this doc** when adding actions, tools to `_TOOL_MAP`, changing `PARALLEL_SAFE`, modifying timeout behavior, or adding a new dispatch engine.
26. **Always update `docs/system_prompts/system_prompt.md`** when the call signature changes (e.g., `tools` → `tasks` rename in v1.0). The system prompt examples are the LLM's primary reference.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** Pre-v1 used `as_completed()` + `future.result(timeout=30)` for the `run` action's timeout.
> - **Why it matters:** `as_completed()` blocks indefinitely waiting for a future to finish, so the per-future timeout never fires if the future hangs. A single hung tool could block the entire parallel call forever.
> - **Fix:** `dispatch_run` uses `concurrent.futures.wait(futures, timeout=effective_timeout)` which enforces a true global deadline. (`dispatch_race` still uses `as_completed()` legitimately — it needs to react to completion order.)

> - **What happened:** In v1.0, the `mock_cfg` fixture in `conftest.py` initially patched `core.config.cfg` instead of `tools.parallel_ops.executor.cfg`. Tests using `timeout=-1` fell back to the real `cfg.worker_timeout` (60s) instead of the mocked 60s, making the test slow and brittle.
> - **Why it matters:** Python's `from core.config import cfg` creates a local binding to the `cfg` object at import time. Patching `core.config.cfg` after import doesn't affect existing bindings. Each module that did `from core.config import cfg` has its own `cfg` name that must be patched individually.
> - **Fix:** Patch the local binding: `patch("tools.parallel_ops.executor.cfg", SimpleNamespace(worker_timeout=60))`. This is the same Python `from-x-import-y` pitfall documented in `consult-v1.0-staging` (the `_call_vision` indirection).

> - **What happened:** During the v1.0 refactor, `_TOOL_MAP` was briefly expanded to include `"parallel": None` (with the intent of letting the nested-parallel guard catch it). Tests showed the error message `"Nested parallel calls are not allowed"` was confusing when the user intent was simply "I tried to nest parallel calls" — they didn't realize the guard fires from inside `dispatch_run`, not from the validator.
> - **Why it matters:** Error messages should fail fast at the right layer. The validator layer is the right place to reject unknown tools; the executor layer is the right place to reject nested calls.
> - **Fix:** `"parallel"` was omitted from `_TOOL_MAP` entirely. Attempting `parallel(action="run", tasks=[{"name": "parallel", ...}])` now returns `"Tool 'parallel' not found"` from the validator — a clearer error at the right layer.

> - **What happened:** The pre-v1 `parallel` tool had a `test_parallel.py` with 15 tests in 4 monolithic classes (`TestValidation`, `TestParallelSafe`, `TestParallelExecution`, `TestExecutorEngine`). Adding a single new validation rule required touching 3 of the 4 classes.
> - **Why it matters:** Monolithic test files discourage coverage growth — every addition risks breaking unrelated tests in the same file.
> - **Fix:** v1.0 split into 7 files (1 conftest + 6 test files), each focused on one concern (run / race / pipeline / dispatch / tool_map / executor). Test count grew 15 → 93 with no friction.

> - **What happened:** During v1.0, an early draft of `dispatch_pipeline` made `feed` dict-mode a hard error when a dot-path resolved to `None`. Tests showed this broke legitimate use cases where downstream tools tolerate `None` args (e.g. `consult(question="...", context=None)` is valid).
> - **Why it matters:** Strict validation at the wrong layer forces callers to pre-check upstream results, defeating the purpose of the feed mechanism.
> - **Fix:** Dict-mode `feed` with a missing dot-path yields `None` (soft error — chain continues). The str-mode `feed` remains strict (resolved value must be a dict — otherwise the call has no valid args).

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
