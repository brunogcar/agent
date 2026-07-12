<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 API Reference

This file documents the autocode workflow **facade** + **graph overview** +
**output format** + **state fields** + **state accessors**. For the per-node
reference (Purpose / Logic / Output / Notes for each of the 28 nodes), see
[NODES.md](NODES.md).

**[v2.0 GA] Phase 7.3 doc consolidation:** API.md was split — the bulky per-node
reference (was ~600 lines) moved to NODES.md so this file can focus on the
facade + state accessors + graph overview (~250 lines).

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

**[v1.1] Facade contract:** `run_autocode_agent()` MUST delegate to
`run_workflow("autocode", ...)` — never call `get_graph().compile().invoke()`
directly (the facade was broken for 2 versions because of this; see CHANGELOG.md
§ "Cross-LLM Review Findings (Pre-2.0)" and INSTRUCTIONS.md NEVER DO #14, #15, #17).

**[v2.0] Cancellation flag wiring:** `invoke_with_timeout()` (in `base.py`,
called from the facade) calls `clear_cancellation()` at start and
`request_cancellation()` on timeout — the in-flight `_call()` retries in
`helpers.py` notice and abort instead of sleeping through exponential backoff.
Partial mitigation for #35 (daemon-thread zombie risk); full process-level
termination was DESCOPED from Phase 7 to a post-2.0 cleanup.

---

## 🗺️ Graph Overview

The autocode workflow is a **28-node LangGraph StateGraph** (25 active + 3
backward-compat wrappers — wrappers registered via `add_node(...)` for
`import`-compatibility but NOT wired; excluded from `WORKFLOW_METADATA["nodes"]`
so MCP clients render only the 27 active-node entries + 2 wrapper entries marked
"(not wired)"). The 3 wrappers (`node_write_files` / `node_verify` /
`node_publish`) are KEPT for test compatibility — `# TODO(2.0-post):` removal.

| # | Node | Type | Phase | Purpose |
|---|------|------|-------|---------|
| 1 | `node_classify_task` | llm (router) | 1 | Classify task type from goal |
| 2 | `node_validate_input` | logic | 2 | Validate input files + path safety |
| 3 | `node_brainstorm` | llm (planner) | 3 | Brainstorm spec tailored to task type |
| 4 | `node_write_plan` | llm (planner) | 4 | Write structured plan with acceptance criteria |
| 5 | `node_git_branch` | tool (git) | 5 | Create git branch for the task |
| 6 | `node_write_tests` | llm (executor) | 6 | Write TDD tests before implementation |
| 7 | `node_execute_step` | llm (executor) | 7 | Generate implementation code from plan |
| 8 | `node_apply_patches` | tool (file) | 8a [v2.0-beta] | Apply str_replace patches to existing files |
| 9 | `node_write_new_files` | tool (file) | 8b [v2.0-beta] | Write new/overwrite files atomically + build files_map |
| 10 | `node_persist_artifacts` | tool (file) | 8c [v2.0-beta] | Persist test file + generated code + debug log to run_dir |
| 11 | `node_analyze_impact` | llm (analyze) | 9 | Blast radius analysis using dependency graph |
| 12 | `node_run_tests` | tool (pytest) | 10 | Run TDD tests via pytest subprocess |
| 13 | `node_systematic_debug` | llm (executor) | 11 [v2.0-rc1] | 4-phase debug: investigation → pattern → hypothesis → fix |
| 14 | `node_summarize_context` | logic | 11a [v2.0-rc1] | Compress debug_history before re-entering loop |
| 15 | `node_run_pytest` | tool (pytest) | 12a [v2.0-beta] | Fresh pytest on autocode test files |
| 16 | `node_run_lint` | tool (ruff) | 12b [v2.0-beta] | Ruff lint on modified files only |
| 17 | `node_llm_review` | llm (executor) | 12c [v2.0-beta] | LLM spec coverage + cleanliness review |
| 18 | `node_verify_decision` | logic | 12d [v2.0-beta] | Compose results + hallucination guard |
| 19 | `node_report` | llm (summarize) | 13 | Generate structured report of what was done |
| 20 | `node_commit` | tool (git) | 14 | Commit changes to the git branch |
| 21 | `node_push` | tool (github) | 15a [v2.0-beta] | Push branch to remote |
| 22 | `node_create_pr` | tool (github) | 15b [v2.0-beta] | Create pull request from branch |
| 23 | `node_merge_pr` | tool (github) | 15c [v2.0-beta] | Auto-merge PR (if enabled) |
| 24 | `node_distill_memory` | llm (planner) | 16 | Distill procedural memory for future runs |
| 25 | `node_create_skill` | tool (file) | 17 | Generate a new skill file (bypasses TDD, has AST validation) |
| — | `node_write_files` | composite | wrapper [v2.0-beta] | Backward-compat wrapper (not wired) — calls `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` |
| — | `node_verify` | composite | wrapper [v2.0-beta] | Backward-compat wrapper (not wired) — calls the 4 split verify nodes |
| — | `node_publish` | tool (github) | wrapper [v2.0-beta] | Backward-compat wrapper (not wired) — calls `node_push` → `node_create_pr` → `node_merge_pr` |

**Loops:**

- **`debug_loop`** — `node_systematic_debug` → `node_summarize_context` →
  `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` →
  `node_analyze_impact` → `node_run_tests` → (back to `node_systematic_debug`
  until tests pass, `MAX_RETRIES` exceeded, `tdd_status="stuck"`, OR the
  architecture-question exit fires — see NODES.md § `node_systematic_debug`).

**Conditional routes:**

- `route_after_classify` — `feature`/`fix`/`refactor`/`edit`/`audit` → `node_brainstorm`; `create_skill` → `node_create_skill` (bypasses TDD).
- `route_after_write_files` — `fix`/`refactor`/`improve`/`feature`/`audit`/`edit` → `node_analyze_impact`; other → `node_run_pytest`.
- `route_after_run_tests` — `pass` → `node_run_pytest`; `fail` → `node_systematic_debug`; `stuck` → `node_run_pytest` (skips doomed debug).
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

**[v1.3] Additional fields when GitHub + Swarm integration is enabled** (all default to their "off" values when the corresponding flags are OFF):

```json
{
  "pushed": false,
  "pr_number": 0,
  "pr_url": "",
  "swarm_verdict": {}
}
```

| Field | Type | Default | When populated |
|-------|------|---------|----------------|
| `pushed` | `bool` | `false` | Set by `node_publish` — `true` if `_github_push()` succeeded. |
| `pr_number` | `int` | `0` | Set by `node_publish` — the PR number from `_github_pr_create()`. |
| `pr_url` | `str` | `""` | Set by `node_publish` — the PR HTML URL from `_github_pr_create()`. |
| `swarm_verdict` | `dict` | `{}` | Set by `node_systematic_debug` when `AUTOCODE_SWARM_DEBUG=1` and swarm returned a verdict. Shape: `{fix, root_cause, defense_notes, confidence: "HIGH"\|"MEDIUM"\|"LOW", agreement: str, providers: int}`. |
| `branch` | `str` | `""` | **[v1.3] fix:** declared in `AutocodeState` TypedDict (was read by `branch.py` but not declared — TypedDict drift). Already populated by `node_write_plan` since v1.0. |

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

**[v1.3] New state fields (GitHub + Swarm integration):**

| Field | Type | Default | Source node | Purpose |
|-------|------|---------|-------------|---------|
| `pushed` | `bool` | `False` | `node_publish` | Whether the branch was pushed to `origin`. |
| `pr_number` | `int` | `0` | `node_publish` | PR number (0 = no PR created). |
| `pr_url` | `str` | `""` | `node_publish` | PR HTML URL. |
| `swarm_verdict` | `dict` | `{}` | `node_systematic_debug` | Swarm consensus + vote result. Shape: `{fix, root_cause, defense_notes, confidence, agreement, providers}`. |

**[v1.3] TypedDict drift fix:**
- `branch: str` was already read by `nodes/branch.py` (line 55: `if state.get("branch"):`) and set by `nodes/plan.py` since v1.0, but was NOT declared in the `AutocodeState` TypedDict. v1.3 adds the declaration (`state.py` line 94) and the default in `_default_state()` (`state.py` line 154). No runtime behavior change — pure type-safety fix.

**[v2.0-rc1] New state fields (Phase 4 debug loop refactor):**

| Field | Type | Default | Source node | Purpose |
|-------|------|---------|-------------|---------|
| `debug_history` | `list[dict]` | `[]` | `node_systematic_debug` | Within-run debug-loop history. Each entry: `{iteration: int, phase: str, root_cause: str, fix: str (truncated to 200 chars), tests_passed: bool}` (swarm path adds `confidence: str`). Declared in Phase 2 (v2.0-alpha) as a placeholder; **POPULATED as of Phase 4.2 (v2.0-rc1)**. Last 5 entries injected into the LLM user prompt; full history read by `node_summarize_context` and by the architecture-question exit check. Stored in `TDDState` sub-state (accessed via `_get_tdd`). |
| `debug_summary` | `str` | `""` | `node_summarize_context` | Compressed `debug_history` string produced by the new `node_summarize_context` node (Phase 4.3). Reverses history (most recent first), renders each entry as a single sentence, tries `chonkie.SentenceChunker(chunk_size=512)` (soft dep, lazy import) and returns the FIRST chunk; falls back to `json.dumps(last_3_entries)` on any exception. Stored in `TDDState` sub-state (accessed via `_get_tdd`). `# TODO(2.0-post):` No downstream node reads it yet — see F3 in CHANGELOG.md § "Future Tracks (Post-2.0)". |

For the full field list, see `workflows/autocode_impl/state.py`.

---

## 🧭 [v2.0] State Accessors

The v2.0-alpha release introduces a backward-compatible accessor layer over
`AutocodeState`. Each accessor reads from the corresponding sub-state dict if
present, else falls back to the legacy flat field. See ARCHITECTURE.md §
"[v2.0] Sub-state Architecture" for the design rationale and the 7-phase
migration plan.

### The 8 accessor functions

| Function | Sub-state TypedDict | Reads from | Legacy fallback fields |
|----------|---------------------|------------|------------------------|
| `_get_plan(state, key, default=None)` | `PlanState` | `state["plan"]` dict | `task_type`, `plan`, `branch`, `current_step` |
| `_get_tdd(state, key, default=None)` | `TDDState` | `state["tdd"]` dict | `test_code`, `test_results`, `tdd_status`, `tdd_iteration`, `debug_history` **[v2.0-rc1] new** (populated by `node_systematic_debug`), `debug_summary` **[v2.0-rc1] new** (written by `node_summarize_context`) |
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

**[v2.0] `node_git_commit` is the proof-of-concept.** It reads the branch name
via `_get_vcs(state, "branch", "main")` instead of `state.get("branch", "main")`:

```python
# Before (v1.4):
branch = state.get("branch", "main")

# After (v2.0-alpha):
from workflows.autocode_impl.state import _get_vcs
branch = _get_vcs(state, "branch", "main")
```

`# TODO(2.0-post):` The remaining 15 nodes still use the legacy `state.get(...)`
pattern. **[v2.0-rc1]** `node_systematic_debug` and `node_summarize_context` are
now migrated to accessors (Phase 4). They will continue migrating in a future
post-2.0 cleanup pass. **[v2.0-rc2]** Phase 5 actually shipped as VCS consolidation
+ cleanup (the original "async refactor" scope was dropped since `_run_async` was
already simplified in Phase 1). **[v2.0 GA]** The original Phase 6 scope (legacy
flat-field removal + accessor fallback branch removal) was DESCOPED — sub-states
are now PRIMARY storage (Phase 6 / v2.0-rc3 — `_default_state()` populates all 8
sub-states with default values), but the legacy flat fields remain KEPT as mirrors
for backward compat with unmigrated nodes + tests. Legacy field removal is now
`# TODO(2.0-post):`.

### `helpers._write_files()` — [v2.0 GA] DELETED (was [v2.0-rc2] DEPRECATED)

The `helpers._write_files()` function is **DELETED as of v2.0 GA (Phase 7.2)**. It
was marked DEPRECATED in v2.0-rc2 (Phase 5.3) after a dead-code audit found it was
never called by any node — `execute.py` imported it but never used the import (the
dead import was removed: `from ...helpers import _call, _write_files, ...` →
`from ...helpers import _call, _files_context, _parse_json`). Phase 7.2 deleted the
function body entirely. The `helpers.py` source now carries a single comment in its
place:

```
# [v2.0] Phase 7: _write_files() DELETED — was dead code (never called by any node).
# The actual file writing logic lives in nodes/apply_patches.py + nodes/write_new_files.py.
```

- **DELETED, not deprecated:** Phase 7.2 removed the function body. Code that
  imports `helpers._write_files` will now `ImportError`. (Phase 5.3 had kept the
  function for backward compat — Phase 7.2 closed that grace period.)
- **Use the Phase 3.1 split nodes instead:** New code (and any code that was
  still calling `_write_files()`) MUST use `node_apply_patches` (for `str_replace`
  patches to existing files) + `node_write_new_files` (for new-file writes /
  overwrites) + `node_persist_artifacts` (for run-dir artifact persistence). See
  NEVER DO #38 + #39 in INSTRUCTIONS.md.
- **No behavior change:** The function was unreachable before Phase 5.3 (no node
  called it). Phase 5.3 just documented that fact + removed the dead import from
  `execute.py`; Phase 7.2 removes the function body itself.

### `vcs_ops.py` — [v2.0-rc2] Unified VCS module (Phase 5.1)

The new `workflows/autocode_impl/vcs_ops.py` module is the **single source of
truth for all VCS helpers** as of v2.0-rc2 (Phase 5.1). It merges the former
`git_ops.py` (local operations) + `github_ops.py` (remote operations) into one
module, organized in 3 sections:

1. **Local operations** — `_git_commit()`, `_git_create_branch()` (was in
   `git_ops.py`)
2. **Remote operations** — `_github_pull()`, `_github_push()`,
   `_github_pr_create()`, `_github_pr_comment()`, `_github_pr_merge()` (was in
   `github_ops.py`)
3. **Swarm integration** — `_swarm_debug_consensus()` (was in `github_ops.py`)

All lazy imports, `is_configured()` guards, `tracer.step` logging, and structured
returns are preserved — pure move + merge, no behavior change.

**Backward compat:** `git_ops.py` + `github_ops.py` are kept as thin re-export
wrappers (re-export from `vcs_ops`) so existing `from workflows.autocode_impl.git_ops import ...`
and `from workflows.autocode_impl.github_ops import ...` calls still work. **New
code MUST import from `vcs_ops.py` directly** — see INSTRUCTIONS.md ALWAYS DO #53.

Resolves the v1.3 "2.0 Review Notes" item `git_ops.py + github_ops.py split →
consider merging into unified vcs_ops.py`.

### `debug_history` field — [v2.0-rc1] POPULATED by `node_systematic_debug`

The `debug_history` field in `TDDState` was **declared in Phase 2 as a
forward-declared placeholder** and is **now populated by `node_systematic_debug`
on every iteration as of Phase 4.2 (v2.0-rc1)**. It is the within-run debug-loop
history that closes the #37 prerequisite (context summarization):

- **[v2.0-rc1] POPULATED:** `node_systematic_debug` appends a new entry on every
  iteration: `{iteration: int, phase: str, root_cause: str, fix: str (truncated
  to 200 chars), tests_passed: bool}` (`tests_passed=False` when the entry is
  created — `run_tests` updates it to `True` on the next loop iteration if the
  fix worked). Swarm-path entries use `phase="swarm"` and include an extra
  `confidence` field.
- **[v2.0-rc1] CONSUMED by `node_systematic_debug`:** Last 5 entries are
  injected into the LLM user prompt under a `--- PRIOR DEBUG ATTEMPTS (do NOT
  repeat these) ---` block so the LLM doesn't repeat failed hypotheses/fixes.
- **[v2.0-rc1] CONSUMED by `node_summarize_context`:** The new
  `node_summarize_context` node (Phase 4.3) reads `debug_history` and compresses
  it into `debug_summary` via chonkie `SentenceChunker` (soft dep, lazy import)
  before re-entering the loop.
- **[v2.0-rc1] Architecture-question exit:** `node_systematic_debug` reads the
  last 3 entries — if all have `tests_passed=False`, it bails with
  `tdd_status="max_retries_exceeded"` + procedural memory store. DIFFERENT from
  #39 stuck detection (same error repeating) — this fires when DIFFERENT errors
  occur each iteration.
- **[v2.0-rc1] Preserved on early exit:** Both early-exit paths (architecture +
  max_retries) return `"tdd": {"debug_history": debug_history}` so the full
  history is available for downstream inspection / procedural memory store.
- **Accessor:** `_get_tdd(state, "debug_history", [])` reads from the TDD
  sub-state dict if present, else falls back to the legacy flat field.

`# TODO(2.0-post):` Cross-run learning (procedural memory recall before debug)
is still pending — see CHANGELOG.md § "Future Tracks (Post-2.0)" F5.

### `debug_summary` field — [v2.0-rc1] NEW, written by `node_summarize_context`

The new `debug_summary: str` field in `TDDState` (Phase 4.3, v2.0-rc1) holds the
compressed `debug_history` string produced by `node_summarize_context`. It is the
bounded-context view of the within-run debug-loop history:

- **[v2.0-rc1] WRITTEN by `node_summarize_context`:** The new node (Phase 4.3)
  reads `debug_history`, reverses it (most recent first), renders each entry as
  a single sentence, then tries `chonkie.SentenceChunker(chunk_size=512)` and
  returns the FIRST chunk. On any exception (including `ModuleNotFoundError`
  when chonkie isn't installed) falls back to `json.dumps(last_3_entries)`.
- **[v2.0-rc1] NOT YET READ by `node_systematic_debug`:** The LLM user prompt
  still uses the raw last-5-entries block from `debug_history`. The summary is
  available for future migration — see F3 in CHANGELOG.md § "Future Tracks
  (Post-2.0)".
- **[v2.0-rc1] Empty when history is empty:** First debug iteration (no prior
  attempts) → `node_summarize_context` returns `{"tdd": {"debug_summary": ""}}`.
- **Accessor:** `_get_tdd(state, "debug_summary", "")` reads from the TDD
  sub-state dict if present, else falls back to the legacy flat field.

`# TODO(2.0-post):` Migrate the LLM user prompt in `node_systematic_debug` to
use `debug_summary` (compressed) instead of the raw last-5-entries block once
`debug_history` grows past ~10 entries (F3 in CHANGELOG.md).

---

## 🔒 Security

*(Fill this section with relevant info from edits and refactors. Add security details as they are learned.)*

---

## 📝 Error Handling

*(Fill this section with relevant info from edits and refactors. Add error classification as it is learned.)*

---

*Last updated: 2026-07-11 (v2.0 GA — **all 7 phases of the 2.0 refactor ✅ COMPLETE.** Phase 7.3 doc consolidation: this file was SPLIT — the per-node reference (was ~600 lines) moved to new [NODES.md](NODES.md); this file now focuses on the facade + graph overview + output format + state fields + state accessors (~250 lines). New `## 🚀 Facade` section documenting `run_autocode_agent()` parameters; new `## 🗺️ Graph Overview` section with a 28-node table (25 active + 3 backward-compat wrappers) + loops + conditional routes. `helpers._write_files()` subsection updated from [v2.0-rc2] DEPRECATED → [v2.0 GA] DELETED (Phase 7.2 — function body removed). Accessor-migration TODO note updated from `# TODO(2.0):` Phase 6 → `# TODO(2.0-post):` (legacy field removal was DESCOPED from Phase 6 to post-2.0 — sub-states are now PRIMARY storage as of Phase 6 / v2.0-rc3, but legacy flat fields remain as mirrors). Prior v2.0-rc2 — Phase 5 (VCS consolidation + cleanup): new `vcs_ops.py` Unified VCS module subsection + node source lines for 6 VCS-touching nodes updated with [v2.0-rc2] notes. Prior v2.0-rc1 — Phase 4 (debug loop refactor): `node_systematic_debug` section rewritten + new `node_summarize_context` section + new `debug_summary` field subsection. See [NODES.md](NODES.md) for the per-node reference, [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history + 7-phase refactor progress, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
