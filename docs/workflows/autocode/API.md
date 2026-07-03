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
2. Build prompt with goal, task type, and context
3. Call `llm.complete(role="planner", ...)` for brainstorming
4. Parse JSON response for approach

**Output:** Partial dict with `brainstorm` (approach text) and `files` (updated with KG files).

**Critical bug:** KG files are lost. The code merges `kg_files` into `files_update` but then stores `state["files"]` (original) instead of `files_update`:
```python
if kg_files:
    files_update = {**kg_files, **state.get("files", {})}
    # ... but then:
    updates["files"] = state["files"]  # BUG: stores original, not merged!
```

---

### `node_write_plan(state)` — Phase 4: Generate Plan

**Purpose:** Generate a step-by-step plan using the Planner LLM.

**Logic:**
1. Build prompt with goal, task type, and context
2. Call `llm.complete(role="planner", ...)` for planning
3. Parse JSON response for plan steps

**Output:** Partial dict with `plan` (list of step dicts) and `branch` (branch name).

**Note:** Fallback plan has 3 steps: write_tests → implement → verify. This is used when LLM planning fails.

**Note:** `slug` generation may produce empty string if `task[:40]` is all non-alphanumeric. This creates invalid branch name `"autocode/"`.

---

### `node_git_branch(state)` — Phase 5: Create Git Branch

**Purpose:** Create a git branch for the changes.

**Logic:**
1. Take git snapshot
2. Create branch (if specified)

**Output:** Empty dict (side effects only).

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

**Bug:** Uses `state.get('files_context', '')` but `files_context` doesn't exist in `AutocodeState`. Should use `_files_context(state.get('files', {}))`.

**Bug:** `modified_files` derivation from JSON may fail on non-JSON code. If `code` is not valid JSON, `json.loads(code)` fails and `modified_files` is `[]`.

---

### `node_write_files(state)` — Phase 8: Write/Modify Files

**Purpose:** Write or modify files on disk.

**Logic:**
1. For each modified file:
   - Apply patch (if patch provided)
   - Write new file (if new file)
   - Update existing file (if content provided)
2. Use `FileLock` for atomic writes
3. Use `tempfile.NamedTemporaryFile` + `os.replace` for atomicity

**Output:** Partial dict with `written_files`, `test_files`, `autocode_run_path`.

**Critical bug:** `.bak` files are created, violating user rule.

**Critical bug:** If `test_code` is missing but `tdd_source_code` exists, `run_dir` is undefined when persisting generated code. NameError.

**Bug:** `node_write_files` doesn't return `status` on error. If JSON parse fails, returns `{}` (empty dict). Workflow continues as if nothing happened.

**Bug:** `FileLock` timeout is 10s but no retry logic. If lock is held by another process, it times out and skips the write.

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

**Bug:** `run_tests_on_disk` in `nodes/run_tests.py` has different signature from `test_runner.py`. Same name, different signatures. Confusing.

---

### `node_systematic_debug(state)` — Phase 11: Debug Failures

**Purpose:** Debug test failures.

**Logic:**
1. Build prompt with test output and context
2. Call `llm.complete(role="executor", ...)` for debug analysis
3. Parse JSON response for root cause and fix

**Output:** Partial dict with `root_cause`, `defense_notes`, `suggested_fix`, `tdd_source_code`.

**Note:** `memory.store()` is called without `await` but `memory.store()` is sync. This is correct.

**Note:** `blast_radius_note` is constructed but used in the system prompt. Correct.

---

### `node_write_files_with_flag_reset(state)` — Phase 12: Retry with Fix

**Purpose:** Write the fix after debug analysis.

**Logic:**
1. Call `node_write_files(state)` to apply the fix
2. Reset `step_attempt` to 0

**Output:** Partial dict from `node_write_files` with `step_attempt: 0`.

**Note:** This is a thin wrapper around `node_write_files` that resets the retry counter.

---

### `node_verify(state)` — Phase 13: Verify Changes

**Purpose:** Verify the changes with linting and regression tests.

**Logic:**
1. Run `ruff check` for linting
2. Run regression tests (if applicable)
3. Return verification results

**Output:** Partial dict with `lint_passed`, `lint_output`, `regression_passed`, `evidence_outputs`.

**Bug:** `lint_passed = True` when ruff is not available. Should be `False` or `None`.

**Bug:** `evidence_outputs` includes `regression: fresh_output[:2000]` which is the same as `tests`. Redundant.

---

### `node_report(state)` — Phase 14: Generate Report

**Purpose:** Generate a structured report with the final result.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with result and metadata
2. Return the report

**Output:** Empty dict (side effects only).

**Bug:** Type annotation says `AutocodeState` but returns `{}`.

**Bug:** `modified_files` uses `state.get("files_map", {}).keys()` but `files_map` is always empty.

---

### `node_git_commit(state)` — Phase 15: Commit Changes

**Purpose:** Commit the changes to git.

**Logic:**
1. Generate commit message
2. Call `git(action="commit", message=..., root=...)`
3. Return commit SHA

**Output:** Partial dict with `commit_sha`, `status`, `result`.

**Bug:** `result_lines` includes `state.get("defense_note")` but the field is `defense_notes` (plural). Always empty.

**Bug:** `status` is set to `"done"` regardless of whether commit succeeded. If `_git_commit` returns `None` (no changes), `status` is still `"done"`.

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
2. Write to `cfg.agent_root / "skills" / f"{skill_name}.py"`

**Output:** Partial dict with `skill_path`, `status`, `result`, `error`.

**Bug:** `skill_path` is `cfg.agent_root / "skills" / f"{skill_name}.py"` but should use `project_root` or `workspace_root` for non-agent projects.

**Bug:** No validation that `skill_name` is a valid filename. If it contains `/` or `\`, path traversal may escape `skills/`.

**Bug:** `skill_file_content` is written without checking if it's valid Python. No syntax check.

**Bug:** `skill_created` is never set in state. `autocode.py` checks for it but it's always missing.

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

## 🔒 Security

*(Fill this section with relevant info from edits and refactors. Add security details as they are learned.)*

---

## 📝 Error Handling

*(Fill this section with relevant info from edits and refactors. Add error classification as it is learned.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
