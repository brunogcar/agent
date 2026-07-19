<- Back to [Autocode Overview](../AUTOCODE.md)

# 🧭 Sub-state Reference (v3.0)

Single source of truth for the v3.0 sub-state architecture. All 8 sub-states, the accessor layer, the RMW pattern, and the flat-field split live here. For per-node reads/writes, see [NODES.md](NODES.md). For state-field semantics, see [API.md](API.md).

> **[v3.0] Migration status: ✅ COMPLETE.** Track M1 shipped across v2.1–v2.7 + v3.0. All 8 accessors are safe and are the ONLY read path for sub-state fields — legacy flat-field mirrors + accessor fallback branches were removed. Ephemeral flat fields stay flat by design.

---

## 📦 The 8 Sub-states

| Sub-state key | TypedDict | Writers (RMW) | Readers (accessor) | Key fields |
|---------------|-----------|---------------|---------------------|------------|
| `plan_state` | `PlanState` | `brainstorm.py`, `plan.py`, `execute.py`, `tests.py` | `commit.py`, `execute.py`, `llm_review.py`, `plan.py`, `tests.py` | `brainstorm_notes`, `plan`, `plan_accepted`, `spec`, `current_step` |
| `tdd` | `TDDState` | `debug.py`, `summarize_context.py`, `run_tests.py`, `execute.py`, **`swarm_fallback.py`** (v3.2 P0-2) | `debug.py`, `llm_review.py`, `verify_decision.py`, `persist_artifacts.py`, `summarize_context.py` | `iteration`, `source_code`, `error`, `status`, `max_retries`, `last_test_error`, `tests_written`, `debug_history`, `debug_summary` |
| `files_state` | `FilesState` | `apply_patches.py`, `write_new_files.py`, `persist_artifacts.py`, `brainstorm.py`, `execute.py` | `analyze_impact.py`, `brainstorm.py`, `debug.py`, `memory.py`, `plan.py`, `report.py`, `run_lint.py`, `validate.py`, `write_new_files.py` | `files_map`, `modified_files` (`input_files` removed in v3.0 — readers use core `files` flat field directly) |
| `impact` | `ImpactState` | `analyze_impact.py` | `run_tests.py` | `warnings`, `targeted_test_cmd`, `failed` |
| `debug` | `DebugState` | `debug.py` | `commit.py`, `create_pr.py`, `memory.py`, `persist_artifacts.py` | `notes`, `root_cause`, `defense_notes`, `swarm_verdict`, `subagent_verdict` |
| `verify` | `VerifyState` | `verify_decision.py` | `commit.py`, `create_pr.py`, `merge_pr.py`, `push.py`, `report.py` | `notes`, `report`, `passed` |
| `vcs` | `VCSState` | `commit.py`, `branch.py`, `plan.py`, `push.py`, `create_pr.py`, `merge_pr.py` | `commit.py`, `create_pr.py`, `push.py`, `branch.py`, `report.py`, `debug.py`, `merge_pr.py` | `commit_sha`, `branch`, `pushed`, `pr_number`, `pr_url` (`branch_name` removed in v3.2 P2-6 — was declared but no node ever wrote it) |
| `memory` | `MemoryState` | `memory.py` | (internal only) | `notes` (`context` removed in v3.2 P1-2 — was declared in the TypedDict but never populated by any node) |

> **`plan` lives in `plan_state["plan"]` — it is NOT a flat field in v3.0+.** Pre-v3.0, `plan` was overloaded: `state["plan"]` was a flat `list[dict]` step list (legacy mirror) AND `state["plan_state"]["plan"]` was the sub-state field. v3.0 removed the flat mirror — the only storage for `plan` is now `plan_state["plan"]`. `_get_plan(state, "plan", [])` reads from `plan_state`. Direct `state.get("plan", [])` returns `None` (the flat field no longer exists). **[v3.1.2 doc fix]** The earlier doc text claiming `plan` is "kept flat for backward compat with route_after_* lookups" was stale — `route_after_*` functions in `routes.py` read `state.get("task_type", ...)` + `state.get("status", ...)`, never `state.get("plan")`.

---

## 🔧 The 8 Accessor Functions

All 8 share this 4-line shape — sub-state-only, NO legacy fallback:

```python
def _get_vcs(state: dict, key: str, default: Any = None) -> Any:
    """Read `key` from state["vcs"] if present, else return `default`."""
    sub = state.get("vcs")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default
```

| Function | Sub-state key | Reads from |
|----------|---------------|------------|
| `_get_plan(state, key, default=None)` | `plan_state` | `state["plan_state"]` dict |
| `_get_tdd(state, key, default=None)` | `tdd` | `state["tdd"]` dict |
| `_get_files(state, key, default=None)` | `files_state` | `state["files_state"]` dict |
| `_get_impact(state, key, default=None)` | `impact` | `state["impact"]` dict |
| `_get_debug(state, key, default=None)` | `debug` | `state["debug"]` dict |
| `_get_verify(state, key, default=None)` | `verify` | `state["verify"]` dict |
| `_get_vcs(state, key, default=None)` | `vcs` | `state["vcs"]` dict |
| `_get_memory(state, key, default=None)` | `memory` | `state["memory"]` dict |

