<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 Node Reference

Per-node reference for all 28 nodes in the autocode workflow graph
(25 active + 3 backward-compat wrappers — see [ARCHITECTURE.md](ARCHITECTURE.md)
§ "Backward-compat wrappers" for wrapper details). Nodes are listed in
graph-execution order (Phase 1 → Phase 17). For the workflow facade, output format,
state fields, and accessor functions, see [API.md](API.md).

**[v2.0] Lazy Dev / YAGNI Ladder:** `CODER_SYSTEM` includes the 7-rung minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code). Enforced at the prompt level — every code-generating node benefits. See INSTRUCTIONS.md ALWAYS DO #54 + #55.

---

## ⚡ Nodes

### `node_classify_task(state)` — Phase 1: Classify Task Type

**Purpose:** Classify the task type using the Router LLM.

**Logic:**
1. Build prompt with goal, mode, and context
2. Call `llm.complete(role="router", ...)` for classification
3. Parse JSON response for task type. **[Hardening P1.6]** `json_schema` enforces the `task_type` enum (`feature`/`audit`/`edit`/`fix`/`refactor`/`create_skill`/`unclear`) at generation time.

**Output:** Partial dict with `task_type` ("fix" | "improve" | "feature" | "create_skill" | "unclear").

**Error handling:**
- LLM failure → returns `{"task_type": "unclear"}`
- Parse failure → returns `{"task_type": "unclear"}`

**Note:** Mode override takes precedence over LLM classification. If `mode == "fix_error"`, `task_type` is always `"fix"`.

---

### `node_validate_input(state)` — Phase 2: Validate Input

**Purpose:** Validate input parameters.

**Logic:**
1. Check `goal` is non-empty
2. Check `files` is a dict with valid paths
3. Check `target_file` is valid (if provided)

**Output:** Partial dict with `status` ("valid" | "error") and `error` (if invalid).

**Error handling:**
- Invalid goal → `"error"` status with message
- Invalid files → `"error"` status with message
- Invalid target_file → `"error"` status with message

**Note:** Path traversal check is incomplete. Doesn't catch absolute Windows paths (`C:\file.txt`) or Unicode traversal.

---

### `node_brainstorm(state)` — Phase 3: Brainstorm Approach

**Purpose:** Brainstorm the approach using the Planner LLM.

**Logic:**
1. Recall relevant memories
2. **[Pre-2.0 Fix]** Query the knowledge graph (KG) for relevant files and merge them into the files context BEFORE building the LLM prompt (was: merged into state AFTER the call — brainstorm never saw them).
3. **[Hardening P1.10]** Unconditionally initialize `files_update` before the KG block (was: brittle `if "files_update" not in dir()` check). Merge KG files via `files_update = {**kg_files, **files_update}` (preserves state-files-take-priority merge order).
4. Build prompt with goal, task type, context (now including KG files)
5. Call `llm.complete(role="planner", ...)` for brainstorming
6. Parse JSON response for approach

**Output:** Partial dict with `brainstorm` (approach text) and `files` (updated with KG files).

---

### `node_write_plan(state)` — Phase 4: Generate Plan

**Purpose:** Generate a step-by-step plan using the Planner LLM.

**Logic:**
1. Build prompt with goal, task type, and context
2. Call `llm.complete(role="planner", ...)` for planning
3. Parse JSON response for plan steps

**Output:** Partial dict with `plan` (list of step dicts) and `branch` (branch name).

**Note:** Fallback plan has 3 steps: write_tests → implement → verify. Used when LLM planning fails.

**[Pre-2.0 Fix] Branch name uniqueness:** Branch name appends a `trace_id` suffix (`autocode/{slug}-{tid_suffix}` where `tid_suffix = tid.replace("-", "")[:8]`). Without this, same task → same branch → cross-contamination.

---

### `node_git_branch(state)` — Phase 5: Create Git Branch

**Purpose:** Create a git branch for the changes.

**Logic:**
1. If `cfg.autocode_pull_before_branch` is ON, call `_github_pull(tid)` to pull recent commits from `origin` before creating the branch. Pull failure is non-blocking.
2. Create branch via `_git_create_branch()` (if `state["branch"]` is set).

**Output:** Empty dict (side effects only). On branch-creation failure: `{"status": "error", "error": "Failed to create git branch: <name>"}`.

