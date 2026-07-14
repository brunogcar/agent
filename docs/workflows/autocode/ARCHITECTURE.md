<- Back to [Autocode Overview](../AUTOCODE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `workflows/autocode.py` | `run_autocode_agent()` — main entry point |
| `workflows/autocode_impl/graph.py` | `build_graph()` — 28-node LangGraph StateGraph builder (25 active + 3 backward-compat wrappers registered but NOT wired). `WORKFLOW_METADATA["version"] == "2.0.5"` (Phase 4g review). |
| `workflows/autocode_impl/state.py` | `AutocodeState` TypedDict + 8 sub-state TypedDicts + 8 accessor functions. All sub-states populated as PRIMARY storage by `_default_state()` (legacy flat fields kept as mirrors for backward compat). |
| `workflows/autocode_impl/routes.py` | `route_after_classify()`, `route_after_write_files()`, `route_after_run_tests()`, `route_after_verify()` — conditional routing. **[Hardening P1.5]** short-circuits to `node_run_pytest` when `status=="error"`. |
| `workflows/autocode_impl/helpers.py` | `_call()`, `_extract_code()`, `_parse_json()`, `_files_context()` — shared helpers. `_call()` retries 2× with exponential backoff; **[Hardening P1.7]** backoff is interruptible via `threading.Event` so cancellation aborts retry sleep. |
| `workflows/autocode_impl/constants.py` | All SYSTEM prompts. `DEBUG_SYSTEM` is a 4-phase structured prompt (investigation → pattern → hypothesis → fix). `CODER_SYSTEM` includes the 7-rung Lazy Dev minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code). |
| `core/json_extract.py` | **[v2.0]** Consolidated JSON extraction utility. 3 functions: `extract_json`, `extract_json_array`, `extract_first_json`. Single source of truth for all LLM JSON parsing. |
| `workflows/autocode_impl/vcs_ops.py` | **[v2.0]** Unified VCS helper module. 3 sections: Local operations (`_git_commit`, `_git_create_branch`) / Remote operations (`_github_pull`, `_github_push`, `_github_pr_create`, `_github_pr_comment`, `_github_pr_merge`) / Swarm integration (`_swarm_debug_consensus`). |
| `workflows/autocode_impl/git_ops.py` | Thin re-export wrapper for `vcs_ops.py` Local operations (kept for backward compat). New code imports from `vcs_ops.py`. |
| `workflows/autocode_impl/github_ops.py` | Thin re-export wrapper for `vcs_ops.py` Remote + Swarm operations (kept for backward compat). New code imports from `vcs_ops.py`. |
| `workflows/autocode_impl/patch.py` | `apply_patch()`, `apply_patches()`, `extract_relevant_sections()` — patch application |
| ~~`workflows/autocode_impl/mermaid.py`~~ | DELETED in v1.4 — never called (`WORKFLOW_METADATA` serves the same purpose for MCP clients). |
| ~~`workflows/autocode_impl/test_mapper.py`~~ | DELETED in v1.4 — unused (analyze_impact imports from `core.kgraph.test_mapper`). |
| ~~`workflows/autocode_impl/test_runner.py`~~ | DELETED in v1.4 — unused (`node_run_tests` has its own test execution logic). |
| `workflows/autocode_impl/nodes/classify.py` | `node_classify_task()` — task classification. **[Hardening P1.6]** enforces JSON schema (`task_type` enum). |
| `workflows/autocode_impl/nodes/validate.py` | `node_validate_input()` — input validation |
| `workflows/autocode_impl/nodes/brainstorm.py` | `node_brainstorm()` — approach brainstorming. **[Hardening P1.10]** unconditionally initializes `files_update` before KG block (was using brittle `dir()` check). |
| `workflows/autocode_impl/nodes/plan.py` | `node_write_plan()` — plan generation |
| `workflows/autocode_impl/nodes/branch.py` | `node_git_branch()` — git branch creation |
| `workflows/autocode_impl/nodes/tests.py` | `node_write_tests()` — test generation |
| `workflows/autocode_impl/nodes/execute.py` | `node_execute_step()` — plan step execution. **[Hardening P2]** dead `json.loads(code)` fallback removed. |
| `workflows/autocode_impl/nodes/write_files.py` | **[v2.0]** BACKWARD-COMPAT WRAPPER — calls `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts`. Registered, NOT wired. |
| `workflows/autocode_impl/nodes/apply_patches.py` | **[v2.0]** Applies `str_replace` patches to existing files. Hosts `_is_path_safe()` (shared with `write_new_files.py`). **[Hardening P1.4]** uses `_parse_json` for markdown-fenced JSON. |
| `workflows/autocode_impl/nodes/write_new_files.py` | **[v2.0]** Writes new files / overwrites existing ones atomically. Builds `files_map` for `analyze_impact`. **[Hardening P1.4 + P1.8]** uses `_parse_json`; propagates new files into `modified_files`. |
| `workflows/autocode_impl/nodes/persist_artifacts.py` | **[v2.0]** Persists `test_autocode_feature.py` + `generated_code.json` + `debug_log.json` to `run_dir`. |
| `workflows/autocode_impl/nodes/run_tests.py` | `node_run_tests()` — test execution. **[Hardening P0.2]** marks last `debug_history` entry's `tests_passed=True`. |
| `workflows/autocode_impl/nodes/analyze_impact.py` | `node_analyze_impact()` — blast radius analysis. **[v2.0]** `_run_async()` simplified to `asyncio.run(coro)`. |
| `workflows/autocode_impl/nodes/debug.py` | `node_systematic_debug()` — 4-phase debug analysis. Accumulates `debug_history`. **[Hardening P0.1 + P1.9 + P2]** preserves TDD sub-state on writes; `blast_radius_note` precedes "Output JSON ONLY:"; consumes `debug_summary` when `debug_history` > 5 entries. |
| `workflows/autocode_impl/nodes/summarize_context.py` | **[v2.0]** `node_summarize_context(state)` compresses `debug_history` before re-entering the debug loop. Uses chonkie `SentenceChunker` (soft dep) with JSON-of-last-3-entries fallback. **[Hardening P0.1]** preserves TDD sub-state. |
| `workflows/autocode_impl/nodes/verify.py` | **[v2.0]** BACKWARD-COMPAT WRAPPER — calls `node_run_pytest` → `node_run_lint` → `node_llm_review` → `node_verify_decision`. Registered, NOT wired. |
| `workflows/autocode_impl/nodes/run_pytest.py` | **[v2.0]** Fresh pytest subprocess on autocode run directory. |
| `workflows/autocode_impl/nodes/run_lint.py` | **[v2.0]** `ruff check --select E,F --no-cache` scoped to `modified_files` only. |
| `workflows/autocode_impl/nodes/llm_review.py` | **[v2.0]** LLM spec coverage + cleanliness review. Only LLM-calling node in the verify chain. |
| `workflows/autocode_impl/nodes/verify_decision.py` | **[v2.0]** Composes results + hallucination guard (real pytest exit code overrides LLM claim) + max_retries/stuck early-exit. `route_after_verify` routes from this node. |
| `workflows/autocode_impl/nodes/commit.py` | `node_git_commit()` — git commit. **[v2.0]** First node migrated to the accessor pattern (`_get_vcs`). |
| `workflows/autocode_impl/nodes/publish.py` | **[v2.0]** BACKWARD-COMPAT WRAPPER — calls `node_push` → `node_create_pr` → `node_merge_pr`. Registered, NOT wired. |
| `workflows/autocode_impl/nodes/push.py` | **[v2.0]** Pushes branch to remote via `_github_push` (gated on `AUTOCODE_PUSH_ON_COMMIT`). |
| `workflows/autocode_impl/nodes/create_pr.py` | **[v2.0]** Opens PR via `_github_pr_create` (gated on `AUTOCODE_OPEN_PR`). Hosts `_build_pr_body(state)`. |
| `workflows/autocode_impl/nodes/merge_pr.py` | **[v2.0]** Auto-merges PR via `_github_pr_merge` (gated on `AUTOCODE_AUTO_MERGE`; terminal). |
| `workflows/autocode_impl/nodes/memory.py` | `node_distill_memory()` — procedural memory storage |
| `workflows/autocode_impl/nodes/create_skill.py` | `node_create_skill()` — skill creation (atomic write + AST validation) |
| `workflows/autocode_impl/nodes/report.py` | `node_report()` — report generation |
| `workflows/base.py` | `WorkflowState`, `node_step()`, `node_error()`, `node_done()` — shared infrastructure. `invoke_with_timeout()` calls `request_cancellation()` on timeout. **[Hardening P0.3]** surfaces graph exceptions as crashes (was misreporting as timeout). |
| `tools/agent.py` | `agent(action="dispatch", role="...")` — LLM calls |
| `tools/git.py` | `git(action="snapshot")`, `git(action="commit")` — git operations |
| `tools/python.py` | `python(code=...)` — sandboxed Python execution |
| `tools/memory.py` | `memory.recall()`, `memory.store_procedural()` — memory operations |
| `tools/notify.py` | `notify(action="notify", message=...)` — user notification |
| `tools/report.py` | `report(action="report", title=...)` — report generation |
| `core/config.py` | `cfg.autocode_graph_timeout`, `cfg.autocode_max_retries`, etc. — config (6 GitHub/Swarm flags default OFF) |
| `core/utils.py` | `compress_result()` — result compression |
| `tools/github.py` | `github(action="pull"|"push"|"pr_create"|"pr_comment"|"pr_merge")` — remote GitHub operations |
| `tools/swarm.py` | `swarm(action="consensus"|"vote")` — multi-model consultation |
| `tests/workflows/autocode/` | Per-concern test files + `conftest.py` (see Testing section below) |

