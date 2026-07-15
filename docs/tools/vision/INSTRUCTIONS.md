<- Back to [Vision Overview](../VISION.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never skip the `action` param** — the v1.0 refactor **reversed** the Pre-v1 rule ("Never add an `action` param — wait for the `@meta_tool` refactor"). Every action MUST be registered via `@register_action("vision", "<name>", ...)` in `vision_ops/actions/<name>.py`. The `action: Literal[...]` annotation and docstring action list are auto-generated from `DISPATCH` — do not hand-write them in `tools/vision.py`.
2. **Never call `llm.call()` directly from an action handler** — always go through `helpers._call_vision(system, user_content, json_mode, json_schema, trace_id)`. Direct `llm.call()` calls bypass the conftest patch surface and break testability (see Anti-Patterns #1 below).
3. **Never bypass `is_safe_network_address()`** — always validate URLs via `_validate_vision_inputs()` before any HTTP request. The SSRF check must run before `_download_image_to_data_uri()` is called. Hardcoding a URL fetch that skips the check is a security regression.
4. **Never bypass `retry_sync` for URL downloads** — `_download_image_to_data_uri()` must wrap `_do_download()` in `retry_sync()` from `core/net/retry.py`. Hand-rolling a `try/except` loop with manual `time.sleep` (the Pre-v1 pattern) defeats the central backoff tuning and `is_retryable_error` classification.
5. **Never add a new action without `@register_action`** — dropping a `.py` file in `vision_ops/actions/` without the decorator is a silent no-op: the file is auto-imported by `__init__.py`, but the handler is never registered in `DISPATCH`, so callers get `Unknown action`. The decorator is the contract.
6. **Never hardcode model names** — always use `cfg.vision_model` (via `_check_vision_available()` helper). Hardcoded model strings break the kill-switch and provider resolution.
7. **Never remove the kill-switch check** — the `_check_vision_available()` call is the first thing every handler runs after `_validate_vision_inputs()`. The tool must degrade gracefully to `status=disabled` when `VISION_MODEL` is unconfigured.
8. **Never increase `MAX_IMAGE_BYTES` or `MAX_BASE64_LEN` without explicit user approval** — these are deliberate safety rails (20MB / 10M chars default). Same for `_VISION_DOWNLOAD_RETRIES` (2) — it's vision-specific tuning, not a typo.
9. **Never accept multiple image sources** — exactly one of `file_path`, `base64`, or `url` must be enforced. The `_validate_vision_inputs()` helper does this — don't bypass it.
10. **Never print to stdout** — MCP stdio corruption. Return dicts only. Use `sys.stderr` for debug logs only.
11. **Never create `.bak` files** — forbidden by project rules.
12. **Never rewrite the entire facade (`tools/vision.py`) for a new action** — surgical edits only. New actions go in `vision_ops/actions/<name>.py`; the facade's `action: Literal[...]` and docstring update themselves via `@meta_tool`.
13. **Never add `**kwargs` to the `@tool @meta_tool` facade** — FastMCP schema breaks. All params must be explicit named kwargs. (Action handlers may accept `**kwargs` to absorb facade extras, but the facade itself cannot.)
14. **Never duplicate JSON parsing logic** — use `llm.call()` built-in `json_mode` / `json_schema` parsing (via `_call_vision`), not manual fence stripping. The `parsed` field on the LLM response is the canonical source.
15. **Never accept non-http URL schemes** — `file://`, `ftp://`, `data:`, etc. must be rejected by `_validate_vision_inputs()`.
16. **Never mutate the base system prompts at runtime** — `DESCRIBE_SYSTEM` / `EXTRACT_TEXT_SYSTEM` / `ANALYSE_UI_SYSTEM` and their `*_JSON_SYSTEM` variants are immutable module-level strings. Format and context-type customization happens via *suffix concatenation* inside the handler, never via `+=` on the module-level prompt.
17. **Never leave temp files on disk** — `_file_to_block` reads bytes into memory and never writes intermediates; `_download_image_to_data_uri` keeps the downloaded bytes in memory and converts to a data URI without writing a temp file. If a future action adds temp-file handling, always use a `try/finally` + `os.unlink` (or `tempfile.NamedTemporaryFile(delete=True)`) to clean up.
18. **Never collapse the three return statuses** — `success`, `disabled`, `error` are distinct. Do not merge `disabled` into `error`; downstream callers (router, workflows) branch on these.
19. **Never silently drop the deprecated `task` alias warning** — when `task` is used, BOTH `logger.warning` AND `tracer.warning` must fire. The tracer payload includes `deprecated_param`, `mapped_action`, and `task_preview` (truncated to 100 chars) for observability.

## ✅ ALWAYS DO

20. **Always include `trace_id` in every return path** — when the caller passed a non-empty `trace_id`, every response (success, disabled, error) MUST echo it back. Workflow tracing depends on this. The facade handles facade-level errors; handlers handle their own returns.
21. **Always include `model`, `elapsed`, and `usage` on success** — consumers need to know which model produced the output and how long it took. These come from `result.model` / `result.elapsed` / `result.usage` on the `LLMResponse`.
22. **Always include `parse_warning` when JSON parsing fails** — when `use_json` is true AND `result.parsed` is falsy, add `parse_warning: "LLM response was not valid JSON. Check response.<payload_key>."` and set `parsed = result.parsed or {}`. Consumers need to know their structured output is missing.
23. **Always set `duration_ms` on the response** — the facade does this unconditionally after the handler returns. Do not override it in handlers. Even error returns carry timing.
24. **Always use `compileall` before `pytest`** — catches syntax errors early across the 8-file subpackage + facade.
25. **Always test the kill-switch path** — patch `tools.vision_ops.helpers.cfg.vision_model = ""` and assert `status == "disabled"`. Patch via the `helpers` module, not `core.config` (see Anti-Patterns #1).
26. **Always test SSRF blocking** — patch `tools.vision_ops.helpers.is_safe_network_address` to return `False` and assert `status == "error"` with the SSRF message.
27. **Always test URL download failures** — patch `tools.vision_ops.helpers.httpx.Client.get` (or `_do_download`) with timeout, HTTP error, and success side effects. Verify `retry_sync` retries transient failures and exhausts on persistent ones.
28. **Always test `format` and `context_type` params** — for each action, verify that `format="json"` appends the JSON suffix and `context_type="screenshot"` appends the screenshot modifier to the system prompt passed to `_call_vision`. The `test_describe.py` / `test_extract_text.py` / `test_analyse_ui.py` `Format` and `ContextType` classes are the contract.
29. **Always test `json_schema` parsing** — verify that a valid JSON schema string is forwarded as a dict to `llm.call(json_schema=...)`; verify that a malformed JSON schema string silently degrades to `None` (no crash); verify `parsed` is present on success and `parse_warning` is set when `result.parsed` is falsy.
30. **Always test the deprecated `task` alias** — verify `vision(task="...", file_path="...")` maps to `action="describe"` + `question=task`, that the deprecation warning is logged via `logger.warning`, and that `tracer.warning` is called with `deprecated_param="task"` and `mapped_action="describe"`.
31. **Always add a test class for any new action** — mirror the 9-class structure (`Success` / `Disabled` / `LLMError` / `Validation` / `TraceID` / `Format` / `ContextType` / `JsonSchema` / `JsonMode`). Skipping any class leaves a coverage hole.
32. **Always register new actions with help text + examples** — `@register_action("vision", "<name>", help_text=..., examples=[...])`. The help text feeds the auto-generated docstring; the examples show up in the `@meta_tool` doc_sections.
33. **Always preserve the handler signature `(question, file_path, base64, url, mime_type, json_mode, json_schema, context, context_type, format, trace_id, **kwargs)`** — the facade calls every handler with these exact kwargs. Adding handler-specific params requires either extending the facade (rare) or using `**kwargs` to absorb extras. Never break the shared signature.
34. **Always clean up temp files (if any)** — current handlers don't write temp files, but if you add one (e.g. for `pdf_page_extraction`), use `tempfile.NamedTemporaryFile(delete=True)` or `try/finally + os.unlink`.
35. **Always update this doc** when adding params, changing return shapes, modifying behavior, or discovering a new anti-pattern.

---

## 🚫 Anti-Patterns & Lessons Learned

### #1 — Direct `llm.call()` calls in action handlers (DISCOVERED DURING v1.0 REFACTOR)

> - **What happened:** The first v1.0 test run had numerous failures. Action handlers did `from core.llm import llm` and called `llm.call(...)` directly. The conftest fixture `mock_llm` patches `tools.vision_ops.helpers.llm`, but the handlers' local `llm` binding was unaffected — they kept calling the real (unconfigured) LLMClient.
> - **Why it matters:** Python's `from X import Y` creates a local binding at import time. Patching `X.Y` later has no effect on already-imported local references. The tests appear to "pass" the patch but the handler bypasses it silently — leading to mysterious failures that look like config issues but are actually import-binding issues.
> - **Fix:** Added `helpers._call_vision(system, user_content, json_mode, json_schema, trace_id)` which calls `llm.call(role="vision", ...)`. Refactored all 3 action handlers to call `_call_vision()` instead of `llm.call()` directly. After the refactor, `_call_vision` looks up `llm` in the `helpers` module namespace at call time (not import time), so patching `tools.vision_ops.helpers.llm` transparently intercepts every LLM call.
> - **Generalization:** this applies to *every* external dependency accessed from action handlers — `cfg`, `llm`, `is_safe_network_address`. Centralize access in `helpers.py` so conftest only needs 3 patch points (`mock_cfg`, `mock_llm`, `mock_is_safe_network_address`) to control all three dependencies. Mirrors the same pattern in `consult_ops/`, `swarm_ops/`, `tavily_ops/`.

### #2 — Hand-writing the `action: Literal[...]` annotation in the facade

> - **What happened:** (Hypothetical — caught during review.) A maintainer adds a 4th action `compare` and manually edits `tools/vision.py` to add `"compare"` to the `Literal`. The next session adds a 5th action and forgets to update the facade — callers get `Unknown action 'compare'` even though the handler is registered.
> - **Why it matters:** The facade annotation is the LLM's schema. If it drifts from `DISPATCH`, the LLM is told an action exists that the runtime can't dispatch (or vice versa).
> - **Fix:** Never hand-write the `Literal`. `@meta_tool` generates it from `DISPATCH.get("vision", {})` keys. Adding a new action = drop a file in `vision_ops/actions/` with `@register_action`. The facade updates itself.

### #3 — Mutating the base system prompts at runtime

> - **What happened:** (Hypothetical.) A handler does `DESCRIBE_SYSTEM += "\n\nExtra rules..."` to inject caller-specific guidance. The next call sees the polluted prompt because the module-level string was mutated.
> - **Why it matters:** Module-level strings are shared across all calls in the process. Mutation = state leak = nondeterministic behavior.
> - **Fix:** Base prompts are immutable strings. Format and context-type customization happens via *suffix concatenation* (`BASE + FORMAT_SUFFIXES[format] + CONTEXT_TYPE_MODIFIERS[context_type]`) inside the handler — never via mutation. If a caller needs custom rules, add a new `context_type` modifier to `prompts.py`.

### #4 — Bypassing `retry_sync` for URL downloads

> - **What happened:** (Hypothetical.) A maintainer copies the Pre-v1 hand-rolled `try/except + time.sleep` loop into a new action's URL-download helper "to keep things simple". The new helper doesn't use `is_retryable_error` classification, so it retries 4xx errors that will never succeed, wasting the user's time on broken URLs.
> - **Why it matters:** `core/net/retry.py` is the project-wide retry utility. Using it ensures consistent backoff tuning (via `core/net/default.py`), consistent error classification (via `is_retryable_error`), and consistent jitter behavior across `tavily_ops` / `web_ops` / `browser` / `vision_ops`. Bypassing it creates drift.
> - **Fix:** Always wrap URL downloads in `retry_sync(_do_download, max_retries=_VISION_DOWNLOAD_RETRIES, base_delay=RETRY_BASE_DELAY, max_delay=RETRY_MAX_DELAY, jitter=True, is_retryable=is_retryable_error)`. If you need a different retry count for a new action (e.g. `batch_analyse` doing N parallel fetches), add a vision-specific local constant — don't promote it to `core/net/default.py` unless it's a project-wide default.

### #5 — Skipping the SSRF check in a new URL-fetching helper

> - **What happened:** (Hypothetical.) A maintainer adds a `compare` action that fetches two URLs side-by-side. They write a new `_fetch_two_urls()` helper that calls `_do_download()` directly without going through `_validate_vision_inputs()` first. The new helper accepts `http://localhost/...` URLs and downloads them — SSRF hole.
> - **Why it matters:** SSRF protection is non-negotiable. A vision tool that can fetch arbitrary internal URLs is a server-side request forgery vector — an attacker who controls the `url` param can scan the internal network, hit cloud metadata endpoints, etc.
> - **Fix:** Always call `_validate_vision_inputs(file_path, base64_str, url)` before any URL download. If you need a multi-URL helper, validate each URL individually first. Never call `_do_download()` or `httpx.Client.get()` directly from an action handler.

### #6 — Adding `model` / `elapsed` to facade-level error responses

> - **What happened:** (Hypothetical.) A maintainer adds `"model": "unknown"` to the empty-action error response "for consistency". This pollutes the error schema and breaks callers that branch on `if "model" in result`.
> - **Why it matters:** Facade-level errors (bad `action`, exception in handler) happen *before* the LLM call. There is no model to report. Handlers add `model`/`elapsed` only on errors that occur after `_call_vision()` has run.
> - **Fix:** Facade errors carry `status`, `error`, `trace_id` (and `duration_ms`). Handler errors carry `status`, `error`, `model`, `elapsed`, `trace_id` (and `duration_ms`). Do not unify the schemas.

### #7 — Leaving temp files on disk

> - **What happened:** (Hypothetical — current code doesn't do this.) A future `pdf_page_extraction` action writes each rendered page to `/tmp/page-N.png` and forgets to clean up. After a long session, `/tmp` fills up with thousands of orphan PNGs.
> - **Why it matters:** Disk exhaustion is a denial-of-service vector. The agent runs long-lived; orphans accumulate.
> - **Fix:** Use `tempfile.NamedTemporaryFile(delete=True)` (auto-cleans on close) or `try/finally` with `os.unlink(path)`. Never write intermediates to a hardcoded path. The current `_file_to_block` / `_download_image_to_data_uri` helpers keep everything in memory — preserve that pattern unless the file is genuinely too large to fit (rare for images under 20MB).

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
