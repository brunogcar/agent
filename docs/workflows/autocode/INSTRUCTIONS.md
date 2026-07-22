<- Back to [Autocode Overview](../AUTOCODE.md)

# 🛡️ AI Instructions

Editing rules for the autocode subsystem. NEVER DO and ALWAYS DO are 1-line each. Anti-Patterns (restored v3.8) describe bad patterns with why + fix. Deferred roadmap items live in [CHANGELOG.md](CHANGELOG.md).

---

## ❌ NEVER DO

1. Never mutate state in-place — LangGraph does not deep-copy; return partial update `dict`s only.
2. Never spread `**state` in a node return — return only changed keys (`{**state, "k": v}` clobbers).
3. Never remove TDD-first — test generation ensures code quality.
4. Never remove the debug loop — iteration catches edge cases.
5. Never remove impact analysis — blast radius prevents unintended side effects.
6. Never use `print()` to stdout — MCP stdio corruption; use `tracer.step()` for logging.
7. Never create `.bak` files — forbidden by project rules.
8. Never rewrite an entire file — surgical edits only; preserve existing code exactly.
9. Never skip `ruff --select E999` before pytest — catches syntax errors early (saves ~30s).
10. Never call `agent()` without `action="dispatch"` — the facade requires `action`.
11. Never return `None` from LangGraph nodes — return a `dict` (even `{}`).
12. Never use `files_context` field — doesn't exist; use `_files_context()` helper.
13. Never store `files_map` outside `files_state` — use `modified_files`.
14. Never import removed facade symbols (`AGENT_ROOT`, `route_after_brainstorm`, `_git_snapshot`) — run facade tests after refactor.
15. Never call `.compile()` on an already-compiled graph — use `get_graph().invoke(state)` directly.
16. Never let `distill_memory` fail the workflow — code is already committed; use `tracer.warning`.
17. Never bypass `base.py`'s `run_workflow()` from the facade — skips tracing, checkpointing, timeout.
18. Never put push / PR / merge logic in `node_commit` — `node_commit` is local-only.
19. Never call GitHub API actions without `is_configured()` — every `vcs_ops.py` helper MUST call `_github_is_configured()`.
20. Never add an integration flag that defaults ON — all 12 integration flags default OFF.
21. Never block the debug loop on a swarm verdict — LOW surfaces as PR comment, not a block.
22. Never call `vcs_ops.py` helpers from outside `nodes/` — external code MUST call `tools.github` / `tools.git` / `tools.swarm`.
23. Never mix local and remote VCS helpers — `_git_*` = local; `_github_*` = remote (requires `is_configured()`).
24. Never use raw `json.loads()` on LLM output — use `_parse_json()` (delegates to `core.json_extract`).
25. Never write LLM-generated paths to disk without `_is_path_safe()` — `node_validate_input` only covers user-supplied paths.
26. Never re-add `node_write_files_with_flag_reset` — dead code (registered, never wired).
27. Never re-add `route_after_analyze_impact` — always returned `"node_run_tests"`; use a direct edge.
28. Never re-add `mermaid.py`, `test_mapper.py`, or `test_runner.py` — all three were unused.
29. Never call `tracer.error()` with 2 args — signature is `tracer.error(trace_id, category, message)` (3 args).
30. Never assume `state["branch_name"]` is populated — `node_write_plan` writes `vcs.branch`; use `branch`.
31. Never use `s["label"]` on plan steps — LLM plans aren't guaranteed to label every step; use `s.get("label", "step")`.
32. Never re-add legacy flat-field mirrors — sub-states are the ONLY storage (v3.0).
33. Never use `state.get()` for sub-state fields — returns `None`; use accessors.
34. Never wire the backward-compat wrappers (`node_write_files`, `node_verify`, `node_publish`) into the graph — NOT wired.
35. Never patch `_call(...)` on backward-compat wrappers in tests — patch `nodes.llm_review._call`.
36. Never repeat a failed debug approach — last 5 entries are injected as `PRIOR DEBUG ATTEMPTS (do NOT repeat these)`.
37. Never wire `node_summarize_context` as a wrapper or skip it — fully-wired active node; skipping causes unbounded `debug_history`.
38. Never call `helpers._write_files()` — DELETED in v2.0; use split nodes.
39. Never hand-roll what the stdlib ships — check rung 3 of the Lazy Dev ladder first.
40. Never enable more than ONE of `AUTOCODE_SWARM_DEBUG` / `AUTOCODE_PARALLEL_SUBAGENT_DEBUG` / `AUTOCODE_SUBAGENT_DEBUG` — mutually exclusive. Priority order if multiple are set: swarm → parallel subagent → single subagent → single-LLM.
41. Never write flat-field mirrors in node returns — write sub-state only via RMW (`{"files_state": current_files}` not `{"modified_files": [...]}`).
42. Never assume `input_files` exists in `files_state` — removed in v3.0; readers use core `files` flat field directly.
43. Never skip the `ruff --select E999` pre-check in `node_run_pytest` (v3.1 #41) — non-fatal if ruff missing.
44. Never disable `MAX_TASK_LENGTH = 2000` in `node_validate_input` (v3.1 #42) — entry gate against LLM token waste.
45. Never call `_call()` without `trace_id=tid` (v3.1.2 P1) — retry-exhaustion errors are unattributed otherwise.
46. Never write an empty skill file (v3.1.2 P1) — try fallback keys `skill_file` → `skill_code` → `code`.
47. Never use top-level `kgraph` imports in autocode nodes — use lazy imports (v3.2 P0-1).
48. Never return `None` from `_git_commit` for errors — return structured dict `{"committed": bool, "sha": str, "reason": str}` (v3.2 P1-5).
49. Never use the sync-pause pattern for HiTL — use async-checkpoint-resume (v3.4 #38).
50. Never wire `node_publish` / `node_verify` / `node_write_files` into the graph — backward-compat wrappers (NOT wired).
51. Never assume `automated_checks_passed` defaults to `True` — default is `False` (v3.2 P0-3).
52. Never add a debug-chain flag without updating NEVER DO #40.
53. Never assume `tdd_iteration` is reset by `node_swarm_fallback` — it resets both `tdd.status` AND `tdd.iteration` (v3.1.1).
54. Never swallow HiTL checkpoint-save failures silently (v3.11 B2) — was: `except Exception: pass` → returned `awaiting_approval` as if the pause succeeded → resume found no checkpoint → full restart, potentially producing a different implementation than reviewed. Now returns `status=hitl_checkpoint_failed` so `route_after_hitl_gate` routes to END.
55. Never let the debug LLM-dispatch paths (swarm/parallel-subagent/single-subagent) skip the `is_cancellation_requested()` check (v3.11 B5) — in-flight `swarm()`/`agent()` calls outlive the graph deadline if not checked. The v3.6 "≤1s zombie linger" only covers subprocess calls; LLM dispatches need their own check.

---

## ✅ ALWAYS DO

1. Always return `dict` from nodes — not `AutocodeState`; partial updates only.
2. Always pass `trace_id` to every `tracer.*` call — observability requires trace correlation.
3. Always handle validation failure gracefully — invalid input returns error state, not crash.
4. Always use `defense_notes` (plural) — the state field is `defense_notes`, not `defense_note`.
5. Always use `asyncio.to_thread()` for CPU-bound work — AST parsing and file I/O block the event loop.
6. Always wrap `vcs_ops.py` calls in the node's natural skip-conditions (`status`, `verification_passed`, `dry_run`).
7. Always use `tracer.step()` (not `tracer.error()`) for graceful-skip events in `vcs_ops.py` — `is_configured()` returning `False` is the documented opt-out.
8. Always lazy-import `tools.github` and `tools.swarm` inside the helper function — not at module top.
9. Always log the swarm verdict in `state["debug"]["swarm_verdict"]` when `_swarm_debug_consensus()` returns non-`None`.
10. Always gate `AUTOCODE_DEBUG_COMMENT_PR` on `state["vcs"]["pr_number"]` (LOW confidence + flag + pr_number).
11. Always use `_parse_json()` for LLM JSON output — delegates to `core/json_extract.py`.
12. Always validate LLM-generated paths with `_is_path_safe()`.
13. Always include `trace_id` suffix in branch names — `autocode/{slug}-{tid_suffix}` where `tid_suffix = tid.replace("-", "")[:8]`.
14. Always use atomic writes (`tempfile` + `os.replace`) for skill files.
15. Always handle `tdd_status="stuck"` in the verify chain — routes to verify, skipping the doomed debug loop.
16. Always skip `pytest` when no test files exist — check `tests_dir.exists() or test_file.exists()` first.
17. Always scope `ruff check` to `modified_files` only — `workspace_root` is slow and surfaces false failures.
18. Always align prompt field names with state field names (`root_cause` + `defense_notes` plural).
19. Always use accessor functions for sub-state reads — `_get_tdd`, `_get_impact`, `_get_memory`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_files`, `_get_plan`.
20. Always delegate LLM JSON parsing to `core/json_extract.py` — `extract_json`, `extract_json_array`, `extract_first_json`.
21. Always import the split nodes directly, not the wrappers.
22. Always remember `_build_pr_body(state)` lives in `create_pr.py` (Phase 3.3 move).
23. Always remember `_is_path_safe(base_path, rel_path)` lives in `apply_patches.py` (Phase 3.1 move).
24. Always use the 4-phase debug structure — `DEBUG_SYSTEM` requires `phase` in JSON output (enum enforced by `_DEBUG_JSON_SCHEMA`).
25. Always honor the architecture-question threshold (3+ consecutive failures) — bails with `tdd_status="max_retries_exceeded"`; different from #39 stuck detection.
26. Always write `debug_summary` to `TDDState` via RMW in `node_summarize_context`.
27. Always import VCS functions from `vcs_ops.py`, not `git_ops` / `github_ops` (thin re-export wrappers).
28. Always follow the 7-rung Lazy Dev ladder before writing code — YAGNI → reuse → stdlib → native → installed dep → one line → minimum code.
29. Always use the `ponytail:` comment convention for deliberate simplifications — NOT for tech debt.
30. Always isolate subagent context — never pass `state` wholesale to `agent(action="subagent")`.
31. Always let `node_validate_input` strip control chars — don't bypass by writing to `state["task"]` directly.
32. Always prefer `node_swarm_fallback` over hard `status="failed"` when `AUTOCODE_SWARM_DEBUG_FALLBACK=1`.
33. Always pass `trace_id=tid` to `_call()` — extract `tid = state.get("trace_id", "")` at top of node.
34. Always smoke-test skill files with `importlib` after writing — catches missing deps / circular imports / top-level raises that `ast.parse()` misses.
35. Always clear `last_test_error` when resetting the debug loop — without it, stuck-detection short-circuits the fresh fix attempt (v3.2 P0-2).
36. Always handle `test_code` as `list[str]` in consumers — join with `"\n\n"` before slicing (v3.2 P0-4).
37. Always run validation in `dry_run` paths — `patch_errors` MUST be populated (v3.2 P0-5).
38. Always use `cfg.sandbox_timeout` for subprocess timeouts — never hardcode `120` or `30`; use `_remaining_timeout(cfg.sandbox_timeout)` (v3.2 P1-3).
39. Always use `_should_skip_node(state)` for status checks (v3.3 #58).
40. Always use the async-checkpoint-resume pattern for HiTL (v3.4 #38) — `save_checkpoint` + `{"status": "awaiting_approval"}` + route to END.
41. Always use parallel subagent debug for complex multi-hypothesis bugs (v3.5 F1) — `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`.
42. Always wrap `subprocess.run(...)` in cancellation-aware helpers (v3.6 #35) — pre-check + `_remaining_timeout(default)` + post-check.
43. Always use `task_type="audit"` for read-only codebase audits (v3.7 F7) — bypasses TDD.
44. Always run per-node unit tests when adding/changing a node (v3.8 #57) — pattern is `tests/workflows/autocode/test_<node_name>.py`.
45. Always update this doc when adding nodes, routing logic, config flags, or error handling.
46. Always use `dict(state.get("<sub_state>", {}))` for RMW.
47. Always copy list entries before mutating — `[dict(e) for e in history]`.
48. Always mark `[v<version>]` in source comments + docs when shipping a versioned change.
49. Always check `is_configured()` before any GitHub API call — graceful-skip on missing env vars.
50. Always prefer `chonkie.SentenceChunker` (soft dep) for `debug_history` compression — JSON fallback.
51. Always use `cfg.autocode_graph_timeout` (or `_TASK_TYPE_TIMEOUTS[task_type]` when `AUTOCODE_ADAPTIVE_TIMEOUT=1`).
52. Always populate `parallel_verdicts` (ALL verdicts) alongside the winner in `subagent_verdict`.
53. Always pass the resolved per-run `timeout` to `set_graph_start_time(timeout)` (v3.11 B1) — was: only stored the start time, so `_remaining_timeout()` read the static `cfg.autocode_graph_timeout` (300s) instead of the adaptive timeout (900s for feature) → spurious 1-second subprocess timeouts at 400s elapsed.
54. Always surface a `truncated` flag + `files_total` when audit scan caps the file list (v3.11 B3) — dead-code claims are only valid when the full file set was scanned for imports. Use `all_scanned_files` param in `_find_dead_code` so importers in unscanned directories aren't missed.
55. Always document the git_ops.py aliases as "name-only" not "backward-compat" (v3.11 B7 / git tool v1.3) — the signature changed (project_root first); in-tree callers updated, but external callers using `_git_commit(message, tid, project_root)` must update to `_git_commit(project_root, message, target_file, tid)`.

---

## 🚫 Anti-Patterns

Patterns that have bitten production. Each entry: bad pattern + why + fix. NOT duplicates of NEVER DO rules — these describe the shape of the mistake, not a single rule.

### AP-1: Flat-field clobbering in node returns

**Bad:** `return {"tdd": {"status": "max_retries_exceeded"}}` clobbers every other `tdd` field (LangGraph replaces dict values, doesn't deep-merge).
**Fix:** Read-modify-write (RMW) — `current_tdd = dict(state.get("tdd", {}))`; `current_tdd["status"] = "..."`; `return {"tdd": current_tdd}`. For list fields: `history = [dict(e) for e in history]` before appending. See [SUBSTATE.md](SUBSTATE.md) § RMW Pattern.

### AP-2: Top-level `kgraph` imports in autocode nodes

**Bad:** `from core.kgraph.queries import get_callers` at module top of `nodes/plan.py` or `nodes/debug.py`.
**Why:** `core.kgraph` initializes `tree_sitter_languages` on import; missing/failing grammar = entire module fails to import = whole autocode graph down (since `build_graph()` imports every node). Shipped in v3.1, fixed v3.2 P0-1.
**Fix:** Lazy-import inside the function (`helpers._blast_radius_warning()` is the canonical pattern). Same rule for any `tree_sitter_languages`-dependent module.

### AP-3: Hardcoded subprocess timeouts

**Bad:** `subprocess.run([...], timeout=120)` for pytest, `timeout=30` for ruff, inside `node_run_pytest` / `node_run_lint`.
**Why:** Bypasses operator's `cfg.sandbox_timeout` tuning — on a slow CI runner, the operator bumps the config to 600s but the node still hard-fails at 120s with no way to fix without code edits. Shipped pre-v3.2 P1-3.
**Fix:** Read `cfg.sandbox_timeout` for the default, cap at remaining graph budget via `_remaining_timeout(cfg.sandbox_timeout)` (v3.6 cancellation-aware). Smaller constants for sub-timeouts (e.g., ruff E999 pre-check uses 10s) are fine.

### AP-4: Test mocks using wrong JSON keys

**Bad:** `test_create_skill.py` mocks `_call(...)` returning `{"skill_code": "..."}` while production reads `data.get("skill_file", "")`. Tests silently pass (empty-file rejection fires, test never asserts on `skill_created=False`); the production bug (LLM returning content under `skill_code`, silently writing empty file + `skill_created=True`) shipped for 4 months before v3.1.2 P1 caught it.
**Fix:** Tests MUST use the same JSON keys production reads. When adding an LLM-returned field, audit prompt + node + test together — all three must agree. v3.1.2 added fallback keys (`skill_file` → `skill_code` → `code`) as defense-in-depth.

### AP-5: Sync-pause for HiTL (holding worker threads)

**Bad:** Inside `node_hitl_gate`, block on `event.wait()` until the MCP client responds with approval.
**Why:** The gateway's worker pool assumes stateless workers (one worker per request). A sync-paused worker consumes a worker slot for the entire review duration (could be hours) — under load, the pool exhausts and the gateway stops serving. Considered and rejected for v3.4 #38.
**Fix:** Async-checkpoint-resume — `save_checkpoint(tid, "hitl", state)` + `{"status": "awaiting_approval"}` + `route_after_hitl_gate` → END. Operator resumes with `run_workflow("autocode", goal="...", resume=True, hitl_approved=True)`. Adds one round-trip but preserves the worker pool. Checkpoint failure is non-fatal.

---

*Last updated: 2026-07-22 (v3.11.1).*
