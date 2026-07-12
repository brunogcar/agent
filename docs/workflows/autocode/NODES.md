<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 Node Reference

Per-node reference for all 28 nodes in the autocode workflow graph
(25 active + 3 backward-compat wrappers — see [ARCHITECTURE.md](ARCHITECTURE.md)
§ "Backward-compat wrappers (Phase 3)" for wrapper details). Nodes are listed in
graph-execution order (Phase 1 → Phase 17). For the workflow facade, output format,
state fields, and accessor functions, see [API.md](API.md).

**[v2.0 GA] Phase 7.1 — Lazy Dev / YAGNI Ladder:** `CODER_SYSTEM` now includes the
7-rung minimization ladder inspired by [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail).
The ladder is enforced at the prompt level — every code-generating node benefits.
See INSTRUCTIONS.md ALWAYS DO #54 + #55 for the rules.

---

## ⚡ Nodes

### `node_classify_task(state)` — Phase 1: Classify Task Type

**Purpose:** Classify the task type using the Router LLM.

**Logic:**
1. Build prompt with goal, mode, and context
2. Call `llm.complete(role="router", ...)` for classification
3. Parse JSON response for task type

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
2. **[Pre-2.0 Fix]** Query the knowledge graph (KG) for relevant files and merge them into the files context BEFORE building the LLM prompt (was: merged into state AFTER the call — brainstorm never saw KG files)
3. Build prompt with goal, task type, context (now including KG files)
4. Call `llm.complete(role="planner", ...)` for brainstorming
5. Parse JSON response for approach

**Output:** Partial dict with `brainstorm` (approach text) and `files` (updated with KG files).

**[Pre-2.0 Fix] KG files now in LLM prompt:** The previous bug merged `kg_files` into `files_update` but built the LLM `files_ctx` from `state.get("files", {})` (original) — KG files were fetched but never shown to the planner. Fixed by building `merged_files = {**kg_files, **state.get("files", {})}` and passing that to `_files_context()`. Found by: MiMo. See CHANGELOG.md § "Cross-LLM Review Findings (Pre-2.0)".

---

### `node_write_plan(state)` — Phase 4: Generate Plan

**Purpose:** Generate a step-by-step plan using the Planner LLM.

**Logic:**
1. Build prompt with goal, task type, and context
2. Call `llm.complete(role="planner", ...)` for planning
3. Parse JSON response for plan steps

**Output:** Partial dict with `plan` (list of step dicts) and `branch` (branch name).

**Note:** Fallback plan has 3 steps: write_tests → implement → verify. This is used when LLM planning fails.

