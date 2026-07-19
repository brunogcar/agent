<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 API Reference

Facade signature, config flags, return shape, state field list. For per-node reference see [NODES.md](NODES.md); for state TypedDicts/accessors see [SUBSTATE.md](SUBSTATE.md); for design rationale see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🚀 Facade — `run_workflow("autocode")`

```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="autocode",
    goal="Fix the timeout handling in web search",
    mode="feature",                          # feature | fix | fix_error | refactor | improve | edit | create_skill | audit
    files={"web.py": "..."},
    dry_run=False,
    trace_id="",                             # "" → run_workflow creates one
    resume=False,                            # True → restore from checkpoint
    hitl_approved=False,                     # [v3.4] pass True on resume to clear HiTL gate
    target_file="web.py",                    # autocode requires target_file
    error_msg="",                            # fix_error mode: the error traceback
    feature_desc="",                         # feature mode: feature description
)
```

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `workflow_type` | `str` | (required) | Must be `"autocode"`. |
| `goal` | `str` | (required) | Natural-language task; aliased to `state["task"]`. |
| `mode` | `str` | `"feature"` | One of 8 valid modes; overrides LLM classification. `fix_error`→`fix`, `improve`→`refactor`; others pass through as `task_type`. |
| `files` | `dict[str, str]` | `{}` | Initial file contents. `{"all changed": ""}` + `git_diff=True` for git-diff input. |
| `git_diff` | `bool` | `False` | Resolve `"all changed"` key via `git diff --name-only`. |
| `dry_run` | `bool` | `False` | Skip writes/commits/branches. |
| `trace_id` | `str` | `""` | Trace correlation ID. |
| `resume` | `bool` | `False` | Restore from checkpoint (HiTL resume). |
| `hitl_approved` | `bool` | `False` | Pass `True` on resume to clear the HiTL gate. |
| `target_file` | `str` | `""` | Target file path (autocode requires this). |
| `**kwargs` | — | — | `error_msg`, `feature_desc`, `project_root`. |

