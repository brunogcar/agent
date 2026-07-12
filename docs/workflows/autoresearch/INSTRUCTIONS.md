<- Back to [Autoresearch Overview](../AUTORESEARCH.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s. (Same rule as autocode.)
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove the indefinite loop** — `route_after_decide` MUST always return `"propose"`. The loop is evolutionary by design; the only exit is human interrupt (or LangGraph's `recursion_limit`). Adding a "convergence" exit breaks the workflow's core premise — see CHANGELOG § Deferred #4.
4. **Never skip the ledger** — `node_log` MUST append every experiment (keep OR discard) to `results.tsv`. The ledger is the human audit trail; operators `tail -f` it while the loop runs. Skipping a log entry creates a gap in the audit trail.
5. **Never modify `target_file` outside `node_modify`** — Every write to `target_file` MUST go through `node_modify._atomic_write` (`tempfile.mkstemp` + `os.fsync` + `os.replace`). Direct `open(path, "w").write(...)` leaves the file in a half-written state if the process is killed mid-write.
6. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` / `tracer.warning()` / `tracer.error()` for all logging. (Same rule as autocode.)
7. **Never create `.bak` files** — forbidden by project rules. The atomic write in `node_modify` does NOT create a backup; git is the backup (every keep is committed; every discard is `git reset --hard HEAD`).
8. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).
9. **Never call `agent()` for LLM calls** — `node_propose` uses `workflows.autocode_impl.helpers._call()` (the same helper autocode uses) for retry + cancellation + `json_schema` plumbing. Calling `agent()` directly bypasses the retry/backoff/cancellation infrastructure.
10. **Never use raw `json.loads()` on LLM-generated output** — LLMs frequently wrap JSON in markdown fences. Always use `core.json_extract.extract_json()` (single source of truth — same rule as autocode).
11. **Never call the `git` tool from `node_decide`** — `node_decide` runs `subprocess.run(["git", ...])` directly (NOT the `git` tool) to bypass tracing + compression noise during the tight experiment loop. The `git` tool is fine for `node_setup._git_create_branch` (called once).
12. **Never treat equality as an improvement** — `node_decide._is_improvement` returns `False` when `new == best`. This is deliberate — discourage no-op changes that just shuffle code without moving the metric.
13. **Never reset `current_best` on discard** — `node_decide` updates `current_best` ONLY on keep. On discard, `current_best` is unchanged (the next proposal starts from the same baseline). Returning `current_metric` (the discarded value) as the new `current_best` would silently regress the optimization.
14. **Never write the `results.tsv` header on resume** — `node_setup` checks `Path(results_path).exists()` before writing the header. On resume, the existing ledger is preserved.
15. **Never cap `experiment_history` below 20 entries** — `node_propose._format_history` shows the most recent 20 experiments. Capping lower (e.g. 5) starves the LLM of context; capping higher bloats the prompt. 20 is the sweet spot.
16. **Never run experiments without `time_budget`** — `node_run_experiment` MUST pass `timeout=time_budget` to `subprocess.run`. A hung experiment without a timeout freezes the entire loop forever.
17. **Never forget `os.fsync` before `os.replace`** — `node_modify._atomic_write` calls `f.flush()` + `os.fsync(f.fileno())` BEFORE `os.replace(tmp_path, path)`. Without fsync, a power loss after `os.replace` may leave a zero-byte file (the OS hasn't flushed the tempfile's bytes to disk yet).
18. **Never use `shell=True` in subprocess calls** — `node_run_experiment` and `node_decide._git_commit` / `_git_reset_hard` all pass explicit list args (`["git", "add", "-A"]`, `[sys.executable, target_file]`). Shell injection risk + quoting bugs.
19. **Never re-add `node_setup._extract_metric_from_output` to `node_evaluate`** — The two functions look similar but live in different nodes for a reason: setup extracts the BASELINE metric (called once, before the loop); evaluate extracts the per-iteration metric (called every iteration). Duplicating the function in evaluate would create drift. If you need to refactor, extract to a shared helper module.

## ✅ ALWAYS DO

1. **Always return `dict` from nodes** — Not `AutoresearchState`. Partial updates only.
2. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
3. **Always use atomic writes for `target_file`** — `tempfile.mkstemp(dir=target_path.parent)` + `os.fsync` + `os.replace`. The tempfile MUST be in the same directory as the target (same-filesystem rename — `os.replace` is atomic on POSIX + Windows for same-FS renames only).
4. **Always clean up the tempfile on write failure** — `node_modify._atomic_write` wraps the write in try/except. On failure, `os.unlink(tmp_path)` (wrapped in try/except OSError — best-effort cleanup) then re-raise. No `.tmp` file leaks.
5. **Always log every experiment to the ledger** — `node_log` runs BEFORE `node_decide`, so even discarded experiments are recorded. The ledger is the source of truth for human audit; the in-memory `experiment_history` is the source of truth for the LLM.
6. **Always time-box experiments** — `node_run_experiment` passes `timeout=time_budget` to `subprocess.run`. On `TimeoutExpired`, the partial output + sentinel is returned (don't silently drop the experiment).
7. **Always use `subprocess.run` with list args** — `[sys.executable, target_file]` for experiments, `["git", "add", "-A"]` / `["git", "commit", "-m", message]` / `["git", "reset", "--hard", "HEAD"]` / `["git", "clean", "-fd"]` / `["git", "rev-parse", "--short", "HEAD"]` for git. No `shell=True`.
8. **Always truncate `experiment_output` to 50KB** — `node_run_experiment` keeps the last 50KB if larger. The metric is usually printed at the end; the truncation prevents state bloat + ledger bloat.
9. **Always `re.escape(metric_name)` before building the regex** — `node_evaluate._extract_metric` escapes the metric name so special chars like `val/loss` or `loss-1` don't break the pattern or inject regex metacharacters.
10. **Always take the LAST regex match** — Training scripts often print the metric per epoch; we want the FINAL value. `matches[-1]`, not `matches[0]`.
11. **Always sanitize `description` before writing to the ledger** — `node_log` does `" ".join(str(description).split())` to collapse whitespace + strip newlines/tabs. The TSV row MUST stay one line.
12. **Always copy `experiment_history` before appending** — `node_log` does `history = list(state.get("experiment_history", []) or [])` then `history.append(entry)`. Never mutate the list in-place (LangGraph doesn't deep-copy).
13. **Always lazy-import tools** — `from tools.git import git` (in `node_setup._git_create_branch`), `from core.json_extract import extract_json` (in `node_propose._parse_proposal`), `from workflows.autocode_impl.helpers import _call` (in `node_propose._call_planner`) are all INSIDE the node functions, not at module top. Avoids circular imports.
14. **Always reuse `autocode_impl.helpers._call()` for LLM calls** — Don't reimplement retry/backoff/cancellation. The helper has interruptible sleep via `threading.Event` (so `request_cancellation()` from a timeout aborts the backoff) and `json_schema` plumbing.
15. **Always reuse `core.json_extract.extract_json()` for LLM JSON parsing** — Single source of truth. Strips markdown fences, handles partial JSON.
16. **Always set `proposal["status"]` + `proposal["commit"]` + `proposal["metric"]` in `node_decide`** — `node_log` reads these to build the ledger row. Missing any of them creates an incomplete audit entry.
17. **Always clear `current_experiment` in `node_log`** — After appending to `experiment_history`, set `current_experiment = {}` so the next iteration's `node_propose` starts fresh.
18. **Always propagate `status="failed"` through the chain** — `node_modify` sets it on empty proposal / write failure; `node_run_experiment` checks it and skips the run; `node_evaluate` checks it and returns `current_metric=0.0`; `node_decide` checks it and discards. This short-circuit prevents wasted work and ensures the failed experiment is still logged.
19. **Always check `Path(results_path).exists()` before writing the TSV header** — `node_setup` only writes the header if the file doesn't already exist. On resume, the existing ledger is preserved.
20. **Always use `[v1.0]` markers in source comments** — Matches the convention used by all other workflows. Helps future editors understand which features shipped in which version.
21. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.

---

## 🚫 Anti-Patterns & Lessons Learned

> **Don't add a "convergence" exit to the loop:** Unlike `deep_research` (cosine similarity threshold) or `autocode` (tests pass), autoresearch has no clean convergence signal. The metric can plateau for 50 iterations then jump 10%. Adding an "exit if no improvement in N iterations" rule would prematurely terminate productive runs. The human operator is the only valid convergence detector — they see the ledger + the git log and decide when to stop.

> **Don't store `experiment_output` in `experiment_history` entries:** The output is captured per-iteration in `state.experiment_output` (truncated to 50KB), but is NOT copied into `experiment_history` entries. The history entries are `{iteration, description, metric, status, commit}` — lean on purpose. Storing the full output in history would bloat the LLM prompt exponentially (history grows linearly; output is constant per iteration). Operators who want to debug a specific iteration should re-run it manually.

> **Don't use the `git` tool for `node_decide`:** The first prototype used `git(action="commit")` and `git(action="rollback")` from `node_decide`. Every call wrapped in `tracer.step` + result compression added ~50ms of noise per iteration × ~100 iterations/hour = ~5s/hour of pure overhead. Switched to raw `subprocess.run(["git", ...])` — same semantics, no overhead. The `git` tool is fine for `node_setup._git_create_branch` (called once).

> **Don't propagate `status="failed"` past `node_decide`:** `node_decide` does NOT clear `status="failed"` after discarding — but `node_log` writes `status="running"` back into state. If `node_log` didn't reset status, the next iteration's `node_run_experiment` would skip the run (thinking a prior node failed). The status reset in `node_log` is the loop's recovery point.

> **Don't forget `os.fsync` before `os.replace`:** A prototype skipped the `os.fsync` "for performance". On a power loss after `os.replace`, the target file was zero bytes (the OS hadn't flushed the tempfile's bytes to disk yet — the rename succeeded, but the data wasn't there). `os.fsync(f.fileno())` after `f.flush()` forces the bytes to disk BEFORE the atomic rename. The cost is ~1ms per write; the benefit is crash safety.

> **Don't treat equality as improvement:** A prototype used `<=` (lower is better) instead of `<` in `_is_improvement`. The LLM quickly discovered that proposing the same change repeatedly kept the metric "equal" → counted as improvement → committed as a new commit. The git log filled with no-op commits. Switched to strict `<` — equality is now a discard, discouraging the LLM from proposing no-op changes.

---

*Last updated: 2026-07-12 (v1.0 — initial implementation).*
