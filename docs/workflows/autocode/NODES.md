<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 Node Reference

Per-node reference for all 32 nodes (29 active + 3 backward-compat wrappers) in the autocode workflow graph, in graph-execution order. For the facade/config see [API.md](API.md); for design rationale see [ARCHITECTURE.md](ARCHITECTURE.md); for state TypedDicts/accessors see [SUBSTATE.md](SUBSTATE.md).

> **[v3.0]** Sub-state is the ONLY storage. Accessors (`_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`) are the ONLY read path for sub-state fields. Ephemeral flat fields (`test_code`, `test_results`, `_pytest_output`, etc.) read via `state.get(key, default)`. See [SUBSTATE.md](SUBSTATE.md).
>
> **[v3.6]** `node_run_pytest`, `node_run_lint`, `node_run_tests` wrap every `subprocess.run(...)` with pre-check + `_remaining_timeout()` + post-check — bounds zombie linger to ≤1s past graph deadline.

---

## 📊 Nodes Table

| # | Phase | Node | Reads | Writes | Purpose |
|---|-------|------|-------|--------|---------|
| 1 | 1 | `node_classify_task` | `task`, `mode` | `task_type` | Classify task type via Router LLM with `mode` override (`fix_error`→`fix`, `improve`→`refactor`); JSON schema enforces enum. |
| 2 | 2 | `node_validate_input` | `task`, `mode`, `files` | `status`, `error`, `task` (sanitized) | Validate input + sanitize task (max 2000 chars + strip control chars) + path traversal check on `files` keys. |
| 3 | 3 | `node_brainstorm` | `task`, `task_type`, `files`, `project_root` | `plan_state.brainstorm_notes`, `memory_context`, `files` (KG-merged) | Brainstorm approach via Planner LLM; merges KG files BEFORE LLM call. |
| 4 | 4 | `node_write_plan` | `task`, `task_type`, `files`, `plan_state.spec` | `plan_state.plan`, `plan_state.current_step`, `vcs.branch` | Generate structured plan + branch name (`autocode/{slug}-{tid_suffix}`). |
| 5 | 5 | `node_git_branch` | `vcs.branch`, `project_root`, `dry_run` | (side effects only) | Create git branch; optional `AUTOCODE_PULL_BEFORE_BRANCH=1` pull first (graceful-skip if GitHub not configured). |
| 6 | 6 | `node_write_tests` | `task`, `task_type`, `files`, `plan_state.plan`, `plan_state.current_step`, `plan_state.spec` | `test_code` (list[str]), `plan_state.current_step` | Generate TDD tests via `role="test"` LLM. |
| 7 | 7 | `node_execute_step` | `task`, `task_type`, `files`, `plan_state.plan`, `plan_state.current_step` | `tdd.source_code`, `files_state.modified_files`, `plan_state.current_step`, `execution_notes` | Execute current plan step via `role="executor"` LLM; `_parse_json()` derives `modified_files`. |
| 8 | 8a | `node_apply_patches` | `tdd.source_code`, `project_root`, `dry_run` | `files_state.modified_files`, `patch_errors`, `status` (`dry_run`/`error`) | Apply `str_replace` patches to existing files; runs validation even in `dry_run` (v3.2 P0-5). |
| 9 | 8b | `node_write_new_files` | `tdd.source_code`, `project_root`, `dry_run` | `files_state.files_map`, `files_state.modified_files` | Write new/overwrite files atomically (`tempfile` + `os.replace` + `FileLock`); build `files_map` snapshots. |
| 10 | 8c | `node_persist_artifacts` | `test_code`, `trace_id`, `dry_run`, `tdd.source_code`, `tdd.iteration`, `debug.notes/root_cause/defense_notes` | `test_files`, `autocode_run_path` | Persist test file + generated code + debug log to per-run autocode folder. |
| 11 | 9 | `node_analyze_impact` | `files_state.files_map`, `project_root` | `impact.warnings`, `impact.targeted_test_cmd`, `impact.failed` | Blast radius analysis via `_run_async()` (asyncio.run); lazily queries kgraph for callers. |
| 12 | 10 | `node_run_tests` | `test_files`, `project_root`, `tdd.iteration`, `tdd.debug_history`, `impact.targeted_test_cmd` | `test_results`, `tests_passed`, `tdd.debug_history`, `tdd.status`, `tdd.iteration`, `tdd.last_test_error`, `tdd.error` | Run pytest subprocess (cancellation-aware v3.6); marks last `debug_history` entry `tests_passed=True` on success. |
| 13 | 11b | `node_swarm_fallback` | `tdd.debug_history`, `tdd.debug_summary`, `tdd.error` | `debug.root_cause/defense_notes/swarm_verdict/notes`, `tdd.status`/`source_code`/`last_test_error`/`debug_history` (HIGH), `status="failed"` (LOW) | Escalate to swarm consensus when debug retries exhausted (`AUTOCODE_SWARM_DEBUG_FALLBACK=1`); HIGH → reset for one more cycle, LOW → verify chain. |
| 14 | 11 | `node_systematic_debug` | `tdd.debug_history`, `tdd.iteration`, `tdd.max_retries`, `tdd.error`, `tdd.source_code`, `tdd.debug_summary` | `tdd.source_code`, `tdd.debug_history`, `tdd.status`, `tdd.error`, `debug.root_cause/defense_notes/notes/swarm_verdict/subagent_verdict/parallel_verdicts` | 4-phase debug (investigation → pattern → hypothesis → fix); 4-path chain (swarm → parallel subagent → single subagent → single-LLM); bails on architecture-question exit (3+ consecutive `tests_passed=False`). |
| 15 | 11a | `node_summarize_context` | `tdd.debug_history` | `tdd.debug_summary` | Compress `debug_history` via chonkie `SentenceChunker` (soft dep, JSON fallback) before re-entering loop. |
| 16 | 12a | `node_run_pytest` | `autocode_run_path`, `project_root`, `test_files` | `test_results`, `tests_passed`, `_pytest_output` | Fresh pytest on autocode test files; `ruff --select E999` pre-check (v3.1); cancellation-aware (v3.6). |
| 17 | 12b | `node_run_lint` | `files_state.modified_files`, `project_root` | `lint_output`, `lint_passed` | Ruff lint scoped to `modified_files` only (advisory — does not block commit); cancellation-aware (v3.6). |
| 18 | 12c | `node_llm_review` | `tdd.source_code`, `tests_passed`, `_pytest_output`, `lint_output`, `tdd.debug_summary`, `tdd.debug_history` | `llm_review_data` | LLM spec coverage + cleanliness review via `role="executor"`; injects `debug_summary` when `debug_history` > 5. |
| 19 | 12d | `node_verify_decision` | `tdd.status`, `tests_passed`, `lint_passed`, `_pytest_output`, `lint_output`, `llm_review_data`, `tdd.max_retries`, `tdd.error` | `verify.passed`, `verify.notes`, `evidence_outputs`, `status` (`failed` on early exit) | Compose results + hallucination guard (LLM claiming pass when tests fail); max_retries/stuck early-exit. |
| 20 | 13 | `node_report` | `task`, `task_type`, `files_state.files_map`, `test_results`, `verify.notes`, `vcs.commit_sha` | (side effects only — report tool call) | Generate structured report via `report(action="report", ...)`. |
| 21 | 13a | `node_hitl_gate` | `hitl_approved`, `trace_id` | `status` (`awaiting_approval` when gate fires) | Opt-in HiTL approval gate between `node_report` and `node_commit` (`AUTOCODE_HITL_ENABLED=1`, default OFF); saves checkpoint + pauses via async-checkpoint-resume. |
| 22 | 14 | `node_commit` | `verify.passed`, `dry_run`, `plan_state.plan`, `task_type`, `vcs.branch` | `vcs.commit_sha`, `status`, `result` | Commit changes to git branch; reads branch via `_get_vcs` accessor (v3.0). |
| 23 | 15a | `node_push` | `verify.passed`, `dry_run`, `vcs.branch` | `vcs.pushed` | Push branch to remote via `_github_push()` (gated on `AUTOCODE_PUSH_ON_COMMIT=1`); graceful-skip if not configured. |
| 24 | 15b | `node_create_pr` | `verify.passed`, `dry_run`, `task`, `task_type`, `vcs.commit_sha`, `vcs.pushed`, `vcs.branch`, `verify.passed`, `debug.root_cause`, `debug.swarm_verdict` | `vcs.pr_number`, `vcs.pr_url` | Create PR via `_github_pr_create()` (gated on `AUTOCODE_OPEN_PR=1`); hosts `_build_pr_body(state)`. |
| 25 | 15c | `node_merge_pr` | `verify.passed`, `dry_run`, `vcs.pr_number` | (terminal — `{}` always) | Auto-merge PR via `_github_pr_merge()` (gated on `AUTOCODE_AUTO_MERGE=1`, **DANGEROUS**); hardcoded to squash. |
| 26 | 16 | `node_distill_memory` | `task`, `task_type`, `debug.root_cause`, `debug.defense_notes` | (side effects only — memory store) | Distill procedural knowledge for future recall; non-fatal (code already committed; uses `tracer.warning`). |
| 27 | 17 | `node_create_skill` | `task`, `dry_run`, `hitl_approved`, `trace_id`, `project_root` | `skill_path`, `skill_created`, `status`, `result`, `error` | Create skill file (atomic write + AST validation + `importlib` smoke-test + git commit); HiTL check at top; empty-file rejection with fallback keys. |
| 28 | A1 | `node_audit_scan` | `project_root`, `trace_id` | `impact.audit_scan` (dict with `total_files`, `total_lines`, `files`, `dead_code_candidates`, `missing_type_hints`, `complexity_hotspots`, `dependency_map`), `status` (`audit_scan_complete`) | Walk `project_root`, find dead code via AST importer analysis, missing type hints; lazily queries kgraph. (v3.7 F7) |
| 29 | A2 | `node_audit_report` | `impact.audit_scan`, `trace_id` | `result`, `status` (`success`/`failed`) | Planner LLM summarizes audit findings into structured report via `AUDIT_REPORT_SYSTEM`. (v3.7 F7) |
| — | wrapper | `node_write_files` | (calls 3 split nodes) | (merges 3 split-node returns) | **Backward-compat wrapper** — calls `apply_patches` → `write_new_files` → `persist_artifacts`. Registered, NOT wired. |
| — | wrapper | `node_verify` | (calls 4 split nodes) | (merges 4 split-node returns) | **Backward-compat wrapper** — calls `run_pytest` → `run_lint` → `llm_review` → `verify_decision`. Registered, NOT wired. |
| — | wrapper | `node_publish` | (calls 3 split nodes) | (merges 3 split-node returns) | **Backward-compat wrapper** — calls `push` → `create_pr` → `merge_pr`. Registered, NOT wired. |

