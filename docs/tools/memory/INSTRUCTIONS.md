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

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
