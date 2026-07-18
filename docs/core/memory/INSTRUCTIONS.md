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
17. **Never run vector dedup on chunked stores** — v1.1: Chunks from the same document are semantically similar and would falsely trigger the vector dedup pipeline. `execute_store_chunked()` does hash-dedup-only. Do not add vector dedup to `execute_store_chunked()`.
18. **Never call `execute_store()` for chunks** — v1.1: Use `execute_store_chunked()` instead. The standard `execute_store()` runs two-layer dedup on every call; chunks would be silently dropped. See `write_ops.py` block comment for full rationale.
19. **Never write `confidence_score` without also writing `confidence`** — v1.5 (Bug 2): `confidence` is the canonical field per `rule_schema.py`; `confidence_score` is a legacy mirror kept for pre-migration readers. `feedback.py update_rule_confidence()` previously wrote only `confidence_score`, so the injector's canonical `meta.get("confidence", ...)` read saw STALE data (boosts/penalties never reached the Planner). Always write BOTH: `meta["confidence"] = new_conf; meta["confidence_score"] = new_conf`. When reading, read canonical first: `meta.get("confidence", meta.get("confidence_score", 0.8))`.
20. **Never use non-canonical tag prefixes** — v1.5 (Bugs 3, 7): `validate_tags()` only accepts the 5 canonical prefixes — `source:`, `domain:`, `category:`, `status:`, `evidence:`. Bare tags like `"meta-learned,auto-distilled"` and non-canonical prefixes like `type:{fact['type']}` fail validation and would be rejected at write time once the schema is enforced. Use `source:meta_learner,category:auto_distilled` and `category:{fact['type']}` instead. (`type:` is NOT in `VALID_TAG_PREFIXES` — common mistake.)

