<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 Node Reference

Per-node reference for all 30 nodes in the autocode workflow graph
(26 active + 3 backward-compat wrappers + 1 HiTL gate). Nodes are listed in
graph-execution order. For the facade, output format, state accessors, see
[API.md](API.md). For the sub-state architecture, see [SUBSTATE.md](SUBSTATE.md).

> **[v3.0]** Sub-state is the ONLY storage. Accessors are the ONLY read path. See [SUBSTATE.md](SUBSTATE.md).
>
> **[v3.6]** `node_run_pytest`, `node_run_lint`, `node_run_tests` wrap `subprocess.run(...)` with pre-check + deadline-aware timeout (`_remaining_timeout()`) + post-check — bounds zombie linger to ≤1s past the graph deadline.
>
> **[v3.5]** Parallel subagent debug — 4th debug path in `node_systematic_debug` (mutually exclusive with swarm + single-subagent).
>
> **[v3.4]** `node_hitl_gate` (Phase 13a, opt-in via `AUTOCODE_HITL_ENABLED=1`).
>
> **[v3.3]** `_should_skip_node(state)` helper — canonical skip-status set for all 11 nodes.
>
> **[v3.2]** 6-LLM collective review hardening — 19 fixes (5 P0 + 6 P1 + 8 P2). See [CHANGELOG.md](CHANGELOG.md) § v3.2.
>
> **[v3.1]** Debug loop improvements — #42 goal sanitization, #41 AST pre-check, F3 `debug_summary` injection, #48 `node_swarm_fallback`.

See [CHANGELOG.md](CHANGELOG.md) for version history.

**[v2.0] Lazy Dev / YAGNI Ladder:** `CODER_SYSTEM` includes the 7-rung minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code). See INSTRUCTIONS.md ALWAYS DO #38 + #39.

---

## ⚡ Nodes

### `node_classify_task(state)` — Phase 1: Classify Task Type

**Purpose:** Classify the task type using the Router LLM.

**Logic:**
1. Build prompt with goal, mode, and context.
2. Call `llm.complete(role="router", ...)`.
3. Parse JSON response for task type. `json_schema` enforces the `task_type` enum (`feature`/`audit`/`edit`/`fix`/`refactor`/`create_skill`/`unclear`) at generation time.

**Output:** Partial dict with `task_type` ("fix" | "improve" | "feature" | "create_skill" | "unclear").

**Error handling:** LLM failure or parse failure → returns `{"task_type": "unclear"}`.

**Note:** Mode override takes precedence over LLM classification. If `mode == "fix_error"`, `task_type` is always `"fix"`.

---

### `node_validate_input(state)` — Phase 2: Validate Input

**Purpose:** Validate input parameters. Also sanitizes the task: enforces max length (2000 chars) + strips control characters before downstream nodes see the task.

