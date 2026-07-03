<- Back to [Memory Backend Overview](../MEMORY.md)

# 🛡️ AI Instructions

### NEVER DO
1. **Never add logic to `core/memory_engine.py` or `store.py`** — Logic belongs in `write_ops.py`, `read_ops.py`, `scoring.py`, `maintenance.py`, etc.
2. **Never remove the `_write_lock` or double-check locking pattern** — Never lock `recall()` operations.
3. **Never remove the `store._hash_cache` synchronization** — Call `.discard()` on delete/prune to prevent ghost entries.
4. **Never return a blind `{"status": "skipped_duplicate"}`** — Always use the structured payload with `directive` and `matched_snippet`.
5. **Never skip procedural duplicates** — Always increment `reinforcement_count` inside the write lock.
6. **Never apply time-decay to `collection == "procedural"`** — Decay bypass is intentional.
7. **Never remove `ensure_not_cancelled(trace_id)` guards** — All write operations must check cancellation before mutating.
8. **Never validate tags in the backend** — Tag validation belongs in `tools/memory.py` before passing to the backend.
9. **Never add LLM calls to `_rewrite_query()`** — Query rewriting is model-free for speed.
10. **Never manually delete or merge procedural rules** — The background Diversity Enforcer handles this autonomously.
11. **Never prune `procedural` collection or memories tagged `"summary"`, `"critical"`, `"protected"`** — These are immune to automatic pruning.
12. **Never create `.bak` files** — Forbidden by project rules.
13. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
14. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
15. **Never print to stdout** — MCP stdio corruption. Return dicts only.
16. **Never skip `compileall` before `pytest`** — Catches syntax errors early.

### ALWAYS DO
17. **Always use `from core.memory_engine import memory`** — The facade is the only public API surface.
18. **Always thread `trace_id` through all operations** — For observability and cancellation.
19. **Always call `ensure_not_cancelled(trace_id)` before writes** — Prevents ghost mutations.
20. **Always use typed helpers (`store_episodic`, `store_semantic`, `store_procedural`)** — Clearer intent than raw `store()`.
21. **Always include `error_code` in `fail()` calls** — Every error response must include a structured code.
22. **Always run `compileall` after editing memory files** — Verify syntax before running tests.
23. **Always run targeted tests (`tests/core/memory/`) after changes** — 41 tests cover the full backend.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for API reference, [CHANGELOG.md](CHANGELOG.md) for version history.*