---

## 🌳 Module Tree

```text
workflows/autocode.py
├── run_autocode_agent()              # Main entry point
│   ├── build_graph()                 # 28-node LangGraph StateGraph (25 active + 3 backward-compat wrappers)
│   │   ├── node_classify_task()      # Phase 1: Classify task type
│   │   ├── node_validate_input()     # Phase 2: Validate input
│   │   ├── node_brainstorm()         # Phase 3: Brainstorm approach
│   │   ├── node_write_plan()         # Phase 4: Generate plan
│   │   ├── node_git_branch()         # Phase 5: Create git branch
│   │   ├── node_write_tests()        # Phase 6: Generate tests (TDD)
│   │   ├── node_execute_step()       # Phase 7: Execute plan step
│   │   ├── node_apply_patches()      # Phase 8a: Apply str_replace patches
│   │   ├── node_write_new_files()    # Phase 8b: Write new/overwrite files + build files_map
│   │   ├── node_persist_artifacts()  # Phase 8c: Persist test file + gen code + debug log
│   │   ├── node_analyze_impact()     # Phase 9: Analyze blast radius
│   │   ├── node_run_tests()          # Phase 10: Run tests
│   │   ├── node_systematic_debug()   # Phase 11: 4-phase debug (loops back via summarize_context)
│   │   ├── node_summarize_context()  # Phase 11a: Compress debug_history before re-entering loop
│   │   ├── node_run_pytest()         # Phase 12a: Fresh pytest subprocess
│   │   ├── node_run_lint()           # Phase 12b: Ruff on modified_files only
│   │   ├── node_llm_review()         # Phase 12c: LLM spec + cleanliness review
│   │   ├── node_verify_decision()    # Phase 12d: Compose results + hallucination guard
│   │   ├── node_report()             # Phase 13: Generate report
│   │   ├── node_git_commit()         # Phase 14: Commit changes
│   │   ├── node_push()               # Phase 15a: Push branch
│   │   ├── node_create_pr()          # Phase 15b: Create PR
│   │   ├── node_merge_pr()           # Phase 15c: Auto-merge PR (terminal)
│   │   ├── node_distill_memory()     # Phase 16: Store procedural memory
│   │   └── node_create_skill()       # Phase 17: Create skill (if applicable)
│   │   # Backward-compat wrappers (registered but NOT wired):
│   │   # ├── node_write_files()      #   wrapper → apply_patches + write_new_files + persist_artifacts
│   │   # ├── node_verify()           #   wrapper → run_pytest + run_lint + llm_review + verify_decision
│   │   # └── node_publish()          #   wrapper → push + create_pr + merge_pr
│   └── tracer.finish()               # Mark trace complete
```