**Usage rules:**
- Sub-state field read → MUST use the accessor. Direct `state.get("flat_field")` returns `None` (the flat field no longer exists).
- Ephemeral flat field read → `state.get(key, default)` directly (see table below).
- `_get_debug` maps `notes` → `debug_notes` (legacy field-name alias preserved).
- `input_files` was removed from `FilesState` in v3.0 — it was just a mirror of the core `files` flat field. `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly (the core flat field set by the facade).

---

## 🔁 RMW Pattern (Read-Modify-Write)

LangGraph replaces dict values, doesn't deep-merge. Returning `{"tdd": {"debug_history": [...]}}` clobbers every other `tdd` field. Always do read-modify-write:

```python
from workflows.autocode_impl.state import _get_vcs

def node_push(state):
    current_vcs = dict(state.get("vcs", {}))           # 1. READ (shallow copy)
    success = _github_push(_get_vcs(state, "branch", ""), tid)
    current_vcs["pushed"] = success                    # 2. MODIFY (on the copy)
    return {"vcs": current_vcs}                        # 3. WRITE (return partial)
```

**Variants:**
- List field — copy elements before mutating: `history = [dict(e) for e in history]` (preserves snapshot safety).
- Multiple writers to the same sub-state — every writer does its own RMW on the latest state.

See [CHANGELOG.md](CHANGELOG.md) § "Track M1" → "Learnings from the tdd migration" for the historical P0 clobbering bugs that motivated this pattern.

---

## 🏗 Core Flat Fields (stay flat)

Set by the facade + read directly via `state.get(key, default)`. NOT sub-state — these are workflow input/output, not per-node scratch space.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `task` | `str` | `""` | Natural-language goal (facade-set — `run_workflow(goal=...)` is aliased to `state["task"]` by `base.py` for autocode). |
| `files` | `dict[str, str]` | `{}` | Initial file contents (facade-set). Read directly via `state.get("files", {})` — `input_files` mirror was removed in v3.0. |
| `mode` | `str` | `""` | One of `feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, `create_skill`, `audit`. (`add_feature` and `unclear` are NOT valid modes — `unclear` is a `task_type` value, not a `mode`.) |
| `trace_id` | `str` | `""` | Trace correlation ID. |
| `dry_run` | `bool` | `False` | Skip writes / commits / branches when `True`. |
| `task_type` | `str` | `""` | Classified task type (`feature`/`audit`/`edit`/`fix`/`refactor`/`create_skill`/`unclear`). |
| `project_root` | `str` | `""` | Workspace root for path resolution. |
| `autocode_run_path` | `str` | `""` | Per-run output directory. |
| `messages` | `list[AnyMessage]` | `[]` | LangGraph message reducer (annotated). |
| `status` | `str` | `"running"` | Workflow status (`running`/`success`/`failed`/etc.). |
| `error` | `str` | `""` | Error message on failure. |
| `result` | `str` | `""` | Final result string on success. |

> **Note:** `plan` is NOT in this table — it's a sub-state field (`plan_state["plan"]`), not a core flat field. Pre-v3.0 it was overloaded as both; v3.0 removed the flat mirror.

---

## ⚡ Ephemeral Flat Fields (stay flat — inter-node scratch)

These stay flat because they're inter-node scratch space, not part of any sub-state. Explicitly declared in `AutocodeState` TypedDict + `_default_state()`.

| Field | Set by | Read by | Purpose |
|-------|--------|---------|---------|
| `test_code` | `node_write_tests` | `node_persist_artifacts`, `node_llm_review` (preview only) | **[v3.2 P1-1]** Type annotation corrected from `str` to `list[str]` in `state.py` (was declared as `str` but `node_write_tests` always writes a `list[str]` — one string per test function). Consumers MUST handle the list type: `node_persist_artifacts` joins with `"\n\n"` before writing; `node_llm_review` does the same before slicing for the prompt preview (v3.2 P0-4). Never assume `test_code` is a `str`. |
| `test_files` | `node_persist_artifacts` | `node_run_pytest`, `node_run_tests` | Relative paths of test files. |
| `test_results` | `node_run_pytest`, `node_run_tests` | `node_debug`, `node_verify_decision`, `node_report`, `_shape_artifacts` | `{success, stdout, stderr, returncode}`. Removed from `TDDState` in v3.0 (stays flat-only). |
| `_pytest_output` | `node_run_pytest` | `node_llm_review`, `node_verify_decision` | First 2000 chars of pytest stdout+stderr. |
| `tests_passed` | `node_run_pytest`, `node_run_tests` | `node_verify_decision`, `node_llm_review` | Boolean test-pass status. |
| `lint_output` | `node_run_lint` | `node_llm_review`, `node_verify_decision` | First 500 chars of ruff stdout+stderr. |
| `lint_passed` | `bool \| None` | `node_verify_decision` | `None` when ruff unavailable. |
| `llm_review_data` | `node_llm_review` | `node_verify_decision` | `{automated_checks_passed, checks, summary}`. |
| `execution_notes` | `node_execute_step` | (downstream inspection) | Per-step execution notes. |
| `skill_path` | `node_create_skill` | `_shape_artifacts` | Path to created skill file. |
| `skill_created` | `node_create_skill` | `_shape_artifacts` | Skill creation success flag. |
| `patch_errors` | `node_apply_patches` | (downstream inspection) | Path-traversal blocks + missing-file + apply failures. |
| `evidence_outputs` | `node_verify_decision` | `_shape_artifacts` | `{tests, lint, regression}` (truncated). |
| `memory_context` | `node_brainstorm` | (downstream inspection) | KG-recalled memory context for the brainstorm. |

