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
29. Never wire `route_after_log` directly from `log` — v1.5 N1 inserted `node_reflect` between them; the conditional edge must start from `reflect` (was `log` in v1.4).
30. Never let `node_reflect` raise out — LLM failure must be caught and return `{}` (non-fatal) so the loop continues with the prior reflection.
31. Never let `_record_failure_memory` or `node_propose`'s memory recall raise out — `core.memory_engine` may be unavailable (chromadb missing) and the experiment loop must NEVER halt on a memory call. Wrap in `try/except Exception: pass`.
32. Never activate the parallel path when `parallel_count == 1` — the v1.5 single-experiment path MUST run unchanged (singular state fields only). The parallel path is ONLY for `parallel_count > 1` (plural state fields). Mixing the two breaks backward compat.
33. Never touch the real `target_file` in `node_modify` when `parallel_count > 1` — write each proposal to its own temp dir under `{project_root}/.autoresearch/parallel/{i}/{target_file}`. The real `target_file` is only modified by `node_decide` (which copies the winner back).
34. Never skip `shutil.rmtree(parallel_dir, ignore_errors=True)` in `node_decide` — the temp dir MUST be cleaned up on EVERY exit path (improvement, no-improvement, commit failure). Leaking temp dirs accumulates disk usage over overnight runs.
35. Never let one parallel LLM call abort the batch — per-call failures (after the v1.3 P1-2 retry) must be recorded as failed-proposal placeholders (`status="failed"`); the remaining N-1 calls continue. Only set `status="failed"` for the iteration if ALL N calls fail.
36. Never checkpoint on a discard path — only successful `_git_commit` (non-empty SHA) triggers `save_checkpoint(tid, "keep", state)` in `node_decide` (v1.7 N7). Discard paths have NO recoverable state (the working tree was reset to the prior HEAD), so checkpointing them would mislead resume into restoring a non-improvement.
37. Never run the baseline on resume — when `state["resume"]=True` AND `state["current_best"] > 0.0`, `node_setup` MUST skip the baseline run and reload `experiment_history` from `results.tsv` via `_load_history_from_ledger` (v1.7 N3). Re-running the baseline wastes time AND can change `current_best` if the target_file is non-deterministic, invalidating prior comparisons.
38. Never let `save_checkpoint` raise out of `node_decide` — the `try/except Exception: pass` wrapper is mandatory (v1.7 N7). A checkpoint-disk error must NEVER halt the experiment loop. The keep still completes; only the journal write fails.
39. Never let `_write_full_output_log` raise out of `node_run_experiment` — the `try/except Exception: pass` wrapper is mandatory (v1.8 N5). A log-write disk error must NEVER halt the experiment loop. The experiment still runs + truncates + returns its normal result; only the per-iteration log file isn't written.
40. Never change `_call_planner`'s return type away from `tuple[str, dict]` — `node_propose`, `_generate_single_proposal`, AND `node_reflect` all unpack the tuple. Returning just a string would break all 3 callers + every test that mocks `_call_planner`. The usage dict (2nd element) may be `{}` when the subagent doesn't report usage — callers default `tokens` to 0 via `usage.get("total", 0)` (v1.8 N6).
41. Never extract the metric from the truncated `experiment_output` in `node_evaluate` (single path) when `pre_extracted_metric` is set — that's the whole point of v1.8 N10. The pre-extracted value came from the FULL output BEFORE truncation; re-extracting from the truncated tail could miss the metric (false negative) OR find a different value (if the metric is printed multiple times and truncation kept a different occurrence). Trust the pre-extracted value when it's not None.
42. Never set `pre_extracted_metric` in the parallel `node_run_experiment` path — parallel evaluate doesn't read it (extracts per-output metrics from `experiment_outputs` directly). A stale value from a prior single-mode iteration could leak into the next single-mode evaluate. Parallel run_experiment explicitly clears it to `None`.

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
29. Always check `experiment_count % interval == 0` (and `experiment_count != 0`) in `node_reflect` before calling the planner LLM — non-reflect iterations must short-circuit and return `{}` (v1.5 N1).
30. Always reuse `propose._call_planner` from `node_reflect` (module-level import so tests can patch `reflect._call_planner`) — don't reimplement subagent dispatch + retry (v1.5 N1).
31. Always wrap `_record_failure_memory`'s `memory.recall` + `memory.store_procedural` calls in try/except — `core.memory_engine` may not be importable (chromadb missing), and the discard path must NEVER fail because of a memory-store error (v1.5 N4).
32. Always check `parallel_count > 1` at the top of every node (propose / modify / run_experiment / evaluate / decide / log) — when False, run the v1.5 single-experiment path UNCHANGED (singular state fields). The parallel path is the ONLY place plural state fields are read or written (v1.6).
33. Always mirror the first element of plural state fields to the singular field for v1.5 backward compat — `current_experiments[0]` → `current_experiment`, `experiment_outputs[0]` → `experiment_output`, `current_metrics[0]` → `current_metric` (v1.6).
34. Always run each parallel subprocess in its OWN temp dir as cwd — `{project_root}/.autoresearch/parallel/{i}/` — so relative paths in the experiment script still resolve (v1.6).
35. Always copy the winner's temp-file content to the REAL `target_file` in `node_decide` before `git add + commit` — the real file is the source of truth for the next iteration's `node_propose` (which reads it via `_read_target_file`) (v1.6).
36. Always pull `parallel_count` from `cfg.autoresearch_parallel_count` in the type handler when the caller didn't pass it — env-overridable via `AUTORESEARCH_PARALLEL_COUNT` for operators who want batch mode on every run (v1.6).
37. Always call `save_checkpoint(tid, "keep", state)` after a successful `_git_commit` in `node_decide` (both single-experiment and parallel paths) — non-fatal try/except, but the call must happen so resume can pick up from the last-known-good metric (v1.7 N7).
38. Always set `ar_state["resume"] = True` in the dispatcher's autoresearch branch when `resume=True` AND `get_latest(trace_id)` returns a checkpoint — without this flag, `node_setup` will run the v1.6 fresh-start path (new branch + baseline) instead of resuming (v1.7 N3).
39. Always reload `experiment_history` from `results.tsv` via `_load_history_from_ledger` when resuming — the in-memory history was lost when the prior run crashed; the ledger is the persistent source of truth (v1.7 N3).
40. Always preserve caller params (goal, target_file, metric_name, etc.) when merging a restored checkpoint into `ar_state` — only autoresearch-specific fields (`experiment_count`, `current_best`, `baseline_metric`, `experiment_history`, `branch`, `results_path`, `reflect_notes`) should be merged from the checkpoint. The caller's params are the authoritative inputs for THIS run (v1.7 N3).
41. Always write the FULL output to `{results_path}.d/{iteration}.log` (single) or `{iteration}_{i}.log` (parallel) in `node_run_experiment` BEFORE truncating to 50KB (v1.8 N5). Operators need the full output for debugging when the truncated state copy doesn't have enough context. Non-fatal — wrap in `try/except Exception: pass`.
42. Always unpack `_call_planner`'s return value as a tuple — `raw, usage = _call_planner(...)` (v1.8 N6). The 2nd element is the usage dict (may be `{}`); capture `usage.get("total", 0)` on the proposal as `tokens` for cost tracking. `node_reflect` also unpacks the tuple but discards `usage` (reflection isn't an experiment).
43. Always include `tokens` in `_build_history_entry`'s return dict — `proposal.get("tokens", 0)` (v1.8 N6). Operators sum `tokens` across `experiment_history` entries to estimate LLM cost per run. Defaults to 0 for failed-proposal placeholders.
44. Always extract the metric from the FULL output in `node_run_experiment` (single path) BEFORE truncating to 50KB (v1.8 N10). Store in `pre_extracted_metric` (None when no metric found). `node_evaluate` reads this FIRST — prevents false negatives when the metric was printed early and pushed out of the 50KB tail.
45. Always check `state["pre_extracted_metric"]` FIRST in `node_evaluate` (single path) — when set (not None), trust it and skip re-extracting from the (possibly truncated) `experiment_output` (v1.8 N10). When None, fall through to extraction-from-output.
46. Always clear `pre_extracted_metric` to `None` in the parallel `node_run_experiment` path AND on the single-path skip path (`status="failed"` from modify) — prevents stale-state leakage across iterations (v1.8 N10).

