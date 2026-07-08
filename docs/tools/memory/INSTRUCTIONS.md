<- Back to [Memory Overview](../MEMORY.md)

# 🛡️ AI Instructions

### NEVER DO
1. **Never add logic to `tools/memory.py`** — Logic belongs in `core.memory_backend/` or `core.memory_engine`. The facade is pure dispatch.
2. **Never remove the janitor bypass** — `archive_old_episodes()` and `purge_stale_rules()` must run without loading the memory store.
3. **Never skip `_validate_tags()`** — All tag inputs must pass validation before reaching the backend.
4. **Never remove `compress_result()`** — All success tool outputs must be compressed to prevent context window bloat.
5. **Never hardcode tag limits** — Use `cfg.max_tags_per_entry` and `cfg.max_tag_length`, not magic numbers.
6. **Never create `.bak` files** — Forbidden by project rules.
7. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
8. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never skip `compileall` before `pytest`** — Catches syntax errors early.
11. **Never call `_mem()` from `janitor.py`** — The janitor action must remain completely isolated from the main store.
12. **Never rely on backend silent coercion** — The backend defaults invalid `memory_type` to "semantic". The tool layer must reject invalid types explicitly.
13. **Never add `PARALLEL_SAFE` for memory** — ChromaDB SQLite is not thread-safe for concurrent writes. Keep `memory` out of `PARALLEL_SAFE`.
14. **Never allow string `confirm_ids`** — Must be a list. Strings iterate character-wise in the backend.
15. **Never silently ignore unsupported params** — `recall_context` must reject `tags_filter`/`min_score` with clear errors.
16. **Never use `chunk=True` on `procedural` memories** — v1.3: The procedural collection has a reinforcement feature (increment `reinforcement_count` on semantic match) that is nonsensical for chunks. The store action rejects this combination with a clear error.
17. **Never call `memory.store()` N times for chunks** — v1.3: Use `memory.store_chunked()` (or `memory(action="store", chunk=True)` from the tool layer). The standard `store()` runs vector dedup on every call; chunks from the same document would falsely trigger it and get silently dropped.
18. **Never reimplement chunking** — v1.3: Reuse `_chunk_text()` from `tools/file_ops/actions/read_file.py`. See file tool INSTRUCTIONS.md rule #25.

### ALWAYS DO
16. **Always use `_mem()` for lazy loading** — Never import `core.memory_engine` at module level.
17. **Always handle `janitor` before `_mem()`** — Preserve the ChromaDB bypass optimization.
18. **Always thread `trace_id` through all results** — For observability and result correlation.
19. **Always validate `tags` and `tags_filter` with `_validate_tags()`** — MED-05 compliance is mandatory.
20. **Always return `fail()` with clear messages** — Unknown actions, missing params, validation errors.
21. **Always run `compileall` after editing tool files** — Verify syntax before running tests.
22. **Always run targeted tests (`tests/tools/memory/`) after changes** — Per-action coverage.
23. **Always reject empty `collections=[]`** — Prevent silent all-collections fallback.
24. **Always reject non-list `collections`** — `isinstance(collections, list)` guard prevents TypeError.
25. **Always catch exceptions in action handlers** — Wrap backend calls in `try/except` and return `fail()`.
26. **Always document `**kwargs` absorption trade-off** — If a handler accepts `**kwargs`, misspelled params are silently ignored. This is the established pattern. Document it.
27. **Always include `duration_ms` in responses** — v1.2: Performance monitoring for every action.
28. **Always force janitor errors to strings** — v1.2: Prevents JSON serialization failures.
29. **Always validate `threshold` range** — v1.2: Must be 0.0–1.0 for meaningful similarity search.
30. **Always use comma-only tag splitting** — v1.2: Multi-word tags are supported and preserved.
31. **Always validate `memory_type` before calling `store_chunked()`** — v1.3: The backend's `store_chunked()` does not check for procedural; the tool layer must reject `chunk=True` on `procedural` before calling the backend.
32. **Always pass `source_doc_id`/`chunk_index`/`chunk_count` in recall results** — v1.3: These fields let the LLM identify recall results as fragments of a larger document. Non-chunked memories return defaults (`""`, `None`, `0`).

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** v1.3 chunking initially tried to call `memory.store()` N times (once per chunk). Each call hit the two-layer dedup pipeline in `write_ops.execute_store()`. Chunks from the same document are semantically similar, so chunk #2 was flagged as a vector duplicate of chunk #1 and skipped. The document was silently truncated to 1 chunk.
> - **Why it matters:** The LLM has no way to know chunks were dropped — it sees `status: stored` for 1 chunk and assumes the whole document was saved. Recall returns a single vague chunk instead of the specific paragraph the LLM needs.
> - **Fix (v1.3):** New `execute_store_chunked()` function in `write_ops.py` that does hash dedup only (skips vector dedup). All non-duplicate chunks are batch-inserted in a single `col.add()` call. The tool layer routes `chunk=True` to `store_chunked()` instead of `store()`.

> - **What happened:** v1.3 initially allowed chunking on all 3 collections. On `procedural`, the vector dedup hit triggers the reinforcement path (increment `reinforcement_count` on the existing memory). For chunks, this is nonsensical — which chunk gets reinforced? The first? The closest? All of them?
> - **Why it matters:** Procedural reinforcement is a self-improving feedback loop. Feeding it chunk fragments would corrupt the reinforcement counts with meaningless increments, degrading the quality of the procedural rule ranking.
> - **Fix (v1.3):** The tool layer rejects `chunk=True` on `procedural` with a clear error before reaching the backend. Chunking is restricted to `semantic` and `episodic`.

> - **What happened:** The system prompt (`docs/system_prompts/system_prompt.md`) rule #6 said "~450 chars per entry to avoid timeout (-32001)". The actual config limit is 50KB (`MAX_MEMORY_BYTES=50000`). The 450-char claim was a pre-v1.0 transport issue that no longer exists.
> - **Why it matters:** The LLM was splitting memories unnecessarily at 450 chars, creating fragmented memories that recall poorly. The real constraint is recall payload size (5 results × 50KB = 250KB), not per-entry size.
> - **Fix (v1.3):** Updated the system prompt to reference the actual 50KB limit and point to `chunk=True` as the systematic solution for large documents.

> - **What happened:** v1.3 tool-layer chunking tests (`tests/tools/memory/test_store_chunking.py`) mock `_mem()` and patch `_chunk_text` — they pass reliably (107 tests). But the core-layer chunked tests (`tests/core/memory/test_write_ops_chunked.py`) run against the REAL persistent ChromaDB and hit 3 separate test-design issues on re-runs: (1) static text became hash duplicates on the second run, (2) `recall()` couldn't find short synthetic chunks in a large DB, (3) `store_semantic()` setup returned `skipped_duplicate` (vector dedup) and never stored the memory.
> - **Why it matters:** Tool-layer tests mock the backend, so they're deterministic. Core-layer tests use the real persistent ChromaDB, so they're sensitive to DB state across runs. AI editors writing core memory tests must account for this — the existing `test_write_ops.py` is the reference pattern.
> - **Fix (v1.3/V1.1 V4):** Core chunked tests now use: (1) UUID-suffixed text per run, (2) `col.get()` for metadata verification (not `recall()`), (3) `_direct_store()` helper for setup (bypasses dedup, syncs `_hash_cache`). All 3 lessons documented in `docs/core/memory/INSTRUCTIONS.md` anti-patterns section. See `tests/core/memory/test_write_ops_chunked.py` module docstring for the 3 design notes.

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