---

## 🗺 Migration History (Track M1)

**Status:** ✅ COMPLETE (v2.1–v2.7 + v3.0).

Track M1 migrated autocode from a flat ~35-field state dict to 8 focused sub-state TypedDicts behind a backward-compatible accessor layer. Each sub-state was migrated one at a time (lowest-risk first), building on what was learned from the `tdd` migration.

| Sub-state | Writer nodes | Shipped |
|-----------|-------------|---------|
| `tdd` | `debug.py`, `summarize_context.py`, `run_tests.py` | ✅ v2.0 → v2.0.1 |
| `vcs` | `commit.py`, `branch.py`, `plan.py`, `push.py`, `create_pr.py`, `merge_pr.py` | ✅ v2.1 (Batch 3a) |
| `plan` | `brainstorm.py`, `plan.py`, `execute.py`, `tests.py` | ✅ v2.2 (Batch 3c) |
| `files` | `apply_patches.py`, `write_new_files.py`, `persist_artifacts.py`, `brainstorm.py`, `execute.py` | ✅ v2.3 (Batch 3b) |
| `impact` | `analyze_impact.py` | ✅ v2.4 (Batch 1) |
| `debug` | `debug.py` | ✅ v2.5 (Batch 2) |
| `verify` | `verify_decision.py` | ✅ v2.6 (Batch 2) |
| `memory` | `memory.py` | ✅ v2.7 (Batch 1) |

**v3.0 cleanup (one mechanical pass):**
- Removed ~32 legacy flat-field mirrors from `AutocodeState` + `_default_state()`.
- Simplified all 8 accessors — legacy-fallback branches removed; each is now a 4-line sub-state-only read.
- 13 ephemeral flat fields explicitly declared (test_code, test_results, _pytest_output, etc.).
- 16 node files updated for flat-mirror removal + remaining direct flat reads switched to accessor calls.
- 9 test files updated to assert on sub-state reads.
- 2 nodes with `tdd_*` flat writes (`execute.py` + `run_tests.py`) converted to RMW sub-state writes.
- 1 state.py fix (pre-existing `"steps"` → `"plan"` key mismatch in `_default_state()` plan_state).
- `input_files` removed from `FilesState` (it was just a mirror of the core `files` flat field). `validate.py`, `brainstorm.py`, `plan.py`, `tests.py` now read `state.get("files", {})` directly.

The v2.0.5 split-brain warning is lifted — there is no flat fallback to be split-brained against.

**Key learnings (proven out across all 7 sub-states):**
1. RMW is mandatory — LangGraph replaces dict values, doesn't deep-merge.
2. Tests must use `_default_state()`, not minimal hand-built state (the split-brain bug was invisible to hand-built tests).
3. Copy before mutating — `[dict(e) for e in history]` before mutating list/dict entries.
4. Migrate the writer first, then the reader — readers using accessors before writers were migrated hit split-brain.
5. The accessor layer is the trap — 6 of 8 accessors were dead code at v2.0.5 (zero callers). Following INSTRUCTIONS.md #33 (old version) without writer migration would have hit split-brain.

See [CHANGELOG.md](CHANGELOG.md) § "Track M1" for the full per-version narrative + git history for per-commit details.

---

## 🔗 Cross-references

- **[API.md](API.md)** — State Fields (AutocodeState) section has the field tables; State Accessors section has the signature pattern + usage examples.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — § "[v3.0] Sub-state Architecture" has the design rationale + "Why an accessor layer" narrative.
- **[INSTRUCTIONS.md](INSTRUCTIONS.md)** — NEVER DO #32 (Never re-add legacy flat-field mirrors) + #33 (Always use accessors for sub-state reads) + #41 (Never use `state.get()` for sub-state fields) + #42 (Never write flat-field mirrors in node returns) + #43 (Never assume `input_files` exists in `files_state`); ALWAYS DO #29 (Always use accessor functions for sub-state reads) + the v3.0 anti-patterns.
- **[NODES.md](NODES.md)** — Per-node Reads/Returns lines reflect the accessor reads + sub-state-only RMW writes.
- **[CHANGELOG.md](CHANGELOG.md)** — Version History (v3.0 + v2.1–v2.7) + § "Track M1" for the migration narrative.

---

*Last updated: 2026-07-19 (v3.7). See [CHANGELOG.md](CHANGELOG.md) for version history.*
