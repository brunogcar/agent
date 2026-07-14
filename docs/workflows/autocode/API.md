<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 API Reference

This file documents the autocode workflow **facade** + **graph overview** +
**output format** + **state fields** + **state accessors**. For the per-node
reference (Purpose / Logic / Output / Notes for each of the 28 nodes), see
[NODES.md](NODES.md).

---

## 🚀 Facade — `run_autocode_agent()`

The autocode workflow is invoked through the shared `run_workflow()` facade in
`workflows/base.py`. The autocode-specific facade `run_autocode_agent()` (in
`workflows/autocode.py`) is a thin wrapper that delegates to
`run_workflow("autocode", ...)` for tracing, checkpointing, and timeout.

```python
from workflows.autocode import run_autocode_agent

result = run_autocode_agent(
    goal="Fix the timeout handling in web search",
    mode="fix_error",                        # fix_error | improve | add_feature | create_skill | unclear
    error_msg="TimeoutError: Request timed out after 30 seconds",
    files={"web.py": "..."},
    trace_id="autocode_001",
)
```

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `goal` | `str` | (required) | Natural-language description of the task. |
| `mode` | `str` | `"fix_error"` | One of `fix_error`, `improve`, `add_feature`, `create_skill`, `unclear`. Overrides LLM classification if set. |
| `error_msg` | `str` | `""` | Error message (for `fix_error` mode). |
| `feature_desc` | `str` | `""` | Feature description (for `add_feature` mode). |
| `files` | `dict[str, str]` | `{}` | Initial file contents keyed by relative path. Pass `{"all changed": ""}` + `git_diff=True` for multi-file git-diff input (#46). |
| `git_diff` | `bool` | `False` | If True, `files` values are interpreted as git-diff snippets (#46). |
| `dry_run` | `bool` | `False` | If True, skip writes / commits / branches (#47 dry-run guards). |
| `trace_id` | `str` | (required) | Trace correlation ID. |

**Return value:** `dict` — see [📤 Output](#-output) below.

**Facade contract:** `run_autocode_agent()` MUST delegate to `run_workflow("autocode", ...)` — never call `get_graph().compile().invoke()` directly (the facade was broken for 2 versions because of this; see INSTRUCTIONS.md NEVER DO #14, #15, #17).

**Cancellation flag wiring:** `invoke_with_timeout()` (in `base.py`, called from the facade) calls `clear_cancellation()` at start and `request_cancellation()` on timeout — the in-flight `_call()` retries in `helpers.py` notice and abort instead of sleeping through exponential backoff. **[Hardening P0.3]** graph exceptions in the daemon thread are surfaced as `"Autocode graph crashed: <exception>"` (was swallowed as timeout). Full process-level termination deferred to post-2.0.

---

## 🗺️ Graph Overview

The autocode workflow is a **28-node LangGraph StateGraph** (25 active + 3 backward-compat wrappers — wrappers registered via `add_node(...)` for `import`-compatibility but NOT wired; excluded from `WORKFLOW_METADATA["nodes"]` so MCP clients render only the 27 active-node entries). The 3 wrappers (`node_write_files` / `node_verify` / `node_publish`) are KEPT for test compatibility — removal deferred to post-2.0.

| # | Node | Type | Phase | Purpose |
|---|------|------|-------|---------|
| 1 | `node_classify_task` | llm (router) | 1 | Classify task type from goal |
| 2 | `node_validate_input` | logic | 2 | Validate input files + path safety |
| 3 | `node_brainstorm` | llm (planner) | 3 | Brainstorm spec tailored to task type |
| 4 | `node_write_plan` | llm (planner) | 4 | Write structured plan with acceptance criteria |
| 5 | `node_git_branch` | tool (git) | 5 | Create git branch for the task |
| 6 | `node_write_tests` | llm (executor) | 6 | Write TDD tests before implementation |
| 7 | `node_execute_step` | llm (executor) | 7 | Generate implementation code from plan |
| 8 | `node_apply_patches` | tool (file) | 8a | Apply str_replace patches to existing files |
| 9 | `node_write_new_files` | tool (file) | 8b | Write new/overwrite files atomically + build files_map |
| 10 | `node_persist_artifacts` | tool (file) | 8c | Persist test file + generated code + debug log to run_dir |
| 11 | `node_analyze_impact` | llm (analyze) | 9 | Blast radius analysis using dependency graph |
| 12 | `node_run_tests` | tool (pytest) | 10 | Run TDD tests via pytest subprocess |
| 13 | `node_systematic_debug` | llm (executor) | 11 | 4-phase debug: investigation → pattern → hypothesis → fix |
| 14 | `node_summarize_context` | logic | 11a | Compress debug_history before re-entering loop |
| 15 | `node_run_pytest` | tool (pytest) | 12a | Fresh pytest on autocode test files |
| 16 | `node_run_lint` | tool (ruff) | 12b | Ruff lint on modified files only |
| 17 | `node_llm_review` | llm (executor) | 12c | LLM spec coverage + cleanliness review |
| 18 | `node_verify_decision` | logic | 12d | Compose results + hallucination guard |
| 19 | `node_report` | llm (summarize) | 13 | Generate structured report of what was done |
| 20 | `node_commit` | tool (git) | 14 | Commit changes to the git branch |
| 21 | `node_push` | tool (github) | 15a | Push branch to remote |
| 22 | `node_create_pr` | tool (github) | 15b | Create pull request from branch |
| 23 | `node_merge_pr` | tool (github) | 15c | Auto-merge PR (if enabled) |
| 24 | `node_distill_memory` | llm (planner) | 16 | Distill procedural memory for future runs |
| 25 | `node_create_skill` | tool (file) | 17 | Generate a new skill file (bypasses TDD, has AST validation) |
| — | `node_write_files` | composite | wrapper | Backward-compat wrapper (not wired) — calls `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` |
| — | `node_verify` | composite | wrapper | Backward-compat wrapper (not wired) — calls the 4 split verify nodes |
| — | `node_publish` | tool (github) | wrapper | Backward-compat wrapper (not wired) — calls `node_push` → `node_create_pr` → `node_merge_pr` |

**Loops:**

- **`debug_loop`** — `node_systematic_debug` → `node_summarize_context` →
  `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` →
  `node_analyze_impact` → `node_run_tests` → (back to `node_systematic_debug`
  until tests pass, `MAX_RETRIES` exceeded, `tdd_status="stuck"`, OR the
  architecture-question exit fires — see NODES.md § `node_systematic_debug`).

**Conditional routes:**

- `route_after_classify` — `feature`/`fix`/`refactor`/`edit`/`audit` → `node_brainstorm`; `create_skill` → `node_create_skill` (bypasses TDD).
- `route_after_write_files` — `fix`/`refactor`/`improve`/`feature`/`audit`/`edit` → `node_analyze_impact`; other → `node_run_pytest`. **[Hardening P1.5]** short-circuits to `node_run_pytest` when `status=="error"`.
- `route_after_run_tests` — `pass` → `node_run_pytest`; `fail` → `node_systematic_debug`; `stuck` → `node_run_pytest` (skips doomed debug). **[Hardening P1.5]** short-circuits on `status=="error"`.
- `route_after_verify` — `pass` → `node_report`; `fail` → `node_systematic_debug` (re-enter debug loop).

For the per-node reference (Purpose / Logic / Output / Notes / Source), see
[NODES.md](NODES.md). For the mermaid diagram + module tree, see
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "Code changes applied successfully: Added retry logic to web search",
  "error": "",
  "artifacts": ["web.py", "test_web.py"],
  "commit_sha": "abc123",
  "test_passed": true,
  "lint_passed": true
}
```

**Additional fields when GitHub + Swarm + Subagent integration is enabled** (all default to their "off" values when the corresponding flags are OFF):

```json
{
  "pushed": false,
  "pr_number": 0,
  "pr_url": "",
  "swarm_verdict": {},
  "subagent_verdict": {}
}
```

| Field | Type | Default | When populated |
|-------|------|---------|----------------|
| `pushed` | `bool` | `false` | Set by `node_push` — `true` if `_github_push()` succeeded. |
| `pr_number` | `int` | `0` | Set by `node_create_pr` — the PR number from `_github_pr_create()`. |
| `pr_url` | `str` | `""` | Set by `node_create_pr` — the PR HTML URL from `_github_pr_create()`. |
| `swarm_verdict` | `dict` | `{}` | Set by `node_systematic_debug` when `AUTOCODE_SWARM_DEBUG=1` and swarm returned a verdict. Shape: `{fix, root_cause, defense_notes, confidence: "HIGH"\|"MEDIUM"\|"LOW", agreement, providers}`. |
| `subagent_verdict` | `dict` | `{}` | Set by `node_systematic_debug` when `AUTOCODE_SUBAGENT_DEBUG=1` and the subagent dispatch returned a verdict. Shape: `{fix, root_cause, defense_notes}` (single isolated dispatch — no consensus/agreement). Falls back to single-LLM on subagent failure. |
| `branch` | `str` | `""` | Set by `node_write_plan`. Includes `trace_id` suffix for uniqueness. |

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Code generation failed: timeout",
  "artifacts": [],
  "commit_sha": "",
  "test_passed": false,
  "lint_passed": false
}
```

---

## 🗂️ State Fields (AutocodeState)

The workflow state is a `TypedDict(total=False)` defined in
`workflows/autocode_impl/state.py`. **[v3.0]** All sub-state fields live in
8 typed sub-state dicts (`plan_state`, `tdd`, `files_state`, `impact`, `debug`,
`verify`, `vcs`, `memory`) — the legacy flat-field mirrors were removed.
Accessors are the ONLY read path for sub-state fields; ephemeral flat fields
are read directly via `state.get(key, default)`.

**For the complete sub-state reference** — TypedDicts, writer/reader node lists, the RMW pattern, migration history — **see [SUBSTATE.md](SUBSTATE.md).**

### Core flat fields (read directly via `state.get(key, default)`)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `task` | `str` | `""` | Natural-language goal (set by facade). |
| `files` | `dict[str, str]` | `{}` | Initial file contents keyed by relative path. |
| `mode` | `str` | `""` | `fix_error` / `improve` / `add_feature` / `create_skill` / `unclear`. |
| `target_file` | `str` | `""` | Optional target file path. |
| `trace_id` | `str` | `""` | Trace correlation ID. |
| `dry_run` | `bool` | `False` | Skip writes / commits / branches when `True`. |
| `task_type` | `str` | `""` | Classified task type (`feature`/`audit`/`edit`/`fix`/`refactor`/`create_skill`/`unclear`). |
| `project_root` | `str` | `""` | Workspace root for path resolution. |
| `autocode_run_path` | `str` | `""` | Per-run output directory. |
| `messages` | `list[AnyMessage]` | `[]` | LangGraph message reducer (annotated). |
| `status` | `str` | `"running"` | Workflow status (`running`/`success`/`failed`/etc.). |
| `error` | `str` | `""` | Error message on failure. |
| `result` | `str` | `""` | Final result string on success. |

### Sub-state fields (read via accessors ONLY — see [🧭 State Accessors](#-v30-state-accessors) below)

| Sub-state key | TypedDict | Representative fields | Accessor |
|---------------|-----------|----------------------|----------|
| `plan_state` | `PlanState` | `brainstorm_notes`, `plan`, `plan_accepted`, `spec`, `current_step` | `_get_plan` |
| `tdd` | `TDDState` | `iteration`, `source_code`, `error`, `status`, `max_retries`, `last_test_error`, `tests_written`, `debug_history`, `debug_summary` | `_get_tdd` |
| `files_state` | `FilesState` | `files_map`, `modified_files` (`input_files` removed in v3.0) | `_get_files` |
| `impact` | `ImpactState` | `warnings`, `targeted_test_cmd`, `failed` | `_get_impact` |
| `debug` | `DebugState` | `notes`, `root_cause`, `defense_notes`, `swarm_verdict`, `subagent_verdict` | `_get_debug` |
| `verify` | `VerifyState` | `notes`, `report`, `passed` | `_get_verify` |
| `vcs` | `VCSState` | `commit_sha`, `branch`, `branch_name`, `pushed`, `pr_number`, `pr_url` | `_get_vcs` |
| `memory` | `MemoryState` | `notes`, `context` | `_get_memory` |

> **Note:** `input_files` was removed from `FilesState` in v3.0 — it was just a mirror of the core `files` flat field. `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly.

### Ephemeral flat fields (read directly via `state.get(key, default)`)

**[v3.0]** Ephemeral flat fields stay flat — they're inter-node scratch space, not part of any sub-state. See [SUBSTATE.md](SUBSTATE.md) § "Ephemeral Flat Fields" for the full table.

| Field | Set by | Read by | Purpose |
|-------|--------|---------|---------|
| `test_code` | `node_write_tests` | `node_persist_artifacts` | Generated test code (joined `"\n\n"` if list). |
| `test_files` | `node_persist_artifacts` | `node_run_pytest`, `node_run_tests` | Relative paths of test files. |
| `test_results` | `node_run_pytest`, `node_run_tests` | `node_debug`, `node_verify_decision`, `node_report`, `_shape_artifacts` | `{success, stdout, stderr, returncode}`. Removed from `TDDState` in v3.0. |
| `_pytest_output` | `node_run_pytest` | `node_llm_review`, `node_verify_decision` | First 2000 chars of pytest stdout+stderr. |
| `tests_passed` | `node_run_pytest`, `node_run_tests` | `node_verify_decision`, `node_llm_review` | Boolean test-pass status. |
| `lint_output` | `node_run_lint` | `node_llm_review`, `node_verify_decision` | First 500 chars of ruff stdout+stderr. |
| `lint_passed` | `node_run_lint` | `node_verify_decision` | `None` when ruff unavailable. |
| `llm_review_data` | `node_llm_review` | `node_verify_decision` | `{automated_checks_passed, checks, summary}`. |
| `execution_notes` | `node_execute_step` | (downstream) | Per-step execution notes. |
| `skill_path` | `node_create_skill` | `_shape_artifacts` | Path to created skill file. |
| `skill_created` | `node_create_skill` | `_shape_artifacts` | Skill creation success flag. |
| `patch_errors` | `node_apply_patches` | (downstream) | Path-traversal blocks + missing-file + apply failures. |
| `evidence_outputs` | `node_verify_decision` | `_shape_artifacts` | `{tests, lint, regression}` (truncated). |
| `memory_context` | `node_brainstorm` | (downstream) | KG-recalled memory context. |

For the full field list, see `workflows/autocode_impl/state.py`.

---

## 🧭 [v3.0] State Accessors

**[v3.0]** All 8 accessors are the ONLY read path for sub-state fields. Each is a 4-line sub-state-only read — no legacy fallback. For the full accessor reference (signatures, RMW pattern, writer/reader node lists), see [SUBSTATE.md](SUBSTATE.md).

> **[v3.0] All 8 accessors are safe and are the ONLY path.** Use them for any
> sub-state field read (`_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`,
> `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`). For ephemeral flat
> fields (test_results, test_code, _pytest_output, lint_output, etc.), use
> `state.get(key, default)` directly. See INSTRUCTIONS.md NEVER DO #33 +
> ALWAYS DO #29.

### The 8 accessor functions

| Function | Sub-state TypedDict | Reads from |
|----------|---------------------|------------|
| `_get_plan(state, key, default=None)` | `PlanState` | `state["plan_state"]` dict (NOT `state["plan"]` — that's the legacy `list[dict]` step list) |
| `_get_tdd(state, key, default=None)` | `TDDState` | `state["tdd"]` dict |
| `_get_files(state, key, default=None)` | `FilesState` | `state["files_state"]` dict |
| `_get_impact(state, key, default=None)` | `ImpactState` | `state["impact"]` dict |
| `_get_debug(state, key, default=None)` | `DebugState` | `state["debug"]` dict |
| `_get_verify(state, key, default=None)` | `VerifyState` | `state["verify"]` dict |
| `_get_vcs(state, key, default=None)` | `VCSState` | `state["vcs"]` dict |
| `_get_memory(state, key, default=None)` | `MemoryState` | `state["memory"]` dict |

**Signature (all 8 accessors share this 4-line shape — no legacy fallback):**

```python
def _get_vcs(state: dict, key: str, default: Any = None) -> Any:
    """Read `key` from state["vcs"] if present, else return `default`."""
    sub = state.get("vcs")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default
```

### Usage in nodes

Every node that reads a sub-state field MUST use the corresponding accessor.
Example: `node_git_commit` reads the branch name via `_get_vcs(state, "branch", "")`
instead of the legacy `state.get("branch", "")`:

```python
# [v3.0] accessor read — sub-state is the ONLY storage
from workflows.autocode_impl.state import _get_vcs
branch = _get_vcs(state, "branch", "") or "main"

# [v3.0] ephemeral flat field — read directly (no accessor)
test_results = state.get("test_results", {})
```

**[v3.0]** All nodes that read sub-state fields have been migrated: routes.py
(2 reads), autocode.py `_shape_artifacts` (5 reads), and 11 node files (tdd_*,
debug_notes, root_cause, modified_files, etc.). The v2.0.5 split-brain warning
is lifted — there is no flat fallback to be split-brained against.

### RMW pattern (write side)

LangGraph replaces dict values, doesn't deep-merge. Returning `{"vcs": {"pushed": True}}` clobbers every other `vcs` field. Always do read-modify-write:

```python
current_vcs = dict(state.get("vcs", {}))           # 1. READ (shallow copy)
current_vcs["pushed"] = success                    # 2. MODIFY (on the copy)
return {"vcs": current_vcs}                        # 3. WRITE (return partial)
```

See [SUBSTATE.md](SUBSTATE.md) § "RMW Pattern" for full pattern + variants.

### `helpers._write_files()` — DELETED

The `helpers._write_files()` function is **DELETED as of v2.0 GA (Phase 7.2)**.
A dead-code audit found it was never called by any node — `execute.py` imported
it but never used the import. The `helpers.py` source now carries a single
comment in its place:

```
# [v2.0] Phase 7: _write_files() DELETED — was dead code (never called by any node).
# The actual file writing logic lives in nodes/apply_patches.py + nodes/write_new_files.py.
```

- **DELETED, not deprecated:** Code that imports `helpers._write_files` will now `ImportError`.
- **Use the split nodes instead:** `node_apply_patches` (for `str_replace` patches) + `node_write_new_files` (for new-file writes) + `node_persist_artifacts` (for run-dir artifact persistence). See NEVER DO #38 + #39 in INSTRUCTIONS.md.
- **No behavior change:** The function was unreachable before deletion.

### `vcs_ops.py` — Unified VCS module

The `workflows/autocode_impl/vcs_ops.py` module is the **single source of truth
for all VCS helpers**. It merges the former `git_ops.py` (local operations) +
`github_ops.py` (remote operations) into one module, organized in 3 sections:

1. **Local operations** — `_git_commit()`, `_git_create_branch()`
2. **Remote operations** — `_github_pull()`, `_github_push()`, `_github_pr_create()`, `_github_pr_comment()`, `_github_pr_merge()`
3. **Swarm integration** — `_swarm_debug_consensus()`

All lazy imports, `is_configured()` guards, `tracer.step` logging, and
structured returns are preserved. `git_ops.py` + `github_ops.py` are kept as
thin re-export wrappers so existing imports still work. **New code MUST import
from `vcs_ops.py` directly** — see INSTRUCTIONS.md ALWAYS DO #37.

### `debug_history` field — written by `node_systematic_debug`, read by `node_summarize_context`

`debug_history` is the within-run debug-loop history that closes the #37 prerequisite (context summarization):

**Three debug paths** (mutually exclusive — see INSTRUCTIONS.md NEVER DO #40):

1. **Single-LLM (default)** — `node_systematic_debug` calls `_call()` directly with the 4-phase `DEBUG_SYSTEM` prompt. No flag required.
2. **Swarm** (`AUTOCODE_SWARM_DEBUG=1`) — `node_systematic_debug` calls `_swarm_debug_consensus()` which dispatches to 2+ providers, then votes (confidence HIGH/MEDIUM/LOW). Non-blocking: the fix is applied regardless of confidence.
3. **Subagent** (`AUTOCODE_SUBAGENT_DEBUG=1`, v2.0.2) — `node_systematic_debug` calls `agent(action="subagent", role="planner")` with isolated curated context (failing test + error output + current source + truncated prior fix attempts). Subagent does NOT see autocode session state. Non-blocking: falls back to single-LLM on subagent failure.

All three paths populate `debug_history` (with `phase` set accordingly: `investigation`/`pattern`/`hypothesis`/`fix` for single-LLM, `swarm` for swarm, `subagent` for subagent).

- **POPULATED** by `node_systematic_debug` on every iteration: `{iteration, phase, root_cause, fix (truncated to 200 chars), tests_passed: bool}` (`tests_passed=False` when the entry is created — `run_tests` updates it to `True` on the next loop iteration if the fix worked). **[Hardening P0.2]** `run_tests` now correctly marks the last entry's `tests_passed=True`. Swarm-path entries use `phase="swarm"` and include `confidence`. Subagent-path entries use `phase="subagent"`.
- **CONSUMED** by `node_systematic_debug`: last 5 entries are injected into the LLM user prompt under a `--- PRIOR DEBUG ATTEMPTS (do NOT repeat these) ---` block so the LLM doesn't repeat failed hypotheses/fixes.
- **CONSUMED** by `node_summarize_context`: reads `debug_history` and compresses it into `debug_summary` via chonkie `SentenceChunker` (soft dep, lazy import) before re-entering the loop.
- **Architecture-question exit:** `node_systematic_debug` reads the last 3 entries — if all have `tests_passed=False`, it bails with `tdd_status="max_retries_exceeded"` + procedural memory store. Different from #39 stuck detection (same error repeating) — this fires when DIFFERENT errors occur each iteration.
- **Preserved on early exit:** Both early-exit paths (architecture + max_retries) return `"tdd": {"debug_history": debug_history}` so the full history is available for downstream inspection / procedural memory store.
- **Accessor:** `_get_tdd(state, "debug_history", [])` reads from the TDD sub-state dict (sub-state is the ONLY storage since v3.0 — no legacy fallback).

`# TODO(2.0-post):` Cross-run learning (procedural memory recall before debug) is still pending — see CHANGELOG.md § "Future Tracks (Post-2.0)" F5.

### `debug_summary` field — written by `node_summarize_context`, consumed by `node_systematic_debug`

`debug_summary: str` in `TDDState` holds the compressed `debug_history` string
produced by `node_summarize_context`:

- **WRITTEN** by `node_summarize_context`: reverses history (most recent first), renders each entry as a single sentence, tries `chonkie.SentenceChunker(chunk_size=512)`, returns the FIRST chunk. On any exception falls back to `json.dumps(last_3_entries)`.
- **[Hardening P2] CONSUMED** by `node_systematic_debug`: when `debug_history` grows past 5 entries, the LLM user prompt replaces the raw last-5-entries block with a "DEBUG SUMMARY (compressed)" block containing the summary string. Keeps LLM context bounded (#37) in long-running debug loops.
- **Empty when history is empty:** First debug iteration (no prior attempts) → `node_summarize_context` returns `{"tdd": {"debug_summary": ""}}`.
- **Accessor:** `_get_tdd(state, "debug_summary", "")` reads from the TDD sub-state dict (sub-state is the ONLY storage since v3.0 — no legacy fallback).

---

## 🔒 Security

**[v3.0] Sub-state architecture is a security improvement — no more split-brain.**
Before v3.0, sub-state fields had flat-field mirrors that could drift out of sync (writer updated one, reader read the other). The v2.0.5 split-brain bug in `commit.py` (`_get_vcs(state, "branch", "main")` returning stale `""` instead of the actual branch) was the proof. v3.0 removed the flat-field mirrors entirely — every read goes through the accessor, every write goes through RMW, there is no second source of truth to drift.

### Path traversal protection
- **User-supplied paths:** `node_validate_input` checks `target_file` + `files` keys.
- **LLM-generated paths:** `patches[].path` + `new_files{}` keys are validated via `_is_path_safe(base_path, rel_path)` in `apply_patches.py` (imported by `write_new_files.py`). Uses `Path.resolve().is_relative_to()`.
- **Skill names:** `_sanitize_skill_name()` strips non-`[a-zA-Z0-9_]` chars (prevents `/` or `\` path traversal).

### Secret handling
- All 7 GitHub/Swarm/Subagent config flags (`AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`, `AUTOCODE_SUBAGENT_DEBUG`) default **OFF** — backward compat (with all OFF, autocode behaves identically to v1.2).
- `is_configured()` guard: every `vcs_ops.py` helper MUST call `_github_is_configured()` (wraps `tools.github_ops.client.is_configured()`) before any GitHub API call. Missing `GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` → graceful-skip (returns `False`/`None`, workflow continues).
- `_call()` retries are interruptible via `threading.Event` — secrets/credentials are never logged.

### Atomic writes
- `node_write_new_files` uses `tempfile.NamedTemporaryFile` + `os.replace` + `FileLock` (1 retry on timeout).
- `node_create_skill` uses `tempfile.NamedTemporaryFile` + `os.replace` (was direct `write_text` — crash mid-write corrupted the skill file).

### LLM JSON parsing
- All LLM-generated JSON is parsed via `_parse_json()` (in `helpers.py`) which delegates to `core/json_extract.py`. Handles markdown fences (```` ```json ... ``` ````), partial JSON, and trailing content. Never use raw `json.loads()` on LLM output — see INSTRUCTIONS.md NEVER DO #24.

### vcs_ops.py encapsulation
- `vcs_ops.py` helpers (`_git_*`, `_github_*`, `_swarm_debug_consensus`) are **private to the autocode workflow nodes**. External code MUST call the public `tools.github` / `tools.git` / `tools.swarm` facades (see INSTRUCTIONS.md NEVER DO #22).

---

## 📝 Error Handling

The workflow uses a `status` field on `AutocodeState` to track workflow-level state. Nodes return partial dicts with `status` + `error` to signal failure; LangGraph routes via `route_after_*` functions.

### Status values

| `status` value | Meaning | Set by | Next route |
|----------------|---------|--------|------------|
| `"running"` | Default — workflow in progress. | `_default_state()` | continues |
| `"valid"` | Input validation passed. | `node_validate_input` | continues |
| `"error"` | Hard error (parse failure, missing file, etc.). | Various | short-circuit: `route_after_*` routes to `node_run_pytest` (Hardening P1.5) or END |
| `"needs_clarification"` | LLM returned ambiguous output. | Various | node skips (`{}` return) |
| `"failed"` | Workflow failed. | `node_verify_decision`, `node_push`, etc. | END |
| `"skipped"` | Node skipped (e.g., `node_create_skill` when not applicable). | Various | continues |
| `"dry_run"` | `dry_run=True` — writes/commits/branches skipped. | `node_apply_patches`, `node_push` | continues |
| `"success"` | Workflow succeeded. | terminal node | END |

### Error categories

| Category | Example | Handling |
|----------|---------|----------|
| **LLM failure** | `_call()` exhausted retries, returned `""` | Node falls back to default (e.g., `task_type="unclear"`) or returns `{"status": "error", "error": ...}`. |
| **JSON parse failure** | LLM returned non-JSON or markdown-fenced JSON | `_parse_json()` returns `{}`; node logs warning + uses defaults. |
| **Subprocess failure** | `pytest` / `ruff` / `git` returned non-zero | Captured as structured return; workflow continues (lint is advisory). |
| **GitHub API failure** | `_github_pr_create()` raised | Graceful-skip: `is_configured()` returns `False` → helper returns `None`/`False`. |
| **Path traversal** | LLM returned `../../etc/passwd` | `_is_path_safe()` returns `False`; path added to `patch_errors`. |
| **Timeout** | `invoke_with_timeout()` exceeded `cfg.autocode_graph_timeout` | `request_cancellation()` → `_call()` retries abort; status set to `"Autocode graph crashed: <exception>"` (Hardening P0.3). |
| **Max retries exceeded** | `iteration > max_retries` in debug loop | `tdd_status="max_retries_exceeded"` + procedural memory store; verify chain returns `"failed"`. |
| **Stuck detection** | Same error signature on consecutive debug iterations | `route_after_run_tests` routes `"stuck"` → `node_run_pytest` (skips doomed debug). |
| **Architecture-question exit** | 3+ consecutive `tests_passed=False` (different errors each iteration) | `tdd_status="max_retries_exceeded"` + procedural memory store (different from stuck — fires on architectural bug). |

### Tracing
- Every node should call `tracer.step(tid, ...)` for graceful events + `tracer.error(tid, category, message)` (3 args — see NEVER DO #29) for failures.
- `trace_id` is mandatory on every tracer call (INSTRUCTIONS.md ALWAYS DO).
- `_call()` retry-exhaustion errors now include `trace_id` (Hardening P3-1).

---

*Last updated: 2026-07-14 (v3.0 — flat-field removal, Track M1 ✅ COMPLETE, accessor legacy-fallback branches removed, ephemeral flat fields explicitly declared; v2.0.2 — subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
