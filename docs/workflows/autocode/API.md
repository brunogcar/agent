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
`workflows/autocode_impl/state.py`. The most relevant fields for callers and
future editors:

**GitHub + Swarm + Subagent integration fields:**

| Field | Type | Default | Source node | Purpose |
|-------|------|---------|-------------|---------|
| `pushed` | `bool` | `False` | `node_push` | Whether the branch was pushed to `origin`. |
| `pr_number` | `int` | `0` | `node_create_pr` | PR number (0 = no PR created). |
| `pr_url` | `str` | `""` | `node_create_pr` | PR HTML URL. |
| `swarm_verdict` | `dict` | `{}` | `node_systematic_debug` | Swarm consensus + vote result. |
| `subagent_verdict` | `dict` | `{}` | `node_systematic_debug` | Subagent dispatch result (single isolated LLM call with curated context). |

**Debug loop fields (Phase 4):**

| Field | Type | Default | Source node | Purpose |
|-------|------|---------|-------------|---------|
| `debug_history` | `list[dict]` | `[]` | `node_systematic_debug` | Within-run debug-loop history. Each entry: `{iteration, phase, root_cause, fix (truncated to 200 chars), tests_passed}`. Swarm-path entries use `phase="swarm"` and include `confidence`. |
| `debug_summary` | `str` | `""` | `node_summarize_context` | Compressed `debug_history` string. Reverses history (most recent first), renders each entry as a sentence, returns first chonkie `SentenceChunker(chunk_size=512)` chunk (or JSON-of-last-3-entries fallback if chonkie unavailable). **[Hardening P2]** consumed by `node_systematic_debug` prompt when `debug_history` > 5 entries (was written but never read). |

For the full field list, see `workflows/autocode_impl/state.py`.

---

## 🧭 [v2.0] State Accessors

The v2.0 refactor introduced a backward-compatible accessor layer over
`AutocodeState`. Each accessor reads from the corresponding sub-state dict if
present, else falls back to the legacy flat field. See ARCHITECTURE.md §
"[v2.0] Sub-state Architecture" for the design rationale.