**[P1 #12] `slug` fallback:** `slug` generation may produce empty string if `task[:40]` is all non-alphanumeric. Fallback to `"autocode"` prevents invalid branch name `"autocode/"`.

**[Pre-2.0 Fix] Branch name uniqueness:** Branch name now appends a `trace_id` suffix (`autocode/{slug}-{tid_suffix}` where `tid_suffix = tid.replace("-", "")[:8]`). Was: same task → same branch → second run checked out first run's branch → cross-contamination. Found by: MiMo, Kimi. `# TODO(2.0):` Consider making this configurable (some users may want reusable branches).

---

### `node_git_branch(state)` — Phase 5: Create Git Branch

**Purpose:** Create a git branch for the changes.

**Logic:**
1. **[v1.3]** If `cfg.autocode_pull_before_branch` is ON, call `_github_pull(tid)` to pull recent commits from `origin` before creating the branch. Pull failure is non-blocking — the workflow continues regardless (a `tracer.step` is logged).
2. Take git snapshot (legacy — see `git_ops.py` note below; the snapshot action was removed in v1.0.1).
3. Create branch via `_git_create_branch()` (if `state["branch"]` is set).

**Output:** Empty dict (side effects only). On branch-creation failure: `{"status": "error", "error": "Failed to create git branch: <name>"}`.

**[v1.3] Optional pull before branch:**
- Gated on `AUTOCODE_PULL_BEFORE_BRANCH=1` (default OFF).
- Uses `github(action="pull", remote="origin")` via `github_ops._github_pull()` (**[v2.0-rc2]** `_github_pull` now lives in `vcs_ops.py` — `github_ops.py` is a thin re-export wrapper; new code should import from `workflows.autocode_impl.vcs_ops`).
- Graceful-skip if GitHub is not configured (`is_configured()` returns `False`).
- Non-blocking: pull failure does NOT stop the workflow — the branch is still created.
- `# TODO(2.0):` Consider making pull-failure behavior configurable (fail-fast vs graceful-skip).

**Note:** `_git_snapshot` calls `git(action="snapshot")` which doesn't exist in the current git tool. This will fail.

**Note:** No check of return values. If snapshot or branch creation fails, the workflow continues silently.

---

### `node_write_tests(state)` — Phase 6: Generate Tests (TDD)

**Purpose:** Generate tests for the feature/fix.

**Logic:**
1. Build prompt with goal, task type, and context
2. Call `llm.complete(role="test", ...)` for test generation
3. Extract code from markdown fences

**Output:** Partial dict with `test_code` (list of test strings) and `current_step`.

**Note:** `test_code` is `list[str]` but stored as-is in state. Later, `node_write_files` checks if it's a list and joins with `"\n\n"`.

---

### `node_execute_step(state)` — Phase 7: Execute Plan Step

**Purpose:** Execute a single step of the plan.

**Logic:**
1. Get current step from plan
2. Build prompt with step description and context
3. Call `llm.complete(role="executor", ...)` for code generation
4. Extract code from JSON or markdown fences

**Output:** Partial dict with `code` (generated code), `modified_files`, `current_step`.

**[Pre-2.0 Fix] Uses `_parse_json`:** Was: raw `json.loads(code)` to derive `modified_files` — markdown-fenced JSON (```` ```json\n{...}\n``` ````) raised `JSONDecodeError` and `modified_files` was silently `[]`. Now uses `_parse_json(code)` which strips code fences before parsing. Found by: MiMo. See CHANGELOG.md.

**Note:** `files_context` field is still referenced defensively in some places, but the canonical path is `_files_context(state.get('files', {}))`. Do NOT add a `files_context` field to `AutocodeState`.

---

### `node_write_files(state)` — [v2.0-beta] Phase 8: BACKWARD-COMPAT WRAPPER

**Purpose:** File writing — apply patches, write new files, persist run-dir artifacts. Runs after `node_execute_step`, before `node_analyze_impact` (or directly before the verify chain for task types that skip impact analysis).

**[v2.0-beta] BACKWARD-COMPAT WRAPPER (Phase 3.1 split):** This node is now a thin wrapper that calls the 3 split nodes in sequence and merges their partial state updates into one dict matching the original return shape. The graph wires the 3 split nodes directly (`execute → apply_patches → write_new_files → persist_artifacts → [route]`); this wrapper is registered via `add_node(...)` so external callers + tests that `import node_write_files` still work, but it has NO edges in or out. Excluded from `WORKFLOW_METADATA["nodes"]` (27-entry list — wrappers excluded). See the 3 split-node sections below for the actual logic.

**Wrapper logic:** Runs `node_apply_patches({**state, **result})` → `node_write_new_files({**state, **result})` → `node_persist_artifacts({**state, **result})` in sequence, accumulating partial updates into `result`. Returns the merged dict.

**Original Logic (now distributed across 3 split nodes):**
1. For each modified file:
   - Validate the LLM-generated path with `_is_path_safe(base_path, rel_path)` (path traversal guard — helper now lives in `apply_patches.py`, imported by `write_new_files.py`)
   - Apply patch (if patch provided) — **`node_apply_patches`**
   - Write new file (if new file) — **`node_write_new_files`**
   - Update existing file (if content provided) — **`node_write_new_files`**
2. Use `FileLock` for atomic writes — **`node_write_new_files`**
3. Use `tempfile.NamedTemporaryFile` + `os.replace` for atomicity — **`node_write_new_files`**
4. Persist `test_autocode_feature.py` + `generated_code.json` + `debug_log.json` to `run_dir` — **`node_persist_artifacts`**

**Output (merged):** Partial dict with `written_files`, `files_map`, `test_files`, `autocode_run_path`, `modified_files`, `patch_errors` (if any).

**[Pre-2.0 Fix] `_is_path_safe()` path traversal guard:** New helper `_is_path_safe(base_path, rel_path) -> bool` uses `Path.resolve().is_relative_to()` to verify the resolved target stays inside `base_path.resolve()`. Applied to BOTH patch targets and new-file targets. Was: only user-supplied paths were validated (in `node_validate_input`) — LLM-generated paths like `"../../etc/passwd"` would escape `base_path`. Found by: Qwen. See CHANGELOG.md. **[v2.0-beta]** Phase 3.1 moved the helper from `write_files.py` to `apply_patches.py` (re-exported from `write_files.py` for `import`-compatibility).

**[P1 #9] Returns `status: "error"` on JSON parse failure** (was: returned `{}` — workflow continued silently). Now handled by `node_apply_patches`.

**[P2 #13] `FileLock` timeout retries once** (was: no retry — lock contention silently skipped the write). Now handled by `node_write_new_files`.

**Note:** `.bak` files are forbidden by project rules — atomic writes (tempfile + `os.replace`) only. Git is the backup.

---

### `node_apply_patches(state)` — [v2.0-beta] Phase 8a: Apply str_replace Patches

**Purpose:** Apply `str_replace` patches to existing files only. First of the 3 Phase 3.1 split nodes (was inside `node_write_files`).

**Logic:**
1. Read `state["tdd_source_code"]` JSON, extract `patches[]` array
2. For each patch: validate path via `_is_path_safe()`, skip if protected, skip if file missing, else call `apply_patch(target, old_text, new_text)`
3. Build `modified_files` list (paths successfully patched) + `patch_errors` list (path-traversal blocks + missing-file + apply failures)

**Params:** None beyond `state`. Reads: `state["tdd_source_code"]`, `state["status"]`, `state["dry_run"]`, `state["project_root"]`.

**Returns:** `{"modified_files": list[str], "patch_errors"?: list[str]}` — or `{"status": "error", "error": str}` on JSON parse failure, or `{"status": "dry_run", "modified_files": []}` when `dry_run=True`, or `{}` when `status` is `needs_clarification`/`failed` or `tdd_source_code` is empty.

**Source:** `workflows/autocode_impl/nodes/apply_patches.py` (Phase 3.1 — also hosts `_is_path_safe()` shared with `write_new_files.py`).

---

### `node_write_new_files(state)` — [v2.0-beta] Phase 8b: Write New Files + Build files_map

**Purpose:** Write new files / overwrite existing ones atomically. Also builds `files_map` for `analyze_impact`. Second of the 3 Phase 3.1 split nodes.

**Logic:**
1. Read `state["tdd_source_code"]` JSON, extract `new_files{}` dict (backwards-compat: if no `patches`/`new_files` keys, treat whole dict as files)
2. For each file: validate path via `_is_path_safe()` (imported from `apply_patches.py`), skip if protected, else write atomically (`tempfile.NamedTemporaryFile` + `os.replace` + `FileLock` with 1 retry on timeout)
3. Call `_cleanup_old_autocode_runs()` for on-demand run-dir pruning
4. Build `files_map` — snapshots of all modified files (patches from `apply_patches` + new files written here) with `{content_preview, preview_md5, full_md5, size, truncated}` for `analyze_impact`

**Params:** None beyond `state`. Reads: `state["tdd_source_code"]`, `state["status"]`, `state["dry_run"]`, `state["project_root"]`.

**Returns:** `{"files_map": dict[str, dict]}` — or `{}` when `status` is `needs_clarification`/`failed`/`error`, `tdd_source_code` is empty, or `dry_run=True`.

**Source:** `workflows/autocode_impl/nodes/write_new_files.py` (Phase 3.1 — imports `_is_path_safe` from `apply_patches.py`).

---

### `node_persist_artifacts(state)` — [v2.0-beta] Phase 8c: Persist Test File + Generated Code + Debug Log

**Purpose:** Persist the test file + generated code + debug log to the per-run autocode folder. Third of the 3 Phase 3.1 split nodes. Sets `test_files` + `autocode_run_path` for downstream verify nodes.

**Logic:**
1. Resolve `run_dir` via `_get_autocode_run_path(tid)` (or read from `state["autocode_run_path"]` if set)
2. Write `test_autocode_feature.py` from `state["test_code"]` (joined with `"\n\n"` if list) using `FileLock` (10s timeout)
3. Write `generated_code.json` from `state["tdd_source_code"]` (if present)
4. Write `debug_log.json` from `state["debug_notes"]` / `root_cause` / `defense_notes` / `tdd_iteration` (if any are present)
5. Return `test_files` (relative path from `workspace_root`) + `autocode_run_path` (absolute path)

**Params:** None beyond `state`. Reads: `state["test_code"]`, `state["tdd_source_code"]`, `state["debug_notes"]`, `state["root_cause"]`, `state["defense_notes"]`, `state["tdd_iteration"]`, `state["status"]`, `state["dry_run"]`, `state["trace_id"]`, `state["autocode_run_path"]`.

**Returns:** `{"test_files": list[str], "autocode_run_path": str}` — or `{}` when `status` is `needs_clarification`/`failed`/`error`, `dry_run=True`, or `test_code` is empty.

**Source:** `workflows/autocode_impl/nodes/persist_artifacts.py` (Phase 3.1).

---

### `node_analyze_impact(state)` — Phase 9: Analyze Blast Radius

**Purpose:** Analyze the impact of changes on the codebase.

**Logic:**
1. Get modified files from state
2. Query dependency graph for affected files
3. Generate impact warnings

**Output:** Partial dict with `impact_warnings` (list of dicts with `type`, `message`, `agent_fault`).

**Critical bug:** `files_map` is never populated by previous nodes. `node_execute_step` sets `modified_files` (list of dicts), not `files_map` (dict of FileSnapshot). `node_write_files` doesn't set it either. So `node_analyze_impact` always returns early with empty warnings.

**Bug:** `node_analyze_impact` is `async` but LangGraph `StateGraph.add_node` expects sync functions. This may fail or hang.

**Bug:** `impact_warnings` type mismatch. `state.py` says `list[str]`, but `analyze_impact.py` returns `list[dict]`.

---

### `node_run_tests(state)` — Phase 10: Run Tests

**Purpose:** Run the generated tests.

**Logic:**
1. Get test files from state
2. Run tests via `pytest`
3. Return results

**Output:** Partial dict with `test_results`, `test_passed`, `test_output`.

**Bug:** `test_files` may contain paths that don't exist. `node_write_files` sets them to relative paths, but if the file wasn't written, the test run fails.

**[v1.4]** The legacy `workflows/autocode_impl/test_runner.py` (which exported a different `run_tests_on_disk` with a different signature) is **DELETED** as dead code — `node_run_tests` has its own test execution logic and never imported from `test_runner.py`. The signature-confusion note above is no longer applicable. Found by: Kimi.

---

### `node_systematic_debug(state)` — Phase 11: Debug Failures

**Purpose:** Debug test failures. **[v2.0-rc1]** Phase 4 refactor: now uses a 4-phase prompt (investigation → pattern → hypothesis → fix), accumulates `debug_history` across iterations, and bails with an architecture-question exit when 3+ consecutive iterations fail tests with different errors.

**Logic:**
1. **[v2.0-rc1]** Read `debug_history` from `TDDState` sub-state via `_get_tdd(state, "debug_history", [])` (was stateless per iteration — closes the #37 prerequisite).
2. **[v2.0-rc1] Architecture-question exit:** If `len(debug_history) >= _ARCHITECTURE_QUESTION_THRESHOLD` (3) AND all last 3 entries have `tests_passed=False`, bail with `tdd_status="max_retries_exceeded"` + procedural memory store (`memory.store(text=..., memory_type="procedural", importance=9, tags="tdd_failure,architecture_question,autocode,phase4", outcome="failed")`). DIFFERENT from #39 stuck detection (same error signature repeating) — this fires when DIFFERENT errors occur on each iteration, suggesting the bug is architectural, not a fix-the-line bug. Return shape: `{"tdd_status": "max_retries_exceeded", "error": ..., "debug_notes": ..., "tdd": {"debug_history": debug_history}}` (history preserved on early exit).
3. Check `current_iteration > max_retries` — bail with `tdd_status="max_retries_exceeded"` + procedural memory store (`tags="tdd_failure,retry_exhaustion,autocode"`). Return preserves `debug_history`.
4. Build prompt with test output and context (includes blast-radius warning from `kgraph` if `modified_files` is set).
5. **[v2.0-rc1]** Use `DEBUG_SYSTEM` from `constants.py` (was inline) — the 4-phase structured prompt (investigation → pattern → hypothesis → fix) inspired by obra/superpowers `systematic-debugging`. `blast_radius_note` appended.
6. **[v2.0-rc1]** Inject last 5 `debug_history` entries into the user prompt under a `--- PRIOR DEBUG ATTEMPTS (do NOT repeat these) ---` block (format: `- iteration N [phase=P]: root_cause[:120] | fix[:120]`).
7. **[v1.3]** If `cfg.autocode_swarm_debug` is ON, call `_swarm_debug_consensus(system, user, tid)`:
   - **Run 1:** `swarm(action="consensus")` — all configured cloud providers propose a `{root_cause, defense_notes, fix}` object.
   - **Run 2:** `swarm(action="vote")` — providers vote YES/NO on whether the consensus root-cause + fix is correct.
   - Confidence is derived from the vote `agreement` field:
     - `unanimous` → `HIGH`
     - `majority` → `MEDIUM`
     - `split` / `disagreement` / unknown → `LOW`
   - If swarm returns `None` (no providers configured, import failure, consensus exception), falls through to single-LLM debug.
8. Otherwise (flag OFF or swarm unavailable), call `llm.complete(role="executor", ..., json_schema=_DEBUG_JSON_SCHEMA)` for debug analysis (v1.2 behavior). **[v2.0-rc1]** `_DEBUG_JSON_SCHEMA` now includes required `phase` field (enum: `"investigation"` / `"pattern"` / `"hypothesis"` / `"fix"`).
9. Parse JSON response for `phase`, `root_cause`, `defense_notes`, and `fix`. **[v2.0-rc1]** Validate `phase` against the allowed enum; default to `"investigation"` on unknown value (defensive — schema enforcement should prevent this). Trace-log `[phase=P] Root cause: ...`.
10. **[v1.3]** If swarm returned LOW confidence AND `cfg.autocode_debug_comment_pr` is ON AND a PR exists in state (`state["pr_number"]` is set), post a warning comment on the PR via `_github_pr_comment()` so human reviewers see the disagreement.
11. **[v2.0-rc1]** Append a new entry to `debug_history`: `{iteration: current_iteration, phase: phase, root_cause: root_cause, fix: (suggested_fix or "")[:200], tests_passed: False}` (`tests_passed` is updated by `run_tests` on the next loop iteration). Swarm path appends with `phase="swarm"` + extra `confidence` field. Return includes `"tdd": {"debug_history": updated_history}`.

**Output:** Partial dict with `root_cause`, `defense_notes`, `tdd_source_code`, `debug_notes`, **[v2.0-rc1]** `"tdd": {"debug_history": updated_history}`. **[v1.3]** When swarm was used, also includes `swarm_verdict: {fix, root_cause, defense_notes, confidence, agreement, providers}`.

**[Pre-2.0 Fix] `constants.py` field name alignment:** The `DEBUG_SYSTEM` prompt now uses `root_cause` / `defense_notes` (matching the `_DEBUG_JSON_SCHEMA` and `AutocodeState` TypedDict). Was: `hypothesis` / `defense_note` — the prompt asked the LLM for those keys, but the code read `root_cause` / `defense_notes`, so swarm debug's `root_cause` was always `"Unknown"`. Found by: MiMo. See CHANGELOG.md.

**[v2.0-rc1] 4-phase prompt structure:** `DEBUG_SYSTEM` in `constants.py` restructured from 16 lines to ~46 lines. 4 explicit phases: Phase 1 "investigation" (read error, reproduce mentally, check git diff, trace data flow), Phase 2 "pattern" (find working example, compare line-by-line, identify the SINGLE difference), Phase 3 "hypothesis" (form a SINGLE specific falsifiable hypothesis — "the bug is X because Y"), Phase 4 "fix" (ONE targeted fix — no shotgun edits; if fix would touch >3 files, STOP — hypothesis is wrong). JSON output now includes required `phase` field so the orchestrator can track progression and detect stuck loops. Inspired by obra/superpowers `systematic-debugging` skill. Preserved the `[Pre-2.0 Fix]` note about field-name alignment.

**[v2.0-rc1] debug_history accumulation:** Each iteration appends an entry `{iteration, phase, root_cause, fix[:200], tests_passed: False}` to `debug_history` in the `TDDState` sub-state. Last 5 entries are injected into the LLM user prompt so the LLM doesn't repeat failed hypotheses/fixes. The full history is preserved across iterations (closes the #37 prerequisite — was stateless per iteration before Phase 4). Swarm path accumulates with `phase="swarm"` and an extra `confidence` field. Both early-exit paths (architecture + max_retries) also return `"tdd": {"debug_history": debug_history}` to preserve history for downstream inspection.

**[v2.0-rc1] Architecture-question exit:** `_ARCHITECTURE_QUESTION_THRESHOLD = 3` module constant. If `len(debug_history) >= 3` AND all last 3 entries have `tests_passed=False`, bail with `tdd_status="max_retries_exceeded"` + procedural memory store (`tags="tdd_failure,architecture_question,autocode,phase4"`, `importance=9`, `outcome="failed"`). The memory text includes the task, iteration count, threshold, and last error so a human reviewing the procedural memory store can see the architectural problem. This is DIFFERENT from #39 stuck detection (`route_after_run_tests` checks `last_test_error` signature equality across consecutive iterations — fires on the SAME error repeating). The architecture-question exit fires when DIFFERENT errors occur each iteration, suggesting the bug is architectural, not a fix-the-line bug. Inspired by superpowers Phase 4.5 pattern.

**[v1.3] Swarm is non-blocking:** the fix is always applied regardless of confidence. LOW confidence surfaces as a PR comment (if enabled), not as a workflow block. Rationale: the debug loop already has `MAX_RETRIES`, stuck-detection routing, the `node_verify` gate, and the git branch as safety nets; blocking on a multi-LLM vote would add latency and a new failure mode without improving correctness. **[v2.0-rc1]** Add the architecture-question exit to that safety-net list.

**[v1.3] Fallback chain:** `AUTOCODE_SWARM_DEBUG=1` + swarm available → use swarm. `AUTOCODE_SWARM_DEBUG=1` + swarm unavailable (no providers, import failure, consensus exception) → single-LLM debug (v1.2 path). `AUTOCODE_SWARM_DEBUG=0` → single-LLM debug (v1.2 path).

**Note:** `memory.store()` is called without `await` but `memory.store()` is sync. This is correct.

**Note:** `blast_radius_note` is constructed but used in the system prompt. Correct.

**[v2.0-rc1] Debug statelessness caveat RESOLVED:** Each debug call now sees the last 5 entries of `debug_history` (within the current run) in addition to the current iteration's `test_results`. The full history is also available to `node_summarize_context` which compresses it for bounded-context reads. Cross-run learning (procedural memory recall before debug) is still a `# TODO(2.0-post):` item — see CHANGELOG.md § "Future Tracks (Post-2.0)" F5.
- `# TODO(2.0-post):` Migrate the LLM user prompt to use `debug_summary` (compressed) instead of the raw last-5-entries block once `debug_history` grows past ~10 entries (F3 in CHANGELOG.md).
- `# TODO(2.0-post):` Add `memory.recall(query=stderr[:200], memory_type="procedural", k=3)` before the LLM debug prompt for cross-run learning (F5 in CHANGELOG.md).
- `# TODO(2.0-post):` Consider `AUTOCODE_PARALLEL_DEBUG=1` flag for subagent dispatch (one subagent per hypothesis) instead of the single-LLM sequential 4-phase loop (F1 in CHANGELOG.md).
- `# TODO(2.0-post):` Make `_ARCHITECTURE_QUESTION_THRESHOLD` configurable per task type (F4 in CHANGELOG.md).
- `# TODO(2.0):` Consider making swarm the default debug path for cloud-enabled setups.
- `# TODO(2.0):` Review confidence thresholds (e.g., MEDIUM should require ≥3 providers).
- `# TODO(2.0):` Consider `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag for stricter gating.

---

### `node_summarize_context(state)` — [v2.0-rc1] Phase 11a: Compress debug_history (NEW)

**Purpose:** Compress `debug_history` before re-entering the debug loop. Closes #37 (context summarization). Wired between `node_systematic_debug` and `node_apply_patches` in the debug loop so the next debug iteration sees a bounded context.

**Logic:**
1. Read `debug_history` from `TDDState` sub-state via `_get_tdd(state, "debug_history", [])`.
2. If `debug_history` is empty, return `{"tdd": {"debug_summary": ""}}` (no work to do — typically the first debug iteration).
3. Otherwise, call `_summarize_debug_history(history)` helper:
   a. Reverse the history (most recent first — the freshest hypothesis is the most relevant for the next iteration).
   b. Render each entry as a single sentence: `iter=N phase=P tests_passed=B [confidence=C] root_cause=R fix_preview=F` (where `confidence` is included only for swarm-path entries that have it).
   c. Join sentences with `. ` and append a trailing `.`.
   d. Try `from chonkie import SentenceChunker` (lazy import, soft dependency). If import succeeds, instantiate `SentenceChunker(chunk_size=512, chunk_overlap=0)` and call `.chunk(text)`. Return the FIRST chunk only (most recent, since we reversed) — keeps the summary tight and bounded.
   e. On ANY `Exception` (including `ModuleNotFoundError` when chonkie isn't installed, or chunking failure), silently fall back to `json.dumps(reversed_history[:3], ensure_ascii=False, default=str)` — JSON serialization of the last 3 entries (most recent first). The fallback keeps the node usable in environments where chonkie is not yet pip-installed (e.g., CI without optional deps).
4. Trace-log entry count + compressed length: `tracer.step(tid, "summarize_context", f"Compressed {len(debug_history)} debug_history entries into {len(summary)} chars")`.
5. Return `{"tdd": {"debug_summary": summary}}`.

**Params:** None beyond `state`. Reads (via `_get_tdd` accessor): `state["tdd"]["debug_history"]` (or legacy `state["debug_history"]` fallback) — `list[dict]` where each dict has shape `{iteration: int, phase: str, root_cause: str, fix: str, tests_passed: bool, [confidence: str]}`.

**Returns:** `{"tdd": {"debug_summary": str}}` — partial state update writing the compressed summary to the `debug_summary` field in the `TDDState` sub-state. Empty string when history is empty.

**Source:** `workflows/autocode_impl/nodes/summarize_context.py` (Phase 4.3 NEW — ~110 lines).

**Note:** This node does NOT mutate `debug_history` — the full history is preserved for the architecture-question exit check in `node_systematic_debug`. The summary is purely additive (a compressed view for bounded-context reads).

**Note:** chonkie is a SOFT dependency — the node imports it lazily inside a `try` block. If chonkie is not installed, the node silently falls back to JSON-of-last-3-entries. Do NOT make chonkie a hard dependency of `workflows.autocode_impl` (the workflow must remain importable in environments without chonkie installed, e.g., CI without optional deps).

**`# TODO(2.0-post):`** No downstream node reads `debug_summary` yet — `node_systematic_debug` still uses the raw last-5-entries block. Once `debug_history` grows past ~10 entries, switch the LLM user prompt to use `debug_summary` (the compressed chunk) instead of the raw entries (F3 in CHANGELOG.md § "Future Tracks (Post-2.0)").

---

### `node_verify(state)` — [v2.0-beta] Phase 12: BACKWARD-COMPAT WRAPPER

**Purpose:** Verify the changes with linting, regression tests, and LLM spec review.

**[v2.0-beta] BACKWARD-COMPAT WRAPPER (Phase 3.2 split):** This node is now a thin wrapper that calls the 4 split nodes in sequence and merges their partial state updates into one dict matching the original return shape. The graph wires the 4 split nodes directly (`route → run_pytest → run_lint → llm_review → verify_decision → [route_after_verify]`); this wrapper is registered via `add_node(...)` so external callers + tests that `import node_verify` still work (e.g., `test_verify.py` imports it to exercise the full verify chain), but it has NO edges in or out. Excluded from `WORKFLOW_METADATA["nodes"]` (27-entry list — wrappers excluded). See the 4 split-node sections below for the actual logic.

**Wrapper logic:** Runs `node_run_pytest({**state, **result})` → `node_run_lint({**state, **result})` → `node_llm_review({**state, **result})` → `node_verify_decision({**state, **result})` in sequence, accumulating partial updates into `result`. Returns the merged dict.

**Original Logic (now distributed across 4 split nodes):**
1. **[Pre-2.0 Fix]** Handle `tdd_status` in `{"max_retries_exceeded", "stuck"}` → return early with `verification_passed: False` — **`node_verify_decision`**
2. **[Pre-2.0 Fix]** Skip `pytest` entirely if no test files exist — **`node_run_pytest`**
3. Run `ruff check` for linting (advisory only — does not block commit) — **`node_run_lint`**
4. **[Pre-2.0 Fix]** Scope ruff to `modified_files` only — **`node_run_lint`**
5. Run LLM verification (spec coverage + cleanliness) with hallucination guard — **`node_llm_review`** (LLM call) + **`node_verify_decision`** (hallucination guard: real pytest exit code overrides LLM claim)
6. Return verification results — **`node_verify_decision`**

**Output (merged):** Partial dict with `lint_passed`, `lint_output`, `regression_passed`, `evidence_outputs`, `verification_passed`, `verification_notes`, `test_results`, `tests_passed`, `llm_review_data`, `trace_id`, `status` (failed on max_retries/stuck early-exit).

**[P1 #7] `lint_passed = None` when ruff is unavailable** (was `True` — missing ruff should not report as pass). Now handled by `node_run_lint`.

**Note:** `evidence_outputs` includes `regression: fresh_output[:2000]` which is the same as `tests`. Redundant — `# TODO(2.0):` collapse into a single `tests` entry. Now produced by `node_verify_decision`.

**[v2.0-beta] Test impact:** `test_verify.py` patches `workflows.autocode_impl.nodes.llm_review._call` instead of `…verify._call` — `_call` is now imported into `llm_review.py` for the LLM spec check. The `verify.py` wrapper re-exports nothing (it just runs the 4 split nodes), so patching `verify._call` no longer works.

---

### `node_run_pytest(state)` — [v2.0-beta] Phase 12a: Fresh Pytest Subprocess

**Purpose:** Run a fresh pytest subprocess on the autocode run directory. First of the 4 Phase 3.2 split nodes (was inside `node_verify`).

**Logic:**
1. Resolve `run_dir` from `state["autocode_run_path"]` or `_get_autocode_run_path(tid)`
2. **[Pre-2.0 Fix]** If no test files exist (`tests_dir` and `test_file` both missing), skip pytest entirely — return `{"test_results": {...stderr: "No test files found..."}, "tests_passed": False}`
3. Run `[python, "-m", "pytest", "--tb=short", "--color=no", "-q", ...targets]` with `cwd=base_path` and 120s timeout
4. Build `test_results` dict `{success, stdout, stderr, returncode}` + `tests_passed` bool + ephemeral `_pytest_output` (first 2000 chars — stashed for `llm_review`)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["trace_id"]`, `state["autocode_run_path"]`, `state["project_root"]`.

**Returns:** `{"test_results": dict, "tests_passed": bool, "_pytest_output": str}` — handles `FileNotFoundError` (pytest missing) + `subprocess.TimeoutExpired` (120s) with structured error returns. Or `{}` when `status` is `needs_clarification`/`failed`.

**Source:** `workflows/autocode_impl/nodes/run_pytest.py` (Phase 3.2).

---

### `node_run_lint(state)` — [v2.0-beta] Phase 12b: Ruff Lint on modified_files Only

**Purpose:** Run `ruff check` scoped to `modified_files` only (advisory — does not block commit). Second of the 4 Phase 3.2 split nodes.

**Logic:**
1. Read `modified_files` from state (set by `node_apply_patches`); if empty, return `{"lint_output": "No modified files to lint", "lint_passed": None}`
2. Resolve `lint_targets` as absolute paths via `base_path / f` for each `f` in `modified_files`
3. Run `[python, "-m", "ruff", "check", ...targets, "--select", "E,F", "--no-cache"]` with 30s timeout
4. Build `lint_output` (first 500 chars of stdout+stderr) + `lint_passed` (bool — `returncode == 0`)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["trace_id"]`, `state["modified_files"]`, `state["project_root"]`.

**Returns:** `{"lint_output": str, "lint_passed": bool | None}` — `lint_passed` is `None` when ruff is unavailable (`except Exception` branch — **[P1 #7]** was `True` before Pre-2.0 Fix) or when no modified files exist. Or `{}` when `status` is `needs_clarification`/`failed`.

**Source:** `workflows/autocode_impl/nodes/run_lint.py` (Phase 3.2).

---

### `node_llm_review(state)` — [v2.0-beta] Phase 12c: LLM Spec Coverage + Cleanliness Review

**Purpose:** LLM-based spec review of the implementation. Third of the 4 Phase 3.2 split nodes. Calls `_call(role="executor", system=VERIFY_SYSTEM, ...)` with implementation context, fresh pytest output, and ruff output.

**Logic:**
1. Build `impl_ctx` from `state["tdd_source_code"]` JSON — extract `patches[].new` (first 1500 chars each) + `new_files{}` values (first 1500 chars each). Fallback: raw `tdd_source_code[:3000]` on parse error
2. Read `tests_passed`, `_pytest_output` (from `node_run_pytest`), `lint_output` (from `node_run_lint`) from state
3. Call `_call(role="executor", system=VERIFY_SYSTEM, user=<spec + impl + tests + pytest output + ruff output>, timeout=EXECUTOR_TIMEOUT)`
4. Parse response via `_parse_json(raw)` → `data` dict `{automated_checks_passed, checks: {syntax, tests, spec, regressions, cleanliness}, summary}`
5. On `_call` exception: `tracer.error(tid, "llm_review", ...)` + return `{"llm_review_data": {"automated_checks_passed": False, "checks": {}, "summary": "LLM verification error"}}`

**Params:** None beyond `state`. Reads: `state["status"]`, `state["trace_id"]`, `state["tdd_source_code"]`, `state["tests_passed"]`, `state["_pytest_output"]`, `state["test_results"]`, `state["lint_output"]`, `state["spec"]`, `state["test_code"]`.

**Returns:** `{"llm_review_data": dict}` — always returns a dict (even on error). Or `{}` when `status` is `needs_clarification`/`failed`.

**Source:** `workflows/autocode_impl/nodes/llm_review.py` (Phase 3.2 — imports `_call` + `_parse_json` from `helpers.py`; `VERIFY_SYSTEM` from `constants.py`; `EXECUTOR_TIMEOUT` from `state.py`).

**Note:** This is the only node in the verify chain that calls the LLM. `node_verify_decision` (next) consumes `llm_review_data` and applies the hallucination guard.

---

### `node_verify_decision(state)` — [v2.0-beta] Phase 12d: Compose Results + Hallucination Guard

**Purpose:** Compose the results from the 3 previous nodes (run_pytest + run_lint + llm_review) and make the final verification decision. Fourth of the 4 Phase 3.2 split nodes. Also handles the `tdd_status="max_retries_exceeded"` / `"stuck"` early exit (moved here from the original `node_verify`).

**Logic:**
1. **Early exit:** If `tdd_status in ("max_retries_exceeded", "stuck")`, log `tracer.error(tid, "verify_decision", ...)`, store a procedural memory (`memory.store(...)` — non-fatal, wrapped in try/except), and return `{"status": "failed", "verification_notes": f"TDD {tdd_status}", "verification_passed": False, "trace_id": tid}`. Skip conditions (`needs_clarification`/`failed`): return `{}`.
2. Read results from state: `tests_passed`, `lint_passed`, `_pytest_output`, `lint_output`, `llm_review_data`
3. Compute `automated_ok = tests_passed` (lint is advisory only)
4. **Hallucination guard:** If `not tests_passed` AND `llm_review_data["automated_checks_passed"]` is True, log `tracer.step` "HALLUCINATION DETECTED" — real exit code overrides LLM claim
5. Compute `llm_checks_ok` = all of `syntax`, `tests`, `spec`, `regressions`, `cleanliness` checks pass
6. Final decision: `all_passed = automated_ok AND llm_checks_ok`
7. Build `verification_notes` (Automated/LLM PASS/FAIL + summary + JSON-encoded checks) + `evidence_outputs` `{tests, lint, regression}` (each truncated to 2000/500/2000 chars)

**Params:** None beyond `state`. Reads: `state["trace_id"]`, `state["tdd_status"]`, `state["max_retries"]`, `state["task"]`, `state["tdd_error"]`, `state["status"]`, `state["tests_passed"]`, `state["lint_passed"]`, `state["_pytest_output"]`, `state["test_results"]`, `state["lint_output"]`, `state["llm_review_data"]`.

**Returns:** `{"verification_passed": bool, "verification_notes": str, "evidence_outputs": dict, "trace_id": str}` — or `{"status": "failed", ...}` on max_retries/stuck early-exit, or `{}` on `needs_clarification`/`failed` skip.

**Source:** `workflows/autocode_impl/nodes/verify_decision.py` (Phase 3.2).

**[v2.0-beta] `route_after_verify` now routes from this node** (was: from `node_verify`). The conditional edge `workflow.add_conditional_edges("node_verify_decision", route_after_verify, {...})` in `graph.py` reads `verification_passed` to decide between `node_report` and `END`.

---

### `node_report(state)` — Phase 13: Generate Report

**Purpose:** Generate a structured report with the final result.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with result and metadata
2. Return the report

**Output:** Empty dict (side effects only).

**Bug:** Type annotation says `AutocodeState` but returns `{}`.

**Bug:** `modified_files` uses `state.get("files_map", {}).keys()` but `files_map` is always empty.

---

### `node_git_commit(state)` — Phase 14: Commit Changes

**Purpose:** Commit the changes to git.

**Logic:**
1. Generate commit message
2. Call `git(action="commit", message=..., root=...)`
3. Return commit SHA

**Output:** Partial dict with `commit_sha`, `status`, `result`.

**[Pre-2.0 Fix] `.get("label", "step")` fallback:** Was: `s["label"]` raised `KeyError` if any step in the plan lacked a `"label"` key (LLM-returned plans are not guaranteed to label every step). Now uses `s.get("label", "step")` so malformed plans don't crash commit. Found by: DeepSeek. See CHANGELOG.md.

**Bug:** `status` is set to `"done"` regardless of whether commit succeeded. If `_git_commit` returns `None` (no changes), `status` is still `"done"`. `# TODO(2.0):` Distinguish "committed" / "nothing to commit" / "failed".

**[v1.3] Scope note:** `node_git_commit` is LOCAL-ONLY (no push, no PR). All remote operations live in the next node, `node_publish`. See `workflows/autocode_impl/git_ops.py` (local) vs `workflows/autocode_impl/github_ops.py` (remote) for the split rationale. **[v2.0-rc2]** Both modules are now thin re-export wrappers — the actual implementations live in the unified `workflows/autocode_impl/vcs_ops.py` (Phase 5.1 consolidation). New code MUST import VCS functions from `vcs_ops.py` directly, not from `git_ops` / `github_ops` (see INSTRUCTIONS.md ALWAYS DO #53).

**[v2.0] First node migrated to the accessor pattern:** `node_git_commit` now reads `state["branch"]` via `_get_vcs(state, "branch", "main")` instead of `state.get("branch", "main")`. This is the proof-of-concept migration for the sub-state / legacy-fallback accessor layer introduced in Phase 2 (see ARCHITECTURE.md § "[v2.0] Sub-state Architecture"). No behavior change — the accessor returns the same value as the legacy path until Phase 6 removes the legacy flat fields. `# TODO(2.0):` Migrate the remaining 16 nodes during Phase 3 / Phase 4.

---

### `node_publish(state)` — [v2.0-beta] Phase 15: BACKWARD-COMPAT WRAPPER

**Purpose:** Push the committed branch to the remote, open a PR, and optionally auto-merge it. Runs after `node_commit`, before `node_distill_memory`.

**[v2.0-beta] BACKWARD-COMPAT WRAPPER (Phase 3.3 split):** This node is now a thin wrapper that calls the 3 split nodes in sequence and merges their partial state updates into one dict matching the original return shape. The graph wires the 3 split nodes directly (`commit → push → create_pr → merge_pr → distill_memory`); this wrapper is registered via `add_node(...)` so external callers + tests that `import node_publish` still work, but it has NO edges in or out. Excluded from `WORKFLOW_METADATA["nodes"]` (27-entry list — wrappers excluded). See the 3 split-node sections below for the actual logic.

**Wrapper logic:** Runs `node_push({**state, **result})` → `node_create_pr({**state, **result})` → `node_merge_pr({**state, **result})` in sequence, accumulating partial updates into `result`. Returns the merged dict.

**Original Logic (now distributed across 3 split nodes):**
1. Skip conditions (same as `node_commit`): `status` in `{needs_clarification, failed, skipped}` → return `{}`. `verification_passed` falsy → return `{}`. `dry_run` truthy → return `{"status": "dry_run"}`. — **`node_push`**
2. If none of the three publish flags are ON (`AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`), return `{}` (v1.2 behavior — no-op). — **`node_push`** (returns `{"pushed": False}` when push flag is OFF)
3. If `state["branch"]` is empty, return `{}` (nothing to push). — **`node_push`**
4. **Step 1 — Push:** If `cfg.autocode_push_on_commit`, call `_github_push(branch, tid)`. On failure, return early. — **`node_push`**
5. **Step 2 — PR create:** If `cfg.autocode_open_pr` AND push succeeded, call `_github_pr_create(branch, title, body, tid)` with `body` built by `_build_pr_body(state)` — **`node_create_pr`** (`_build_pr_body` MOVED here from `publish.py` in Phase 3.3; signature unchanged)
6. **Step 3 — Auto-merge:** If `cfg.autocode_auto_merge` AND a PR was created, call `_github_pr_merge(pr_number, tid)`. — **`node_merge_pr`** (terminal — returns `{}`)

**Output (merged):** Partial dict with `pushed: bool`, `pr_number: int`, `pr_url: str` (all three are always present when the node runs to completion; defaults are `False`/`0`/`""`).

**[v1.3] Config flags (all default OFF):**
- `AUTOCODE_PUSH_ON_COMMIT=1` — push the branch to `origin` after commit.
- `AUTOCODE_OPEN_PR=1` — open a PR from the branch to `main` after push.
- `AUTOCODE_AUTO_MERGE=1` — **DANGEROUS.** Auto-merge the PR via squash after creation.

**[v1.3] Graceful-skip behavior:** Every `github_ops.py` helper checks `_github_is_configured()` (wraps `tools.github_ops.client.is_configured()` in try/except) before any GitHub API call. If GitHub is not configured (`GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` missing), the helper logs a `tracer.step` and returns `False`/`None` — the workflow continues without crashing. **[v2.0-rc2]** All `_github_*` helpers now live in `vcs_ops.py` (Phase 5.1 consolidation); `github_ops.py` is a thin re-export wrapper that re-exports them for backward compat with external importers.

**[v1.3] Why `node_publish` is separate from `node_commit`:** See ARCHITECTURE.md § "[v1.3] Design Decision Notes" #1. Short version: commit failure ≠ publish failure; the publish step can be skipped in dry_run / failed / skipped states independently; the graph topology stays self-documenting. **[v2.0-beta]** Phase 3.3 split it further for finer-grained routing and retry.

**`# TODO(2.0):` items:**
- ~~Split `node_publish` into separate `node_push` / `node_pr_create` / `node_pr_merge` for finer-grained routing and retry.~~ **[v2.0-beta] DONE (Phase 3.3)** — split into `node_push` / `node_create_pr` / `node_merge_pr`. `# TODO(2.0):` Phase 6 removes this wrapper once all external callers have migrated to the 3 split nodes.
- Add retry logic for transient push / PR creation failures (currently terminal).
- Add `AUTOCODE_AUTO_MERGE_METHOD` config (squash / merge / rebase) — currently hardcoded to `squash` inside `_github_pr_merge`.
- Richer PR body (test results, diff summary, impact warnings) — currently minimal.

---

### `node_push(state)` — [v2.0-beta] Phase 15a: Push Branch to Remote

**Purpose:** Push the committed branch to the remote via `_github_push(branch, tid)`. First of the 3 Phase 3.3 split nodes (was inside `node_publish`).

**Logic:**
1. Skip conditions (same as `node_commit`): `status in {needs_clarification, failed, skipped}` → `{}`; `verification_passed` falsy → `{}`; `dry_run` truthy → `{"status": "dry_run"}`
2. If `cfg.autocode_push_on_commit` is OFF, return `{"pushed": False}` (let downstream nodes decide)
3. If `state["branch"]` is empty, return `{"pushed": False}` (nothing to push)
4. Call `_github_push(branch, tid)` — returns `bool`
5. Return `{"pushed": success}`

**Params:** None beyond `state`. Reads: `state["status"]`, `state["verification_passed"]`, `state["dry_run"]`, `state["trace_id"]`, `state["branch"]`.

**Returns:** `{"pushed": bool}` — or `{"status": "dry_run"}` when dry_run, or `{}` on skip conditions.

**Source:** `workflows/autocode_impl/nodes/push.py` (Phase 3.3 — imports `_github_push` from `github_ops.py`; **[v2.0-rc2]** `_github_push` now lives in `vcs_ops.py` — `github_ops.py` is a thin re-export wrapper).

---

### `node_create_pr(state)` — [v2.0-beta] Phase 15b: Create Pull Request

**Purpose:** Open a PR from the autocode branch via `_github_pr_create(branch, title, body, tid)`. Second of the 3 Phase 3.3 split nodes. Hosts `_build_pr_body(state)` (moved here from `publish.py` in Phase 3.3 — signature unchanged).

**Logic:**
1. Skip conditions: `status in {needs_clarification, failed, skipped}` → `{}`; `verification_passed` falsy → `{}`; `dry_run` truthy → `{}`
2. If `cfg.autocode_open_pr` is OFF, return `{"pr_number": 0, "pr_url": ""}`
3. If `state["pushed"]` is falsy (can't create a PR without pushing first), return `{"pr_number": 0, "pr_url": ""}` with a `tracer.step` note
4. If `state["branch"]` is empty, return `{"pr_number": 0, "pr_url": ""}`
5. Build `pr_title = f"autocode: {state['task'][:60]}"` and `pr_body = _build_pr_body(state)`
6. Call `_github_pr_create(branch, pr_title, pr_body, tid)` — returns `dict | None`
7. Return `{"pr_number": pr_data["number"], "pr_url": pr_data["url"]}` on success, `{"pr_number": 0, "pr_url": ""}` on failure

**`_build_pr_body(state)` helper (moved here from `publish.py` in Phase 3.3):**
- Reads: `task`, `task_type`, `commit_sha`, `verification_passed`, `root_cause`, `swarm_verdict`
- Outputs a markdown PR body: `## Autocode: <task[:80]>` header + `**Type:**` + `**Commit:**` + `**Verified:**` + optional `**Root cause identified:**` + optional `**Swarm review:**` (with `⚠️ Low-confidence swarm verdict` warning if `confidence == "LOW"`) + footer
- Signature unchanged from `publish.py` (no behavior change — pure move)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["verification_passed"]`, `state["dry_run"]`, `state["trace_id"]`, `state["pushed"]`, `state["branch"]`, `state["task"]`, `state["task_type"]`, `state["commit_sha"]`, `state["root_cause"]`, `state["swarm_verdict"]`.

**Returns:** `{"pr_number": int, "pr_url": str}` — always returns both keys (defaults `0`/`""` if PR not created). Or `{}` on skip conditions.

**Source:** `workflows/autocode_impl/nodes/create_pr.py` (Phase 3.3 — imports `_github_pr_create` from `github_ops.py`; defines `_build_pr_body` locally; **[v2.0-rc2]** `_github_pr_create` now lives in `vcs_ops.py` — `github_ops.py` is a thin re-export wrapper).

---

### `node_merge_pr(state)` — [v2.0-beta] Phase 15c: Auto-merge PR (Terminal)

**Purpose:** Auto-merge the PR via `_github_pr_merge(pr_number, tid)`. Third of the 3 Phase 3.3 split nodes. **DANGEROUS — default OFF.** Terminal — returns `{}` (no state update); no downstream node needs the merge result.

**Logic:**
1. Skip conditions: `status in {needs_clarification, failed, skipped}` → `{}`; `verification_passed` falsy → `{}`; `dry_run` truthy → `{}`
2. If `cfg.autocode_auto_merge` is OFF, return `{}`
3. If `state["pr_number"]` is falsy (no PR to merge — PR not created), return `{}` with a `tracer.step` note
4. Call `_github_pr_merge(pr_number, tid)` (currently hardcoded to `merge_method="squash"` inside the helper)
5. Return `{}` (terminal)

**Params:** None beyond `state`. Reads: `state["status"]`, `state["verification_passed"]`, `state["dry_run"]`, `state["trace_id"]`, `state["pr_number"]`.

**Returns:** `{}` always (terminal — no state update).

**Source:** `workflows/autocode_impl/nodes/merge_pr.py` (Phase 3.3 — imports `_github_pr_merge` from `github_ops.py`; **[v2.0-rc2]** `_github_pr_merge` now lives in `vcs_ops.py` — `github_ops.py` is a thin re-export wrapper).

**`# TODO(2.0):`** Add `AUTOCODE_AUTO_MERGE_METHOD` config (squash/merge/rebase) — currently hardcoded to `squash` inside `_github_pr_merge`.

---

### `node_distill_memory(state)` — Phase 16: Store Procedural Memory

**Purpose:** Store procedural knowledge for future recall.

**Logic:**
1. Build trace text from workflow state
2. Store procedural memory: `memory.store_procedural(text=..., ...)`

**Output:** Empty dict (side effects only).

**Bug:** `node_distill_memory` accesses `state.get("classification", {}).get("task_type", "feature")` but `classification` doesn't exist in state. The fallback to `task_type` is correct but the `classification` access is dead code.

**Bug:** `hypothesis` field is never set by any node. The debug node sets `root_cause`, not `hypothesis`.

**Bug:** `defense_note` (singular) is used but `defense_notes` (plural) is set by debug node. Always empty.

---

### `node_create_skill(state)` — Phase 17: Create Skill

**Purpose:** Create a reusable skill file.

**Logic:**
1. Generate skill code
2. Write to `cfg.agent_root / "skills" / f"{skill_name}.py"` (or `project_root / skills/` if set)

**Output:** Partial dict with `skill_path`, `status`, `result`, `error`.

**[P1 #3] Resolves skill directory via `project_root`** when set (was: always `agent_root` — wrong for workspace projects).

**[P2 #15] `_sanitize_skill_name()`** strips any non-`[a-zA-Z0-9_]` chars (prevents path traversal via `/` or `\` in the skill name).

**[P2 #16] `_validate_python_syntax()`** runs `ast.parse()` before writing (catches `SyntaxError` early).

**[P2 #17] `skill_created: True`** is now set on success (was: never set — `autocode.py` checked it but it was always missing).

**[Pre-2.0 Fix] Atomic write:** Skill file is now written via `tempfile.NamedTemporaryFile` + `os.replace` (was: direct `write_text` — a crash mid-write would corrupt the skill file with a partial write). Found by: MiMo. See CHANGELOG.md.

---

*Last updated: 2026-07-11 (v2.0 GA — **all 7 phases of the 2.0 refactor ✅ COMPLETE.** Phase 7.3 doc consolidation: this file was SPLIT OUT of API.md so that API.md can focus on the facade + state accessors + graph overview. The per-node reference for all 28 nodes (25 active + 3 backward-compat wrappers) lives here, in graph-execution order. Phase 7.1: `CODER_SYSTEM` now includes the 7-rung Lazy Dev minimization ladder (see INSTRUCTIONS.md ALWAYS DO #54). Prior v2.0-rc2 — Phase 5 (VCS consolidation + cleanup): node source lines for `node_git_branch` / `node_git_commit` / `node_publish` / `node_push` / `node_create_pr` / `node_merge_pr` updated with [v2.0-rc2] notes that `_github_*` helpers now live in `vcs_ops.py`. Prior v2.0-rc1 — Phase 4 (debug loop refactor): `node_systematic_debug` section rewritten to document 4-phase prompt + `debug_history` accumulation + last-5-entries injection + architecture-question exit; new `node_summarize_context` section (Phase 11a). See [API.md](API.md) for the workflow facade + output format + state fields + state accessors, [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history + 7-phase refactor progress, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
