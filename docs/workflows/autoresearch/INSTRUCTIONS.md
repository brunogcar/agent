<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 🛡️ AI Instructions

Rules for AI agents editing autoresearch code (same conventions as `autocode/INSTRUCTIONS.md`). Each rule is one line — when in doubt, read the source file referenced.

## ❌ NEVER DO

1. Never mutate state in-place — return partial update `dict`s (LangGraph doesn't deep-copy).
2. Never spread `**state` — return only the changed keys, never `{**state, "key": "value"}`.
3. Never remove the `log → propose` loop back-edge (v1.3 P0-1 — was `decide → propose`) — the loop is evolutionary by design.
4. Never skip the `results.tsv` ledger append in `node_log` — operators `tail -f` it while the loop runs.
5. Never modify `target_file` outside `node_modify._atomic_write` (`tempfile.mkstemp` + `os.fsync` + `os.replace`).
6. Never `print()` to stdout — use `tracer.step()` / `tracer.warning()` / `tracer.error()` (MCP stdio corruption).
7. Never create `.bak` files — git is the backup (every keep committed; every discard is `git reset --hard HEAD`).
8. Never return `None` from a LangGraph node — always a `dict` (even empty `{}`).
9. Never call `agent()` directly outside `node_propose._call_planner` — bypasses the 3× retry loop (v1.3 P1-2). Uses `agent(action="subagent", role="planner")`; NO `_call()` fallback.
10. Never use raw `json.loads()` on LLM output — use `core.json_extract.extract_json()` (markdown fences, partial JSON).
11. Never call the `git` tool from `node_decide` — use raw `subprocess.run(["git", ...])` (bypasses tracing noise). The `git` tool is fine for `node_setup._git_create_branch` (called once).
12. Never treat equality as an improvement — `_is_improvement` returns `False` when `new == best` (discourage no-op changes).
13. Never reset `current_best` on discard — `node_decide` updates it ONLY on keep.
14. Never write the `results.tsv` header on resume — `node_setup` checks `Path(results_path).exists()` first.
15. Never cap `experiment_history` below 20 — `_format_history` shows the most recent 20 (underlying cap is 100, v1.3 P2-3).
16. Never run experiments without `time_budget` — `node_run_experiment` MUST pass `timeout=time_budget` to `subprocess.run`.
17. Never forget `os.fsync` before `os.replace` in `_atomic_write` — without it, a power loss after rename may leave a zero-byte file.
18. Never use `shell=True` in subprocess calls — explicit list args only (no shell injection risk).
19. Never re-add `_extract_metric` to `setup.py` or `evaluate.py` — shared helper is `helpers.extract_metric` (v1.2.1).
20. Never re-add `_run_experiment_subprocess` to `setup.py` or `_run_subprocess` to `run_experiment.py` — shared helper is `helpers.run_target_subprocess` (v1.3 P2-1).
21. Never bypass the path traversal guard in `node_modify` — `relative_to(project_root.resolve())` MUST run before any write (v1.3 P1-3).
22. Never bypass the protected-file check in `node_modify` — `cfg.is_protected(target_path)` MUST run before any write (v1.3 P1-3).
23. Never call `_git_reset_hard` without verifying `project_root` — the function has a safety guard that refuses no-root / non-repo (v1.3 P1-4).
24. Never re-add `route_after_evaluate` or `route_after_decide` routers — both deleted in v1.3 P2-5 (were fake conditionals); use direct `add_edge` calls.
25. Never re-add the direct `log → propose` edge — v1.4 replaced it with a conditional edge via `route_after_log` (checks max_iterations / convergence / stuck). The direct edge would bypass all stopping conditions.
26. Never skip the md5 dedup check in `node_modify` — `hashlib.md5(new_content.encode()).hexdigest()` MUST run before the write; duplicates return `status="failed"` (v1.4 N8).
27. Never set `max_iterations` default to non-zero — the v1.4 default MUST be `0` (unlimited) so v1.3 "loop forever" behavior is preserved unless a caller explicitly opts in.
28. Never trigger convergence/stuck stops with `len(history) < window` — the first few iterations must NEVER false-positive (v1.4).

## ✅ ALWAYS DO

1. Always return `dict` from nodes — partial updates only (not `AutoresearchState`).
2. Always pass `trace_id` to all `tracer.*` calls — observability requires trace correlation.
3. Always use `_atomic_write` for `target_file` — `tempfile.mkstemp(dir=parent)` + `os.fsync` + `os.replace` (same-filesystem rename is atomic).
4. Always `os.unlink` the tempfile on write failure in `_atomic_write` (best-effort, wrapped in try/except OSError) — no `.tmp` leaks.
5. Always run `node_log` AFTER `node_decide` — `decide` annotates `current_experiment` (`status` + `commit` + `metric`), then `log` writes the CORRECT status (v1.3 P0-1).
6. Always pass `timeout=time_budget` to `subprocess.run` in `node_run_experiment` — on `TimeoutExpired`, partial output + sentinel returned.
7. Always use `subprocess.run` with list args — `[sys.executable, target_file]` for experiments, `["git", "add"/"commit"/"reset"/"clean"/"rev-parse", ...]` for git.
8. Always truncate `experiment_output` to last 50KB in `node_run_experiment` — the metric is usually printed at the end.
9. Always `re.escape(metric_name)` before building the regex — `helpers.extract_metric` does this (handles `val/loss`, `loss-1`, etc.).
10. Always take the LAST regex match (`matches[-1]`) — training scripts print per-epoch metrics; we want the final value.
11. Always sanitize `description` before writing to the ledger — `" ".join(str(description).split())` collapses whitespace (TSV row MUST stay one line).
12. Always copy `experiment_history` before appending (`list(state.get(...) or [])`) — LangGraph doesn't deep-copy.
13. Always lazy-import tools INSIDE node functions (`tools.git`, `core.json_extract`, `tools.agent`) — avoids circular imports.
14. Always use `agent(action="subagent", role="planner")` for the planner LLM (v1.1+). NO `_call()` fallback. 3× retry loop (v1.3 P1-2) inside `_call_planner`.
15. Always reuse `core.json_extract.extract_json()` for LLM JSON parsing (strips markdown fences, handles partial JSON).
16. Always set `proposal["status"]` + `proposal["commit"]` + `proposal["metric"]` in `node_decide` — `node_log` reads these for the ledger row.
17. Always clear `current_experiment` in `node_log` after appending to `experiment_history` — next `node_propose` starts fresh.
18. Always propagate `status="failed"` through the chain — `modify` sets it; `run_experiment` skips run; `evaluate` returns `current_metric=0.0`; `decide` discards. Failed experiment still logged.
19. Always reset `status="running"` + `error=""` in `node_decide` (v1.3 P0-1 — was `node_log`). `decide` runs first in the new order; its reset propagates to next `propose`.
20. Always check `Path(results_path).exists()` before writing the TSV header (resume case).
21. Always use `[v1.0]` / `[v1.3]` markers in source comments — matches the convention used by all other workflows.
22. Always check `cfg.is_protected(target_path)` before writing in `node_modify` — same list as `file` tool (blocks `.env`, `pyproject.toml`, agent source).
23. Always verify `project_root` is a git repo before `_git_reset_hard` — the safety guard (v1.3 P1-4) refuses when `.git` is missing.
24. Always update this doc when adding nodes, changing routing logic, or modifying error handling.
25. Always check `route_after_log`'s 3 stopping conditions in order: `max_iterations` → convergence (all discarded) → stuck (within ε of best) — short-circuits on the first hit (v1.4).
26. Always store `content_hash` on `current_experiment` in `node_modify` — `node_log` reads it via `proposal.get("content_hash", "")` and persists it in `experiment_history` for future dedup (v1.4 N8).
27. Always use `hashlib.md5(new_content.encode("utf-8"))` for dedup — md5 is fast and we only need exact-content dedup (semantic dedup is N4, deferred).
28. Always pull `max_iterations` from `cfg.autoresearch_max_iterations` in the type handler when the caller didn't pass it — env-overridable for operators who want auto-stop on every run (v1.4).

---

## 🚫 Anti-Patterns & Lessons Learned

> **Don't add a "convergence" exit to the loop:** Autoresearch has no clean convergence signal — the metric can plateau for 50 iterations then jump 10%. An "exit if no improvement in N iterations" rule would prematurely terminate productive runs. Human operator is the only valid convergence detector.

> **Don't store `experiment_output` in `experiment_history` entries:** History entries are `{iteration, description, metric, status, commit}` — lean on purpose. Storing full output would bloat the LLM prompt exponentially. Operators debugging a specific iteration should re-run it manually (or wait for roadmap item N5).

> **Don't use the `git` tool for `node_decide`:** First prototype used `git(action="commit")` — every call wrapped in `tracer.step` + compression added ~50ms noise/iteration × ~100 iterations/hour = ~5s/hour pure overhead. Switched to raw `subprocess.run(["git", ...])` — same semantics, no overhead.

> **[v1.3 P0-1] Don't let `log` run BEFORE `decide`:** Pre-v1.3 order was `evaluate → log → decide` — `log` read `proposal.get("status", "discard")` BEFORE `decide` set it → ledger ALWAYS said "discard" (even for keeps). Worse, `log` reset `status="running"` AFTER `decide` ran, so `decide` never saw `evaluate`'s `"failed"` status → failed experiments could be committed as improvements. v1.3 order (`evaluate → decide → log`) fixes both.

> **Don't forget `os.fsync` before `os.replace`:** A prototype skipped `os.fsync` "for performance". On power loss after `os.replace`, the target was zero bytes (rename succeeded but data wasn't flushed). `os.fsync(f.fileno())` after `f.flush()` forces bytes to disk BEFORE the atomic rename. ~1ms/write; crash-safe.

