<- Back to [Base Overview](../BASE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove checkpoint saving from `node_error`** — Checkpoints are the safety net for resumability. [v1.2] Must save FULL state, not just `{status, error}`.
4. **Never let `node_error` return an empty message** — The guard ensures meaningful error logs.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never clobber the checkpoint's goal on resume** — [v1.2] `run_workflow(resume=True)` must keep the original goal from the checkpoint, not overwrite it with the new `goal` parameter.
10. **Never skip the checkpoint in the exception handler** — [v1.2] `run_workflow()` `except Exception` must call `save_checkpoint()` before returning the failure dict, so the crash state is preserved.

## ✅ ALWAYS DO

11. **Always return `dict` from `node_error` and `node_done`** — Not `WorkflowState`. Partial updates only.
12. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
13. **Always validate checkpoint version** — `_checkpoint_version == 1` before resuming.
14. **Always handle unknown workflow types** — Return `"failed"` with clear error listing all 6 types, never crash.
15. **Always test `trim_state` with oversized fields** — Assert fields are evicted and replaced with placeholder text.
16. **Always test checkpoint resumption** — Mock `get_latest` to return valid/invalid checkpoints.
17. **Always test autocode compatibility** — Assert `task` key exists when `workflow_type="autocode"`.
18. **Always save full state in `node_error` checkpoint** — [v1.2] `{**state, "status": "failed", "error": msg}`, not just `{"status": "failed", "error": msg}`.
19. **Always save success checkpoint in `node_done` before `mark_complete`** — [v1.2] So the final state is preserved if the process dies.
20. **Always update this doc** when adding fields to `WorkflowState`, changing helper signatures, or modifying dispatch logic.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `node_error` saved only `{"status": "failed", "error": message}` as checkpoint. Resume from an error lost all workflow context — memory context, accumulated results, everything.
> - **Why it matters:** If a workflow crashed at node 10 of 15, resuming would start from scratch with no context, not from the crash point.
> - **Fix:** [v1.2] `node_error` now saves `{**state, "status": "failed", "error": message}` — the full state plus the error.

> - **What happened:** `run_workflow()` exception handler returned a failure dict but never called `save_checkpoint()`. State at crash time was lost.
> - **Why it matters:** A crash at node 12 of a 17-node autocode workflow would lose all work with no way to debug or resume.
> - **Fix:** [v1.2] Exception handler now calls `save_checkpoint(trace_id, "dispatch_error", {**initial_state, "status": "failed", "error": msg})` before returning.

> - **What happened:** Resume did `initial_state = {**restored, "status": "running", "goal": goal}` — overwriting the checkpoint's original goal with the new `goal` parameter.
> - **Why it matters:** If you called `run_workflow("research", goal="NEW query", resume=True)`, the checkpoint's original goal was replaced, making the checkpoint meaningless.
> - **Fix:** [v1.2] `initial_state = {**restored, "status": "running"}` — keeps the checkpoint's original goal.

> - **What happened:** `resume_count` in `save_checkpoint` was computed via string-matching: `'"node": "resume"' in line`. If a state field contained that literal string, it produced a false positive.
> - **Why it matters:** Inflated `resume_count` could trigger false zombie-loop detection.
> - **Fix:** [v1.1] Parse each line as JSON and check `json.loads(line).get("node") == "resume"`.

---

*Last updated: 2026-07-13 (v1.3.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for utility signatures, [CHANGELOG.md](CHANGELOG.md) for version history.*
