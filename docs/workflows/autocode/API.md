<- Back to [Autocode Overview](../AUTOCODE.md)

# 📝 API Reference

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
- Uses `github(action="pull", remote="origin")` via `github_ops._github_pull()`.
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

### `node_write_files(state)` — Phase 8: Write/Modify Files

**Purpose:** Write or modify files on disk.

**Logic:**
1. For each modified file:
   - **[Pre-2.0 Fix]** Validate the LLM-generated path with `_is_path_safe(base_path, rel_path)` (path traversal guard)
   - Apply patch (if patch provided)
   - Write new file (if new file)
   - Update existing file (if content provided)
2. Use `FileLock` for atomic writes
3. Use `tempfile.NamedTemporaryFile` + `os.replace` for atomicity

**Output:** Partial dict with `written_files`, `test_files`, `autocode_run_path`.

**[Pre-2.0 Fix] `_is_path_safe()` path traversal guard:** New helper `_is_path_safe(base_path, rel_path) -> bool` in `nodes/write_files.py` validates that `(base_path / rel_path).resolve()` is strictly within `base_path.resolve()` using `Path.is_relative_to()`. Applied to BOTH patch targets and new-file targets. Was: only user-supplied paths were validated (in `node_validate_input`) — LLM-generated paths like `"../../etc/passwd"` would escape `base_path`. Found by: Qwen. See CHANGELOG.md.