---

## 🚫 Anti-Patterns & Lessons Learned

> **Don't add a "convergence" exit to the loop:** Autoresearch has no clean convergence signal — the metric can plateau for 50 iterations then jump 10%. An "exit if no improvement in N iterations" rule would prematurely terminate productive runs. Human operator is the only valid convergence detector.

> **Don't store `experiment_output` in `experiment_history` entries:** History entries are `{iteration, description, metric, status, commit, content_hash, tokens}` — lean on purpose. Storing full output would bloat the LLM prompt exponentially. **[v1.8 N5]** Operators debugging a specific iteration can now `cat {results_path}.d/{iteration}.log` to see the full output (written by `node_run_experiment` BEFORE truncation). The history entry's `tokens` field (v1.8 N6) gives cost context without bloat.

> **Don't use the `git` tool for `node_decide`:** First prototype used `git(action="commit")` — every call wrapped in `tracer.step` + compression added ~50ms noise/iteration × ~100 iterations/hour = ~5s/hour pure overhead. Switched to raw `subprocess.run(["git", ...])` — same semantics, no overhead.

> **[v1.3 P0-1] Don't let `log` run BEFORE `decide`:** Pre-v1.3 order was `evaluate → log → decide` — `log` read `proposal.get("status", "discard")` BEFORE `decide` set it → ledger ALWAYS said "discard" (even for keeps). Worse, `log` reset `status="running"` AFTER `decide` ran, so `decide` never saw `evaluate`'s `"failed"` status → failed experiments could be committed as improvements. v1.3 order (`evaluate → decide → log`) fixes both.