> **Don't treat equality as improvement:** A prototype used `<=` (lower is better) instead of `<` in `_is_improvement`. The LLM discovered that proposing the same change repeatedly kept the metric "equal" → counted as improvement → committed. Git log filled with no-op commits. Switched to strict `<`.

> **[v1.3 P1-1] Don't set `status="keep"` with an empty commit SHA:** Pre-v1.3, when `_git_commit` returned `""` (hook rejection, nothing to commit, timeout), `node_decide` set `status="keep"` with `commit=""` — ambiguous ledger entry. v1.3 treats empty SHA as discard: runs `_git_reset_hard`, sets `status="discard"` + `commit=""`, does NOT update `current_best`.

> **[v1.3 P1-3] Don't trust `target_file` without validation:** A prototype accepted any `target_file` string from the LLM. A hallucinating LLM proposed `target_file="../../../etc/passwd"` and the node would have happily written to it. Added path traversal guard (`relative_to(project_root.resolve())`) + protected-file check (`cfg.is_protected(target_path)`). Both return `status="failed"`.

> **[v1.3 P1-4] Don't run `git reset --hard` without verifying the repo:** A prototype called `_git_reset_hard(project_root)` without checking if `project_root` was a git repo. When `project_root` was empty (misconfigured state), `subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=None)` reset the agent's own working tree — losing uncommitted agent code. Added safety guard: refuse to reset when `project_root` is empty OR `.git` doesn't exist.

> **[v1.4] Don't auto-stop the loop on by default:** The v1.3 "loop forever" behavior was deliberate — autoresearch has no clean convergence signal (the metric can plateau for 50 iterations then jump 10%). v1.4 adds an OPT-IN `route_after_log` with 3 stopping conditions (max_iterations / convergence / stuck), but ALL defaults are OFF (max_iterations=0, window large, ε small). An overnight run making progress should NEVER auto-stop. Callers wanting auto-stop must explicitly pass `max_iterations=N` or set env vars.

> **[v1.4 N8] Don't re-run the same experiment:** A prototype accepted any `new_content` from the LLM, even if it was byte-identical to a prior experiment. The LLM (especially with low temperature) would re-propose the same change repeatedly — wasting an entire experiment cycle (LLM call + write + subprocess + git). Added md5 hash check in `node_modify`: if `hashlib.md5(new_content) == any prior experiment_history.content_hash`, return `status="failed"` with a "duplicate" error. Semantic dedup (catching whitespace-only diffs) deferred to N4.

---

*Last updated: 2026-07-20 (v1.4). See [CHANGELOG.md](CHANGELOG.md) for version history.*