---

## 🔁 Loops + Branches

**Debug loop:** `node_systematic_debug` → `node_summarize_context` → `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` → `node_analyze_impact` → `node_run_tests` → (back to `node_systematic_debug` until `tdd_status` is `passed`, `max_retries_exceeded`, or `stuck`; OR architecture-question exit fires — 3+ consecutive `tests_passed=False`).

**`create_skill` branch (bypasses TDD):** `node_classify_task` → `node_create_skill` → END. Has AST validation + `importlib` smoke-test + git commit. HiTL check at top of `node_create_skill`.

**`audit` branch (bypasses TDD, read-only, v3.7 F7):** `node_classify_task` → `node_audit_scan` → `node_audit_report` → END. No tests, no commits, no code changes — produces a structured report only.

---

## 🧭 Conditional Routing

| Router | Source node | Branches |
|--------|-------------|----------|
| `route_after_classify` | `node_classify_task` | `feature`/`fix`/`refactor`/`edit`/`audit` → `node_validate_input`; `create_skill` → `node_create_skill`; `audit` → `node_audit_scan` (v3.7); `unclear` → END |
| `route_after_write_files` | `node_persist_artifacts` | `fix`/`refactor`/`feature`/`audit`/`edit` → `node_analyze_impact`; other → `node_run_pytest`; short-circuits to `node_run_pytest` on `status=="error"` |
| `route_after_run_tests` | `node_run_tests` | `pass`/`stuck` → `node_run_pytest`; `fail` → `node_systematic_debug`; `max_retries_exceeded` + `AUTOCODE_SWARM_DEBUG_FALLBACK=1` → `node_swarm_fallback`; short-circuits on `status=="error"` |
| `route_after_swarm_fallback` | `node_swarm_fallback` | HIGH confidence (`tdd.status == ""` AND `state.status != "failed"`) → `node_systematic_debug`; otherwise → `node_run_pytest` |
| `route_after_verify` | `node_verify_decision` | `passed` → `node_report`; `failed` → END (does NOT re-enter debug loop) |
| `route_after_hitl_gate` | `node_hitl_gate` | `awaiting_approval` → END; else → `node_commit` |