**Valid modes (8):** `feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, `create_skill`, `audit`. Validated in `node_validate_input`.

**Facade contract:** Always go through `run_workflow("autocode")` — it handles tracing, checkpointing, and timeout via `invoke_with_timeout()` in `workflows/autocode_impl/graph.py`. Never call `get_graph().invoke()` directly. For machine-consumable structured output, call `_shape_artifacts(result)` (still exported from `workflows.autocode`) — returns `{commit_sha, branch_name, modified_files, test_results, tdd_status, tdd_iteration, verification_passed, skill_created, skill_path}`.

---

## ⚙️ Config Flags (all 17)

All flags live in `core/config_backend/execution.py`. Per-role LLM timeouts come from `cfg.model_registry[role]["timeout"]` — there are no `AUTOCODE_PLANNER_TIMEOUT`/`AUTOCODE_EXECUTOR_TIMEOUT`/`AUTOCODE_ROUTER_TIMEOUT` env vars (earlier doc references were stale).

| Env var | `cfg` attr | Default | Purpose |
|---------|------------|---------|---------|
| `AUTOCODE_GRAPH_TIMEOUT` | `autocode_graph_timeout` | `300` | Workflow timeout (s); validated ≥ max per-role timeout. |
| `AUTOCODE_MAX_RETRIES` | `autocode_max_retries` | `3` | Max debug-loop iterations (range-checked). |
| `AUTOCODE_MAX_FILE_CHARS` | `autocode_max_file_chars` | `6000` | Max file content chars (range-checked). |
| `AUTOCODE_DEBUG` | `autocode_debug` | `False` | Verbose debug logging (truthy: `== "1"`). |
| `AUTOCODE_ADAPTIVE_TIMEOUT` | `autocode_adaptive_timeout` | `False` | Opt-in per-task-type graph timeouts. |
| `AUTOCODE_HITL_ENABLED` | `autocode_hitl_enabled` | `False` | HiTL approval gate before commit (v3.4). |
| `AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD` | `autocode_architecture_question_threshold` | `3` | Consecutive `tests_passed=False` count for architecture-question exit (v3.3 F4). |
| `AUTOCODE_PULL_BEFORE_BRANCH` | `autocode_pull_before_branch` | `False` | Pull recent commits before branching. |
| `AUTOCODE_PUSH_ON_COMMIT` | `autocode_push_on_commit` | `False` | Push branch to origin after commit. |
| `AUTOCODE_OPEN_PR` | `autocode_open_pr` | `False` | Open a PR after push. |
| `AUTOCODE_AUTO_MERGE` | `autocode_auto_merge` | `False` | **DANGEROUS** — auto-merge the PR (squash). |
| `AUTOCODE_DEBUG_COMMENT_PR` | `autocode_debug_comment_pr` | `False` | Post LOW-confidence swarm verdict as PR comment. |
| `AUTOCODE_SWARM_DEBUG` | `autocode_swarm_debug` | `False` | Swarm (consensus → vote) inside debug loop. |
| `AUTOCODE_SUBAGENT_DEBUG` | `autocode_subagent_debug` | `False` | Single isolated subagent dispatch for debug (v2.0.2). |
| `AUTOCODE_SWARM_DEBUG_FALLBACK` | `autocode_swarm_debug_fallback` | `False` | Escalate to swarm when debug retries exhausted (v3.1). |
| `AUTOCODE_PARALLEL_SUBAGENT_DEBUG` | `autocode_parallel_subagent_debug` | `False` | Parallel subagent debug — N hypotheses → N subagents (v3.5 F1). |
| `AUTOCODE_PARALLEL_SUBAGENT_COUNT` | `autocode_parallel_subagent_count` | `3` | Number of parallel hypotheses (recommended 2-5). |

The 3 in-loop debug flags (`AUTOCODE_SWARM_DEBUG`, `AUTOCODE_SUBAGENT_DEBUG`, `AUTOCODE_PARALLEL_SUBAGENT_DEBUG`) are mutually exclusive (chain: swarm → parallel → single subagent → single-LLM, fall-through). `AUTOCODE_SWARM_DEBUG_FALLBACK` fires AFTER the loop exhausts retries — independent of the in-loop flags.

### Adaptive timeout table (when `AUTOCODE_ADAPTIVE_TIMEOUT=1`)

| `task_type` | Timeout (s) |
|-------------|-------------|
| `create_skill` | 120 |
| `audit` | 300 |
| `feature` | 900 |
| `fix` / `refactor` / `edit` | 600 |
| (unknown/empty) | `cfg.autocode_graph_timeout` |

### GitHub prerequisite

`node_push`, `node_create_pr`, `node_merge_pr`, and `_github_pull()` require `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` in `.env`. If any is missing, `is_configured()` returns `False` and every `vcs_ops.py` helper graceful-skips.

---

## 📤 Return Shape

```json
{
  "status": "success",                     // "success" | "failed" | "awaiting_approval"
  "result": "Code changes applied successfully: ...",
  "error": "",
  "trace_id": "autocode_001",
  "artifacts": ["web.py", "test_web.py"],
  "commit_sha": "abc123",
  "test_passed": true,
  "lint_passed": true
}
```

**Extra fields populated when their flags are ON** (default to "off" values otherwise):

| Field | Type | Default | Populated by |
|-------|------|---------|--------------|
| `pushed` | `bool` | `false` | `node_push` (`AUTOCODE_PUSH_ON_COMMIT=1`). |
| `pr_number` | `int` | `0` | `node_create_pr` (`AUTOCODE_OPEN_PR=1`). |
| `pr_url` | `str` | `""` | `node_create_pr` (`AUTOCODE_OPEN_PR=1`). |
| `branch` | `str` | `""` | `node_write_plan` (always set: `autocode/{slug}-{tid_suffix}`). |
| `swarm_verdict` | `dict` | `{}` | `node_systematic_debug` when `AUTOCODE_SWARM_DEBUG=1`. Shape: `{fix, root_cause, defense_notes, confidence, agreement, providers}`. |
| `subagent_verdict` | `dict` | `{}` | `node_systematic_debug` when `AUTOCODE_SUBAGENT_DEBUG=1` OR parallel path's winner. Shape: `{fix, root_cause, defense_notes}`. |
| `parallel_verdicts` | `list[dict]` | `[]` | `node_systematic_debug` when `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`. ALL verdicts sorted by descending `hypothesis_confidence`. |
| `skill_path` / `skill_created` | `str` / `bool` | `""` / `false` | `node_create_skill` (create_skill mode). |

**Failure shape:**

```json
{"status": "failed", "result": "", "error": "Code generation failed: timeout",
 "artifacts": [], "commit_sha": "", "test_passed": false, "lint_passed": false}