**Optional pull before branch:**
- Gated on `AUTOCODE_PULL_BEFORE_BRANCH=1` (default OFF).
- Uses `_github_pull()` from `vcs_ops.py`.
- Graceful-skip if GitHub is not configured (`is_configured()` returns `False`).
- Non-blocking: pull failure does NOT stop the workflow — the branch is still created.

---

### `node_write_tests(state)` — Phase 6: Generate Tests (TDD)

**Purpose:** Generate tests for the feature/fix.

**Logic:**
1. Build prompt with goal, task type, and context
2. Call `llm.complete(role="test", ...)` for test generation
3. Extract code from markdown fences

**Output:** Partial dict with `test_code` (list of test strings) and `current_step`.

**Note:** `test_code` is `list[str]` but stored as-is in state. Later, `node_persist_artifacts` checks if it's a list and joins with `"\n\n"`.

---

### `node_execute_step(state)` — Phase 7: Execute Plan Step

**Purpose:** Execute a single step of the plan.

**Logic:**
1. Get current step from plan
2. Build prompt with step description and context
3. Call `llm.complete(role="executor", ...)` for code generation
4. Extract code from JSON or markdown fences
5. **[Pre-2.0 Fix]** Use `_parse_json()` to derive `modified_files` (was: raw `json.loads(code)` → markdown-fenced JSON raised `JSONDecodeError` and `modified_files` was always `[]`).
6. **[Hardening P2]** Removed dead `json.loads(code)` fallback — `_parse_json` already tries direct `json.loads` first, so when it returns `{}` the fallback would also raise. Now traces a warning + sets `modified_files=[]` on empty dict.

**Output:** Partial dict with `code` (generated code), `modified_files`, `current_step`.

---

### `node_write_files(state)` — Phase 8: BACKWARD-COMPAT WRAPPER

**Purpose:** File writing — apply patches, write new files, persist run-dir artifacts.

**[v2.0] BACKWARD-COMPAT WRAPPER:** This node is a thin wrapper that calls the 3 split nodes in sequence and merges their partial state updates into one dict matching the original return shape:
- `node_apply_patches({**state, **result})` →
- `node_write_new_files({**state, **result})` →
- `node_persist_artifacts({**state, **result})`

**Output (merged):** Partial dict with `written_files`, `files_map`, `test_files`, `autocode_run_path`, `modified_files`, `patch_errors` (if any).

**Note:** Registered via `add_node(...)` so external callers + tests that `import node_write_files` still work, but NOT wired (no edges in or out). Excluded from `WORKFLOW_METADATA["nodes"]`. `# TODO(2.0-post):` wrapper removal deferred.

---

### `node_apply_patches(state)` — Phase 8a: Apply str_replace Patches

**Purpose:** Apply `str_replace` patches to existing files only. First of the 3 Phase 3.1 split nodes (was inside `node_write_files`).

**Logic:**
1. Read `state["tdd_source_code"]` JSON. **[Hardening P1.4]** Use `_parse_json()` (handles markdown fences ```` ```json ... ``` ````); was raw `json.loads()` which failed on fenced output. Empty-dict check raises `ValueError` inside try block so the existing except handler produces `"apply_patches JSON parse failed: ..."`.
2. Extract `patches[]` array
3. For each patch: validate path via `_is_path_safe()`, skip if protected, skip if file missing, else call `apply_patch(target, old_text, new_text)`
4. Build `modified_files` list (paths successfully patched) + `patch_errors` list (path-traversal blocks + missing-file + apply failures)

**Params:** None beyond `state`. Reads: `state["tdd_source_code"]`, `state["status"]`, `state["dry_run"]`, `state["project_root"]`.

**Returns:** `{"modified_files": list[str], "patch_errors"?: list[str]}` — or `{"status": "error", "error": str}` on JSON parse failure, or `{"status": "dry_run", "modified_files": []}` when `dry_run=True`.

**Source:** `workflows/autocode_impl/nodes/apply_patches.py` (also hosts `_is_path_safe()` shared with `write_new_files.py`).

---

### `node_write_new_files(state)` — Phase 8b: Write New Files + Build files_map

**Purpose:** Write new files / overwrite existing ones atomically. Also builds `files_map` for `analyze_impact`. Second of the 3 Phase 3.1 split nodes.