> **⚠️ [v2.0.5] Only `_get_tdd` is safe to use today.** The other 7 accessors
> (`_get_plan`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`,
> `_get_vcs`, `_get_memory`) are **migration scaffolding that return stale
> sub-state defaults** because nodes write to flat fields, not sub-state dicts.
> Only `tdd` is actively maintained by nodes (via read-modify-write). The
> split-brain trap: `_get_vcs(state, "branch", "main")` returns `""` (the
> sub-state default), not the actual branch name (which lives in the flat
> `branch` field). **For all non-`tdd` reads, use `state.get(key, default)`
> directly.** Full migration is the v2.x → v3.0 roadmap (see CHANGELOG Future
> Tracks). See INSTRUCTIONS.md NEVER DO #33 + ALWAYS DO #44.

### The 8 accessor functions

| Function | Sub-state TypedDict | Reads from | Legacy fallback fields |
|----------|---------------------|------------|------------------------|
| `_get_plan(state, key, default=None)` | `PlanState` | `state["plan_state"]` dict (NOT `state["plan"]` — that's overloaded as `list[dict]` step list) | `task_type`, `plan`, `branch`, `current_step` |
| `_get_tdd(state, key, default=None)` | `TDDState` | `state["tdd"]` dict | `test_code`, `test_results`, `tdd_status`, `tdd_iteration`, `debug_history`, `debug_summary` |
| `_get_files(state, key, default=None)` | `FilesState` | `state["files_state"]` dict | `files`, `modified_files`, `written_files`, `files_map` |
| `_get_impact(state, key, default=None)` | `ImpactState` | `state["impact"]` dict | `impact_warnings`, `blast_radius_note` |
| `_get_debug(state, key, default=None)` | `DebugState` | `state["debug"]` dict | `root_cause`, `defense_notes`, `tdd_source_code`, `debug_notes`, `swarm_verdict` |
| `_get_verify(state, key, default=None)` | `VerifyState` | `state["verify"]` dict | `lint_passed`, `lint_output`, `regression_passed`, `evidence_outputs`, `verification_passed`, `verification_notes` |
| `_get_vcs(state, key, default=None)` | `VCSState` | `state["vcs"]` dict | `branch`, `commit_sha`, `pushed`, `pr_number`, `pr_url` |
| `_get_memory(state, key, default=None)` | `MemoryState` | `state["memory"]` dict | `brainstorm`, `skill_path`, `skill_created` |

**Signature (all 8 accessors share this shape):**

```python
def _get_vcs(state: dict, key: str, default=None):
    """Read `key` from state["vcs"] if present, else fall back to state[key]."""
    vcs = state.get("vcs")
    if isinstance(vcs, dict) and key in vcs:
        return vcs[key]
    return state.get(key, default)
```

### Usage in nodes

`node_git_commit` is the proof-of-concept. It reads the branch name via
`_get_vcs(state, "branch", "main")` instead of `state.get("branch", "main")`:

```python
# Before (v1.4):
branch = state.get("branch", "main")

# After (v2.0):
from workflows.autocode_impl.state import _get_vcs
branch = _get_vcs(state, "branch", "main")
```

`node_systematic_debug` and `node_summarize_context` are also migrated to
accessors. `node_git_commit` was migrated as a proof-of-concept, **[v2.0.5]
but the `_get_vcs` call was broken (split-brain) and has been reverted to
direct `state.get("branch")` reads** (see CHANGELOG v2.0.5 P1-1). The remaining
nodes still use the legacy `state.get(...)` pattern; full migration is the
v2.x → v3.0 roadmap (see CHANGELOG Future Tracks).

### Ephemeral fields (not in TypedDict)

| Field | Type | Set by | Read by | Purpose |
|-------|------|--------|---------|---------|
| `_pytest_output` | `str` | `node_run_pytest` (verify chain) | `node_llm_review`, `node_verify_decision` | Ephemeral — passes fresh pytest stdout+stderr between verify-chain nodes. Not persisted in `_default_state()`; not declared in `AutocodeState` TypedDict (intentional — it's scratch space for the verify sub-chain). |

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
from `vcs_ops.py` directly** — see INSTRUCTIONS.md ALWAYS DO #53.

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
- **Accessor:** `_get_tdd(state, "debug_history", [])` reads from the TDD sub-state dict if present, else falls back to the legacy flat field.

`# TODO(2.0-post):` Cross-run learning (procedural memory recall before debug) is still pending — see CHANGELOG.md § "Future Tracks (Post-2.0)" F5.

### `debug_summary` field — written by `node_summarize_context`, consumed by `node_systematic_debug`

`debug_summary: str` in `TDDState` holds the compressed `debug_history` string
produced by `node_summarize_context`:

- **WRITTEN** by `node_summarize_context`: reverses history (most recent first), renders each entry as a single sentence, tries `chonkie.SentenceChunker(chunk_size=512)`, returns the FIRST chunk. On any exception falls back to `json.dumps(last_3_entries)`.
- **[Hardening P2] CONSUMED** by `node_systematic_debug`: when `debug_history` grows past 5 entries, the LLM user prompt replaces the raw last-5-entries block with a "DEBUG SUMMARY (compressed)" block containing the summary string. Keeps LLM context bounded (#37) in long-running debug loops.
- **Empty when history is empty:** First debug iteration (no prior attempts) → `node_summarize_context` returns `{"tdd": {"debug_summary": ""}}`.
- **Accessor:** `_get_tdd(state, "debug_summary", "")` reads from the TDD sub-state dict if present, else falls back to the legacy flat field.

---

## 🔒 Security

*(Fill this section with relevant info from edits and refactors. Add security details as they are learned.)*

---

## 📝 Error Handling

*(Fill this section with relevant info from edits and refactors. Add error classification as it is learned.)*

---

*Last updated: 2026-07-12 (v2.0.2 — subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
