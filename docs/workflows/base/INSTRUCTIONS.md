<- Back to [Base Overview](../BASE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — LangGraph does not deep-copy. Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove checkpoint saving from `node_error`** — Checkpoints are the safety net for resumability.
4. **Never let `node_error` return an empty message** — The guard ensures meaningful error logs.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never skip `compileall` before `pytest`** — catches syntax errors early.
9. **Never return `None` from LangGraph nodes** — `node_step()` returns `None` which violates the node contract. Return `{}` at minimum.

## ✅ ALWAYS DO

10. **Always return `dict` from `node_error` and `node_done`** — Not `WorkflowState`. Partial updates only.
11. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
12. **Always validate checkpoint version** — `_checkpoint_version == 1` before resuming.
13. **Always handle unknown workflow types** — Return `"failed"` with clear error, never crash.
14. **Always test `trim_state` with oversized fields** — Assert fields are evicted and replaced with placeholder text.
15. **Always test checkpoint resumption** — Mock `get_latest` to return valid/invalid checkpoints.
16. **Always test autocode compatibility** — Assert `task` key exists when `workflow_type="autocode"`.
17. **Always update this doc** when adding fields to `WorkflowState`, changing helper signatures, or modifying dispatch logic.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `resume_count` in `save_checkpoint` was computed via string-matching: `sum(1 for line in lines if '"node": "resume"' in line)`. If a state field contained that literal string, it produced a false positive.
> - **Why it matters:** Inflated `resume_count` could trigger false zombie-loop detection, quarantining workflows that weren't actually stuck.
> - **Fix:** Parse each line as JSON and check `json.loads(line).get("node") == "resume"` — only counts actual resume nodes.

> - **What happened:** All `agent()` calls in workflow nodes (research, data, deep_research) were missing `action="dispatch"`. The agent facade requires `action` — without it, every call returned "Unknown action" error.
> - **Why it matters:** `node_synthesize` in research always failed; `node_execute` code-gen in data always failed; `node_critique` was dead code; deep_research's knowledge base never advanced. These were all P0 bugs.
> - **Fix:** Add `action="dispatch"` as the first keyword argument to every `agent()` call in workflow nodes.

> - **What happened:** `understand` workflow validated `project_root` but never forwarded it to `run_workflow()`. The workflow defaulted to agent root instead of the specified project.
> - **Why it matters:** Users scanning a specific project got the agent's own codebase indexed instead.
> - **Fix:** Add `kwargs["project_root"] = project_root` in the `understand` branch of `workflow_tool.py`.

> - **What happened:** Auto-routing low-confidence guard only aborted if `clarifying_questions` was non-empty. Low confidence with empty questions fell through to execution.
> - **Why it matters:** The guard's purpose is to prevent wasting 15+ minutes on misunderstood tasks. Empty questions shouldn't bypass that protection.
> - **Fix:** Abort on low confidence regardless of whether questions exist. Provide a default question when none were given.

---

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for utility signatures, [CHANGELOG.md](CHANGELOG.md) for version history.*