**Logic:**
1. Read `state["tdd_source_code"]` JSON via `_parse_json()` (**[Hardening P1.4]** handles markdown fences). Extract `new_files{}` dict (backwards-compat: if no `patches`/`new_files` keys, treat whole dict as files).
2. For each file: validate path via `_is_path_safe()` (imported from `apply_patches.py`), skip if protected, else write atomically (`tempfile.NamedTemporaryFile` + `os.replace` + `FileLock` with 1 retry on timeout).
3. Call `_cleanup_old_autocode_runs()` for on-demand run-dir pruning
4. Build `files_map` — snapshots of all modified files (patches from `apply_patches` + new files written here) with `{content_preview, preview_md5, full_md5, size, truncated}` for `analyze_impact`
5. **[Hardening P1.8]** Merge new files into `modified_files` (set union with `state.get("modified_files", [])`) so downstream nodes (`analyze_impact`, etc.) see them. Without this, new files were never reflected in `modified_files`.

**Params:** None beyond `state`. Reads: `state["tdd_source_code"]`, `state["status"]`, `state["dry_run"]`, `state["project_root"]`, `state["modified_files"]`.

**Returns:** `{"files_map": dict[str, dict], "modified_files": list[str]}` — or `{}` when `status` is `needs_clarification`/`failed`/`error`, `tdd_source_code` is empty, or `dry_run=True`.

**Source:** `workflows/autocode_impl/nodes/write_new_files.py` (imports `_is_path_safe` from `apply_patches.py`).

---

### `node_persist_artifacts(state)` — Phase 8c: Persist Test File + Generated Code + Debug Log

**Purpose:** Persist the test file + generated code + debug log to the per-run autocode folder. Third of the 3 Phase 3.1 split nodes. Sets `test_files` + `autocode_run_path` for downstream verify nodes.

**Logic:**
1. Resolve `run_dir` via `_get_autocode_run_path(tid)` (or read from `state["autocode_run_path"]` if set)
2. Write `test_autocode_feature.py` from `state["test_code"]` (joined with `"\n\n"` if list) using `FileLock` (10s timeout)
3. Write `generated_code.json` from `state["tdd_source_code"]` (if present)
4. Write `debug_log.json` from `state["debug_notes"]` / `root_cause` / `defense_notes` / `tdd_iteration` (if any are present)
5. Return `test_files` (relative path from `workspace_root`) + `autocode_run_path` (absolute path)

**Params:** None beyond `state`. Reads: `state["test_code"]`, `state["tdd_source_code"]`, `state["debug_notes"]`, `state["root_cause"]`, `state["defense_notes"]`, `state["tdd_iteration"]`, `state["status"]`, `state["dry_run"]`, `state["trace_id"]`, `state["project_root"]`.

**Returns:** `{"test_files": list[str], "autocode_run_path": str}` — or `{}` when `status` is `needs_clarification`/`failed`/`error`, `dry_run=True`, or `test_code` is empty.

**Source:** `workflows/autocode_impl/nodes/persist_artifacts.py`.

---

### `node_analyze_impact(state)` — Phase 9: Analyze Blast Radius

**Purpose:** Analyze the impact of changes on the codebase.

**Logic:**
1. Get modified files from state
2. Query dependency graph for affected files
3. Generate impact warnings

**Output:** Partial dict with `impact_warnings` (list of dicts with `type`, `message`, `agent_fault`).

**Note:** `node_analyze_impact` uses `_run_async()` to wrap async calls (`parse_dependencies_from_string`, `get_targeted_tests`). **[v2.0]** `_run_async()` simplified to `asyncio.run(coro)` (was create/destroy event loop per call).

---

### `node_run_tests(state)` — Phase 10: Run Tests

**Purpose:** Run the generated tests.

**Logic:**
1. Get test files from state
2. Run tests via `pytest`
3. Return results
4. **[Hardening P0.2]** If `test_results.success`, mark the last entry in `debug_history` (read via `_get_tdd`) with `tests_passed=True`, then read-modify-write the `tdd` sub-state to preserve other fields. Without this, every `debug_history` entry stayed `tests_passed=False` forever, causing the architecture-question exit to fire prematurely after 3 iterations.

**Output:** Partial dict with `test_results`, `test_passed`, `test_output`, and (when tests passed) `"tdd": {"debug_history": updated_history}`.

---

### `node_systematic_debug(state)` — Phase 11: Debug Failures

**Purpose:** Debug test failures. Uses a 4-phase prompt (investigation → pattern → hypothesis → fix), accumulates `debug_history` across iterations, and bails on architecture-question detection (3+ consecutive `tests_passed=False`).