### ALWAYS DO
17. **Always use `from core.memory_engine import memory`** — The facade is the only public API surface.
18. **Always thread `trace_id` through all operations** — For observability and cancellation.
19. **Always call `ensure_not_cancelled(trace_id)` before writes** — Prevents ghost mutations.
20. **Always use `generate_trace_id()` (not `new_trace()`) for error-only functions** — The 4 `execute_*` functions in `maintenance.py` only call `tracer.error()` — no `step`/`finish`. Using `tracer.new_trace()` introduces side effects (file I/O, stderr print, `_TraceStore` insert) that can interfere with ChromaDB query timing. `generate_trace_id()` returns a unique 12-char hex ID with ZERO side effects — error events still get a correlation ID, and `tracer.error` still writes to the JSONL log via `_writer.write`. Use `new_trace()` only when you also call `step()`/`finish()` (full trace lifecycle).
20. **Always use typed helpers (`store_episodic`, `store_semantic`, `store_procedural`)** — Clearer intent than raw `store()`.
21. **Always include `error_code` in `fail()` calls** — Every error response must include a structured code.
22. **Always run `compileall` after editing memory files** — Verify syntax before running tests.
23. **Always run targeted tests (`tests/core/memory/`) after changes** — 41 tests cover the full backend.
24. **Always call `validate_tags()` + `normalize_tags()` before `memory.store()`** — v1.5 (Bug 3): `meta_learning.py` was constructing tags as a raw string (`"meta-learned,auto-distilled"`) and passing them straight to `memory.store()`, bypassing the schema. Now it calls `normalize_tags(tags, source="meta_learner")` then `validate_tags(normalized_tags)` and skips the store on validation failure. This catches non-canonical prefixes (see NEVER DO #20) at write time rather than letting them silently land in ChromaDB.
25. **Always produce `reasoning` in distillation** — v1.5 (Bug 5): the injector reads `meta.get("reasoning", "")` and surfaces it in the Planner prompt so future workflows understand WHY a rule holds. If the distiller doesn't emit `reasoning`, the injector shows an empty reason and the rule loses explanatory context. `procedural/distill.py` now (a) includes `reasoning: {type: string, maxLength: 500}` in `_DISTILL_JSON_SCHEMA` properties + required, (b) asks for it in the system prompt, and (c) threads it through `store_procedural(reasoning=...)` → `_store()` → `execute_store()` → `build_unified_metadata()`. End-to-end populated.
26. **Always use `generate_trace_id()` for error-only functions, `tracer.new_trace()` for full trace lifecycle** — v1.5 (Bugs 1, 2 bonus): the v1.4 rule (#19 above) fixed `maintenance.py`; v1.5 extends the SAME pattern to `sleep_learn/injector.py` (error path: literal `"daemon"` → `generate_trace_id()`) and `sleep_learn/feedback.py` (full cycle: literal `"daemon"` → `tracer.new_trace("sleep_learn", goal="feedback cycle")`). The distinction: `generate_trace_id()` returns a unique 12-char hex ID with ZERO side effects (no file I/O, no stderr, no `_TraceStore` insert) — use it when the function only calls `tracer.error()`. `tracer.new_trace()` starts a full trace (writes to JSONL, prints, inserts to store) — use it when the function also calls `step()`/`finish()`. Never reuse a literal string like `"daemon"` as a trace_id — it collides across cycles.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** v1.1 chunking initially tried to reuse `execute_store()` N times (once per chunk). Each call runs two-layer dedup (hash + vector). Chunks from the same document are semantically similar, so chunk #2 was flagged as a vector duplicate of chunk #1 and skipped. The document was silently truncated to 1 chunk.
> - **Why it matters:** The caller sees `status: stored` for 1 chunk and assumes the whole document was saved. Recall returns a single vague chunk instead of the specific paragraph needed.
> - **Fix (v1.1):** New `execute_store_chunked()` function that does hash-dedup-only (skips vector dedup). All non-duplicate chunks are batch-inserted in a single `col.add()` call. The tool layer routes `chunk=True` to `store_chunked()` instead of `store()`.

> - **What happened:** v1.1 `META_FIELDS` in `constants.py` was initially thought to be an enforced schema. Investigation revealed it is documentation-only — no code imports or enforces it. ChromaDB accepts arbitrary key-value pairs in metadatas.
> - **Why it matters:** AI editors might think adding a field to `META_FIELDS` is sufficient to “register” it. The real registration is writing the field in the `metadatas` dict of `col.add()` / `col.update()` calls.
> - **Fix (v1.1):** Added a NOTE comment to `META_FIELDS` clarifying it is documentation-only. The 3 new chunk fields (`source_doc_id`, `chunk_index`, `chunk_count`) are written by `execute_store_chunked()` and read by `execute_recall()` — the `META_FIELDS` list is just a reference for AI editors.

> - **What happened:** v1.1 chunked store tests used `memory.store_semantic()` for setup (to seed a pre-existing memory). `store_semantic()` runs two-layer dedup (hash + vector). Even with a unique UUID marker in the text, vector dedup can flag it as semantically similar to an existing memory and return `skipped_duplicate` — meaning the memory was NEVER STORED. The test then failed because `col.get()` couldn't find the memory by `text_hash`.
> - **Why it matters:** Tests that need a pre-existing memory for setup cannot rely on `store_semantic()` — it's non-deterministic (vector dedup outcome depends on DB state). The existing `test_write_ops.py` sidesteps this by accepting `status in ("stored", "skipped_duplicate")`, but chunked tests need exact stored/skipped counts and can't tolerate setup skips.
> - **Fix (v1.1 V4):** Tests now use a `_direct_store()` helper that calls `col.add()` directly (bypassing `execute_store()` and its dedup) and manually syncs `store._hash_cache`. This guarantees the memory is in the DB with its hash in the cache. Documented in the test module docstring as design note #3.

> - **What happened:** v1.1 chunked store tests used static text ("ChunkAlpha_0: ...") for chunk content. The persistent ChromaDB at `memory_db/` retains data between runs. On the second test run, the hash guard caught the chunks as exact duplicates of the first run → `skipped_duplicate` instead of `stored` → count assertions failed.
> - **Why it matters:** Core memory tests run against the REAL persistent ChromaDB (not an in-memory mock). Any static test text becomes a duplicate on re-run. The existing `test_write_ops.py` uses fixed marker words but accepts both `stored` and `skipped_duplicate` outcomes — chunked tests can't do that.
> - **Fix (v1.1 V3):** Tests now append a UUID hex suffix (`uuid.uuid4().hex[:8]`) to every chunk text and trace_id. Text is unique per run → never a hash duplicate → always `stored`. Documented in the test module docstring as design note #1.

> - **What happened:** v1.1 chunked store tests used `memory.recall()` to verify that stored chunks had correct metadata. Recall uses vector similarity + fetch limits (`fetch_k = max(top_k * multiplier, 15)`). In a persistent DB with hundreds of memories from prior test runs, short synthetic chunks don't reliably rank in the top-K results.
> - **Why it matters:** Tests that depend on recall returning a specific chunk are flaky — they pass when the DB is small but fail as it grows. The existing `test_write_ops.py` uses `col.get(ids=[...])` for metadata verification (deterministic).
> - **Fix (v1.1 V2):** Tests now use `col.get()` (direct ChromaDB access, returns everything or filters by metadata) for all metadata verification. `recall()` is only used to test field PRESENCE in the result dict, not specific chunk retrieval. Documented in the test module docstring as design note #2.

---

*Last updated: 2026-07-18 (v1.5 post-merge cleanup: confidence mirror, canonical tags, reasoning field, trace_id discipline). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for API reference, [CHANGELOG.md](CHANGELOG.md) for version history.*
