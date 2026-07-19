<- Back to [Autocode Overview](../AUTOCODE.md)

# 🧭 Sub-state Reference (v3.0)

Single source of truth for the v3.0 sub-state architecture. 8 TypedDicts, 8 accessor signatures, writers/readers table. For per-node reads/writes see [NODES.md](NODES.md); for state-field semantics see [API.md](API.md); for the v3.0 migration narrative see [CHANGELOG.md](CHANGELOG.md) § v3.0.

> **[v3.0]** Migration status: ✅ COMPLETE (Track M1 shipped across v2.1–v2.7 + v3.0). All 8 accessors are the ONLY read path for sub-state fields — legacy flat-field mirrors + accessor fallback branches were removed. Ephemeral flat fields stay flat by design.

---

## 📦 The 8 Sub-states

| Sub-state key | TypedDict | Writers (RMW) | Readers (accessor) | Key fields |
|---------------|-----------|---------------|---------------------|------------|
| `plan_state` | `PlanState` | `brainstorm.py`, `plan.py`, `execute.py`, `tests.py` | `commit.py`, `execute.py`, `llm_review.py`, `plan.py`, `tests.py` | `brainstorm_notes`, `plan`, `plan_accepted`, `spec`, `current_step` |
| `tdd` | `TDDState` | `debug.py`, `summarize_context.py`, `run_tests.py`, `execute.py`, `swarm_fallback.py` | `debug.py`, `llm_review.py`, `verify_decision.py`, `persist_artifacts.py`, `summarize_context.py` | `iteration`, `source_code`, `error`, `status`, `max_retries`, `last_test_error`, `tests_written`, `debug_history`, `debug_summary` |
| `files_state` | `FilesState` | `apply_patches.py`, `write_new_files.py`, `persist_artifacts.py`, `brainstorm.py`, `execute.py` | `analyze_impact.py`, `brainstorm.py`, `debug.py`, `memory.py`, `plan.py`, `report.py`, `run_lint.py`, `validate.py`, `write_new_files.py` | `files_map`, `modified_files` |
| `impact` | `ImpactState` | `analyze_impact.py`, `audit_scan.py` | `run_tests.py`, `audit_report.py` | `warnings`, `targeted_test_cmd`, `failed`, `audit_scan` |
| `debug` | `DebugState` | `debug.py`, `swarm_fallback.py` | `commit.py`, `create_pr.py`, `memory.py`, `persist_artifacts.py` | `notes`, `root_cause`, `defense_notes`, `swarm_verdict`, `subagent_verdict`, `parallel_verdicts` |
| `verify` | `VerifyState` | `verify_decision.py` | `commit.py`, `create_pr.py`, `merge_pr.py`, `push.py`, `report.py` | `notes`, `report`, `passed` |
| `vcs` | `VCSState` | `commit.py`, `branch.py`, `plan.py`, `push.py`, `create_pr.py`, `merge_pr.py` | `commit.py`, `create_pr.py`, `push.py`, `branch.py`, `report.py`, `debug.py`, `merge_pr.py` | `commit_sha`, `branch`, `pushed`, `pr_number`, `pr_url` |
| `memory` | `MemoryState` | `memory.py` | (internal only) | `notes` |

> **`plan` lives in `plan_state["plan"]` — it is NOT a flat field.** Pre-v3.0, `plan` was overloaded as both a flat `list[dict]` step list AND `plan_state["plan"]`. v3.0 removed the flat mirror — `_get_plan(state, "plan", [])` reads from `plan_state`; direct `state.get("plan", [])` returns `None`.

---

## 🔧 The 8 Accessor Functions

All 8 share this 4-line shape — sub-state-only, NO legacy flat-field fallback:

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
- `input_files` was removed from `FilesState` in v3.0 — readers use core `files` flat field directly (`state.get("files", {})`).

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

See [INSTRUCTIONS.md](INSTRUCTIONS.md) AP-1 for the anti-pattern (flat-field clobbering) that motivates this rule.

---

## 🏗 Flat Fields (stay flat — NOT sub-state)

For the complete flat-field tables (core + ephemeral), see [API.md](API.md) § State Fields. Summary:

**Core flat fields** (set by facade, read via `state.get(key, default)`): `task`, `files`, `mode`, `target_file`, `trace_id`, `dry_run`, `hitl_approved`, `task_type`, `project_root`, `autocode_run_path`, `messages`, `status`, `error`, `result`. Note: `plan` is NOT flat — it lives in `plan_state["plan"]`.

**Ephemeral flat fields** (inter-node scratch, read via `state.get(key, default)`):

| Field | Set by | Read by |
|-------|--------|---------|
| `test_code` (list[str]) | `node_write_tests` | `node_persist_artifacts`, `node_llm_review` |
| `test_files` | `node_persist_artifacts` | `node_run_pytest`, `node_run_tests` |
| `test_results` | `node_run_pytest`, `node_run_tests` | `node_debug`, `node_verify_decision`, `node_report`, `_shape_artifacts` |
| `_pytest_output` | `node_run_pytest` | `node_llm_review`, `node_verify_decision` |
| `tests_passed` | `node_run_pytest`, `node_run_tests` | `node_verify_decision`, `node_llm_review` |
| `lint_output` | `node_run_lint` | `node_llm_review`, `node_verify_decision` |
| `lint_passed` (bool \| None) | `node_run_lint` | `node_verify_decision` |
| `llm_review_data` | `node_llm_review` | `node_verify_decision` |
| `execution_notes` | `node_execute_step` | (downstream) |
| `skill_path` / `skill_created` | `node_create_skill` | `_shape_artifacts` |
| `patch_errors` | `node_apply_patches` | (downstream) |
| `evidence_outputs` | `node_verify_decision` | `_shape_artifacts` |
| `memory_context` | `node_brainstorm` | (downstream) |

---

## 🔗 Cross-references

- **[API.md](API.md)** — State Fields (AutocodeState) section has the field tables; return shape + status values.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — § Key Design Decision #2 ("Sub-state architecture") has the design rationale.
- **[INSTRUCTIONS.md](INSTRUCTIONS.md)** — NEVER DO #32, #33, #41, #42, #43; ALWAYS DO #19, #46, #47; AP-1 (flat-field clobbering anti-pattern).
- **[NODES.md](NODES.md)** — Per-node Reads/Writes columns reflect accessor reads + sub-state-only RMW writes.
- **[CHANGELOG.md](CHANGELOG.md)** — Version History (v3.0 + v2.1–v2.7) for the migration narrative.

---

*Last updated: 2026-07-19 (v3.8). See [CHANGELOG.md](CHANGELOG.md) for version history.*
