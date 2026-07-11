<- Back to [Autocode Overview](../AUTOCODE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove TDD-first** — Test generation ensures code quality.
4. **Never remove debug loop** — Iteration catches edge cases.
5. **Never remove impact analysis** — Blast radius analysis prevents unintended side effects.
6. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
7. **Never create `.bak` files** — forbidden by project rules.
8. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
9. **Never skip `compileall` before `pytest`** — catches syntax errors early.
10. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`. Always pass `action="dispatch"` for LLM calls.
11. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).
12. **Never use `files_context` field** — It doesn't exist in `AutocodeState`. Use `_files_context()` helper.
13. **Never store `files_map` as `dict[str, FileSnapshot]`** — No node populates it. Use `modified_files` instead.
14. **Never import removed symbols in the facade** — [v1.1] The facade was broken for 2 versions because it imported `AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot` after they were removed from their source modules. When removing a symbol from `state.py`/`routes.py`/`git_ops.py`, grep the facade and remove the import + `__all__` entry too.
15. **Never call `.compile()` on an already-compiled graph** — [v1.1] `get_graph()` returns a `CompiledStateGraph` which has no `.compile()` method. Calling it crashes with `AttributeError`. Use `get_graph()` directly, or `build_graph().compile()` for a fresh compile.
16. **Never let `distill_memory` fail the workflow** — [v1.1] The code is already committed by the time distill_memory runs. A ChromaDB failure there must not flip a successful workflow to failed. Use `tracer.warning`, not `tracer.error`, and return `{}`.
17. **Never bypass `base.py`'s `run_workflow()` from the facade** — [v1.1] The facade delegates to `run_workflow("autocode")` for tracing, checkpointing, and timeout. Bypassing it (the old design) caused double trace creation and missing checkpoint support.
18. **Never put push / PR / merge logic in `node_commit` — use `node_publish`** — [v1.3] `node_commit` is local-only (calls `git(action="commit")` via `git_ops.py`). ALL remote operations (push, pr_create, pr_comment, pr_merge) live in `node_publish` via `github_ops.py`. Folding them would couple commit failure semantics with publish failure semantics and would force every autocode run to import the github tool even when only local git is needed. See ARCHITECTURE.md § "[v1.3] Design Decision Notes" #1.
19. **Never call GitHub API actions without `is_configured()`** — [v1.3] Every helper in `workflows/autocode_impl/github_ops.py` MUST call `_github_is_configured()` (wraps `tools.github_ops.client.is_configured()` in try/except) before any `github(action=...)` call. If GitHub is not configured (`GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` missing), log a `tracer.step` and return `False`/`None` — never raise. This is what makes the v1.3 integration safe to deploy with no `.env` changes.
20. **Never add a v1.3 integration flag that defaults ON** — [v1.3] All 6 new flags (`AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`) default OFF. With all flags OFF, autocode v1.3 is byte-for-byte behaviorally identical to v1.2. New integration flags MUST default OFF so existing installations are not surprised by remote API calls or auto-merges after upgrade. `# TODO(2.0):` Per-task overrides may relax this.
21. **Never block the debug loop on a swarm verdict** — [v1.3] Swarm debug (`AUTOCODE_SWARM_DEBUG=1`) is non-blocking by design. The fix is ALWAYS applied, regardless of confidence (HIGH/MEDIUM/LOW). LOW confidence surfaces as an optional PR comment (gated on `AUTOCODE_DEBUG_COMMENT_PR=1` + `state["pr_number"]`), NOT as a workflow block. Rationale: the debug loop already has `MAX_RETRIES`, stuck-detection routing, the `node_verify` gate, and the git branch as safety nets; blocking on a multi-LLM vote would add latency and a new failure mode without improving correctness. See ARCHITECTURE.md § "[v1.3] Design Decision Notes" #3. `# TODO(2.0):` `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` may relax this.
22. **Never call `github_ops.py` helpers from outside `nodes/`** — [v1.3] The helpers (`_github_pull`, `_github_push`, `_github_pr_create`, `_github_pr_comment`, `_github_pr_merge`, `_swarm_debug_consensus`) are private (underscore-prefixed) and intended to be called only from `nodes/branch.py`, `nodes/publish.py`, and `nodes/debug.py`. Other modules should call the `github()` / `swarm()` facades directly if they need remote operations. This keeps the lazy-import + `is_configured()` + `tracer.step` pattern in one place.
23. **Never mix `git_ops.py` and `github_ops.py` helpers in one node** — [v1.3] `git_ops.py` = local git (no network, no auth). `github_ops.py` = remote GitHub (requires `is_configured()`). Exception: `node_git_branch` calls BOTH (local `_git_create_branch` + optional remote `_github_pull`) — this is the ONLY sanctioned mixing point because pull happens immediately before branch creation. `node_publish` is remote-only. `node_commit` is local-only. If you find another node needing both, split it.

## ✅ ALWAYS DO

14. **Always return `dict` from nodes** — Not `AutocodeState`. Partial updates only.
15. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
16. **Always handle validation failure gracefully** — Invalid input should return error state, not crash.
17. **Always test `node_classify_task` with mode override** — Assert correct task_type regardless of LLM output.
18. **Always test `node_brainstorm` with KG files** — Assert merged files (currently broken).
19. **Always test `node_analyze_impact` with empty files_map** — Assert early return (currently broken).
20. **Always test `node_write_files` with patch** — Assert atomic write and no `.bak` files.
21. **Always test `node_run_tests` with missing test files** — Assert error state.
22. **Always test `node_verify` with missing ruff** — Assert `lint_passed=False` (currently `True`).
23. **Always test `node_git_commit` with no changes** — Assert skipped state.
24. **Always test `node_distill_memory` with missing hypothesis** — Assert graceful handling.
25. **Always test `node_create_skill` with invalid name** — Assert error state.
26. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.
27. **Always use `defense_notes` (plural)** — The state field is `defense_notes`, not `defense_note`.
28. **Always use `asyncio.to_thread()` for CPU-bound work** — AST parsing and file I/O blocks the event loop.
29. **[v1.3] Always wrap `github_ops.py` helper calls in the node's natural skip-conditions** — `node_publish` checks `status in {needs_clarification, failed, skipped}`, `verification_passed`, `dry_run`, AND `branch` is non-empty BEFORE calling any `_github_*` helper. Mirror this guard pattern in any future node that touches remote APIs — never call a remote helper unconditionally.
30. **[v1.3] Always use `tracer.step()` (not `tracer.error()`) for graceful-skip events in `github_ops.py`** — `is_configured()` returning `False` is NOT an error — it's the documented opt-out path. Same for `_github_push` returning `False` when push fails (the workflow continues). Use `tracer.error()` only for genuine unexpected exceptions (e.g., `ImportError` on `from tools.github import github`).
31. **[v1.3] Always lazy-import `tools.github` and `tools.swarm` inside the helper function** — `github_ops.py` mirrors the `git_ops.py` pattern: `from tools.github import github` is INSIDE each `_github_*` function, not at module top. This keeps `workflows.autocode_impl` importable even if `tools.github` is uninstalled or its deps are missing. Top-level imports of optional tools in workflow modules are forbidden (see deep_research's `search.py` for the rare sanctioned exception).
32. **[v1.3] Always log the swarm verdict in `state.swarm_verdict`** — When `_swarm_debug_consensus()` returns a non-`None` result, `node_systematic_debug` MUST set `swarm_verdict` in its return dict (not just `root_cause`/`fix`). This is what `node_publish._build_pr_body()` reads to surface confidence/agreement in the PR body, and what `node_publish` uses to decide whether to add the LOW-confidence warning. Skipping this field silently breaks the PR-comment-on-LOW flow.
33. **[v1.3] Always gate `AUTOCODE_DEBUG_COMMENT_PR` on `state["pr_number"]`** — The PR-comment-on-LOW-confidence flow in `node_systematic_debug` checks THREE conditions: `confidence == "LOW"` AND `cfg.autocode_debug_comment_pr` AND `state.get("pr_number")`. All three are required. Posting a PR comment when `pr_number` is 0 would call `github(action="pr_comment", number=0, ...)` which fails uselessly. The `pr_number` field is only set by `node_publish`, which runs AFTER the debug loop in the normal flow — so the LOW-confidence comment fires only on subsequent debug iterations AFTER the first PR has been opened.
34. **[v1.3] Always use `# TODO(2.0):` markers for v1.3 tech debt** — The 2.0 Review Notes section in CHANGELOG.md lists the known tech debt items from v1.3 (git_ops/github_ops split, node_publish single-node, debug statelessness, non-blocking swarm verdict, global config flags, hardcoded squash merge, non-blocking pull failure, swarm confidence thresholds, minimal PR body, no retry on push/PR failure). Any future edit that touches these areas MUST reference the corresponding `# TODO(2.0):` line in the source file.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `.bak` backup files were created on every file write (patch.py, write_files.py, helpers.py). This violated project rules and cluttered the repo with stale backups.
> - **Why it matters:** `.bak` files accumulate, confuse git status, and are unnecessary since git provides versioning. The project explicitly forbids `.bak` files.
> - **Fix:** Use atomic writes (tempfile.NamedTemporaryFile + os.replace) only. No `.bak` creation anywhere. Git is the backup.

> - **What happened:** `_git_snapshot()` called `git(action="snapshot")` which was removed from the git tool in the un-multiplex refactor. The call always failed silently.
> - **Why it matters:** The "pre-autocode snapshot" was supposed to be a safety net, but it never worked. Autocode ran without any snapshot protection.
> - **Fix:** Removed `_git_snapshot` entirely. The git branch itself is the safety net — if something goes wrong, `git checkout main` or `git revert` recovers. Future plan: add GitHub PR integration so autocode can create/fix PRs.

> - **What happened:** `files_map` was declared in `AutocodeState` and initialized to `{}`, but no node ever populated it. `node_analyze_impact` read it and found it empty, so impact analysis never ran.
> - **Why it matters:** Without impact analysis, autocode can't detect regressions or target specific tests. It always falls back to running the full test suite.
> - **Fix:** `node_write_files` now populates `files_map` with file snapshots (content_preview, md5, size) after writing files. `analyze_impact` will now actually run.

> - **What happened:** `node_analyze_impact` was declared `async def` but LangGraph `StateGraph.add_node` expects sync functions. The async node may fail silently or hang the graph.
> - **Why it matters:** Async-in-sync-graph is undefined behavior in LangGraph. The node may never execute, or may hang forever.
> - **Fix:** Converted to `def` (sync). Async calls (`parse_dependencies_from_string`, `get_targeted_tests`) are wrapped in `_run_async()` which creates a new event loop.

> - **What happened:** `node_brainstorm` merged `kg_files` into `files_update` but stored `state["files"]` (the original) instead of the merged result. Knowledge graph files were discarded.
> - **Why it matters:** KG context (relevant files from the dependency graph) was fetched but never made available to downstream nodes. The planner and executor never saw the KG files.
> - **Fix:** Store `files_update` (merged) instead of `state["files"]` (original).

> - **What happened:** `node_distill_memory` read `hypothesis` and `defense_note` (singular), but `node_systematic_debug` sets `root_cause` and `defense_notes` (plural). Both fields were always empty.
> - **Why it matters:** Procedural memory distillation never received root cause or defense notes — the most valuable debugging insights were discarded.
> - **Fix:** Changed to `root_cause` and `defense_notes` to match what debug.py actually sets. Same fix in `node_commit`.

> - **What happened:** The facade (`workflows/autocode.py`) was broken for 2 versions (v1.0.1 + v1.0.2). It imported 4 symbols (`AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot`) that were removed from their source modules during the v1.0.1/v1.0.2 refactors. No test caught it because all 106 tests imported directly from `autocode_impl/`, never from the facade.
> - **Why it matters:** `import workflows.autocode` raised `ImportError`. `run_workflow(workflow_type="autocode")` was also broken (the dispatcher imports from the facade). The entire autocode workflow was unreachable through its documented public API for 2 versions.
> - **Fix:** [v1.1] Removed the 4 dead imports. Added facade contract tests (`test_facade.py`) that import the facade and exercise `run_workflow("autocode")`. This guards against silent facade breakage in future refactors.

> - **What happened:** `base.py`'s autocode branch did `graph = build_graph(); result = graph.invoke(state)`. But `build_graph()` returns an uncompiled `StateGraph`, which has no `.invoke()` method. This would crash with `AttributeError`.
> - **Why it matters:** Even if the facade imported correctly, `run_workflow("autocode")` would still crash at the invoke step.
> - **Fix:** [v1.1] `base.py` now uses `invoke_with_timeout(initial_state)` which calls `get_graph()` (returns compiled) internally. Also wires `cfg.autocode_graph_timeout`.

> - **What happened:** `route_after_write_files` only routed `fix`/`fix_error`/`refactor`/`improve`/`feature` to `node_analyze_impact`. `audit` and `edit` fell through to `node_verify`, skipping impact analysis entirely.
> - **Why it matters:** For `audit` especially, impact analysis IS the audit — skipping it made the audit task type misleading. For `edit`, the docs say it's "heavier than fix" but it skipped TDD, which was inconsistent.
> - **Fix:** [v1.1] Added `audit` and `edit` to the impact-analysis path. Found by cross-LLM review (DeepSeek, Mistral).

> - **What happened:** [v1.3] The autocode workflow had NO git push / PR / merge integration. Branch creation (`node_git_branch`) and commit (`node_commit`) were both local-only via `tools.git`. The A1/A2 research reports confirmed this — and flagged that `docs/tools/github/CHANGELOG.md` had a stale Phase 3 row incorrectly claiming "autocode's branch node uses raw `subprocess.run(['git', 'push', ...])`" (it didn't).
> - **Why it matters:** Operators running autocode in CI / on a remote server had to manually push branches and open PRs after every run. The github tool (with `push`, `pull`, `pr_create`, `pr_comment`, `pr_merge` actions) existed but was not wired in.
> - **Fix:** [v1.3] Added `node_publish` (between `node_commit` and `node_distill_memory`) and the `workflows/autocode_impl/github_ops.py` helper module. All operations are gated on config flags (`AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`) and graceful-skip via `is_configured()`. With all flags OFF (the default), autocode behaves identically to v1.2.

> - **What happened:** [v1.3] The `branch` field was read by `nodes/branch.py` (line 55: `if state.get("branch"):`) and set by `nodes/plan.py` since v1.0, but was NOT declared in the `AutocodeState` TypedDict. This was a TypedDict drift — runtime worked (TypedDict with `total=False` doesn't enforce keys), but type-checkers and IDE autocomplete missed it.
> - **Why it matters:** TypedDict drift is a maintenance hazard — future editors reading `state.py` wouldn't know `branch` is a valid key, and might add a conflicting field with the same name.
> - **Fix:** [v1.3] Added `branch: str` declaration to `AutocodeState` (`state.py` line 94) and the default in `_default_state()` (`state.py` line 154). Pure type-safety fix — no runtime behavior change.

> - **What happened:** [v1.3] The debug node (`node_systematic_debug`) was single-LLM only — one provider proposed a `{root_cause, defense_notes, fix}` and the workflow applied it. There was no cross-model verification, so a single confused model could send the debug loop in circles.
> - **Why it matters:** Multi-model verification ("swarm") is the strongest signal we have for catching hallucinated root causes. Without it, autocode trusts whatever the executor LLM says.
> - **Fix:** [v1.3] Added optional swarm debug (`AUTOCODE_SWARM_DEBUG=1`) using a 2-run pattern: `swarm(consensus)` to propose, `swarm(vote)` to verify. Confidence is mapped from vote agreement: `unanimous → HIGH`, `majority → MEDIUM`, `split`/`disagreement` → `LOW`. The fix ALWAYS applies (non-blocking) — LOW confidence surfaces as an optional PR comment, not a workflow block. Rationale: blocking on a multi-LLM vote would add latency without improving correctness, given the debug loop's existing safety nets (`MAX_RETRIES`, stuck-detection, `node_verify` gate, git branch). Falls back to single-LLM debug if swarm is off / unavailable / fails.

---

*Last updated: 2026-07-10 (v1.3 — added NEVER DO #18-23 and ALWAYS DO #29-34 for node_publish / github_ops.py / swarm debug / config flags; added v1.3 anti-patterns). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
