<- Back to [File Overview](../FILE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add subcommand parsing to action handlers** — one action = one behavior.
2. **Never use `operation` parameter** — removed in v1.0. Use `action` only.
3. **Never create wrapper functions inside `@meta_tool`** — return `fn` directly.
4. **Never hardcode `Literal` values separate from DISPATCH** — DRY violation.
5. **Never forget to delete `fn.__signature__`** — stale cache won't reflect annotation mutations.
6. **Never skip action name validation before `eval()`** — `^[a-z][a-z0-9_]*$` regex.
7. **Never use `str.isidentifier()` alone** — accepts `__import__`, dunder names.
8. **Never create shadow tools** — one `file()` tool with atomic actions.
9. **Never use AST introspection for action discovery** — DISPATCH dict is explicit.
10. **Never patch FastMCP internal schema after registration** — patch `__annotations__` BEFORE `mcp.tool()(fn)`.
11. **Never leave orphaned old files when renaming** — delete `read.py` when creating `read_file.py`.
12. **Never skip test file cleanup when restructuring** — delete old test files.
13. **Never re-validate paths in action handlers** — the facade already validates. Handlers receive pre-resolved paths. Calling `_safe_resolve` again creates dual validation paths with inconsistent logic.
14. **Never add `force` requirement to read-only actions** — only `delete_file`, `move_file` (overwrite), `copy_file` (overwrite), and `edit_file` need explicit confirmation.
15. **Never use `errors="replace"` when reading text files** — v1.2 replaced this with the UTF-8 → cp1252 → latin-1 fallback chain. `errors="replace"` silently corrupts non-UTF-8 bytes to U+FFFD; the fallback chain preserves content and reports which encoding won. Use `tools.file_ops.actions.read_file._read_with_encoding_fallback(path)`.
16. **Never import chonkie at module top level** — it's a soft dependency. Import it lazily inside the chunking branch only (see `_chunk_text()` in `read_file.py`). Existing 1788 tests must pass without chonkie installed.
17. **Never mix `chunk=True` with `head`/`tail`/`max_chars` and expect truncation to apply** — chunking is mutually exclusive with those params. When `chunk=True`, the result shape changes (no `content`/`truncated`, instead `chunks`/`chunk_count`/`chunk_method`/`chunk_size`). Callers must pick one mode per call.
18. **Never use `read_file` just to get a line count** — `read_file` has a 10MB ceiling and loads the full file into memory. Use `count_lines` instead (streams in 64KB binary chunks, O(1) memory, no size limit).
19. **Never add a new file action without updating `core/path_guard.py`** — `READ_OPERATIONS` and `WRITE_OPERATIONS` frozensets must include the new action name, or `check_protected_file` will block it on every file (protected or not) with a confusing error.

## ✅ ALWAYS DO

20. **Use `path` for file paths, `source`/`destination` for move/copy** — semantic clarity.
21. **Add new actions by creating a file + `@register_action`** — DISPATCH auto-updates via `@meta_tool`.
22. **Keep tool facade thin** — validation, dispatch, compression. Business logic in action handlers.
23. **Document design decisions in comments** — explain WHY, not just WHAT.
24. **When adding a read-only action, register it in `READ_OPERATIONS`** in `core/path_guard.py` so it works on protected files. When adding a write action, register it in `WRITE_OPERATIONS`.
25. **When adding chunking to a new read action, reuse `_chunk_text()` and `_read_with_encoding_fallback()` from `read_file.py`** — don't reimplement. Both helpers are public to the `tools.file_ops.actions` package.
26. **When chunking is enabled in a handler, return a clearly different result shape** — `chunks` (list), `chunk_count`, `chunk_method`, `chunk_size` instead of `content`/`truncated`. This makes the two modes unambiguous to callers.
27. **For streaming/stat operations, read in binary mode in fixed-size blocks** — 64KB is the GNU coreutils default and a good baseline. Don't load the whole file into memory just to count something.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** v1.0/v1.1 `read_file` used `path.read_text(encoding="utf-8", errors="replace")`. Non-UTF-8 bytes (common in Windows cp1252 logs and binary-ish text files) were silently replaced with U+FFFD, corrupting the content the LLM saw.
> - **Why it matters:** The LLM has no way to know the corruption happened — it sees `?` chars where smart quotes, accented letters, or section symbols used to be. Downstream analysis on the corrupted text produces wrong conclusions.
> - **Fix (v1.2):** Replaced `errors="replace"` with the UTF-8 (strict) → cp1252 (strict) → latin-1 (never fails) fallback chain. The encoding that succeeded is reported in the result `encoding` field. latin-1 is mathematically incapable of raising `UnicodeDecodeError` (every byte 0x00..0xFF maps to a codepoint), so the chain is guaranteed to return content.

> - **What happened:** v1.2 added `count_lines` action but initially forgot to add it to `READ_OPERATIONS` in `core/path_guard.py`. Every call returned `{"status": "error", "error": "Operation 'count_lines' is not in READ_OPERATIONS or WRITE_OPERATIONS..."}` — even on non-protected files.
> - **Why it matters:** `check_protected_file` is called by the facade for every action. If the action name isn't in either set, the guard returns a blocking error. This is a security property (deny by default) but means new actions are dead on arrival without the set update.
> - **Fix (v1.2):** Added `count_lines` to `READ_OPERATIONS`. Lesson: when adding any new file action, the `core/path_guard.py` sets are part of the change — there is a 3-file minimum (action module, facade kwargs if new params, path_guard set).

> - **What happened:** First draft of v1.2 chunking tried to apply `head`/`tail` to the chunk list (e.g. `head=2` returns first 2 chunks). This created ambiguous semantics: does `tail=3` mean "last 3 chunks" or "last 3 lines of the original file"?
> - **Why it matters:** Mixed modes produce results that are hard to reason about and harder to test. The LLM can't predict what it'll get.
> - **Fix (v1.2):** Made `chunk=True` strictly mutually exclusive with `head`/`tail`/`max_chars`. When `chunk=True`, those params are ignored entirely and the result shape is unambiguous (always `chunks`/`chunk_count`/...). Callers wanting fewer chunks should use a larger `chunk_size`.

> - **What happened:** First draft of v1.2 imported chonkie at module load in `read_file.py`. This made chonkie a hard dependency for the entire file tool — `import tools.file` would crash if chonkie wasn't installed, breaking every test that imports `tools.file` even when no chunking was being tested.
> - **Why it matters:** Soft dependencies should not break imports. The 1788-test baseline must pass with the bare requirements.txt minus optional deps.
> - **Fix (v1.2):** Moved `from chonkie import TokenChunker` inside the `_chunk_text()` function. Non-chunk reads never touch chonkie. If chonkie is missing and `chunk=True` is requested, the action returns a clear `pip install chonkie` error instead of crashing on import.

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