The 3 backward-compat wrappers (`node_write_files`, `node_verify`, `node_publish`) are kept for `import`-compatibility (tests import them directly). They are registered via `add_node(...)` but NOT wired — no edges in or out. Excluded from `WORKFLOW_METADATA["nodes"]` so MCP clients render only the 27 active nodes. Removal deferred to post-2.0 (`# TODO(2.0-post):`).

---

## 🔀 Dispatch Flow

```mermaid
graph TD
    A["node_classify_task<br/>Phase 1: Classify"] --> B["node_validate_input<br/>Phase 2: Validate"]
    B --> C["node_brainstorm<br/>Phase 3: Brainstorm"]
    C --> D["node_write_plan<br/>Phase 4: Plan"]
    D --> E["node_git_branch<br/>Phase 5: Branch"]
    E --> F["node_write_tests<br/>Phase 6: Tests"]
    F --> G["node_execute_step<br/>Phase 7: Execute"]
    G --> AP["node_apply_patches<br/>Phase 8a: Patches"]
    AP --> WNF["node_write_new_files<br/>Phase 8b: New files + files_map"]
    WNF --> PA["node_persist_artifacts<br/>Phase 8c: Persist artifacts"]
    PA --> RT1{"route_after_write_files"}
    RT1 -->|fix/refactor/feature/audit/edit| I["node_analyze_impact<br/>Phase 9: Impact"]
    RT1 -->|other| RP["node_run_pytest<br/>Phase 12a: Fresh pytest"]
    I --> J["node_run_tests<br/>Phase 10: Run Tests"]
    J --> RT2{"route_after_run_tests<br/>Conditional"}
    RT2 -->|pass / max_retries| RP
    RT2 -->|fail| M["node_systematic_debug<br/>Phase 11: 4-phase Debug"]
    M --> SC["node_summarize_context<br/>Phase 11a: Compress debug_history"]
    SC --> AP
    RP --> RL["node_run_lint<br/>Phase 12b: Ruff on modified_files"]
    RL --> LR["node_llm_review<br/>Phase 12c: LLM spec review"]
    LR --> VD["node_verify_decision<br/>Phase 12d: Compose + hallucination guard"]
    VD --> RT3{"route_after_verify"}
    RT3 -->|verification_passed| O["node_report<br/>Phase 13: Report"]
    RT3 -->|failed| S["END<br/>Failed"]
    O --> P["node_git_commit<br/>Phase 14: Commit"]
    P --> PU["node_push<br/>Phase 15a: Push"]
    PU --> CPR["node_create_pr<br/>Phase 15b: Create PR"]
    CPR --> MPR["node_merge_pr<br/>Phase 15c: Auto-merge (terminal)"]
    MPR --> Q["node_distill_memory<br/>Phase 16: Memory"]
    Q --> R["node_create_skill<br/>Phase 17: Skill"]
    R --> S["END<br/>Success"]
```