**Logic:**
1. Read `debug_history` from `TDDState` sub-state via `_get_tdd(state, "debug_history", [])`.
2. **Architecture-question exit:** If `len(debug_history) >= _ARCHITECTURE_QUESTION_THRESHOLD` (3) AND all last 3 entries have `tests_passed=False`, bail with `tdd_status="max_retries_exceeded"` + procedural memory store (`tags="tdd_failure,architecture_question,autocode"`). **[Hardening P0.1]** Uses read-modify-write to preserve sibling TDD fields (was clobbering the entire `tdd` sub-state).
3. Check `current_iteration > max_retries` — bail with `tdd_status="max_retries_exceeded"` + procedural memory store (`tags="tdd_failure,retry_exhaustion,autocode"`).
4. Build prompt with test output and context (includes blast-radius warning from `kgraph` if `modified_files` is set).
5. Use `DEBUG_SYSTEM` from `constants.py` — the 4-phase structured prompt (investigation → pattern → hypothesis → fix) inspired by obra/superpowers `systematic-debugging`. JSON output includes required `phase` field (enum enforced by `_DEBUG_JSON_SCHEMA`). **[Hardening P1.9]** `blast_radius_note` is inserted BEFORE "Output JSON ONLY:" (was after — LLM sometimes treated the warning as output).
6. **[Hardening P2]** If `debug_summary` is non-empty AND `len(debug_history) > 5`, replace the raw last-5-entries history block with a "DEBUG SUMMARY (compressed)" block containing the summary string (keeps LLM context bounded in long-running debug loops). Otherwise, inject last 5 `debug_history` entries into the user prompt under a `--- PRIOR DEBUG ATTEMPTS (do NOT repeat these) ---` block.
7. If `cfg.autocode_swarm_debug` is ON, call `_swarm_debug_consensus(system, user, tid)`:
   - **Run 1:** `swarm(action="consensus")` — all configured cloud providers propose a `{root_cause, defense_notes, fix}` object.
   - **Run 2:** `swarm(action="vote")` — providers vote YES/NO on whether the consensus root-cause + fix is correct.
   - Confidence: `unanimous → HIGH`, `majority → MEDIUM`, `split`/`disagreement`/unknown → `LOW`.
   - If swarm returns `None` (no providers configured, import failure, consensus exception), falls through to single-LLM debug.
8. Otherwise (flag OFF or swarm unavailable), call `llm.complete(role="executor", ..., json_schema=_DEBUG_JSON_SCHEMA)` for debug analysis.
9. Parse JSON response for `phase`, `root_cause`, `defense_notes`, and `fix`. Validate `phase` against the allowed enum; default to `"investigation"` on unknown value.
10. If swarm returned LOW confidence AND `cfg.autocode_debug_comment_pr` is ON AND a PR exists (`state["pr_number"]` is set), post a warning comment on the PR via `_github_pr_comment()`.
11. Append a new entry to `debug_history`: `{iteration: current_iteration, phase: phase, root_cause: root_cause, fix: (suggested_fix or "")[:200], tests_passed: False}` (tests_passed is updated to True by `node_run_tests` on the next loop iteration if the fix worked). Swarm-path entries include extra `confidence` field. **[Hardening P0.1]** Read-modify-write preserves sibling TDD fields.

**Output:** Partial dict with `root_cause`, `defense_notes`, `tdd_source_code`, `debug_notes`, `"tdd": {"debug_history": updated_history}`. When swarm was used, also includes `"swarm_verdict": {...}`. Both early-exit paths preserve `debug_history`.

**[Pre-2.0 Fix] Field name alignment:** `DEBUG_SYSTEM` prompt now uses `root_cause` / `defense_notes` (matching the `_DEBUG_JSON_SCHEMA` and `AutocodeState` TypedDict). Was: `hypothesis` / `defense_note` — swarm debug root_cause was always "Unknown".

**Swarm is non-blocking:** the fix is always applied regardless of confidence. LOW confidence surfaces as a PR comment (if enabled), not as a workflow block.

**Fallback chain:** `AUTOCODE_SWARM_DEBUG=1` + swarm available → use swarm. `AUTOCODE_SWARM_DEBUG=1` + swarm unavailable → single-LLM debug. `AUTOCODE_SWARM_DEBUG=0` → single-LLM debug (default).

**`# TODO(2.0-post):`** items: cross-run procedural memory recall before debug (F5); subagent dispatch for parallel debug (F1); adaptive `_ARCHITECTURE_QUESTION_THRESHOLD` per task type (F4).

