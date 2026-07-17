<- Back to [Knowledge Graph Overview](../KGRAPH.md)

# 🛡️ AI KGraph Instructions

## ❌ NEVER DO

1. **Never use LLM for parsing** — AST parsing is deterministic by design. Never replace `ast.parse()` with LLM-based extraction.
2. **Never block the event loop** — AST parsing is CPU-bound. Always use `_AST_EXECUTOR` via `run_in_executor()`.
3. **Never remove LRU cache** — The `@lru_cache` prevents re-parsing unchanged files. Clear it with `clear_ast_cache()` only for testing or major refactors.
4. **Never share SQLite connections across threads** — Each thread gets its own connection. Thread-local connections are mandatory.
5. **Never bypass `_write_lock`** — All writes go through `_write_lock`. Never bypass it.
6. **Never increase `_CHECKPOINT_EVERY` without understanding disk implications** — The checkpoint every 100 writes prevents WAL file bloat.
7. **Never skip the fast path in hybrid validation** — Test index uses mtime + size (fast) then MD5 (slow). MD5 is expensive for large projects.
8. **Never remove files from `CRITICAL_PATHS` without explicit user approval** — These files have global impact and trigger full test suite.
9. **Never share graph data across projects** — Each project has its own `project_id` based on path hash. Project isolation is mandatory.
10. **Never crash the indexer on parse errors** — Broken Python files should return `frozenset()`, not crash. Use `try/except` around `ast.parse()`.
11. **Never create `.bak` files** — forbidden by project rules.
12. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
13. **Never skip `compileall` before `pytest`** — catches syntax errors early.

## ✅ ALWAYS DO

1. **Always use `GraphStore.close_all()` on shutdown** — v1.0: registered via `atexit` in `server.py`. Without this, SQLite WAL files may not checkpoint → potential data loss.
2. **Always use relative paths for AST cache keys** — v1.0: `parse_file_dependencies()` uses the original `file_path` (not resolved absolute) as the cache key. Cache hits survive project moves.

14. **Always use `ThreadPoolExecutor` for AST parsing** — CPU-bound work must not block the event loop.
15. **Always use `@lru_cache(maxsize=512)` for parsed dependencies** — Cache key must include `project_id` and content hash for cross-project safety.
16. **Always return `frozenset()` on parse errors** — `SyntaxError`, `RecursionError`, `MemoryError` must not crash the indexer.
17. **Always use WAL mode for SQLite** — `journal_mode=WAL` with `synchronous=NORMAL`.
18. **Always checkpoint every 100 writes** — `_CHECKPOINT_EVERY = 100`. Prevents WAL file bloat.
19. **Always use `_repair_wal_on_windows()` on startup** — Deletes stale WAL artifacts from unclean shutdowns.
20. **Always use atomic writes for test index** — Write to `.tmp`, then replace original.
21. **Always test with `tmp_path` for `.understand/` directories** — Isolated test directories prevent cross-test contamination.
22. **Always test with real `GraphStore` using `:memory:` SQLite** — In-memory databases are fast and isolated.
23. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
24. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
25. **Always update this doc** when adding components, changing schemas, or modifying hard limits.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-17. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for component details, [CHANGELOG.md](CHANGELOG.md) for version history.*
