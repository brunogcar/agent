<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 API Reference

This file documents the autocode workflow **facade** + **graph overview** +
**output format** + **state fields** + **state accessors** + **adaptive timeout**. For the per-node
reference (Purpose / Logic / Output / Notes for each of the 29 nodes), see
[NODES.md](NODES.md).

---

## 🚀 Facade — `run_workflow("autocode")`

The autocode workflow is invoked through the shared `run_workflow()` facade in
`workflows/base.py`. **[v3.1.2 #34]** The autocode-specific backward-compat facade
shim in `workflows/autocode.py` was REMOVED — it had no production callers, only
test references. Call `run_workflow("autocode")` directly.

```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="autocode",
    goal="Fix the timeout handling in web search",  # base.py param; becomes state["task"] for autocode
    mode="feature",                                  # feature | fix | fix_error | refactor | improve | edit | create_skill | audit
    files={"web.py": "..."},
    dry_run=False,
    trace_id="",                                     # "" → run_workflow creates one
)
```

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `workflow_type` | `str` | (required) | Must be `"autocode"`. |
| `goal` | `str` | (required) | Natural-language task description. `base.py` aliases this to `state["task"]` for autocode (the workflow's natural-language goal field). |
| `mode` | `str` | `"feature"` | One of `feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, `create_skill`, `audit`. Overrides LLM classification if set (`fix_error`→`fix`, `improve`→`refactor`; other modes pass through as `task_type`). |
| `files` | `dict[str, str]` | `{}` | Initial file contents keyed by relative path. Pass `{"all changed": ""}` + `git_diff=True` for multi-file git-diff input (#46). |
| `git_diff` | `bool` | `False` | If True, `files` values are interpreted as git-diff snippets (#46). |
| `dry_run` | `bool` | `False` | If True, skip writes / commits / branches (#47 dry-run guards). |
| `trace_id` | `str` | `""` | Trace correlation ID. If empty, `run_workflow` calls `tracer.new_trace(...)` and populates it. |
| `resume` | `bool` | `False` | If True, attempt to restore from checkpoint journal. |
| `**kwargs` | — | — | Additional workflow-specific inputs (e.g., `target_file`, `project_root`). |

**Return value:** `dict` — see [📤 Output](#-output) below. For machine-consumable
structured fields, call `_shape_artifacts(result)` (still exported from
`workflows.autocode`) on the returned dict.

**Facade contract:** Callers MUST go through `run_workflow("autocode")` — it
handles tracing, checkpointing, and timeout. Never call
`get_graph().compile().invoke()` directly (the facade was broken for 2 versions
because of this; see INSTRUCTIONS.md NEVER DO #14, #15, #17).

**Cancellation flag wiring:** `invoke_with_timeout()` (in
`workflows/autocode_impl/graph.py`, called from `run_workflow` via `base.py`)
calls `clear_cancellation()` at start and `request_cancellation()` on timeout —
the in-flight `_call()` retries in `helpers.py` notice and abort instead of
sleeping through exponential backoff. **[Hardening P0.3]** graph exceptions in
the daemon thread are surfaced as `"Autocode graph crashed: <exception>"` (was
swallowed as timeout — see [📝 Error Handling](#-error-handling) for the
crashed-vs-timed-out distinction). Full process-level termination deferred to
post-2.0 (roadmap #35).

---

## ⏱️ Adaptive Timeout (v3.1.2 #40)

**[v3.1.2 #40]** `invoke_with_timeout()` now supports per-task-type timeouts,
opt-in via the `AUTOCODE_ADAPTIVE_TIMEOUT=1` env var (mapped to
`cfg.autocode_adaptive_timeout`, default OFF).

| `task_type` | Timeout (seconds) | Rationale |
|-------------|-------------------|-----------|
| `create_skill` | 120 | Single-file generation + AST validation + importlib smoke-test — fast, no debug loop. |
| `audit` | 300 | Whole-task audit (will grow when F7 full-audit mode ships). |
| `feature` | 900 | TDD + debug loop + verify chain — heaviest path. |
| `fix` | 600 | Debug loop + verify, but no brainstorm-from-scratch. |
| `refactor` | 600 | Same as `fix`. |
| `edit` | 600 | Same as `fix`. |
| (unknown/empty) | `cfg.autocode_graph_timeout` | Fallback to the static config. |

**Behavior:**
- **OFF (default):** `invoke_with_timeout()` uses `cfg.autocode_graph_timeout` for every workflow — backward compatible.
- **ON:** Looks up `initial_state["task_type"]` in the table above. Unknown task_type falls back to `cfg.autocode_graph_timeout`.

**Why opt-in:** the static timeout was tuned for the worst case (feature). Tightening it per-task-type could regress long-running `feature` workflows if the LLM provider is slow. Opt-in lets operators opt their environment into the tighter timeouts after validating.

**Note:** The `task_type` is set by `node_classify_task` (Phase 1) — but
`invoke_with_timeout()` runs BEFORE the graph, so for adaptive-timeout lookup
the caller should pass `mode=` (which `node_classify_task` honors as an
override). The mode→task_type mapping (`fix_error`→`fix`, `improve`→`refactor`)
is applied at `invoke_with_timeout()` time too, so `mode="fix_error"` correctly
selects the 600s bucket.

---

## 🛑 HiTL Approval Gate (v3.4 #38)

**[v3.4 #38]** The autocode workflow supports an opt-in Human-in-the-Loop
approval gate that pauses execution before any state-mutating commit. Two
gates are wired:

| Gate | Location | Triggers when | Default behavior (HiTL OFF) |
|------|----------|---------------|-----------------------------|
| **TDD path** | Between `node_report` and `node_commit` | `AUTOCODE_HITL_ENABLED=1` AND `state["hitl_approved"]` is False | `node_hitl_gate` returns `{}` (no-op) → `node_commit` runs |
| **create_skill path** | Top of `node_create_skill` (before LLM call) | `AUTOCODE_HITL_ENABLED=1` AND `state["hitl_approved"]` is False | HiTL check skipped → skill generation proceeds |

### Config flag

```bash
# .env
AUTOCODE_HITL_ENABLED=1   # default: 0 (OFF)
```

Maps to `cfg.autocode_hitl_enabled` (initialized in
`core/config_backend/execution.py`). Default OFF — autocode behaves exactly
as v3.3 unless explicitly opted in.

### State field

`AutocodeState.hitl_approved: bool` (default `False`). Set to `True` on
resume to pass the gate.

### Pause + resume flow

```
┌─ run_workflow("autocode", goal="...", mode="feature") ───────────────┐
│  graph runs: classify → brainstorm → plan → branch → tests → execute  │
│  → apply_patches → run_tests → debug loop → verify chain → report     │
│  → node_hitl_gate                                                     │
│     ├─ cfg.autocode_hitl_enabled=False → returns {} → node_commit     │
│     └─ cfg.autocode_hitl_enabled=True, hitl_approved=False:           │
│           save_checkpoint(tid, "hitl", state)                         │
│           return {"status": "awaiting_approval"}                      │
│           route_after_hitl_gate → END                                 │
└──────────────────────────────────────────────────────────────────────┘
                                ↓
        Operator reviews the run output (report + modified files)
                                ↓
┌─ run_workflow("autocode", goal="...", resume=True, hitl_approved=True) ┐
│  restore checkpoint → merge hitl_approved=True into initial_state     │
│  graph runs: ... → node_hitl_gate                                     │
│     └─ hitl_approved=True → returns {} → node_commit → push → ... → END │
└──────────────────────────────────────────────────────────────────────┘
```

### Resume API

```python
# After the gate returns {"status": "awaiting_approval"}, resume with:
result = run_workflow(
    workflow_type="autocode",
    goal="<original goal>",
    trace_id="<original trace_id>",
    resume=True,
    hitl_approved=True,   # [v3.4 #38] passes the gate
    # ...other original kwargs (target_file, mode, etc.)
)
```

Or via the `workflow` tool:

```python
workflow(
    action="run",
    type="autocode",
    goal="<original goal>",
    trace_id="<original trace_id>",
    resume=True,
    hitl_approved=True,
    # ...other original params
)
```

### Why async-checkpoint-resume (not sync-pause)

Two design options were considered for #38:

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| **(a) sync-pause** | `threading.Event` — block the worker thread until the MCP client responds | Simple; one round-trip | Holds the worker thread indefinitely; blocks the MCP channel; breaks the "stateless worker" assumption; one worker per request means a paused worker is a dead worker |
| **(b) async-checkpoint-resume** (CHOSEN) | Save checkpoint → return `{"status": "awaiting_approval"}` → graph routes to END → operator resumes with `hitl_approved=True` | Doesn't hold threads; preserves the worker pool; works with the existing checkpoint infrastructure | Adds one round-trip; requires the operator to pass `goal` + `trace_id` + `resume=True` + `hitl_approved=True` on the second call |

v3.4 chose **(b)** because the gateway's worker pool assumes stateless workers
— a sync-paused worker would consume a worker slot for the entire review
duration (which could be hours). The async pattern adds one extra call but
preserves the worker pool. See INSTRUCTIONS.md NEVER DO #50 + ALWAYS DO #50.

### create_skill path

`node_create_skill` has its own HiTL check at the TOP of the function
(before the LLM call). When `cfg.autocode_hitl_enabled=True` and
`hitl_approved=False`, it saves a checkpoint + returns
`{"status": "awaiting_approval"}`. The graph routes `node_create_skill → END`
(direct edge), so the workflow pauses. On resume, the operator passes
`hitl_approved=True`, the check passes, and skill generation proceeds.

### Checkpoint failure is non-fatal

The `save_checkpoint(...)` call inside `node_hitl_gate` (and the
`node_create_skill` HiTL check) is wrapped in `try/except`. If the checkpoint
save fails (e.g., disk full, permissions), the gate STILL pauses — but the
operator won't be able to resume. This is intentional: a checkpoint failure
shouldn't block the pause (the operator can still manually re-run the
workflow from scratch). The `tracer.step(...)` call before the checkpoint
ensures the pause is visible in the trace even if the checkpoint fails.

---

## 🧬 Parallel Subagent Debug (v3.5 F1)

**[v3.5 F1]** The autocode workflow supports a 4th debug path: **parallel
subagent debug** — generate N hypotheses, dispatch N subagents in parallel,
aggregate by highest confidence. Opt-in via `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`
(default OFF). Mutually exclusive with `AUTOCODE_SWARM_DEBUG` and
`AUTOCODE_SUBAGENT_DEBUG` (see INSTRUCTIONS.md NEVER DO #40).

### Config flags

```bash
# .env
AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1   # default: 0 (OFF)
AUTOCODE_PARALLEL_SUBAGENT_COUNT=3   # default: 3 (number of parallel hypotheses)
```

Maps to `cfg.autocode_parallel_subagent_debug` +
`cfg.autocode_parallel_subagent_count` (initialized in
`core/config_backend/execution.py`). Default OFF — autocode behaves exactly
as v3.4 unless explicitly opted in.

### Pipeline

```
node_systematic_debug (AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1)
   │
   ├─ 1. _call(role="planner", system=PARALLEL_HYPOTHESES_SYSTEM.format(count=N), user=debug_context)
   │     → JSON array of N hypotheses [{hypothesis_id, root_cause, proposed_fix, confidence}]
   │
   ├─ 2. Parse JSON array. If < 2 hypotheses → fall through to single-LLM.
   │
   ├─ 3. ThreadPoolExecutor(max_workers=N):
   │     for each hypothesis:
   │       agent(action="subagent", role="executor",
   │             task=hypothesis + debug_context,
   │             system=SUBAGENT_VALIDATE_SYSTEM,
   │             json_schema=_DEBUG_JSON_SCHEMA)
   │       → JSON {phase, root_cause, defense_notes, fix}
   │
   ├─ 4. Aggregate: sort verdicts by hypothesis_confidence DESC. Winner = verdicts[0].
   │
   └─ 5. RMW debug sub-state:
         debug.parallel_verdicts = [all verdicts]      # observability
         debug.subagent_verdict   = winner             # unified shape
         debug.root_cause         = winner.root_cause
         debug.defense_notes      = winner.defense_notes
         tdd.source_code          = winner.fix
         tdd.debug_history        += [winner entry]
```

### State field

`DebugState.parallel_verdicts: list[dict]` (default `[]`). Populated by
`_parallel_subagent_debug()` with ALL subagent verdicts (one per dispatched
hypothesis), sorted by descending `hypothesis_confidence`. Each entry:

```python
{
    "hypothesis_id": <int|str>,            # planner-supplied id
    "hypothesis_root_cause": <str>,         # planner-supplied root cause
    "hypothesis_confidence": <float>,       # planner-supplied 0.0-1.0
    "phase": "investigation|pattern|hypothesis|fix",  # subagent-supplied
    "root_cause": <str>,                    # subagent-supplied (refined)
    "defense_notes": <str>,                 # subagent-supplied
    "fix": <str>,                           # subagent-supplied (refined)
}
```

### Fallback behavior

| Failure mode | Behavior |
|--------------|----------|
| Hypothesis generation LLM call raises | Fall through to single-subagent / single-LLM (traced) |
| Hypothesis JSON parse fails OR < 2 hypotheses returned | Fall through to single-subagent / single-LLM (traced) |
| All N subagents fail (status != "success" or unparseable JSON) | Fall through to single-subagent / single-LLM (traced) |
| Some subagents fail, ≥1 succeed | Use the highest-confidence surviving verdict |
| `AUTOCODE_PARALLEL_SUBAGENT_COUNT < 2` | Fall through (traced — parallel is pointless for N<2) |

The parallel path is **non-blocking** — a fall-through is logged via
`tracer.step(...)` and execution continues with the single-subagent /
single-LLM path. The workflow never hard-fails because of the parallel path.

### When to use vs. alternatives

| Debug path | When to use |
|------------|-------------|
| Single-LLM (default) | Simple, single-hypothesis bugs (most cases) |
| Swarm (`AUTOCODE_SWARM_DEBUG=1`) | Multi-provider consensus adds confidence signal; useful when you have 2+ cloud providers configured |
| **Parallel subagent (`AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`, v3.5 F1)** | **Complex multi-hypothesis bugs** — when the LLM is likely to face competing root causes (race vs. cache vs. off-by-one). Generates N hypotheses and validates them in parallel. |
| Single subagent (`AUTOCODE_SUBAGENT_DEBUG=1`) | Single-hypothesis bug where isolated curated context helps (no session state contamination) |

See INSTRUCTIONS.md ALWAYS DO #51 for guidance on when to prefer the parallel
path over the simpler single-subagent path.

---

## 🗺️ Graph Overview

The autocode workflow is a **30-node LangGraph StateGraph** (26 active + 3 backward-compat wrappers + 1 HiTL gate — wrappers registered via `add_node(...)` for `import`-compatibility but NOT wired; excluded from `WORKFLOW_METADATA["nodes"]` so MCP clients render only the 29 active-node entries). The 3 wrappers (`node_write_files` / `node_verify` / `node_publish`) are KEPT for test compatibility — removal deferred to post-2.0. **[v3.4]** Adds `node_hitl_gate` (Phase 12: opt-in Human-in-the-Loop approval between `node_report` and `node_commit`). **[v3.1]** Adds `node_swarm_fallback` (Phase 11b: multi-model escalation when debug retries exhausted).

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
| 13 | `node_swarm_fallback` | llm (executor) | 11b | **[v3.1]** Swarm consensus when debug retries exhausted (`max_retries_exceeded` + `AUTOCODE_SWARM_DEBUG_FALLBACK=1`). HIGH confidence → one more debug cycle; LOW/unavailable → verify chain. Sibling of `node_systematic_debug` (taken on `fail`); same conditional-edge fan-out from `node_run_tests`. |
| 14 | `node_systematic_debug` | llm (executor) | 11 | 4-phase debug: investigation → pattern → hypothesis → fix |
| 15 | `node_summarize_context` | logic | 11a | Compress debug_history before re-entering loop |
| 16 | `node_run_pytest` | tool (pytest) | 12a | Fresh pytest on autocode test files (with **[v3.1]** `ruff --select E999` syntax pre-check) |
| 17 | `node_run_lint` | tool (ruff) | 12b | Ruff lint on modified files only |
| 18 | `node_llm_review` | llm (executor) | 12c | LLM spec coverage + cleanliness review (**[v3.1]** injects `debug_summary` when `debug_history` > 5) |
| 19 | `node_verify_decision` | logic | 12d | Compose results + hallucination guard |
| 20 | `node_report` | llm (summarize) | 13 | Generate structured report of what was done |
| 21 | `node_hitl_gate` | logic | 13a | **[v3.4 #38]** Opt-in Human-in-the-Loop approval gate (between report and commit). When `AUTOCODE_HITL_ENABLED=1` AND `hitl_approved=False`, saves checkpoint + returns `{"status": "awaiting_approval"}` → graph routes to END. On resume with `hitl_approved=True`, passes through. No-op when HiTL is disabled. |
| 22 | `node_commit` | tool (git) | 14 | Commit changes to the git branch |
| 23 | `node_push` | tool (github) | 15a | Push branch to remote |
| 24 | `node_create_pr` | tool (github) | 15b | Create pull request from branch |
| 25 | `node_merge_pr` | tool (github) | 15c | Auto-merge PR (if enabled) |
| 26 | `node_distill_memory` | llm (planner) | 16 | Distill procedural memory for future runs |
| 27 | `node_create_skill` | tool (file) | 17 | Generate a new skill file (bypasses TDD, has AST validation + **[v3.1.2 #36]** importlib smoke-test + git commit; **[v3.4 #38]** HiTL check at top when `AUTOCODE_HITL_ENABLED=1`) |
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
- `route_after_run_tests` — `pass` → `node_run_pytest`; `fail` → `node_systematic_debug`; `stuck` → `node_run_pytest` (skips doomed debug). **[v3.1 #48]** When `tdd_status == "max_retries_exceeded"` AND `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, routes to `node_swarm_fallback` instead of `node_run_pytest`. **[Hardening P1.5]** short-circuits on `status=="error"`.
- `route_after_verify` — `pass` → `node_report`; `fail` → **`END`** (workflow terminates with `status="failed"` — does NOT re-enter the debug loop; the debug loop already exhausted its retries by the time the verify chain runs).

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
  "subagent_verdict": {},
  "parallel_verdicts": []
}
```

| Field | Type | Default | When populated |
|-------|------|---------|----------------|
| `pushed` | `bool` | `false` | Set by `node_push` — `true` if `_github_push()` succeeded. |
| `pr_number` | `int` | `0` | Set by `node_create_pr` — the PR number from `_github_pr_create()`. |
| `pr_url` | `str` | `""` | Set by `node_create_pr` — the PR HTML URL from `_github_pr_create()`. |
| `swarm_verdict` | `dict` | `{}` | Set by `node_systematic_debug` when `AUTOCODE_SWARM_DEBUG=1` and swarm returned a verdict. Shape: `{fix, root_cause, defense_notes, confidence: "HIGH"\|"MEDIUM"\|"LOW", agreement, providers}`. |
| `subagent_verdict` | `dict` | `{}` | Set by `node_systematic_debug` when `AUTOCODE_SUBAGENT_DEBUG=1` and the subagent dispatch returned a verdict. Shape: `{fix, root_cause, defense_notes}` (single isolated dispatch — no consensus/agreement). Falls back to single-LLM on subagent failure. **[v3.5 F1]** Also populated by the parallel subagent path — mirrors the winning verdict from `parallel_verdicts` so downstream readers see a unified shape. |
| `parallel_verdicts` | `list[dict]` | `[]` | **[v3.5 F1]** Set by `node_systematic_debug` when `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`. ALL subagent verdicts (one per dispatched hypothesis), sorted by descending `hypothesis_confidence`. Each entry: `{hypothesis_id, hypothesis_root_cause, hypothesis_confidence, phase, root_cause, defense_notes, fix}`. The winner (index 0) is mirrored into `subagent_verdict` for downstream readers. |
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
| `task` | `str` | `""` | Natural-language goal (set by facade from `run_workflow(goal=...)`). |
| `files` | `dict[str, str]` | `{}` | Initial file contents keyed by relative path. |
| `mode` | `str` | `""` | One of `feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, `create_skill`, `audit`. |
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
| `debug` | `DebugState` | `notes`, `root_cause`, `defense_notes`, `swarm_verdict`, `subagent_verdict`, `parallel_verdicts` | `_get_debug` |
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

**[v3.2 P1-5]** `_git_commit()` now returns a structured dict `{"committed": bool, "sha": str, "reason": str}` instead of `None` for both the "nothing to commit" and "error" cases (the two cases were indistinguishable to callers). `committed=False` + `reason="nothing to commit"` is the graceful no-op path; `committed=False` + `reason="error: <detail>"` is the failure path; `committed=True` + `sha="<commit_sha>"` + `reason="committed"` is the success path. Callers that branched on `if _git_commit(...) is None:` MUST update to `if not result["committed"]:`.

### `debug_history` field — written by `node_systematic_debug`, read by `node_summarize_context`

`debug_history` is the within-run debug-loop history that closes the #37 prerequisite (context summarization):

**Four debug paths** (mutually exclusive — see INSTRUCTIONS.md NEVER DO #40):

1. **Single-LLM (default)** — `node_systematic_debug` calls `_call()` directly with the 4-phase `DEBUG_SYSTEM` prompt. No flag required.
2. **Swarm** (`AUTOCODE_SWARM_DEBUG=1`) — `node_systematic_debug` calls `_swarm_debug_consensus()` which dispatches to 2+ providers, then votes (confidence HIGH/MEDIUM/LOW). Non-blocking: the fix is applied regardless of confidence.
3. **Parallel subagent** (`AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`, v3.5 F1) — `node_systematic_debug` calls `_parallel_subagent_debug()` which: (a) generates N distinct hypotheses via a planner LLM call with `PARALLEL_HYPOTHESES_SYSTEM`; (b) dispatches N subagents in parallel via `ThreadPoolExecutor` (one per hypothesis) using `SUBAGENT_VALIDATE_SYSTEM`; (c) aggregates by picking the highest-confidence verdict; (d) stores ALL verdicts in `debug.parallel_verdicts`. Tunable via `AUTOCODE_PARALLEL_SUBAGENT_COUNT` (default 3). Non-blocking: falls through to single-LLM on hypothesis-generation failure or all-subagents-failed.
4. **Single subagent** (`AUTOCODE_SUBAGENT_DEBUG=1`, v2.0.2) — `node_systematic_debug` calls `agent(action="subagent", role="planner")` with isolated curated context (failing test + error output + current source + truncated prior fix attempts). Subagent does NOT see autocode session state. Non-blocking: falls back to single-LLM on subagent failure.

All four paths populate `debug_history` (with `phase` set accordingly: `investigation`/`pattern`/`hypothesis`/`fix` for single-LLM, `swarm` for swarm, `subagent` for single subagent; the parallel path uses the winner subagent's `phase`).

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
- All 8 GitHub/Swarm/Subagent config flags (`AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`, `AUTOCODE_SUBAGENT_DEBUG`, `AUTOCODE_SWARM_DEBUG_FALLBACK`) default **OFF** — backward compat (with all OFF, autocode behaves identically to v3.1.2). **[v3.1]** `AUTOCODE_SWARM_DEBUG_FALLBACK=1` enables the post-debug-exhaustion swarm escalation node (`node_swarm_fallback`). **[v3.1.2 #40]** `AUTOCODE_ADAPTIVE_TIMEOUT=1` enables per-task-type timeout overrides (default OFF). **[v3.5 F1]** `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` enables the parallel subagent debug path (4th debug chain path); `AUTOCODE_PARALLEL_SUBAGENT_COUNT` (default 3) tunes the number of parallel hypotheses. Both default OFF/3 — backward compat with v3.4.
- `is_configured()` guard: every `vcs_ops.py` helper MUST call `_github_is_configured()` (wraps `tools.github_ops.client.is_configured()`) before any GitHub API call. Missing `GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` → graceful-skip (returns `False`/`None`, workflow continues).
- `_call()` retries are interruptible via `threading.Event` — secrets/credentials are never logged.

### Atomic writes
- `node_write_new_files` uses `tempfile.NamedTemporaryFile` + `os.replace` + `FileLock` (1 retry on timeout).
- `node_create_skill` uses `tempfile.NamedTemporaryFile` + `os.replace` (was direct `write_text` — crash mid-write corrupted the skill file). **[v3.1.2 #36]** After write, runs `importlib.util.spec_from_file_location` smoke-test; on import failure, deletes the broken file and returns `status="failed"`.

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
| **LLM failure** | `_call()` exhausted retries, returned `""` | Node falls back to default (e.g., `task_type="unclear"`) or returns `{"status": "error", "error": ...}`. **[v3.1.2 P1]** `_call()` retry-exhaustion errors now include `trace_id=tid` — all 8 callers (`classify.py`, `brainstorm.py`, `plan.py`, `tests.py`, `execute.py`, `debug.py`, `llm_review.py`, `create_skill.py`) pass `trace_id=tid` so retry-exhaustion errors are attributed to the workflow's trace (was: unattributed `trace_id=""`). **[v3.2 P1-6]** The unreachable `raise last_error` after the retry loop in `helpers._call()` was removed — it was dead code (the loop always returns or raises within the loop body); a stale comment about it was also fixed. |
| **JSON parse failure** | LLM returned non-JSON or markdown-fenced JSON | `_parse_json()` returns `{}`; node logs warning + uses defaults. |
| **Subprocess failure** | `pytest` / `ruff` / `git` returned non-zero | Captured as structured return; workflow continues (lint is advisory). |
| **GitHub API failure** | `_github_pr_create()` raised | Graceful-skip: `is_configured()` returns `False` → helper returns `None`/`False`. |
| **Path traversal** | LLM returned `../../etc/passwd` | `_is_path_safe()` returns `False`; path added to `patch_errors`. |
| **Timeout** | `invoke_with_timeout()` exceeded the configured timeout (static `cfg.autocode_graph_timeout` OR per-task-type adaptive timeout when `AUTOCODE_ADAPTIVE_TIMEOUT=1`) | `request_cancellation()` → `_call()` retries abort; status set to `"Autocode graph timed out"`. The daemon thread can't be killed (Python limitation — see roadmap #35); it exits on the next `_call()` check. |
| **Crashed** | Graph node raised an unhandled exception inside the daemon thread | **Distinct from timeout.** **[Hardening P0.3]** The exception is captured and surfaced as `status="Autocode graph crashed: <exception>"` (was: swallowed and misreported as timeout). The daemon thread dies; the main thread sees the crash result. |
| **Max retries exceeded** | `iteration > max_retries` in debug loop | `tdd_status="max_retries_exceeded"` + procedural memory store. **[v3.1 #48]** If `AUTOCODE_SWARM_DEBUG_FALLBACK=1`, `route_after_run_tests` routes to `node_swarm_fallback` instead of the verify chain — HIGH-confidence swarm verdict resets `tdd_status` for one more debug cycle; LOW/unavailable still falls through to verify chain (returns `"failed"`). |
| **Stuck detection** | Same error signature on consecutive debug iterations | `route_after_run_tests` routes `"stuck"` → `node_run_pytest` (skips doomed debug). |
| **Architecture-question exit** | 3+ consecutive `tests_passed=False` (different errors each iteration) | `tdd_status="max_retries_exceeded"` + procedural memory store (different from stuck — fires on architectural bug). |

### Tracing
- Every node should call `tracer.step(tid, ...)` for graceful events + `tracer.error(tid, category, message)` (3 args — see NEVER DO #29) for failures.
- `trace_id` is mandatory on every tracer call (INSTRUCTIONS.md ALWAYS DO).
- **✅ [v3.1.2]** All 8 `_call()` callers now pass `trace_id=tid` — retry-exhaustion errors are attributed to the workflow's trace. (Before v3.1.2, `_call()` retry-exhaustion errors used `trace_id=""` and were unattributed.)

### `_call()` retry mechanism

`_call(role, system, user, ..., retries=2, trace_id="")` (in `helpers.py`) loops `retries + 1` times with exponential backoff (`2 ** attempt` seconds). **[Hardening P1.7]** Backoff is interruptible via `threading.Event.wait(timeout=...)` so `request_cancellation()` from a timeout aborts the sleep immediately (was `time.sleep(...)` — uninterruptible). **[v3.1.2 P1]** `trace_id` is now passed by all 8 in-tree callers — see Tracing section above. **[v3.2 P1-6]** The unreachable `raise last_error` after the retry loop was removed (dead code — the loop body always returns or raises); the stale comment that referenced it (`# re-raise last error if all retries failed`) was corrected. The control flow is unchanged: an exhausted retry loop returns `""` (empty string), which downstream nodes interpret as an LLM failure and handle via their fallback path (e.g., `task_type="unclear"`, `status="error"`).

---

*Last updated: 2026-07-19 (v3.5 — F1 parallel subagent debug: new § "Parallel Subagent Debug" documents the 4th debug chain path (hypothesis generation → parallel ThreadPoolExecutor dispatch → confidence-weighted aggregation); new config flags `AUTOCODE_PARALLEL_SUBAGENT_DEBUG` + `AUTOCODE_PARALLEL_SUBAGENT_COUNT`; new state field `parallel_verdicts: list[dict]` on `DebugState`; `subagent_verdict` now also populated by the parallel path (mirrors the winner); "Three debug paths" → "Four debug paths" + new entry in the output-fields table; v3.4 — #38 HiTL approval gate: new `node_hitl_gate` between `node_report` and `node_commit` + HiTL check at top of `node_create_skill`; opt-in via `AUTOCODE_HITL_ENABLED=1` (default OFF); async-checkpoint-resume pattern; new `route_after_hitl_gate` in `routes.py`; `hitl_approved` state field; `hitl_approved` param threaded through `workflow` tool → `run_workflow` → checkpoint resume; new § "HiTL Approval Gate" documents the pause/resume flow + design rationale (chose async over sync-pause to preserve worker pool); 29 → 30 nodes (26 active + 3 wrappers + 1 hitl_gate); v3.2 — 6-LLM collective review hardening: `_git_commit` now returns structured dict `{"committed", "sha", "reason"}` (was `None` for both nothing-to-commit and error — P1-5); unreachable `raise last_error` removed from `helpers._call()` retry loop (P1-6); new § "`_call()` retry mechanism" documents the retry semantics end-to-end; v3.1.2 — version-numbering fix: prior `v1.2` references in this file (facade shim removal #34, Adaptive Timeout #40, `_call()` trace_id attribution) were naming mistakes and are now correctly labeled `v3.1.2` — these were patch releases to v3.1, NOT regressions to v1.x; v3.1 — debug loop improvements: #42 goal sanitization, #41 AST pre-check, F3 debug_summary in verify chain, #48 swarm fallback; 28 → 29 nodes; v3.0 — flat-field removal, Track M1 ✅ COMPLETE, accessor legacy-fallback branches removed, ephemeral flat fields explicitly declared; v2.0.2 — subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