**Conditional routes:**
- `route_after_classify` — `feature`/`fix`/`refactor`/`edit`/`audit` → `node_brainstorm`; `create_skill` → `node_create_skill` (bypasses TDD).
- `route_after_write_files` — `fix`/`refactor`/`improve`/`feature`/`audit`/`edit` → `node_analyze_impact`; other → `node_run_pytest`. **[Hardening P1.5]** short-circuits to `node_run_pytest` when `status=="error"`.
- `route_after_run_tests` — `pass` → `node_run_pytest`; `fail` → `node_systematic_debug`; `stuck` → `node_run_pytest` (skips doomed debug). **[Hardening P1.5]** short-circuits on `status=="error"`.
- `route_after_verify` — `pass` → `node_report`; `fail` → `node_systematic_debug` (re-enter debug loop).

**Debug loop:** `node_systematic_debug` → `node_summarize_context` → `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` → `node_analyze_impact` → `node_run_tests` → (back to `node_systematic_debug` until tests pass, `MAX_RETRIES` exceeded, `tdd_status="stuck"`, OR the architecture-question exit fires — 3+ consecutive `tests_passed=False`).

---

## 💡 Key Design Decisions

- **28-node LangGraph StateGraph** — 25 active nodes + 3 backward-compat wrappers (registered, NOT wired) + `node_summarize_context` (Phase 4, debug-loop compression). The 3 wrappers preserve `import`-compatibility for external callers + tests; they are excluded from `WORKFLOW_METADATA["nodes"]` so MCP clients render only the 27 active-node entries.
- **Mode-driven** — The task type (`fix_error`, `improve`, `add_feature`, `create_skill`, `unclear`) determines the workflow path. `node_classify_task` uses the Router LLM to classify.
- **TDD-first** — For `add_feature` and `improve` modes, tests are generated before implementation.
- **Iterative debug loop** — `node_systematic_debug` accumulates `debug_history` across iterations (closes the #37 prerequisite); `node_summarize_context` compresses it before re-entering the loop. Last 5 entries injected into the LLM user prompt under a `PRIOR DEBUG ATTEMPTS (do NOT repeat these)` block. New architecture-question exit fires on 3+ consecutive `tests_passed=False` → `tdd_status="max_retries_exceeded"` + procedural memory store (different from #39 stuck detection — fires on DIFFERENT errors each iteration, suggesting architectural bug).
- **Impact analysis** — `node_analyze_impact` analyzes blast radius using the dependency graph. Prevents unintended side effects.
- **Git integration** — `node_git_branch` creates a new branch (optionally pulls first via `AUTOCODE_PULL_BEFORE_BRANCH`); `node_git_commit` commits changes with a descriptive message. `node_write_plan` appends `trace_id` suffix (`autocode/{slug}-{tid_suffix}`) for branch-name uniqueness.
- **GitHub integration** — `node_push` → `node_create_pr` → `node_merge_pr` (all gated on config flags + `is_configured()`, all default OFF). With all flags OFF, the 3 nodes are no-ops — autocode behaves identically to a local-only workflow.
- **Swarm debug integration** — `node_systematic_debug` optionally uses swarm (2-run pattern: `consensus` → `vote`). Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split). Non-blocking — fix is ALWAYS applied regardless of confidence. LOW confidence surfaces as a PR comment (if `AUTOCODE_DEBUG_COMMENT_PR=1`), not as a workflow block.
- **Memory integration** — `node_distill_memory` stores procedural knowledge for future recall. Non-fatal — code is already committed by the time distill runs.
- **Skill creation** — `node_create_skill` creates a reusable skill file. Atomic write (`tempfile` + `os.replace`) + AST validation.
- **Filelock + atomic writes** — `node_write_new_files` uses `FileLock` and atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) to prevent race conditions and data corruption.
- **Lazy Dev / YAGNI Ladder** — `CODER_SYSTEM` includes the 7-rung minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code). `DEBUG_SYSTEM` Phase 4 ("fix") also applies the ladder. `ponytail:` comment convention marks deliberate simplifications with known ceilings.
- **Result compression** — The final result is compressed via `compress_result()` before being returned.