```

### Status values

| `status` | Meaning | Next route |
|----------|---------|------------|
| `running` | In progress (default). | continues |
| `valid` | Input validation passed. | continues |
| `error` | Hard error (parse failure, missing file). | short-circuit to `node_run_pytest` (Hardening P1.5) or END |
| `needs_clarification` | LLM returned ambiguous output. | node skips (`{}`) |
| `failed` | Workflow failed. | END |
| `skipped` | Node skipped (e.g. prior dry_run). | continues |
| `dry_run` | `dry_run=True` — writes/commits/branches skipped. | continues |
| `success` | Workflow succeeded. | END |
| `awaiting_approval` | HiTL gate paused (v3.4). | END (resume with `hitl_approved=True`) |
| `audit_scan_complete` | `node_audit_scan` finished (v3.7). | continues to `node_audit_report` |

---

## 🗂️ State Fields (AutocodeState)

The workflow state is a `TypedDict(total=False)` defined in `workflows/autocode_impl/state.py`. Three categories:

| Category | Read via | Examples |
|----------|----------|---------|
| Core flat fields (14) | `state.get(key, default)` | `task`, `files`, `mode`, `trace_id`, `dry_run`, `hitl_approved`, `task_type`, `project_root`, `status`, `error`, `result`, `messages` |
| Sub-state fields (8 TypedDicts) | Accessor functions only | `plan_state.plan`, `tdd.debug_history`, `files_state.modified_files`, `impact.warnings`, `debug.root_cause`, `verify.passed`, `vcs.branch`, `memory.notes` |
| Ephemeral flat fields (14) | `state.get(key, default)` | `test_code` (list[str]), `test_results`, `_pytest_output`, `tests_passed`, `lint_output`, `lint_passed`, `llm_review_data`, `execution_notes`, `skill_path`/`skill_created`, `patch_errors`, `evidence_outputs`, `memory_context` |

**For TypedDict definitions, accessor signatures, the RMW pattern, and the full writer/reader node table, see [SUBSTATE.md](SUBSTATE.md).**

---

## 🛑 HiTL Approval Gate (v3.4)

Opt-in via `AUTOCODE_HITL_ENABLED=1`. Two gates: `node_hitl_gate` between `node_report` and `node_commit` (TDD path), and HiTL check at top of `node_create_skill`. When `cfg.autocode_hitl_enabled=True` AND `state["hitl_approved"]=False`, the gate saves a checkpoint (`save_checkpoint(tid, "hitl", state)`, wrapped in `try/except`), returns `{"status": "awaiting_approval"}`, routes to END. Resume with `run_workflow("autocode", goal="...", trace_id="...", resume=True, hitl_approved=True, ...)`. Checkpoint failure is non-fatal — the gate still pauses; only resume capability is lost. See [ARCHITECTURE.md](ARCHITECTURE.md) § Key Design Decision #6 for the async-checkpoint-resume vs sync-pause rationale.

---

## 🧬 Parallel Subagent Debug (v3.5 F1)

4th debug path inside `node_systematic_debug`. Opt-in via `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` (default OFF). Mutually exclusive with `AUTOCODE_SWARM_DEBUG` and `AUTOCODE_SUBAGENT_DEBUG` (chain: swarm → parallel subagent → single subagent → single-LLM, fall-through). Pipeline: planner LLM emits N hypotheses via `PARALLEL_HYPOTHESES_SYSTEM` → `ThreadPoolExecutor(max_workers=N)` dispatches one `agent(action="subagent")` per hypothesis using `SUBAGENT_VALIDATE_SYSTEM` → aggregate by descending `hypothesis_confidence` → store ALL verdicts in `debug.parallel_verdicts`, mirror winner into `debug.subagent_verdict`. Falls through on hypothesis-generation failure, all-subagents-failed, or `< 2` hypotheses.

---

## 🔒 Security

- **Path traversal** — `node_validate_input` checks user-supplied paths; LLM-generated paths (`patches[].path`, `new_files{}` keys) validated via `_is_path_safe()` (uses `Path.resolve().is_relative_to()`); skill names sanitized via `_sanitize_skill_name()`.
- **Secrets** — All 12 integration flags default OFF; every `vcs_ops.py` helper calls `_github_is_configured()` before any GitHub API call; `_call()` retries interruptible via `threading.Event`.
- **Atomic writes** — `node_write_new_files` uses `tempfile` + `os.replace` + `FileLock`; `node_create_skill` adds `importlib` smoke-test (deletes broken file on import failure).
- **LLM JSON** — All LLM JSON parsed via `_parse_json()` (delegates to `core/json_extract.py`).
- **`vcs_ops.py` encapsulation** — helpers are private to autocode nodes; external code MUST call `tools.github` / `tools.git` / `tools.swarm`.

---

## 📝 Error Handling

| Category | Example | Handling |
|----------|---------|----------|
| LLM failure | `_call()` exhausted retries | Node falls back to default or returns `{"status": "error", "error": ...}`. |
| JSON parse failure | LLM returned non-JSON / fenced JSON | `_parse_json()` returns `{}`; node logs warning + uses defaults. |
| Subprocess failure | `pytest` / `ruff` / `git` non-zero | Captured as structured return; workflow continues (lint is advisory). |
| GitHub API failure | `_github_pr_create()` raised | Graceful-skip via `is_configured()` guard. |
| Path traversal | LLM returned `../../etc/passwd` | `_is_path_safe()` returns `False`; path added to `patch_errors`. |
| Timeout | `invoke_with_timeout()` exceeded | `request_cancellation()` → `_call()` retries abort; subprocesses bounded to ≤1s past deadline via `_remaining_timeout()`. |
| Crashed | Node raised unhandled exception in daemon thread | Surfaced as `"Autocode graph crashed: <exception>"` (distinct from timeout). |
| Max retries exceeded | `iteration > max_retries` | `tdd_status="max_retries_exceeded"` + procedural memory store. If `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, routes to `node_swarm_fallback`. |
| Stuck detection | Same error signature on consecutive iterations | `route_after_run_tests` routes `"stuck"` → `node_run_pytest`. |
| Architecture-question exit | 3+ consecutive `tests_passed=False` (different errors) | `tdd_status="max_retries_exceeded"` + procedural memory store. |

**Tracing:** Every node calls `tracer.step(tid, ...)` for graceful events + `tracer.error(tid, category, message)` (3 args) for failures.

**`_call()` retry mechanism:** `_call(role, system, user, ..., retries=2, trace_id="")` loops `retries + 1` times with exponential backoff (`2 ** attempt` seconds). Backoff is interruptible via `threading.Event.wait(timeout=...)`. Returns `""` on exhausted retries.

---

*Last updated: 2026-07-19 (v3.8). See [CHANGELOG.md](CHANGELOG.md) for version history.*