> **Don't forget `os.fsync` before `os.replace`:** A prototype skipped `os.fsync` "for performance". On power loss after `os.replace`, the target was zero bytes (rename succeeded but data wasn't flushed). `os.fsync(f.fileno())` after `f.flush()` forces bytes to disk BEFORE the atomic rename. ~1ms/write; crash-safe.

> **Don't treat equality as improvement:** A prototype used `<=` (lower is better) instead of `<` in `_is_improvement`. The LLM discovered that proposing the same change repeatedly kept the metric "equal" → counted as improvement → committed. Git log filled with no-op commits. Switched to strict `<`.

> **[v1.3 P1-1] Don't set `status="keep"` with an empty commit SHA:** Pre-v1.3, when `_git_commit` returned `""` (hook rejection, nothing to commit, timeout), `node_decide` set `status="keep"` with `commit=""` — ambiguous ledger entry. v1.3 treats empty SHA as discard: runs `_git_reset_hard`, sets `status="discard"` + `commit=""`, does NOT update `current_best`.

> **[v1.3 P1-3] Don't trust `target_file` without validation:** A prototype accepted any `target_file` string from the LLM. A hallucinating LLM proposed `target_file="../../../etc/passwd"` and the node would have happily written to it. Added path traversal guard (`relative_to(project_root.resolve())`) + protected-file check (`cfg.is_protected(target_path)`). Both return `status="failed"`.

> **[v1.3 P1-4] Don't run `git reset --hard` without verifying the repo:** A prototype called `_git_reset_hard(project_root)` without checking if `project_root` was a git repo. When `project_root` was empty (misconfigured state), `subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=None)` reset the agent's own working tree — losing uncommitted agent code. Added safety guard: refuse to reset when `project_root` is empty OR `.git` doesn't exist.

> **[v1.4] Don't auto-stop the loop on by default:** The v1.3 "loop forever" behavior was deliberate — autoresearch has no clean convergence signal (the metric can plateau for 50 iterations then jump 10%). v1.4 adds an OPT-IN `route_after_log` with 3 stopping conditions (max_iterations / convergence / stuck), but ALL defaults are OFF (max_iterations=0, window large, ε small). An overnight run making progress should NEVER auto-stop. Callers wanting auto-stop must explicitly pass `max_iterations=N` or set env vars.

> **[v1.4 N8] Don't re-run the same experiment:** A prototype accepted any `new_content` from the LLM, even if it was byte-identical to a prior experiment. The LLM (especially with low temperature) would re-propose the same change repeatedly — wasting an entire experiment cycle (LLM call + write + subprocess + git). Added md5 hash check in `node_modify`: if `hashlib.md5(new_content) == any prior experiment_history.content_hash`, return `status="failed"` with a "duplicate" error. Semantic dedup (catching whitespace-only diffs) deferred to N4.

> **[v1.5 N1] Don't reflect on every iteration:** A prototype called the planner LLM at the end of every iteration to generate a strategy reflection. The extra LLM call DOUBLED token cost per iteration and added ~2s latency (even with subagent dispatch). Switched to a configurable interval (`autoresearch_reflect_interval`, default 5) — the LLM reflects only on multiples of the interval. The reflection is stored in `state["reflect_notes"]` and surfaced to the next `node_propose`, so strategy context persists across the non-reflect iterations. `interval=0` disables reflection entirely (legacy v1.4 behavior).