### `node_publish` is a separate node — NOT folded into `node_commit`
`node_commit` is local-only and always runs (TDD code is committed even on failure). `node_publish` (now `node_push` + `node_create_pr` + `node_merge_pr`) is opt-in (config flags), remote-touching, and may fail (network, GitHub API, permissions) — its failure must NOT flip a successful workflow to failed.

### `_is_path_safe()` guards LLM-generated paths
The `node_validate_input` path traversal check only covers user-supplied paths. LLM-generated paths (`patches[].path`, `new_files{}` keys) are validated via `_is_path_safe(base_path, rel_path) -> bool` in `apply_patches.py` (imported by `write_new_files.py`) — uses `Path.resolve().is_relative_to()` to verify the resolved target stays inside `base_path`.

### `_call()` retries 2× with exponential backoff + interruptible sleep
`_call(role, system, user, ..., retries=2)` loops `retries + 1` times, sleeping `2 ** attempt` seconds between attempts. **[Hardening P1.7]** sleep uses `threading.Event.wait(timeout=...)` so `request_cancellation()` from a timeout aborts the backoff immediately (was `time.sleep(...)` — uninterruptible, blocked the timeout).

### 6 v1.3 config flags default OFF
`AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`. With all flags OFF, autocode behaves identically to v1.2 (local-only, single-LLM debug).