**Logic:**
1. Check `task` is non-empty + a string.
2. Enforce `MAX_TASK_LENGTH = 2000` — return `{"status": "error", "error": "Task too long (...)"}` if exceeded.
3. Strip control chars via `re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', task)` — keeps `\n`, `\t`, `\r`. If anything was stripped, return `{"task": cleaned_task}` so LangGraph merges the cleaned value.
4. Check `mode` is in the valid-modes set (when provided).
5. Check `files` is a dict with valid paths.
6. Path traversal check — catches Unix (`..` / leading `/`), Windows absolute (`C:\`), and URL-encoded (`%2f`, `%5c`) traversal in `files` keys.

**Output:** Partial dict with `status` ("error" if invalid) + `error` message — OR `{"task": cleaned_task}` when only control-char stripping occurred. Returns `{}` when nothing changed.

**Note:** Control-char stripping is non-fatal — the cleaned task is transparently substituted via the state update. Downstream nodes never see the raw control chars.

---

### `node_brainstorm(state)` — Phase 3: Brainstorm Approach

**Purpose:** Brainstorm the approach using the Planner LLM.

**Logic:**
1. Recall relevant memories.
2. Query the knowledge graph (KG) for relevant files and merge them into the files context BEFORE building the LLM prompt (was: merged into state AFTER the call — brainstorm never saw them).
3. Unconditionally initialize `files_update` before the KG block. Merge KG files via `files_update = {**kg_files, **files_update}` (preserves state-files-take-priority merge order).
4. Build prompt with goal, task type, context (now including KG files).
5. Call `llm.complete(role="planner", ...)`.
6. Parse JSON response for approach.

**Output:** Partial dict with `brainstorm` (approach text) and `files` (updated with KG files).

---

### `node_write_plan(state)` — Phase 4: Generate Plan

**Purpose:** Generate a step-by-step plan using the Planner LLM.

**Logic:**
1. Build prompt with goal, task type, and context.
2. Call `llm.complete(role="planner", ...)`.
3. Parse JSON response for plan steps.

**Output:** Partial dict with `plan` (list of step dicts) and `branch` (branch name).

**Note:** Fallback plan has 3 steps: write_tests → implement → verify. Branch name appends a `trace_id` suffix (`autocode/{slug}-{tid_suffix}` where `tid_suffix = tid.replace("-", "")[:8]`) for uniqueness. Blast-radius warning built via shared `_blast_radius_warning()` helper in `helpers.py` (lazy `kgraph` import).

---

### `node_git_branch(state)` — Phase 5: Create Git Branch

**Purpose:** Create a git branch for the changes.

**Logic:**
1. If `cfg.autocode_pull_before_branch` is ON, call `_github_pull(tid)` (non-blocking on failure).
2. Create branch via `_git_create_branch()` (if `_get_vcs(state, "branch", "")` is set).

**Output:** Empty dict (side effects only). On branch-creation failure: `{"status": "error", "error": "Failed to create git branch: <name>"}`.

**Optional pull before branch:** Gated on `AUTOCODE_PULL_BEFORE_BRANCH=1` (default OFF). Graceful-skip if GitHub is not configured (`is_configured()` returns `False`).

---

### `node_write_tests(state)` — Phase 6: Generate Tests (TDD)

**Purpose:** Generate tests for the feature/fix.

**Logic:**
1. Build prompt with goal, task type, and context.
2. Call `llm.complete(role="test", ...)`.
3. Extract code from markdown fences.

**Output:** Partial dict with `test_code` (list of test strings — ephemeral flat field) and `plan_state` (RMW: `current_step`).

**Note:** `test_code` is `list[str]`. `node_persist_artifacts` joins with `"\n\n"` if list.

---

### `node_execute_step(state)` — Phase 7: Execute Plan Step

**Purpose:** Execute a single step of the plan.

**Logic:**
1. Get current step from plan.
2. Build prompt with step description and context.
3. Call `llm.complete(role="executor", ...)`.
4. Extract code from JSON or markdown fences.
5. Use `_parse_json()` to derive `modified_files` (was: raw `json.loads(code)` → markdown-fenced JSON raised `JSONDecodeError`).
6. Removed dead `json.loads(code)` fallback — `_parse_json` already tries direct `json.loads` first; on empty dict, traces a warning + sets `modified_files=[]`.

**Output:** Partial dict with `tdd` (RMW: `source_code`), `files_state` (RMW: `modified_files`), `plan_state` (RMW: `current_step`). `execution_notes` (ephemeral flat) may also be set.

---


### `node_audit_scan(state)` — [v3.7 F7] Audit: Whole-Repo Scan

**Purpose:** Walk `project_root`, collect codebase metrics for audit mode.
**Reads:** `project_root`, `trace_id`
**Writes:** `impact.audit_scan` (dict with `total_files`, `total_lines`, `files`, `dead_code_candidates`, `missing_type_hints`, `complexity_hotspots`, `dependency_map`)
**Logic:** Walks `.py` files (skips `__pycache__`, `.git`, `venv`, etc.), counts lines, uses AST to find dead code (files not imported by anyone) + missing return type hints. Lazily queries kgraph for dependency maps (non-fatal if unavailable).
**Status:** Returns `{"status": "audit_scan_complete"}` on success.

### `node_audit_report(state)` — [v3.7 F7] Audit: LLM Report

**Purpose:** Call planner LLM to summarize audit findings into a structured report.
**Reads:** `impact.audit_scan`, `trace_id`
**Writes:** `result` (str — the report), `status` ("success")
**Logic:** Builds a user prompt from the scan results (JSON-dumped), calls `_call(role="planner", system=AUDIT_REPORT_SYSTEM, ...)`, stores the response in `state["result"]`.
**Status:** Returns `{"status": "success", "result": report}` on success, `{"status": "failed", "error": ...}` on LLM failure.

### `node_write_files(state)` — Phase 8: BACKWARD-COMPAT WRAPPER

**Purpose:** File writing — apply patches, write new files, persist run-dir artifacts.

**[v2.0] BACKWARD-COMPAT WRAPPER:** Thin wrapper that calls `node_apply_patches({**state, **result})` → `node_write_new_files({**state, **result})` → `node_persist_artifacts({**state, **result})` and merges their partial state updates.

**Output (merged):** Primarily `files_state` sub-state (`files_map`, `modified_files`) + ephemeral flat fields (`test_files`, `autocode_run_path`, `patch_errors`).

**Note:** Registered via `add_node(...)` but NOT wired. Excluded from `WORKFLOW_METADATA["nodes"]`. `# TODO(2.0-post):` wrapper removal deferred.

---

### `node_apply_patches(state)` — Phase 8a: Apply str_replace Patches

**Purpose:** Apply `str_replace` patches to existing files only. First of the 3 Phase 3.1 split nodes (was inside `node_write_files`).

**Logic:**
1. Read `tdd.source_code` JSON via `_get_tdd(state, "source_code", "")` + `_parse_json()` (handles markdown fences).
2. Extract `patches[]` array.
3. For each patch: validate path via `_is_path_safe()`, skip if protected, skip if file missing, else call `apply_patch(target, old_text, new_text)`.
4. Build `modified_files` list + `patch_errors` list.

**Returns:** `{"files_state": current_files (sub-state RMW with modified_files), "patch_errors"?: list[str]}` — or `{"status": "error", "error": str}` on JSON parse failure, or `{"status": "dry_run", "files_state": current_files}` when `dry_run=True`.

**Source:** `workflows/autocode_impl/nodes/apply_patches.py` (also hosts `_is_path_safe()` shared with `write_new_files.py`).

**`dry_run` path runs validation:** Per-patch validation loop runs FIRST (populating `patch_errors`), THEN dry-run early-return fires (with `patch_errors` included). Skip-condition status check includes `"error"` in the set.

---

### `node_write_new_files(state)` — Phase 8b: Write New Files + Build files_map

**Purpose:** Write new files / overwrite existing ones atomically. Also builds `files_map` for `analyze_impact`. Second of the 3 Phase 3.1 split nodes.

**Logic:**
1. Read `tdd.source_code` JSON + `_parse_json()`. Extract `new_files{}` dict (backwards-compat: if no `patches`/`new_files` keys, treat whole dict as files).
2. For each file: validate path via `_is_path_safe()` (imported from `apply_patches.py`), skip if protected, else write atomically (`tempfile.NamedTemporaryFile` + `os.replace` + `FileLock` with 1 retry on timeout).
3. Call `_cleanup_old_autocode_runs()` for on-demand run-dir pruning.
4. Build `files_map` — snapshots of all modified files with `{content_preview, preview_md5, full_md5, size, truncated}` for `analyze_impact`.
5. Merge new files into `modified_files` (set union) so downstream nodes see them.

**Returns:** `{"files_state": current_files (sub-state RMW with files_map + modified_files)}` — or `{}` when `status` is `needs_clarification`/`failed`/`error`, `tdd.source_code` is empty, or `dry_run=True`.

**Source:** `workflows/autocode_impl/nodes/write_new_files.py` (imports `_is_path_safe` from `apply_patches.py`).

---

### `node_persist_artifacts(state)` — Phase 8c: Persist Test File + Generated Code + Debug Log

**Purpose:** Persist test file + generated code + debug log to the per-run autocode folder. Third of the 3 Phase 3.1 split nodes. Sets `test_files` + `autocode_run_path` for downstream verify nodes.

**Logic:**
1. Resolve `run_dir` via `_get_autocode_run_path(tid)` (or read from `state["autocode_run_path"]`).
2. Write `test_autocode_feature.py` from `state["test_code"]` (joined `"\n\n"` if list) using `FileLock` (10s timeout).
3. Write `generated_code.json` from `_get_tdd(state, "source_code", "")` (if present).
4. Write `debug_log.json` from `_get_debug(state, "notes/root_cause/defense_notes", "")` + `_get_tdd(state, "iteration", 0)` (if any are present).
5. Return `test_files` (relative paths) + `autocode_run_path` (absolute path).

**Returns:** `{"test_files": list[str], "autocode_run_path": str}` — or `{}` when `status` is `needs_clarification`/`failed`/`error`, `dry_run=True`, or `test_code` is empty.

**Source:** `workflows/autocode_impl/nodes/persist_artifacts.py`.

---

### `node_analyze_impact(state)` — Phase 9: Analyze Blast Radius

**Purpose:** Analyze the impact of changes on the codebase.

**Logic:**
1. Get modified files from state
2. Query dependency graph for affected files
3. Generate impact warnings

**Output:** Partial dict with `impact` (sub-state RMW: writes `warnings` — list of dicts with `type`, `message`, `agent_fault`).

**Note:** `node_analyze_impact` uses `_run_async()` to wrap async calls (`parse_dependencies_from_string`, `get_targeted_tests`). `_run_async()` is `asyncio.run(coro)` (was create/destroy event loop per call).

---

### `node_run_tests(state)` — Phase 10: Run Tests

**Purpose:** Run the generated tests. Cancellation-aware (v3.6 #35).

**Logic:**
1. **[v3.6 #35]** Check `is_cancellation_requested()` before tests — if the graph already timed out, bail immediately with `{"success": False, "stdout": "", "stderr": "Cancelled", "returncode": -1}`.
2. Get test files from state
3. Filter out test files that don't exist on disk (write_files may have failed to write them).
4. Run tests via `subprocess.run([python, "-m", "pytest", "-v", "--tb=short", ...targets], timeout=_remaining_timeout(cfg.sandbox_timeout), cwd=project_root)`.
   - **[v3.6 #35]** Subprocess timeout is capped at the remaining graph budget via `_remaining_timeout()` so the subprocess can't outlive the graph deadline by more than ~1s.
5. **[v3.6 #35]** Check `is_cancellation_requested()` after tests — if the graph timed out during the subprocess, discard the results.
6. If `test_results.success`, mark the last entry in `debug_history` (read via `_get_tdd`) with `tests_passed=True`, then read-modify-write the `tdd` sub-state to preserve other fields. Without this, every `debug_history` entry stayed `tests_passed=False` forever, causing the architecture-question exit to fire prematurely after 3 iterations.

**Output:** Partial dict with `test_results` (ephemeral flat), `tests_passed` (ephemeral flat), and `tdd` (sub-state RMW: writes `debug_history`, `status`, `iteration`, `last_test_error`, `error` as needed).

**Source:** `workflows/autocode_impl/nodes/run_tests.py`.

---

### `node_swarm_fallback(state)` — Phase 11b: Swarm Consensus when Debug Retries Exhausted

**Purpose:** Give the debug loop one more chance via multi-model consensus. HIGH confidence → inject verdict + reset `tdd_status` (one more debug cycle); LOW/MEDIUM/unavailable → `status="failed"` (verify chain).

**Logic:**
1. Read `debug_history`, `debug_summary`, and `error` from the `tdd` sub-state. Build a context block — prefer `debug_summary` (first 2000 chars); otherwise render last 3 `debug_history` entries (truncated to 200 chars each).
2. Call `_swarm_debug_consensus(system=DEBUG_SYSTEM, user=<context>, tid=tid)` (2-run `consensus → vote` pattern). Returns `None` when no providers configured / import failure / consensus exception.
3. **`None`** → trace + return `{"status": "failed"}` → graph routes to `node_run_pytest`.
4. **`HIGH`** → RMW `debug` (`root_cause`, `defense_notes`, `swarm_verdict`, `notes`) + RMW `tdd` (`status=""` RESET, `source_code=suggested_fix`, `last_test_error=""` cleared). Append `phase="swarm_fallback"` entry to `debug_history`. Graph routes to `node_systematic_debug`.
5. **`LOW`/`MEDIUM`** → RMW `debug` (`swarm_verdict` + `notes`) for report; return `{"status": "failed", "debug": current_debug}`. Graph routes to `node_run_pytest`.

**Returns:** HIGH → `{"tdd": ..., "debug": ...}`; otherwise → `{"status": "failed", "debug": ...}`.

**Routing:** `node_run_tests` → `route_after_run_tests` → `node_swarm_fallback`. Named `route_after_swarm_fallback()` in `routes.py`: HIGH (`tdd.status == ""` AND `state.status != "failed"`) → `node_systematic_debug`; otherwise → `node_run_pytest`.

**Source:** `workflows/autocode_impl/nodes/swarm_fallback.py` (imports `_swarm_debug_consensus` from `vcs_ops.py`, `DEBUG_SYSTEM` from `constants.py`).

**Note:** `AUTOCODE_SWARM_DEBUG_FALLBACK` is INDEPENDENT of `AUTOCODE_SWARM_DEBUG` — the latter controls swarm INSIDE the debug loop; the former controls swarm AFTER the debug loop is exhausted. Non-blocking by design.

**Smoke test:** `tests/workflows/autocode/test_swarm_integration.py::TestSwarmFallbackIntegration` (3 tests) + `test_swarm_fallback_fixes.py` (4 tests for the P0 fixes).

---

### `node_systematic_debug(state)` — Phase 11: Debug Failures

**Purpose:** Debug test failures. 4-phase prompt (investigation → pattern → hypothesis → fix), accumulates `debug_history` across iterations, bails on architecture-question detection (3+ consecutive `tests_passed=False`).

**Logic:**
1. Read `debug_history` from `TDDState` sub-state via `_get_tdd(state, "debug_history", [])`.
2. **Architecture-question exit:** If `len(debug_history) >= _ARCHITECTURE_QUESTION_THRESHOLD` (3, configurable via `AUTOCODE_ARCHITECTURE_QUESTION_THRESHOLD`) AND all last 3 entries have `tests_passed=False`, bail with `tdd_status="max_retries_exceeded"` + procedural memory store. RMW preserves sibling TDD fields.
3. Check `current_iteration > max_retries` — bail with `tdd_status="max_retries_exceeded"` + procedural memory store.
4. Build prompt with test output + context (includes blast-radius warning via shared `_blast_radius_warning()` helper — lazy `kgraph` import).
5. Use `DEBUG_SYSTEM` (4-phase structured prompt, inspired by obra/superpowers `systematic-debugging`). JSON output includes required `phase` field (enum enforced by `_DEBUG_JSON_SCHEMA`).
6. If `debug_summary` is non-empty AND `len(debug_history) > 5`, replace raw last-5-entries with "DEBUG SUMMARY (compressed)" block. Otherwise inject last 5 entries under `--- PRIOR DEBUG ATTEMPTS (do NOT repeat these) ---`.
7. **Debug chain (mutually exclusive — NEVER DO #40):**
   - **Swarm** (`AUTOCODE_SWARM_DEBUG=1`): `_swarm_debug_consensus(...)` — 2-run `consensus → vote`. Confidence: `unanimous → HIGH`, `majority → MEDIUM`, `split` → `LOW`. `None` → fall through.
   - **Parallel subagent** (`AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`, v3.5 F1): `_parallel_subagent_debug(...)` — planner LLM emits N hypotheses via `PARALLEL_HYPOTHESES_SYSTEM`; `ThreadPoolExecutor(max_workers=N)` dispatches N `agent(action="subagent")` calls (`SUBAGENT_VALIDATE_SYSTEM`); aggregate by descending `hypothesis_confidence`; winner in `debug.subagent_verdict`, ALL in `debug.parallel_verdicts`. Falls through on hypothesis-generation failure, `< 2` hypotheses, or all-subagents-failed.
   - **Single subagent** (`AUTOCODE_SUBAGENT_DEBUG=1`): `agent(action="subagent", role="executor", ...)` with curated context. Falls through on failure.
   - **Single-LLM** (default): `llm.complete(role="executor", ..., json_schema=_DEBUG_JSON_SCHEMA)`.
8. Parse JSON response for `phase`, `root_cause`, `defense_notes`, and `fix`. Default `phase` to `"investigation"`.
9. If swarm returned LOW confidence AND `cfg.autocode_debug_comment_pr` is ON AND a PR exists, post a warning comment on the PR.
10. Append entry to `debug_history`: `{iteration, phase, root_cause, fix: (suggested_fix or "")[:200], tests_passed: False}` (updated to True by `node_run_tests` next iteration if fix worked). Swarm-path entries include `confidence`. RMW preserves sibling TDD fields.

**Output:** Partial dict with `tdd` (RMW: `source_code` = suggested fix, `debug_history`, `status`, `error`) + `debug` (RMW: `root_cause`, `defense_notes`, `notes`, `swarm_verdict`, `subagent_verdict`, `parallel_verdicts`). Both early-exit paths preserve `debug_history`.

**Note:** `DEBUG_SYSTEM` prompt uses `root_cause` / `defense_notes` (matching TypedDict). Swarm is non-blocking — fix is always applied regardless of confidence; LOW confidence surfaces as a PR comment (if enabled).

**Fallback chain:** swarm → parallel subagent → single subagent → single-LLM. See [API.md](API.md) § "Parallel Subagent Debug" for parallel-path pipeline.

**Smoke tests:** `tests/workflows/autocode/test_swarm_integration.py::TestSwarmDebugIntegration` (2 tests) + `test_parallel_subagent.py` (3 classes, 4 tests).

---

### `node_summarize_context(state)` — Phase 11a: Compress debug_history

**Purpose:** Compress `debug_history` before re-entering the debug loop. Wired between `node_systematic_debug` and `node_apply_patches` so the next iteration sees a bounded context.

**Logic:**
1. Read `debug_history` from `TDDState` sub-state via `_get_tdd(state, "debug_history", [])`.
2. If empty, return `{"tdd": {"debug_summary": ""}}` (RMW preserves sibling TDD fields).
3. Otherwise, call `_summarize_debug_history(history)`:
   a. Reverse the history (most recent first) + render each entry as a single sentence.
   b. Try `from chonkie import SentenceChunker` (lazy import, soft dep) — instantiate `SentenceChunker(chunk_size=512, chunk_overlap=0)` and return the FIRST chunk's content.
   c. On ANY `Exception`, fall back to `json.dumps(reversed_history[:3], ensure_ascii=False, default=str)`.
4. Read-modify-write `tdd` sub-state with `debug_summary`.

**Returns:** `{"tdd": {"debug_summary": str}}` (or full `tdd` sub-state with `debug_summary` merged in). Empty string when history is empty.

**Source:** `workflows/autocode_impl/nodes/summarize_context.py` (~110 lines).

**Note:** Does NOT mutate `debug_history` — the full history is preserved for the architecture-question exit check in `node_systematic_debug`. chonkie is a SOFT dependency — do NOT make it a hard dependency.

---

### `node_verify(state)` — Phase 12: BACKWARD-COMPAT WRAPPER

**Purpose:** Verify the changes with linting, regression tests, and LLM spec review.

**[v2.0] BACKWARD-COMPAT WRAPPER:** This node is a thin wrapper that calls the 4 split nodes in sequence and merges their partial state updates into one dict matching the original return shape:
- `node_run_pytest({**state, **result})` →
- `node_run_lint({**state, **result})` →
- `node_llm_review({**state, **result})` →
- `node_verify_decision({**state, **result})`

**Output (merged):** Partial dict that merges the 4 split-node returns — primarily the `verify` sub-state (`passed`, `notes`, `report`) + ephemeral flat fields (`test_results`, `tests_passed`, `llm_review_data`, `lint_passed`, `lint_output`, `_pytest_output`) + `evidence_outputs`.

**Note:** Registered via `add_node(...)` but NOT wired. Excluded from `WORKFLOW_METADATA["nodes"]`. `# TODO(2.0-post):` wrapper removal deferred.

---

### `node_run_pytest(state)` — Phase 12a: Fresh Pytest Subprocess (cancellation-aware, with ruff E999 syntax pre-check)

**Purpose:** Run a fresh pytest subprocess on the autocode run directory. First of the 4 Phase 3.2 split nodes (was inside `node_verify`). Runs `ruff --select E999` (syntax-only) BEFORE pytest — if syntax errors exist, skips pytest and returns the error directly (saves ~30s on a doomed pytest run). Cancellation-aware (v3.6 #35).

**Logic:**
1. Resolve `run_dir` from `state["autocode_run_path"]` or `_get_autocode_run_path(tid)`.
2. If no test files exist (`tests_dir` and `test_file` both missing), skip pytest entirely (was: ran `pytest` with no args → entire project test suite).
3. **[v3.6 #35]** Pre-check `is_cancellation_requested()` — bail with a cancelled result if the graph already timed out.
4. **AST/syntax pre-check** (`ruff --select E999`): run with `cwd=base_path` and `timeout=_remaining_timeout(10)`. On syntax errors → return structured error result, skip pytest. On `FileNotFoundError`/`TimeoutExpired`/`Exception` → trace non-fatal warning, fall through to pytest.
5. **[v3.6 #35]** Post-ruff cancellation check — bail before the expensive pytest call if the graph timed out during ruff.
6. Run `[python, "-m", "pytest", "--tb=short", "--color=no", "-q", ...targets]` with `cwd=base_path` and `timeout=_remaining_timeout(cfg.sandbox_timeout)` (capped at remaining graph budget).
7. Build `test_results` dict `{success, stdout, stderr, returncode}` + `tests_passed` bool + ephemeral `_pytest_output` (first 2000 chars — stashed for `llm_review`).
8. **[v3.6 #35]** Post-pytest cancellation check — if the graph timed out during the pytest call, discard the results so the daemon thread can exit promptly.

**Returns:** `{"test_results": dict, "tests_passed": bool, "_pytest_output": str}` — handles `FileNotFoundError` (pytest missing) + `subprocess.TimeoutExpired` with structured error returns. Also returns early with a structured syntax-error result when ruff E999 finds syntax errors (before pytest runs).

**Source:** `workflows/autocode_impl/nodes/run_pytest.py`.

**Note:** The ruff pre-check is a SOFT dependency — `ruff` may not be installed. The `except FileNotFoundError` handler makes it non-fatal: pytest runs anyway. Do NOT make `ruff` a hard dependency. See INSTRUCTIONS.md NEVER DO #44.

---

### `node_run_lint(state)` — Phase 12b: Ruff Lint on modified_files Only (cancellation-aware)

**Purpose:** Run `ruff check` scoped to `modified_files` only (advisory — does not block commit). Second of the 4 Phase 3.2 split nodes. Cancellation-aware (v3.6 #35).

**Logic:**
1. Read `modified_files` from state; if empty, return `{"lint_output": "No modified files to lint", "lint_passed": None}`.
2. Resolve `lint_targets` as absolute paths.
3. **[v3.6 #35]** Pre-check `is_cancellation_requested()` — bail with `{"lint_output": "Cancelled", "lint_passed": None}` if cancelled.
4. Run `[python, "-m", "ruff", "check", ...targets, "--select", "E,F", "--no-cache"]` with `timeout=_remaining_timeout(30)` (capped at remaining graph budget).
5. Build `lint_output` (first 500 chars of stdout+stderr) + `lint_passed` (bool — `returncode == 0`).
6. **[v3.6 #35]** Post-subprocess cancellation check — discard results if cancelled.

**Returns:** `{"lint_output": str, "lint_passed": bool | None}` — `lint_passed` is `None` when ruff is unavailable or when no modified files.

**Source:** `workflows/autocode_impl/nodes/run_lint.py`.

---

### `node_llm_review(state)` — Phase 12c: LLM Spec Coverage + Cleanliness Review (with debug_summary injection)

**Purpose:** LLM-based spec review of the implementation. Third of the 4 Phase 3.2 split nodes. Calls `_call(role="executor", system=VERIFY_SYSTEM, ...)` with implementation context, fresh pytest output, and ruff output. When `debug_history` > 5 entries, also injects the compressed `debug_summary` so the verify LLM has the accumulated debug knowledge without the prompt exploding.

**Logic:**
1. Build `impl_ctx` from `_get_tdd(state, "source_code", "{}")` JSON — extract `patches[].new` (first 1500 chars each) + `new_files{}` values (first 1500 chars each). Fallback: raw `tdd.source_code[:3000]` on parse failure.
2. Read `tests_passed`, `_pytest_output` (from `node_run_pytest`), `lint_output` (from `node_run_lint`) from state.
3. Read `debug_summary` + `debug_history` length via `_get_tdd`. If `debug_summary` is non-empty AND `len(debug_history) > 5`, build a `debug_context_block = "\n\nDEBUG SUMMARY (compressed from <N> iterations):\n<debug_summary[:2000]>\n"`; otherwise empty.
4. Call `_call(role="executor", system=VERIFY_SYSTEM, user=<spec + impl + tests + pytest output + ruff output + debug_context_block>, timeout=EXECUTOR_TIMEOUT, trace_id=tid)`.
5. Parse response via `_parse_json(raw)` → `data` dict `{automated_checks_passed, checks: {syntax, tests, spec, regressions, cleanliness}, summary}`.
6. On `_call` exception: `tracer.error(tid, "llm_review", ...)` + return `{"llm_review_data": {"automated_checks_passed": False, "checks": {}, "summary": "LLM verification error"}}`.

**Returns:** `{"llm_review_data": dict}` — always returns a dict (even on error). Or `{}` when `status` is `needs_clarification`/`failed`.

**Source:** `workflows/autocode_impl/nodes/llm_review.py` (imports `_call` + `_parse_json` from `helpers.py`; `VERIFY_SYSTEM` from `constants.py`; `EXECUTOR_TIMEOUT` + `_get_plan` + `_get_tdd` from `state.py`).

**Note:** This is the only node in the verify chain that calls the LLM. `node_verify_decision` (next) consumes `llm_review_data` and applies the hallucination guard.

---

### `node_verify_decision(state)` — Phase 12d: Compose Results + Hallucination Guard

**Purpose:** Compose the results from the 3 previous nodes (run_pytest + run_lint + llm_review) and make the final verification decision. Fourth of the 4 Phase 3.2 split nodes. Also handles the `tdd_status in ("max_retries_exceeded", "stuck")` early-exit path.

**Logic:**
1. **Early exit:** If `_get_tdd(state, "status", "")` is in (`max_retries_exceeded`, `stuck`), log `tracer.error(...)`, store a procedural memory (non-fatal, wrapped in try/except), return `{"status": "failed", ...}`.
2. Read ephemeral flat results from state: `tests_passed`, `lint_passed`, `_pytest_output`, `lint_output`, `llm_review_data`.
3. Compute `automated_ok = tests_passed` (lint is advisory only).
4. **Hallucination guard:** If `not tests_passed` AND `llm_review_data["automated_checks_passed"]` is True, log "HALLUCINATION DETECTED" — real exit code overrides LLM claim.
5. Compute `llm_checks_ok` = all of `syntax`, `tests`, `spec`, `regressions`, `cleanliness` checks pass.
6. Final decision: `all_passed = automated_ok AND llm_checks_ok`.
7. Build `verify.notes` (Automated/LLM PASS/FAIL + summary + JSON-encoded checks) + `evidence_outputs` `{tests, lint, regression}` (truncated to 2000/500/2000 chars).

**Returns:** `{"verify": current_verify (sub-state RMW with passed + notes), "evidence_outputs": dict, "trace_id": str}` — or `{"status": "failed", ...}` on max_retries/stuck early-exit, or `{}` on `needs_clarification`/`failed`/`dry_run`.

**Source:** `workflows/autocode_impl/nodes/verify_decision.py`.

**Note:** `route_after_verify` routes from this node (was: from `node_verify` before Phase 3.2 split).

**`automated_checks_passed` default `False`:** On malformed JSON (missing the key), `_parse_json()` returns `{}`, and `node_verify_decision` reads `llm_review_data.get("automated_checks_passed", False)` — the verify chain fails cleanly rather than falsely accusing the LLM of hallucinating. The legitimate-LLM-response path is unaffected.

---

### `node_report(state)` — Phase 13: Generate Report

**Purpose:** Generate a structured report with the final result.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with result and metadata
2. Return the report

**Output:** Empty dict (side effects only).

---

### `node_hitl_gate(state)` — Phase 13a: HiTL Approval Gate (v3.4 #38)

**Purpose:** Opt-in Human-in-the-Loop approval gate between `node_report` and `node_commit`. Pauses the workflow when `AUTOCODE_HITL_ENABLED=1` AND `state["hitl_approved"]` is False — saves a checkpoint, returns `{"status": "awaiting_approval"}`, and `route_after_hitl_gate` routes to END. The operator resumes with `run_workflow("autocode", goal="...", resume=True, hitl_approved=True)`.

**Logic:**
1. If `cfg.autocode_hitl_enabled` is False (default) → return `{}` (no-op).
2. If `state.get("hitl_approved", False)` is True → return `{}` (already approved).
3. Else: `tracer.step(...)` → `save_checkpoint(tid, "hitl", state)` (wrapped in `try/except` — checkpoint failure is non-fatal, the pause still happens) → return `{"status": "awaiting_approval"}`.

**Output:** `{}` (pass-through) OR `{"status": "awaiting_approval"}` (pause).

**Routing:** `route_after_hitl_gate(state)`: `status == "awaiting_approval"` → `"END"`; else → `"node_commit"`.

**Design notes:** See [API.md](API.md) § "HiTL Approval Gate" for the async-checkpoint-resume vs. sync-pause rationale. Checkpoint failure is non-fatal — the gate STILL pauses. `node_create_skill` has its OWN HiTL check at the TOP of the function (same pattern).

---

### `node_git_commit(state)` — Phase 14: Commit Changes

**Purpose:** Commit the changes to git.

**Logic:**
1. Generate commit message
2. Call `git(action="commit", message=..., root=...)`
3. Return commit SHA

**Output:** Partial dict with `vcs` (sub-state RMW: writes `commit_sha`), `status`, `result`.

**`.get("label", "step")` fallback:** Was: `s["label"]` raised `KeyError` if any step in the plan lacked a `"label"` key (LLM-returned plans are not guaranteed to label every step). Now uses `.get("label", "step")`.

**Reads branch via accessor:** Reads `_get_vcs(state, "branch", "") or _get_vcs(state, "branch_name", "") or "main"` instead of `state.get("branch", ...)`. The v2.0.5 split-brain band-aid (direct `state.get("branch")`) is no longer needed — `plan.py` writes the `branch` to the `vcs` sub-state via RMW, and the v3.0 accessor reads sub-state ONLY (no flat fallback). All 8 accessors are safe (Track M1 complete).

---

### `node_publish(state)` — Phase 15: BACKWARD-COMPAT WRAPPER

**Purpose:** Push the committed branch to the remote, open a PR, and optionally auto-merge it. Runs after `node_commit`, before `node_distill_memory`.

**[v2.0] BACKWARD-COMPAT WRAPPER:** This node is a thin wrapper that calls the 3 split nodes in sequence and merges their partial state updates into one dict matching the original return shape:
- `node_push({**state, **result})` →
- `node_create_pr({**state, **result})` →
- `node_merge_pr({**state, **result})`

**Output (merged):** Partial dict that merges the 3 split-node returns — primarily the `vcs` sub-state (`pushed`, `pr_number`, `pr_url` — all three populated in `vcs` when the node runs to completion; defaults are `False`/`0`/`""`).

**Note:** Registered via `add_node(...)` but NOT wired. Excluded from `WORKFLOW_METADATA["nodes"]`. `# TODO(2.0-post):` wrapper removal deferred.

---

### `node_push(state)` — Phase 15a: Push Branch to Remote

**Purpose:** Push the committed branch to the remote via `_github_push(branch, tid)`. First of the 3 Phase 3.3 split nodes (was inside `node_publish`).

**Logic:**
1. Skip conditions (same as `node_commit`): `status in {needs_clarification, failed, skipped}` → `{}`; `_get_verify(state, "passed", False)` falsy → `{}`; `dry_run` truthy → `{"status": "dry_run"}`
2. If `cfg.autocode_push_on_commit` is OFF, return `{"vcs": current_vcs}` with `pushed=False` (let downstream nodes decide)
3. If `_get_vcs(state, "branch", "")` is empty, return `{"vcs": current_vcs}` with `pushed=False` (nothing to push)
4. Call `_github_push(branch, tid)` — returns `bool`
5. RMW the `vcs` sub-state with `pushed=success`

**Returns:** `{"vcs": current_vcs (sub-state RMW with pushed)}` — or `{"status": "dry_run"}` when dry_run, or `{}` on skip conditions.

**Source:** `workflows/autocode_impl/nodes/push.py` (imports `_github_push` from `vcs_ops.py`).

---

### `node_create_pr(state)` — Phase 15b: Create Pull Request

**Purpose:** Open a PR from the autocode branch via `_github_pr_create(branch, title, body, tid)`. Second of the 3 Phase 3.3 split nodes. Hosts `_build_pr_body(state)`.

**Logic:**
1. Skip conditions: `status in {needs_clarification, failed, skipped}` → `{}`; `_get_verify(state, "passed", False)` falsy → `{}`; `dry_run` truthy → `{}`
2. If `cfg.autocode_open_pr` is OFF, RMW `vcs` with `pr_number=0, pr_url=""`
3. If `_get_vcs(state, "pushed", False)` is falsy (can't create a PR without pushing first), RMW `vcs` with `pr_number=0, pr_url=""` + a `tracer.step` note
4. If `_get_vcs(state, "branch", "")` is empty, RMW `vcs` with `pr_number=0, pr_url=""`
5. Build `pr_title = f"autocode: {state['task'][:60]}"` and `pr_body = _build_pr_body(state)`
6. Call `_github_pr_create(branch, pr_title, pr_body, tid)` — returns `dict | None`
7. RMW `vcs` with `pr_number=pr_data["number"], pr_url=pr_data["url"]` on success, or `pr_number=0, pr_url=""` on failure

**`_build_pr_body(state)` helper:** Reads `state["task"]`, `state["task_type"]`, `_get_vcs(state, "commit_sha", "")`, `_get_verify(state, "passed", False)`, `_get_debug(state, "root_cause", "")`, `_get_debug(state, "swarm_verdict", {})`. Outputs a markdown PR body with header + Type + Commit + Verified + optional Root cause + optional Swarm review (with ⚠️ Low confidence warning).

**Returns:** `{"vcs": current_vcs (sub-state RMW with pr_number + pr_url)}` — always returns the vcs sub-state with both keys (defaults `0`/`""` if PR not created). Or `{}` on skip conditions.

**Source:** `workflows/autocode_impl/nodes/create_pr.py` (imports `_github_pr_create` from `vcs_ops.py`; defines `_build_pr_body` locally).

---

### `node_merge_pr(state)` — Phase 15c: Auto-merge PR (Terminal)

**Purpose:** Auto-merge the PR via `_github_pr_merge(pr_number, tid)`. Third of the 3 Phase 3.3 split nodes. **DANGEROUS — default OFF.** Terminal — returns `{}` (no state update); no downstream node reads its output.

**Logic:**
1. Skip conditions: `status in {needs_clarification, failed, skipped}` → `{}`; `_get_verify(state, "passed", False)` falsy → `{}`; `dry_run` truthy → `{}`
2. If `cfg.autocode_auto_merge` is OFF, return `{}`
3. If `_get_vcs(state, "pr_number", 0)` is falsy (no PR to merge — PR not created), return `{}` with a `tracer.step` note
4. Call `_github_pr_merge(pr_number, tid)` (currently hardcoded to `merge_method="squash"` inside the helper)
5. Return `{}` (terminal)

**Source:** `workflows/autocode_impl/nodes/merge_pr.py` (imports `_github_pr_merge` from `vcs_ops.py`). Terminal — `{}` always.

**`# TODO(2.0-post):`** Add `AUTOCODE_AUTO_MERGE_METHOD` config (squash/merge/rebase) — currently hardcoded to `squash`.

---

### `node_distill_memory(state)` — Phase 16: Store Procedural Memory

**Purpose:** Store procedural knowledge for future recall.

**Logic:**
1. Build trace text from workflow state
2. Store procedural memory: `memory.store_procedural(text=..., ...)`

**Output:** Empty dict (side effects only).

**Note:** Non-fatal — code is already committed by the time distill runs. A ChromaDB failure there must not flip a successful workflow to failed. Uses `tracer.warning` (not `tracer.error`).

---

### `node_create_skill(state)` — Phase 17: Create Skill

**Purpose:** Create a reusable skill file.

**Logic:**
1. **[v3.4 HiTL check]** If `cfg.autocode_hitl_enabled` is True AND `state.get("hitl_approved", False)` is False, save a checkpoint + return `{"status": "awaiting_approval"}`. The graph's direct edge `node_create_skill → END` handles the pause.
2. Generate skill code via `_call(role="executor", system=CREATE_SKILL_SYSTEM, user=task, trace_id=tid)` (`trace_id=tid` attributes retry-exhaustion errors to this workflow's trace).
3. Validate filename via `_sanitize_skill_name()` (strips non-`[a-zA-Z0-9_]` chars — prevents path traversal via `/` or `\` in the skill name).
4. **Empty-file rejection + fallback keys:** Read `skill_file_content = data.get("skill_file", "")`. If empty, try fallback keys: `data.get("skill_code", "") or data.get("code", "")`. If still empty, return `{"status": "failed", "error": "LLM returned empty skill_file content"}`.
5. Validate syntax via `_validate_python_syntax()` (`ast.parse()` — catches `SyntaxError` before writing). On syntax failure, return `{"status": "failed", "error": "Skill code has invalid Python syntax: ..."}`.
6. Write atomically via `tempfile.NamedTemporaryFile` + `os.replace` (was: direct `write_text` — a crash mid-write would corrupt the skill file).
7. Set `skill_path`, `skill_created: True`, `status="done"`, `result=f"Skill created: {skill_path}\n{explanation}"` on success.
8. **Smoke-test (importlib):** Run `importlib.util.spec_from_file_location(f"_smoke_test_{skill_name}", skill_path)` + `spec.loader.exec_module(_smoke_module)`. Catches missing-dep / import-time errors that `ast.parse()` (step 5) misses. On import failure: **delete the broken file** + return `{"status": "failed", "error": "Skill file failed import smoke-test: ..."}`. No `sys.path.insert` leak — `spec_from_file_location` loads by absolute path.
9. **Git commit:** Call `_git_commit(message=f"skill(autocode): {skill_name}", tid=tid, project_root=state.get("project_root", ""))`. Non-fatal on failure (`tracer.warning`). Returns structured dict `{"committed": bool, "sha": str, "reason": str}`.

**Skip conditions:** `dry_run=True` → returns `{skill_path: "[DRY RUN] Would create: skills/{name}.py", skill_created: True, status: "done", result: "Dry run: ..."}` (no file write, no smoke-test, no git commit).

**Output:** Partial dict with `skill_path`, `skill_created`, `status`, `result`, `error` (failure path only).

**Source:** `workflows/autocode_impl/nodes/create_skill.py`.

**Test coverage:** `tests/workflows/autocode/test_create_skill.py` — name sanitization, syntax validation, `skill_created` flag, empty-file rejection (fallback keys), importlib smoke-test failure path, git commit invocation.

---

*Last updated: 2026-07-19 (v3.7). See [CHANGELOG.md](CHANGELOG.md) for version history.*