**[P1 #9] Returns `status: "error"` on JSON parse failure** (was: returned `{}` — workflow continued silently).

**[P2 #13] `FileLock` timeout retries once** (was: no retry — lock contention silently skipped the write).

**Note:** `.bak` files are forbidden by project rules — atomic writes (tempfile + `os.replace`) only. Git is the backup.

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

**Purpose:** Debug test failures.

**Logic:**
1. Build prompt with test output and context (includes blast-radius warning from `kgraph` if `modified_files` is set)
2. **[v1.3]** If `cfg.autocode_swarm_debug` is ON, call `_swarm_debug_consensus(system, user, tid)`:
   - **Run 1:** `swarm(action="consensus")` — all configured cloud providers propose a `{root_cause, defense_notes, fix}` object.
   - **Run 2:** `swarm(action="vote")` — providers vote YES/NO on whether the consensus root-cause + fix is correct.
   - Confidence is derived from the vote `agreement` field:
     - `unanimous` → `HIGH`
     - `majority` → `MEDIUM`
     - `split` / `disagreement` / unknown → `LOW`
   - If swarm returns `None` (no providers configured, import failure, consensus exception), falls through to single-LLM debug.
3. Otherwise (flag OFF or swarm unavailable), call `llm.complete(role="executor", ..., json_schema=_DEBUG_JSON_SCHEMA)` for debug analysis (v1.2 behavior).
4. Parse JSON response for root cause, defense notes, and fix.
5. **[v1.3]** If swarm returned LOW confidence AND `cfg.autocode_debug_comment_pr` is ON AND a PR exists in state (`state["pr_number"]` is set), post a warning comment on the PR via `_github_pr_comment()` so human reviewers see the disagreement.

**Output:** Partial dict with `root_cause`, `defense_notes`, `tdd_source_code`, `debug_notes`. **[v1.3]** When swarm was used, also includes `swarm_verdict: {fix, root_cause, defense_notes, confidence, agreement, providers}`.

**[Pre-2.0 Fix] `constants.py` field name alignment:** The `DEBUG_SYSTEM` prompt now uses `root_cause` / `defense_notes` (matching the `_DEBUG_JSON_SCHEMA` and `AutocodeState` TypedDict). Was: `hypothesis` / `defense_note` — the prompt asked the LLM for those keys, but the code read `root_cause` / `defense_notes`, so swarm debug's `root_cause` was always `"Unknown"`. Found by: MiMo. See CHANGELOG.md.

**[v1.3] Swarm is non-blocking:** the fix is always applied regardless of confidence. LOW confidence surfaces as a PR comment (if enabled), not as a workflow block. Rationale: the debug loop already has `MAX_RETRIES`, stuck-detection routing, the `node_verify` gate, and the git branch as safety nets; blocking on a multi-LLM vote would add latency and a new failure mode without improving correctness.

**[v1.3] Fallback chain:** `AUTOCODE_SWARM_DEBUG=1` + swarm available → use swarm. `AUTOCODE_SWARM_DEBUG=1` + swarm unavailable (no providers, import failure, consensus exception) → single-LLM debug (v1.2 path). `AUTOCODE_SWARM_DEBUG=0` → single-LLM debug (v1.2 path).

**Note:** `memory.store()` is called without `await` but `memory.store()` is sync. This is correct.

**Note:** `blast_radius_note` is constructed but used in the system prompt. Correct.

**[v1.3] Debug statelessness caveat:** Each debug call sees only the current iteration's `test_results` — there is no accumulation of `debug_notes` / `root_cause` across iterations. Swarm debug does NOT solve this (it also sees only the current iteration's output). Context summarization (#37 in CHANGELOG.md) is blocked on this refactor.
- `# TODO(2.0):` Refactor `debug.py` to accumulate history across iterations.
- `# TODO(2.0):` Consider making swarm the default debug path for cloud-enabled setups.
- `# TODO(2.0):` Review confidence thresholds (e.g., MEDIUM should require ≥3 providers).
- `# TODO(2.0):` Consider `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag for stricter gating.

---

### `node_verify(state)` — Phase 12: Verify Changes

**Purpose:** Verify the changes with linting and regression tests.

**Logic:**
1. **[Pre-2.0 Fix]** Handle `tdd_status` in `{"max_retries_exceeded", "stuck"}` → return early with `verification_passed: False` (was: only checked `max_retries_exceeded` — `"stuck"` routed here by `route_after_run_tests` but was unhandled, so verify proceeded as if tests had passed). Found by: DeepSeek.
2. **[Pre-2.0 Fix]** Skip `pytest` entirely if no test files exist (`tests_dir` and `test_file` both missing). Was: ran `pytest` with no args → entire project test suite (could be thousands of tests, false failures, minutes of waste). Found by: DeepSeek.
3. Run `ruff check` for linting (advisory only — does not block commit)
4. **[Pre-2.0 Fix]** Scope ruff to `modified_files` only. Was: `ruff check workspace_root` (slow, noisy, false failures from pre-existing lint errors elsewhere in the workspace). Found by: DeepSeek, Qwen, Kimi (3 LLMs independently flagged this).
5. Run LLM verification (spec coverage + cleanliness) with hallucination guard (real pytest exit code overrides LLM claim)
6. Return verification results

**Output:** Partial dict with `lint_passed`, `lint_output`, `regression_passed`, `evidence_outputs`, `verification_passed`, `verification_notes`.

**[P1 #7] `lint_passed = None` when ruff is unavailable** (was `True` — missing ruff should not report as pass).

**Note:** `evidence_outputs` includes `regression: fresh_output[:2000]` which is the same as `tests`. Redundant — `# TODO(2.0):` collapse into a single `tests` entry.

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

**[v1.3] Scope note:** `node_git_commit` is LOCAL-ONLY (no push, no PR). All remote operations live in the next node, `node_publish`. See `workflows/autocode_impl/git_ops.py` (local) vs `workflows/autocode_impl/github_ops.py` (remote) for the split rationale.

**[v2.0] First node migrated to the accessor pattern:** `node_git_commit` now reads `state["branch"]` via `_get_vcs(state, "branch", "main")` instead of `state.get("branch", "main")`. This is the proof-of-concept migration for the sub-state / legacy-fallback accessor layer introduced in Phase 2 (see ARCHITECTURE.md § "[v2.0] Sub-state Architecture"). No behavior change — the accessor returns the same value as the legacy path until Phase 6 removes the legacy flat fields. `# TODO(2.0):` Migrate the remaining 16 nodes during Phase 3 / Phase 4.

---

### `node_publish(state)` — [v1.3] Phase 15: Push + PR + Optional Auto-merge

**Purpose:** Push the committed branch to the remote, open a PR, and optionally auto-merge it. Runs after `node_commit`, before `node_distill_memory`.

**Logic:**
1. Skip conditions (same as `node_commit`): `status` in `{needs_clarification, failed, skipped}` → return `{}`. `verification_passed` falsy → return `{}`. `dry_run` truthy → return `{"status": "dry_run"}`.
2. If none of the three publish flags are ON (`AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`), return `{}` (v1.2 behavior — no-op).
3. If `state["branch"]` is empty, return `{}` (nothing to push).
4. **Step 1 — Push:** If `cfg.autocode_push_on_commit`, call `_github_push(branch, tid)`. On failure, return early (`{"pushed": False, "pr_number": 0, "pr_url": ""}`) — do NOT proceed to PR creation.
   - If push flag is OFF but PR/merge flags are ON, return early with a `tracer.step` note (can't create a PR without pushing first).
5. **Step 2 — PR create:** If `cfg.autocode_open_pr` AND push succeeded, call `_github_pr_create(branch, title, body, tid)` with:
   - `title`: `f"autocode: {task[:60]}"`
   - `body`: built by `_build_pr_body(state)` — includes task, task_type, commit_sha, verification status, optional root_cause, optional swarm_verdict (with LOW-confidence warning if applicable).
   - On success, set `pr_number` and `pr_url` from the returned PR data dict. On failure, return early (do NOT proceed to auto-merge).
6. **Step 3 — Auto-merge:** If `cfg.autocode_auto_merge` AND a PR was created, call `_github_pr_merge(pr_number, tid)` with `merge_method="squash"` (hardcoded — see TODO below).

**Output:** Partial dict with `pushed: bool`, `pr_number: int`, `pr_url: str` (all three are always present when the node runs to completion; defaults are `False`/`0`/`""`).

**[v1.3] Config flags (all default OFF):**
- `AUTOCODE_PUSH_ON_COMMIT=1` — push the branch to `origin` after commit.
- `AUTOCODE_OPEN_PR=1` — open a PR from the branch to `main` after push.
- `AUTOCODE_AUTO_MERGE=1` — **DANGEROUS.** Auto-merge the PR via squash after creation.

**[v1.3] Graceful-skip behavior:** Every `github_ops.py` helper checks `_github_is_configured()` (wraps `tools.github_ops.client.is_configured()` in try/except) before any GitHub API call. If GitHub is not configured (`GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` missing), the helper logs a `tracer.step` and returns `False`/`None` — the workflow continues without crashing.

**[v1.3] Why `node_publish` is separate from `node_commit`:** See ARCHITECTURE.md § "[v1.3] Design Decision Notes" #1. Short version: commit failure ≠ publish failure; the publish step can be skipped in dry_run / failed / skipped states independently; the graph topology stays self-documenting.

**`# TODO(2.0):` items:**
- Split `node_publish` into separate `node_push` / `node_pr_create` / `node_pr_merge` for finer-grained routing and retry.
- Add retry logic for transient push / PR creation failures (currently terminal).
- Add `AUTOCODE_AUTO_MERGE_METHOD` config (squash / merge / rebase) — currently hardcoded to `squash`.
- Richer PR body (test results, diff summary, impact warnings) — currently minimal.

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
| `_get_tdd(state, key, default=None)` | `TDDState` | `state["tdd"]` dict | `test_code`, `test_results`, `tdd_status`, `tdd_iteration`, `debug_history` |
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

`# TODO(2.0):` The remaining 16 nodes still use the legacy `state.get(...)`
pattern. They will migrate during Phase 3 (node splits) and Phase 4 (debug
history). Phase 6 removes the legacy flat fields and the accessor fallback
branches.

### `debug_history` field — declared but not yet populated

The new `debug_history` field in `TDDState` is **declared in Phase 2 but not
populated by any node yet.** It is a placeholder for Phase 4 (#37 context
summarization):

- **Phase 4 will:** wire `node_systematic_debug` to append each iteration's
  `{root_cause, defense_notes, fix, test_output}` to `debug_history`, then add
  a `summarize_context` node before debug re-entry that compresses the history
  (likely via Chonkie `SentenceChunker` — see `docs/TOOLS.md` § "Chunking").
- **Until then:** `debug_history` is always empty. The accessor `_get_tdd(state,
  "debug_history", [])` returns `[]`. No node reads it. The field exists only
  so Phase 4 doesn't have to change `state.py` again.

`# TODO(2.0):` Phase 4 — populate `debug_history` in `node_systematic_debug`
and add the `summarize_context` node.

---

## 🔒 Security

*(Fill this section with relevant info from edits and refactors. Add security details as they are learned.)*

---

## 📝 Error Handling

*(Fill this section with relevant info from edits and refactors. Add error classification as it is learned.)*

---

*Last updated: 2026-07-11 (v2.0-alpha — 2.0 refactor Phase 1 + Phase 2: added `[v2.0]` note to `node_git_commit` documenting the `_get_vcs` accessor migration (proof-of-concept); new "[v2.0] State Accessors" section documenting the 8 accessor functions (`_get_plan`/`_get_tdd`/`_get_files`/`_get_impact`/`_get_debug`/`_get_verify`/`_get_vcs`/`_get_memory`) and the 8 sub-state TypedDicts; new `debug_history` field declared in `TDDState` (Phase 4 #37 placeholder — not yet populated); graph structure unchanged — 17 nodes. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history + 7-phase refactor progress, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules).*