> **[v1.5 N4] Don't let cross-run learning block the experiment loop:** A prototype called `memory.store_procedural(...)` directly in `node_decide` without a try/except wrapper. When chromadb was unavailable (test environment, fresh install), the call raised and the ENTIRE discard path aborted — the loop stuck. Wrapped every memory call in `try/except Exception: pass` so cross-run learning is best-effort: it activates when chromadb is available and silently no-ops otherwise. Same pattern in `node_propose`'s `memory.recall` — a recall failure never blocks proposal generation.

> **[v1.6] Don't write N proposals to the same `target_file`:** First prototype tried to write all N proposals sequentially to the real `target_file`, run each, then restore the winner. Race conditions + state tracking made this fragile. Switched to per-experiment temp dirs: `{project_root}/.autoresearch/parallel/{i}/{target_file}`. The real `target_file` is only touched by `node_decide` (which copies the winner back). Clean separation, no race conditions, easy cleanup (`shutil.rmtree(parallel_dir)`).

> **[v1.6] Don't change the graph topology for parallel mode:** First prototype added new nodes (e.g. `parallel_propose`, `parallel_decide`) and conditional edges. Doubled the graph complexity + required new routing logic. Switched to NODE-INTERNAL parallelism: each node handles N experiments internally when `parallel_count > 1`, branching on the state field. The graph topology stays UNCHANGED — the 8-node v1.5 graph handles both single (parallel_count=1) and batch (parallel_count>1) modes via the same edges. Coordination happens inside the nodes via the `parallel_count` state field.

> **[v1.7 N3] Don't re-run the baseline on resume:** First prototype ran `node_setup`'s baseline path unconditionally — every resumed run wasted one experiment cycle re-establishing the metric. Worse, if the target_file was non-deterministic (e.g. random seed not fixed), the baseline metric would CHANGE between runs, invalidating the prior `current_best` and causing the LLM to discard improvements that were actually keeps. Fix: `node_setup` checks `state["resume"]` AND `state["current_best"] > 0.0` — if both, skip the baseline AND reload `experiment_history` from `results.tsv` via the new `_load_history_from_ledger` helper so `node_propose` has the prior experiments in context.

> **[v1.7 N7] Don't checkpoint discards:** First prototype called `save_checkpoint` on every `node_decide` exit path (both keep AND discard). On resume, the dispatcher's `get_latest(trace_id)` would restore a discarded state — `current_best` was unchanged (good) but `current_experiment` was annotated `status="discard"` with empty commit, which made `node_propose` think the last experiment was a known dead-end. Fix: only checkpoint on the keep path (after a successful `_git_commit`). Discards represent a reset to the prior HEAD — there's no recoverable state worth resuming from beyond the prior keep's checkpoint.

> **[v1.8 N5] Don't write the full-output log AFTER truncation:** First prototype wrote the log file from the (already-truncated) `experiment_output` — defeating the whole purpose of N5 (operators want the FULL output for debugging, not the 50KB tail). Fix: write the log file FIRST (from the raw subprocess output), THEN truncate. Non-fatal — disk errors are swallowed so the loop is never blocked. The log dir is `{results_path}.d/` (sibling of `results.tsv`); filenames are `{iteration}.log` (single) or `{iteration}_{i}.log` (parallel, one per experiment).

> **[v1.8 N6] Don't track reflect tokens in `experiment_history`:** First prototype captured `tokens` from `_call_planner` in `node_reflect` too, planning to sum reflect + propose tokens per iteration. Problem: reflect runs every N iterations (default 5), so the sum was inconsistent — most iterations had only propose tokens, reflect iterations had propose + reflect. Operators couldn't tell which. Fix: `node_reflect` discards the usage tuple element (unpacks as `reflection, _usage = _call_planner(...)`). Only `node_propose` tokens are tracked in `experiment_history`. Reflect token cost is visible in the tracer log (the subagent dispatch already traces `completed in {N} tokens`) but not summed into per-iteration cost.

> **[v1.8 N10] Don't extract the metric from the truncated output when a pre-extracted value exists:** First prototype always called `_extract_metric(experiment_output, metric_name)` in `node_evaluate`, even when `pre_extracted_metric` was set. This defeated the whole purpose of N10 — the truncated 50KB tail might not contain the metric (false negative) OR might contain a different occurrence (if the script prints the metric multiple times and truncation kept a different one). Fix: check `pre_extracted_metric` FIRST; only fall through to extraction-from-output when it's None. The pre-extracted value came from the FULL output BEFORE truncation — it's always correct.

---

*Last updated: 2026-07-23 (v1.8). See [CHANGELOG.md](CHANGELOG.md) for version history.*