### Dead-code deletions — do NOT re-add
- `node_write_files_with_flag_reset` — was registered but never wired; reset a non-existent `step_attempt` field.
- `route_after_analyze_impact` — was a conditional router that ALWAYS returned `"node_run_tests"`. Replaced with a direct edge.
- `"node_brainstorm"` mapping in `route_after_classify` — never returned; removed from conditional_edges.
- `mermaid.py`, `test_mapper.py`, `test_runner.py` — never called.

---

## 🧭 [v2.0] Sub-state Architecture

The v2.0 refactor migrated autocode from a flat ~35-field state dict to 8 focused sub-state TypedDicts behind a backward-compatible accessor layer. All 7 phases ✅ COMPLETE.

> **⚠️ [v2.0.5] Migration status: only `tdd` is fully migrated.** `_default_state()`
> populates all 8 sub-states as PRIMARY storage, but nodes only WRITE to the `tdd`
> sub-state (via read-modify-write). The other 7 sub-states hold stale defaults
> because nodes still write to flat fields (`branch`, `commit_sha`, `modified_files`,
> etc.). The accessors read sub-state first — so `_get_vcs(state, "branch", "main")`
> returns `""` (the stale default), not the actual branch name. **[v2.0.5 P1-1]**
> `node_commit` was reverted to direct `state.get("branch")` reads after this
> split-brain bug was found. Only `_get_tdd` is safe to use today (see INSTRUCTIONS.md
> NEVER DO #33). Full migration of the remaining 7 sub-states is the v2.x → v3.0
> roadmap (see CHANGELOG Future Tracks).

Legacy flat fields remain as mirrors for backward compat with unmigrated nodes + tests. Legacy field removal is deferred to v3.0 (`# TODO(v3.0):`).

### The 8 sub-state TypedDicts

| Sub-state | TypedDict | Representative fields |
|-----------|-----------|----------------------|
| Plan | `PlanState` | `task_type`, `plan`, `branch`, `current_step` |
| TDD | `TDDState` | `test_code`, `test_results`, `tdd_status`, `tdd_iteration`, `debug_history`, `debug_summary` |
| Files | `FilesState` | `files`, `modified_files`, `written_files`, `files_map` |
| Impact | `ImpactState` | `impact_warnings`, `blast_radius_note` |
| Debug | `DebugState` | `root_cause`, `defense_notes`, `tdd_source_code`, `debug_notes`, `swarm_verdict` |
| Verify | `VerifyState` | `lint_passed`, `lint_output`, `regression_passed`, `evidence_outputs`, `verification_passed`, `verification_notes` |
| VCS | `VCSState` | `branch`, `commit_sha`, `pushed`, `pr_number`, `pr_url` |
| Memory | `MemoryState` | `brainstorm`, `skill_path`, `skill_created` |

### The 8 backward-compat accessor functions

Each accessor reads from the corresponding sub-state dict if present, else falls back to the legacy flat field.

```python
# Signature pattern (state.py)
def _get_vcs(state: dict, key: str, default=None):
    """Read `key` from state["vcs"] if present, else fall back to state[key]."""
    vcs = state.get("vcs")
    if isinstance(vcs, dict) and key in vcs:
        return vcs[key]
    return state.get(key, default)
```

The 8 accessors: `_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`.

**Why an accessor layer:** No big-bang refactor — migrate one node at a time. Legacy fallback buys time until Phase 6 makes sub-states PRIMARY. `node_systematic_debug` + `node_summarize_context` migrated to accessors in Phase 4 (these are the only 2 nodes that write to sub-state via read-modify-write, so `_get_tdd` is safe). `node_git_commit` was migrated as a proof-of-concept in Phase 1, **[v2.0.5] but the `_get_vcs` call was broken (split-brain) and has been reverted** — see CHANGELOG v2.0.5 P1-1. Remaining nodes still read legacy flat fields directly; full migration is the v2.x → v3.0 roadmap.

### Cancellation flag

Phase 1 added a module-level cancellation flag to `helpers.py`:

```python
def request_cancellation() -> None: ...
def clear_cancellation() -> None: ...
def is_cancellation_requested() -> bool: ...
```

`_call()` checks `is_cancellation_requested()` before each retry. `invoke_with_timeout()` (in `base.py`) calls `clear_cancellation()` at start and `request_cancellation()` on timeout — the in-flight `_call()` retries notice and abort instead of sleeping through exponential backoff. **[Hardening P0.3]** graph exceptions in the daemon thread are now surfaced as `"Autocode graph crashed: <exception>"` (was swallowed and misreported as timeout). Full process-level termination deferred to post-2.0 (`# TODO(2.0-post):`).

---

## 🧪 Testing

```powershell
# Run autocode tests
.\venv\Scripts\python tests/workflows/autocode/ -W error --tb=short -v
```

> **Note:** Ensure `pytest` resolves to your venv. If not, use `python -m pytest` or the full venv path.

**Mock strategy:**
- Patch `llm.complete(role="router")` for classification
- Patch `llm.complete(role="planner")` for planning and brainstorming
- Patch `llm.complete(role="executor")` for code generation and debug
- Patch `llm.complete(role="test")` for test generation
- Patch `git(action="snapshot")` and `git(action="commit")` for git operations
- Patch `python(code=...)` for test execution
- Patch `memory.recall()` and `memory.store_procedural()` for memory operations
- Patch `report(action="report")` for report generation
- Patch `notify(action="notify")` for notification

**Test counts:** 121/121 autocode tests pass after v2.0.1 hardening.

**Test layout (per-concern, one concern per file):**
```text
tests/workflows/autocode/
├── conftest.py            # base_state + temp_workspace fixtures
├── test_graph.py          # topology + WORKFLOW_METADATA + singleton + state schema + partial-dict
├── test_routes.py         # all 5 route_after_* functions + #39 stuck routing
├── test_facade.py         # imports + run_workflow + #44 artifacts + #46 git-diff + #47 dry-run + distill
├── test_execute.py        # node_execute_step + node_write_files + .bak checks
├── test_run_tests.py      # #39 stuck detection + file-existence + budget wiring
├── test_debug.py          # debug loop routing + JSON parsing + max-retries
├── test_verify.py         # node_verify + lint + commit + defense_notes
├── test_branch.py         # node_git_branch + git scoping + dry-run + no-snapshot
├── test_create_skill.py   # name sanitization + syntax validation + skill_created flag
├── test_helpers.py        # path helpers + patch + protected files + path traversal
├── test_safety.py         # dry-run mode + protected files + memory callbacks + TDD loop + dead routes
└── test_analyze_impact.py # AST parser
```

---

*Last updated: 2026-07-11 (v2.0.1 — hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
