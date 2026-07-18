<- Back to [Sleep & Learn Overview](../SLEEP_LEARN.md)

# 🛡️ AI Sleep & Learn Instructions

## ❌ NEVER DO

1. **Never bypass `llm.complete()` with raw HTTP calls** — Circuit breakers, rate limiters, and token budgets exist for a reason.
2. **v1.0 (Commit 4): This rule is SUPERSEDED.** With `SLEEP_LEARN_UNIFIED=true` (default), sleep_learn writes to the main `procedural` collection via `build_unified_metadata()`. The isolated `procedural_meta` collection is deprecated.
3. **Never read from `procedural_meta` during distillation** — Ouroboros prevention: the daemon must not reinforce its own output. **v1.0 (Commit 4): `procedural_meta` is deprecated/migrated; with `SLEEP_LEARN_UNIFIED=true` the daemon reads/writes the unified `procedural` collection, and ouroboros prevention is enforced via `source="sleep_learn_daemon"` filtering rather than collection isolation.**
4. **Never reduce the 60s distiller timeout** — Intentional for local model stability.
5. **Never put ChromaDB imports at module level** — Lazy loading prevents startup slowdown.
6. **Never import `core.tracer` or workflow engines from `sleep_learn/`** — Zero coupling: feedback reads JSONL logs directly.
7. **Never weaken the quality filters in `filters.py`** — Generic rules pollute the Planner prompt.
8. **Never lower `SLEEP_LEARN_MIN_CONFIDENCE` below 0.5** — Low thresholds produce noise.
9. **Never ignore `SLEEP_LEARN_INJECT_ENABLED`** — If disabled, return base prompt unchanged.
10. **Never create `.bak` files** — Forbidden by project rules.
11. **Never rewrite the entire file** — Surgical edits only. Preserve existing code exactly.
12. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
13. **Never print to stdout** — MCP stdio corruption. Return dicts only.
14. **Never skip `compileall` before `pytest`** — Catches syntax errors early.
15. **Never query `procedural_meta` when `SLEEP_LEARN_UNIFIED=true`** — v1.5 (Bug 1): the injector's `get_relevant_rules()` previously queried the legacy `procedural_meta` collection unconditionally AND the unified `procedural` collection — a true split-brain (rules appeared twice or the legacy read masked the unified read). Now the legacy query is gated behind `if not SLEEP_LEARN_UNIFIED:`. When `SLEEP_LEARN_UNIFIED=true` (default), ONLY the unified `procedural` collection (via `memory.recall(collections=["procedural"])`) is queried. The legacy path is dead code in default deployments — do not re-enable it.
16. **Never use `time.sleep()` in daemon loops — use `Event.wait()`** — v1.5 (Bug 4): `meta_learning.py run_forever()` was using `_time.sleep(1800)` unconditionally. `time.sleep` is globally mockable (tests patch it), which can cause daemons to either never sleep or sleep forever in test environments. `threading.Event().wait(timeout=1800)` is immune to `time.sleep` mocks and is the pattern already used in `sleep_learn/daemon.py`. Always use `Event.wait(timeout=...)` for daemon loop pauses.

## ✅ ALWAYS DO

15. **Always use `llm.complete()` for distillation** — Public API only; respects all global limits.
16. **v1.0 (Commit 4): With `SLEEP_LEARN_UNIFIED=true`, writes go to the main memory's `procedural` collection, not the isolated `sleep_learn_db`.** Physical isolation is deprecated; the unified rule schema (`core/memory_backend/rule_schema.py`) preserves provenance via `source` metadata.
17. **Always check `SLEEP_LEARN_ENABLED` before daemon operations** — Kill switch for the entire subsystem.
18. **Always validate rules with `is_quality_rule()` before storage** — Safety gates are mandatory.
19. **Always use `seen_ids` dedup in the injector** — O(n) hash set, not O(n²) scan.
20. **Always thread `trace_id` through all operations** — For observability and result correlation.
21. **Always run `compileall` after editing sleep_learn files** — Verify syntax before running tests.
22. **Always run targeted tests (`tests/core/sleep_learn/`) after changes** — Full coverage of the daemon.
23. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
24. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
25. **Always update this doc** when adding components, changing confidence thresholds, or modifying guardrails.
26. **Always gate background daemons on `tracker.try_acquire_background_slot()`** — v1.5 (Bug 4): `meta_learning.py run_forever()` now mirrors `sleep_learn/daemon.py` — it calls `tracker.try_acquire_background_slot(min_idle_seconds=300)` before running and `tracker.release_background_slot()` in a `finally` block. This prevents the meta-learner from running in test/short-lived sessions (where there's no real idle period) and avoids VRAM contention with user-facing calls. Any new background daemon MUST follow this pattern: acquire slot → run → release in `finally`.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-18 (v1.5: SLEEP_LEARN_UNIFIED gate enforced, Event.wait in daemon loops, background-slot gating). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [CHANGELOG.md](CHANGELOG.md) for version history.*