---

### `node_summarize_context(state)` — Phase 11a: Compress debug_history

**Purpose:** Compress `debug_history` before re-entering the debug loop. Closes #37 (context summarization). Wired between `node_systematic_debug` and `node_apply_patches` in the debug loop so the next iteration sees a bounded context.

**Logic:**
1. Read `debug_history` from `TDDState` sub-state via `_get_tdd(state, "debug_history", [])`.
2. If `debug_history` is empty, return `{"tdd": {"debug_summary": ""}}` (no work to do — typically the first debug iteration). **[Hardening P0.1]** Read-modify-write preserves sibling TDD fields.
3. Otherwise, call `_summarize_debug_history(history)` helper:
   a. Reverse the history (most recent first).
   b. Render each entry as a single sentence: `iter=N phase=P tests_passed=B [confidence=C] root_cause=R fix_preview=F`.
   c. Join sentences with `. ` and append a trailing `.`.
   d. Try `from chonkie import SentenceChunker` (lazy import, soft dependency). If import succeeds, instantiate `SentenceChunker(chunk_size=512, chunk_overlap=0)` and call `.chunk(text)`. Return the FIRST chunk's content.
   e. On ANY `Exception` (including `ModuleNotFoundError` when chonkie isn't installed, or chunking failure), fall back to `json.dumps(reversed_history[:3], ensure_ascii=False, default=str)`.
4. Trace-log entry count + compressed length.
5. **[Hardening P0.1]** Read-modify-write: `current_tdd = dict(state.get("tdd", {}))` then `current_tdd["debug_summary"] = summary` — preserves `debug_history`, `iteration`, `status`, etc. Return `{"tdd": current_tdd}`.

**Params:** None beyond `state`. Reads (via `_get_tdd` accessor): `state["tdd"]["debug_history"]` (or legacy `state["debug_history"]` fallback) — `list[dict]` where each dict has shape `{iteration, phase, root_cause, fix, tests_passed, confidence?}`.

**Returns:** `{"tdd": {"debug_summary": str}}` (or full `tdd` sub-state with `debug_summary` merged in after Hardening P0.1). Empty string when history is empty.

**Source:** `workflows/autocode_impl/nodes/summarize_context.py` (~110 lines).

**Note:** This node does NOT mutate `debug_history` — the full history is preserved for the architecture-question exit check in `node_systematic_debug`.

**Note:** chonkie is a SOFT dependency — lazy import inside a `try` block. If chonkie is not installed, falls back to JSON-of-last-3-entries. Do NOT make chonkie a hard dependency.

---

### `node_verify(state)` — Phase 12: BACKWARD-COMPAT WRAPPER

**Purpose:** Verify the changes with linting, regression tests, and LLM spec review.

**[v2.0] BACKWARD-COMPAT WRAPPER:** This node is a thin wrapper that calls the 4 split nodes in sequence and merges their partial state updates into one dict matching the original return shape:
- `node_run_pytest({**state, **result})` →
- `node_run_lint({**state, **result})` →
- `node_llm_review({**state, **result})` →
- `node_verify_decision({**state, **result})`

**Output (merged):** Partial dict with `lint_passed`, `lint_output`, `regression_passed`, `evidence_outputs`, `verification_passed`, `verification_notes`, `test_results`, `tests_passed`, `llm_review_data`.

**Note:** Registered via `add_node(...)` but NOT wired. Excluded from `WORKFLOW_METADATA["nodes"]`. `# TODO(2.0-post):` wrapper removal deferred.

---

### `node_run_pytest(state)` — Phase 12a: Fresh Pytest Subprocess

**Purpose:** Run a fresh pytest subprocess on the autocode run directory. First of the 4 Phase 3.2 split nodes (was inside `node_verify`).

**Logic:**
1. Resolve `run_dir` from `state["autocode_run_path"]` or `_get_autocode_run_path(tid)`
2. **[Pre-2.0 Fix]** If no test files exist (`tests_dir` and `test_file` both missing), skip pytest entirely — return `{"test_results": {...stderr: "No test files found..."}, "tests_passed": False}`. Was: ran `pytest` with no args → entire project test suite.
3. Run `[python, "-m", "pytest", "--tb=short", "--color=no", "-q", ...targets]` with `cwd=base_path` and 120s timeout
4. Build `test_results` dict `{success, stdout, stderr, returncode}` + `tests_passed` bool + ephemeral `_pytest_output` (first 2000 chars — stashed for `llm_review`)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["trace_id"]`, `state["autocode_run_path"]`, `state["project_root"]`.

**Returns:** `{"test_results": dict, "tests_passed": bool, "_pytest_output": str}` — handles `FileNotFoundError` (pytest missing) + `subprocess.TimeoutExpired` (120s) with structured error returns.

**Source:** `workflows/autocode_impl/nodes/run_pytest.py`.

---

### `node_run_lint(state)` — Phase 12b: Ruff Lint on modified_files Only

**Purpose:** Run `ruff check` scoped to `modified_files` only (advisory — does not block commit). Second of the 4 Phase 3.2 split nodes.

**Logic:**
1. Read `modified_files` from state (set by `node_apply_patches` + `node_write_new_files`); if empty, return `{"lint_output": "No modified files to lint", "lint_passed": None}`
2. Resolve `lint_targets` as absolute paths via `base_path / f` for each `f` in `modified_files`
3. Run `[python, "-m", "ruff", "check", ...targets, "--select", "E,F", "--no-cache"]` with 30s timeout
4. Build `lint_output` (first 500 chars of stdout+stderr) + `lint_passed` (bool — `returncode == 0`)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["trace_id"]`, `state["modified_files"]`, `state["project_root"]`.

**Returns:** `{"lint_output": str, "lint_passed": bool | None}` — `lint_passed` is `None` when ruff is unavailable (was `True` before Pre-2.0 Fix) or when no modified files.

**Source:** `workflows/autocode_impl/nodes/run_lint.py`.

---

### `node_llm_review(state)` — Phase 12c: LLM Spec Coverage + Cleanliness Review

**Purpose:** LLM-based spec review of the implementation. Third of the 4 Phase 3.2 split nodes. Calls `_call(role="executor", system=VERIFY_SYSTEM, ...)` with implementation context, fresh pytest output, and ruff output.

**Logic:**
1. Build `impl_ctx` from `state["tdd_source_code"]` JSON — extract `patches[].new` (first 1500 chars each) + `new_files{}` values (first 1500 chars each). Fallback: raw `tdd_source_code[:3000]` on parse failure.
2. Read `tests_passed`, `_pytest_output` (from `node_run_pytest`), `lint_output` (from `node_run_lint`) from state
3. Call `_call(role="executor", system=VERIFY_SYSTEM, user=<spec + impl + tests + pytest output + ruff output>, timeout=EXECUTOR_TIMEOUT)`
4. Parse response via `_parse_json(raw)` → `data` dict `{automated_checks_passed, checks: {syntax, tests, spec, regressions, cleanliness}, summary}`
5. On `_call` exception: `tracer.error(tid, "llm_review", ...)` + return `{"llm_review_data": {"automated_checks_passed": False, "checks": {}, "summary": "LLM verification error"}}`

**Params:** None beyond `state`. Reads: `state["status"]`, `state["trace_id"]`, `state["tdd_source_code"]`, `state["tests_passed"]`, `state["_pytest_output"]`, `state["test_results"]`, `state["lint_output"]`, `state["project_root"]`.

**Returns:** `{"llm_review_data": dict}` — always returns a dict (even on error). Or `{}` when `status` is `needs_clarification`/`failed`.

**Source:** `workflows/autocode_impl/nodes/llm_review.py` (imports `_call` + `_parse_json` from `helpers.py`; `VERIFY_SYSTEM` from `constants.py`; `EXECUTOR_TIMEOUT` from `state.py`).

**Note:** This is the only node in the verify chain that calls the LLM. `node_verify_decision` (next) consumes `llm_review_data` and applies the hallucination guard.

---

### `node_verify_decision(state)` — Phase 12d: Compose Results + Hallucination Guard

**Purpose:** Compose the results from the 3 previous nodes (run_pytest + run_lint + llm_review) and make the final verification decision. Fourth of the 4 Phase 3.2 split nodes. Also handles the `tdd_status in ("max_retries_exceeded", "stuck")` early-exit path.

**Logic:**
1. **Early exit:** If `tdd_status in ("max_retries_exceeded", "stuck")`, log `tracer.error(tid, "verify_decision", ...)`, store a procedural memory (`memory.store(...)` — non-fatal, wrapped in try/except), return `{"status": "failed", ...}`.
2. Read results from state: `tests_passed`, `lint_passed`, `_pytest_output`, `lint_output`, `llm_review_data`
3. Compute `automated_ok = tests_passed` (lint is advisory only)
4. **Hallucination guard:** If `not tests_passed` AND `llm_review_data["automated_checks_passed"]` is True, log `tracer.step` "HALLUCINATION DETECTED" — real exit code overrides LLM claim
5. Compute `llm_checks_ok` = all of `syntax`, `tests`, `spec`, `regressions`, `cleanliness` checks pass
6. Final decision: `all_passed = automated_ok AND llm_checks_ok`
7. Build `verification_notes` (Automated/LLM PASS/FAIL + summary + JSON-encoded checks) + `evidence_outputs` `{tests, lint, regression}` (each truncated to 2000/500/2000 chars)

**Params:** None beyond `state`. Reads: `state["trace_id"]`, `state["tdd_status"]`, `state["max_retries"]`, `state["task"]`, `state["tdd_error"]`, `state["status"]`, `state["tests_passed"]`, `state["lint_passed"]`, `state["_pytest_output"]`, `state["lint_output"]`, `state["llm_review_data"]`.

**Returns:** `{"verification_passed": bool, "verification_notes": str, "evidence_outputs": dict, "trace_id": str}` — or `{"status": "failed", ...}` on max_retries/stuck early-exit, or `{}` on `needs_clarification`/`failed`/`dry_run`.

**Source:** `workflows/autocode_impl/nodes/verify_decision.py`.

**Note:** `route_after_verify` routes from this node (was: from `node_verify` before Phase 3.2 split).

---

### `node_report(state)` — Phase 13: Generate Report

**Purpose:** Generate a structured report with the final result.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with result and metadata
2. Return the report

**Output:** Empty dict (side effects only).

---

### `node_git_commit(state)` — Phase 14: Commit Changes

**Purpose:** Commit the changes to git.

**Logic:**
1. Generate commit message
2. Call `git(action="commit", message=..., root=...)`
3. Return commit SHA

**Output:** Partial dict with `commit_sha`, `status`, `result`.

**[Pre-2.0 Fix] `.get("label", "step")` fallback:** Was: `s["label"]` raised `KeyError` if any step in the plan lacked a `"label"` key (LLM-returned plans are not guaranteed to label every step). Now uses `.get("label", "step")`.

**[v2.0] First node migrated to the accessor pattern:** Reads `state["branch"]` via `_get_vcs(state, "branch", "main")` instead of `state.get("branch", "main")`. Proof-of-concept for the 8-accessor migration.

---

### `node_publish(state)` — Phase 15: BACKWARD-COMPAT WRAPPER

**Purpose:** Push the committed branch to the remote, open a PR, and optionally auto-merge it. Runs after `node_commit`, before `node_distill_memory`.

**[v2.0] BACKWARD-COMPAT WRAPPER:** This node is a thin wrapper that calls the 3 split nodes in sequence and merges their partial state updates into one dict matching the original return shape:
- `node_push({**state, **result})` →
- `node_create_pr({**state, **result})` →
- `node_merge_pr({**state, **result})`

**Output (merged):** Partial dict with `pushed: bool`, `pr_number: int`, `pr_url: str` (all three are always present when the node runs to completion; defaults are `False`/`0`/`""`).

**Note:** Registered via `add_node(...)` but NOT wired. Excluded from `WORKFLOW_METADATA["nodes"]`. `# TODO(2.0-post):` wrapper removal deferred.

---

### `node_push(state)` — Phase 15a: Push Branch to Remote

**Purpose:** Push the committed branch to the remote via `_github_push(branch, tid)`. First of the 3 Phase 3.3 split nodes (was inside `node_publish`).

**Logic:**
1. Skip conditions (same as `node_commit`): `status in {needs_clarification, failed, skipped}` → `{}`; `verification_passed` falsy → `{}`; `dry_run` truthy → `{"status": "dry_run"}`
2. If `cfg.autocode_push_on_commit` is OFF, return `{"pushed": False}` (let downstream nodes decide)
3. If `state["branch"]` is empty, return `{"pushed": False}` (nothing to push)
4. Call `_github_push(branch, tid)` — returns `bool`
5. Return `{"pushed": success}`

**Params:** None beyond `state`. Reads: `state["status"]`, `state["verification_passed"]`, `state["dry_run"]`, `state["trace_id"]`, `state["branch"]`.

**Returns:** `{"pushed": bool}` — or `{"status": "dry_run"}` when dry_run, or `{}` on skip conditions.

**Source:** `workflows/autocode_impl/nodes/push.py` (imports `_github_push` from `vcs_ops.py`).

---

### `node_create_pr(state)` — Phase 15b: Create Pull Request

**Purpose:** Open a PR from the autocode branch via `_github_pr_create(branch, title, body, tid)`. Second of the 3 Phase 3.3 split nodes. Hosts `_build_pr_body(state)`.

**Logic:**
1. Skip conditions: `status in {needs_clarification, failed, skipped}` → `{}`; `verification_passed` falsy → `{}`; `dry_run` truthy → `{}`
2. If `cfg.autocode_open_pr` is OFF, return `{"pr_number": 0, "pr_url": ""}`
3. If `state["pushed"]` is falsy (can't create a PR without pushing first), return `{"pr_number": 0, "pr_url": ""}` with a `tracer.step` note
4. If `state["branch"]` is empty, return `{"pr_number": 0, "pr_url": ""}`
5. Build `pr_title = f"autocode: {state['task'][:60]}"` and `pr_body = _build_pr_body(state)`
6. Call `_github_pr_create(branch, pr_title, pr_body, tid)` — returns `dict | None`
7. Return `{"pr_number": pr_data["number"], "pr_url": pr_data["url"]}` on success, `{"pr_number": 0, "pr_url": ""}` on failure

**`_build_pr_body(state)` helper:** Reads `task`, `task_type`, `commit_sha`, `verification_passed`, `root_cause`, `swarm_verdict`. Outputs a markdown PR body with header + Type + Commit + Verified + optional Root cause + optional Swarm review (with ⚠️ Low confidence warning).

**Params:** None beyond `state`. Reads: `state["status"]`, `state["verification_passed"]`, `state["dry_run"]`, `state["trace_id"]`, `state["pushed"]`, `state["branch"]`, `state["task"]`, `state["task_type"]`, `state["commit_sha"]`, `state["root_cause"]`, `state["swarm_verdict"]`.

**Returns:** `{"pr_number": int, "pr_url": str}` — always returns both keys (defaults `0`/`""` if PR not created). Or `{}` on skip conditions.

**Source:** `workflows/autocode_impl/nodes/create_pr.py` (imports `_github_pr_create` from `vcs_ops.py`; defines `_build_pr_body` locally).

---

### `node_merge_pr(state)` — Phase 15c: Auto-merge PR (Terminal)

**Purpose:** Auto-merge the PR via `_github_pr_merge(pr_number, tid)`. Third of the 3 Phase 3.3 split nodes. **DANGEROUS — default OFF.** Terminal — returns `{}` (no state update); no downstream node reads its output.

**Logic:**
1. Skip conditions: `status in {needs_clarification, failed, skipped}` → `{}`; `verification_passed` falsy → `{}`; `dry_run` truthy → `{}`
2. If `cfg.autocode_auto_merge` is OFF, return `{}`
3. If `state["pr_number"]` is falsy (no PR to merge — PR not created), return `{}` with a `tracer.step` note
4. Call `_github_pr_merge(pr_number, tid)` (currently hardcoded to `merge_method="squash"` inside the helper)
5. Return `{}` (terminal)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["verification_passed"]`, `state["dry_run"]`, `state["trace_id"]`, `state["pr_number"]`.

**Returns:** `{}` always (terminal — no state update).

**Source:** `workflows/autocode_impl/nodes/merge_pr.py` (imports `_github_pr_merge` from `vcs_ops.py`).

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
1. Generate skill code
2. **[Pre-2.0 Fix]** Validate filename via `_sanitize_skill_name()` (strips non-`[a-zA-Z0-9_]` chars — prevents path traversal via `/` or `\` in the skill name).
3. **[Pre-2.0 Fix]** Validate syntax via `_validate_python_syntax()` (`ast.parse()` — catches `SyntaxError` before writing).
4. **[Pre-2.0 Fix]** Write atomically via `tempfile.NamedTemporaryFile` + `os.replace` (was: direct `write_text` — a crash mid-write would corrupt the skill file).
5. Set `skill_created: True` on success (was: never set — `autocode.py` checked it but it was always missing).

**Output:** Partial dict with `skill_path`, `status`, `result`, `error`.

**Source:** `workflows/autocode_impl/nodes/create_skill.py`.

---

*Last updated: 2026-07-11 (v2.0.1 — hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