---

## 🧬 Debug Chain (inside `node_systematic_debug`)

Mutually exclusive — pick ONE per workflow run (NEVER DO #40). Chain is fall-through: each path's failure leads to the next.

| # | Path | Flag | Mechanism |
|---|------|------|-----------|
| 1 | Swarm | `AUTOCODE_SWARM_DEBUG=1` | `_swarm_debug_consensus()` — 2-run `consensus → vote`; confidence: `unanimous → HIGH`, `majority → MEDIUM`, `split → LOW`. |
| 2 | Parallel subagent (v3.5 F1) | `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` | `_parallel_subagent_debug()` — planner LLM emits N hypotheses via `PARALLEL_HYPOTHESES_SYSTEM`; `ThreadPoolExecutor(max_workers=N)` dispatches N `agent(action="subagent")` calls using `SUBAGENT_VALIDATE_SYSTEM`; aggregate by descending `hypothesis_confidence`. |
| 3 | Single subagent (v2.0.2) | `AUTOCODE_SUBAGENT_DEBUG=1` | `agent(action="subagent", role="executor")` with curated context (isolated — no full `state` passed). |
| 4 | Single-LLM (default) | (none) | `_call(role="executor", system=DEBUG_SYSTEM, ...)` with `_DEBUG_JSON_SCHEMA`. |

`AUTOCODE_SWARM_DEBUG_FALLBACK=1` (v3.1) is independent — it fires AFTER the debug loop exhausts retries (not inside `node_systematic_debug`). HIGH confidence → one more debug cycle; LOW/unavailable → verify chain.

---

*Last updated: 2026-07-19 (v3.8). See [CHANGELOG.md](CHANGELOG.md) for version history.*
