<- Back to [Autocode Overview](../AUTOCODE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `workflows/autocode.py` | Exports `build_graph`, `get_graph`, `WORKFLOW_METADATA`, `AutocodeState`, `_default_state`, `_shape_artifacts`, `_resolve_files_input`. Main entry: `run_workflow(workflow_type="autocode", goal="...", **kwargs)` in `workflows/base.py` → delegates to `invoke_with_timeout()` in `workflows/autocode_impl/graph.py`. |
| `workflows/autocode_impl/graph.py` | `build_graph()` — 30-node LangGraph StateGraph builder (26 active + 3 backward-compat wrappers + 1 HiTL gate). `WORKFLOW_METADATA["version"] == "3.6"`. `invoke_with_timeout(initial_state)` — wraps `graph.invoke()` with `threading.Thread.join(timeout=...)` + cancellation-flag signaling; supports adaptive per-task-type timeouts via `AUTOCODE_ADAPTIVE_TIMEOUT=1`. `get_graph()` singleton guarded by `threading.Lock`. Calls `_cleanup_old_autocode_runs()` at start. **[v3.6]** `invoke_with_timeout()` calls `set_graph_start_time()` to anchor the deadline for `_remaining_timeout()`. |
| `workflows/autocode_impl/state.py` | `AutocodeState` TypedDict + 8 sub-state TypedDicts + 8 accessor functions. Sub-states are the PRIMARY (and ONLY) storage — legacy flat-field mirrors removed. 13 ephemeral flat fields explicitly declared. |
| `workflows/autocode_impl/routes.py` | `route_after_classify()`, `route_after_write_files()`, `route_after_run_tests()`, `route_after_verify()`, `route_after_swarm_fallback()`, `route_after_hitl_gate()` — conditional routing. Short-circuits to `node_run_pytest` when `status=="error"`. |
| `workflows/autocode_impl/helpers.py` | `_call()`, `_extract_code()`, `_parse_json()`, `_files_context()`, `_should_skip_node()`, `_blast_radius_warning()`, `_get_autocode_run_path()`, `_cleanup_old_autocode_runs()` — shared helpers. `_call()` retries 2× with interruptible exponential backoff. **[v3.6]** Also hosts `set_graph_start_time()`, `_remaining_timeout(default)`, `_cancelled()` for cancellation-aware subprocess calls. |
| `workflows/autocode_impl/constants.py` | All SYSTEM prompts. `DEBUG_SYSTEM` = 4-phase structured prompt (investigation → pattern → hypothesis → fix). `CODER_SYSTEM` includes the 7-rung Lazy Dev minimization ladder. `PARALLEL_HYPOTHESES_SYSTEM` + `SUBAGENT_VALIDATE_SYSTEM` (v3.5 F1). |
| `core/json_extract.py` | Consolidated JSON extraction utility. 3 functions: `extract_json`, `extract_json_array`, `extract_first_json`. |
| `workflows/autocode_impl/vcs_ops.py` | Unified VCS helper module. 3 sections: Local (`_git_commit`, `_git_create_branch`) / Remote (`_github_pull`, `_github_push`, `_github_pr_create`, `_github_pr_comment`, `_github_pr_merge`) / Swarm (`_swarm_debug_consensus`). |
| `workflows/autocode_impl/git_ops.py` + `github_ops.py` | Thin re-export wrappers for `vcs_ops.py` (kept for backward compat). New code imports from `vcs_ops.py`. |
| `workflows/autocode_impl/patch.py` | `apply_patch()`, `apply_patches()`, `extract_relevant_sections()` — patch application. |
| ~~`mermaid.py` / `test_mapper.py` / `test_runner.py`~~ | DELETED in v1.4 — never called. `/autocode/graph` HTTP endpoint in `core/gateway_backend/routes/metrics.py` also removed. |
| `nodes/classify.py` | `node_classify_task()` — task classification (JSON-schema enforced `task_type` enum). |
| `nodes/validate.py` | `node_validate_input()` — input validation + #42 goal sanitization (max 2000 chars + strip control chars). |
| `nodes/brainstorm.py` | `node_brainstorm()` — approach brainstorming. Merges KG files BEFORE LLM call. |
| `nodes/plan.py` | `node_write_plan()` — plan generation. Branch name with `trace_id` suffix. Uses `_blast_radius_warning()` helper (lazy `kgraph` import). |
| `nodes/branch.py` | `node_git_branch()` — git branch creation. |
| `nodes/tests.py` | `node_write_tests()` — test generation. Writes `test_code` as `list[str]`. |
| `nodes/execute.py` | `node_execute_step()` — plan step execution. Uses `_parse_json()` for `modified_files`. |
| `nodes/write_files.py` | **BACKWARD-COMPAT WRAPPER** — calls `apply_patches` → `write_new_files` → `persist_artifacts`. Registered, NOT wired. |
| `nodes/apply_patches.py` | Applies `str_replace` patches. Hosts `_is_path_safe()`. `dry_run` runs validation. |
| `nodes/write_new_files.py` | Writes new files atomically (`tempfile` + `os.replace` + `FileLock`). Builds `files_map`. |
| `nodes/persist_artifacts.py` | Persists test file + generated code + debug log to `run_dir`. |
| `nodes/run_tests.py` | `node_run_tests()` — test execution. **[v3.6]** Cancellation-aware subprocess (pre-check + `_remaining_timeout()` + post-check). |
| `nodes/swarm_fallback.py` | `node_swarm_fallback()` (v3.1) — escalates to `_swarm_debug_consensus` when debug retries exhausted. HIGH → reset `tdd_status`; LOW/unavailable → `status="failed"`. |
| `nodes/analyze_impact.py` | `node_analyze_impact()` — blast radius analysis. `_run_async()` = `asyncio.run(coro)`. |
| `nodes/debug.py` | `node_systematic_debug()` — 4-phase debug. Accumulates `debug_history`. Hosts `_parallel_subagent_debug()` (v3.5 F1). Uses `_blast_radius_warning()` (lazy `kgraph` import). |
| `nodes/summarize_context.py` | `node_summarize_context()` — compresses `debug_history` via chonkie `SentenceChunker` (soft dep). |
| `nodes/verify.py` | **BACKWARD-COMPAT WRAPPER** — calls `run_pytest` → `run_lint` → `llm_review` → `verify_decision`. Registered, NOT wired. |
| `nodes/run_pytest.py` | Fresh pytest subprocess. **[v3.1]** `ruff --select E999` syntax pre-check. **[v3.6]** Cancellation-aware subprocess. |
| `nodes/run_lint.py` | `ruff check --select E,F --no-cache` scoped to `modified_files`. **[v3.6]** Cancellation-aware subprocess. |
| `nodes/llm_review.py` | LLM spec coverage + cleanliness review. Only LLM-calling node in verify chain. Injects `debug_summary` when `debug_history` > 5. Handles `test_code` as `list[str]`. |
| `nodes/verify_decision.py` | Composes results + hallucination guard + max_retries/stuck early-exit. |
| `nodes/commit.py` | `node_git_commit()` — git commit. Reads branch via `_get_vcs` accessor. |
| `nodes/publish.py` | **BACKWARD-COMPAT WRAPPER** — calls `push` → `create_pr` → `merge_pr`. Registered, NOT wired. |
| `nodes/push.py` / `create_pr.py` / `merge_pr.py` | Push branch / create PR / auto-merge PR (all gated on config flags + `is_configured()`, default OFF). |
| `nodes/memory.py` | `node_distill_memory()` — procedural memory storage (non-fatal). |
| `nodes/create_skill.py` | `node_create_skill()` — skill creation (atomic write + AST validation + importlib smoke-test + git commit + empty-file rejection with fallback keys). HiTL check at top. |
| `nodes/report.py` | `node_report()` — report generation. |
| `nodes/hitl_gate.py` | `node_hitl_gate()` (v3.4) — opt-in HiTL approval gate between `node_report` and `node_commit`. Async-checkpoint-resume pattern. |
| `workflows/base.py` | `WorkflowState`, `node_step()`, `node_error()`, `node_done()`, `run_workflow()` — shared infrastructure. `run_workflow()` delegates to `invoke_with_timeout()`. Surfaces graph exceptions as crashes (Hardening P0.3). |
| `tools/agent.py` / `git.py` / `python.py` / `memory.py` / `notify.py` / `report.py` / `github.py` / `swarm.py` | Public tool facades (LLM calls, git operations, sandboxed Python, memory ops, notifications, reports, GitHub ops, swarm consensus). |
| `core/config.py` | `cfg.autocode_graph_timeout`, `cfg.autocode_max_retries`, `cfg.autocode_adaptive_timeout`, `cfg.sandbox_timeout`, 9 GitHub/Swarm/Subagent/HiTL flags (all default OFF). |
| `tests/workflows/autocode/` | Per-concern test files + `conftest.py` (see Testing section below). |


---

## 🌳 Module Tree

```text
workflows/base.py
└── run_workflow(workflow_type="autocode", goal="...", **kwargs)   # Main entry point (v3.1.2 #34 — legacy facade shim removed)
    ├── invoke_with_timeout(initial_state)     # in workflows/autocode_impl/graph.py (NOT base.py)
    │   ├── build_graph()                       # 29-node LangGraph StateGraph (26 active + 3 backward-compat wrappers)
    │   │   ├── node_classify_task()            # Phase 1: Classify task type
    │   │   ├── node_validate_input()           # Phase 2: Validate input + sanitize task (v3.1: max 2000 chars + strip control chars)
    │   │   ├── node_brainstorm()               # Phase 3: Brainstorm approach
    │   │   ├── node_write_plan()               # Phase 4: Generate plan
    │   │   ├── node_git_branch()               # Phase 5: Create git branch
    │   │   ├── node_write_tests()              # Phase 6: Generate tests (TDD)
    │   │   ├── node_execute_step()             # Phase 7: Execute plan step
    │   │   ├── node_apply_patches()            # Phase 8a: Apply str_replace patches
    │   │   ├── node_write_new_files()          # Phase 8b: Write new/overwrite files + build files_map
    │   │   ├── node_persist_artifacts()        # Phase 8c: Persist test file + gen code + debug log
    │   │   ├── node_analyze_impact()           # Phase 9: Analyze blast radius
    │   │   ├── node_run_tests()                # Phase 10: Run tests (3-way conditional out: verify / debug / swarm_fallback)
    │   │   ├── node_swarm_fallback()           # Phase 11b: [v3.1] Swarm consensus when debug exhausted (HIGH → debug, LOW → verify)
    │   │   ├── node_systematic_debug()         # Phase 11: 4-phase debug (loops back via summarize_context)
    │   │   ├── node_summarize_context()        # Phase 11a: Compress debug_history before re-entering loop
    │   │   ├── node_run_pytest()               # Phase 12a: Fresh pytest subprocess (v3.1: ruff E999 pre-check)
    │   │   ├── node_run_lint()                 # Phase 12b: Ruff on modified_files only
    │   │   ├── node_llm_review()               # Phase 12c: LLM spec + cleanliness review (v3.1: debug_summary injection)
    │   │   ├── node_verify_decision()          # Phase 12d: Compose results + hallucination guard
    │   │   ├── node_report()                   # Phase 13: Generate report
    │   │   ├── node_git_commit()               # Phase 14: Commit changes
    │   │   ├── node_push()                     # Phase 15a: Push branch
    │   │   ├── node_create_pr()                # Phase 15b: Create PR
    │   │   ├── node_merge_pr()                 # Phase 15c: Auto-merge PR (terminal)
    │   │   ├── node_distill_memory()           # Phase 16: Store procedural memory
    │   │   └── node_create_skill()             # Phase 17: Create skill (if applicable) — v3.1.2: importlib smoke-test + git commit
    │   │   # Backward-compat wrappers (registered but NOT wired):
    │   │   # ├── node_write_files()            #   wrapper → apply_patches + write_new_files + persist_artifacts
    │   │   # ├── node_verify()                 #   wrapper → run_pytest + run_lint + llm_review + verify_decision
    │   │   # └── node_publish()                #   wrapper → push + create_pr + merge_pr
    │   └── tracer.finish()                      # Mark trace complete
└── workflows/autocode.py                         # Exports: build_graph, get_graph, WORKFLOW_METADATA, _shape_artifacts, _resolve_files_input
                                                  # (legacy facade shim REMOVED in v3.1.2 #34)
```

The 3 backward-compat wrappers (`node_write_files`, `node_verify`, `node_publish`) are kept for `import`-compatibility (tests import them directly). They are registered via `add_node(...)` but NOT wired — no edges in or out. Excluded from `WORKFLOW_METADATA["nodes"]` so MCP clients render only the 28 active nodes. Removal deferred to post-2.0 (`# TODO(2.0-post):`).

---

## 🔀 Dispatch Flow

```mermaid
graph TD
    A["node_classify_task<br/>Phase 1: Classify"] --> B["node_validate_input<br/>Phase 2: Validate (v3.1: sanitize task)"]
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
    RT1 -->|other| RP["node_run_pytest<br/>Phase 12a: Fresh pytest (v3.1: ruff pre-check)"]
    I --> J["node_run_tests<br/>Phase 10: Run Tests"]
    J --> RT2{"route_after_run_tests<br/>3-way conditional"}
    RT2 -->|pass / max_retries (flag OFF) / stuck| RP
    RT2 -->|fail| M["node_systematic_debug<br/>Phase 11: 4-phase Debug"]
    RT2 -->|max_retries + AUTOCODE_SWARM_DEBUG_FALLBACK=1| SF["node_swarm_fallback<br/>Phase 11b: Swarm consensus (v3.1)"]
    SF --> SF2{"swarm verdict"}
    SF2 -->|HIGH confidence| M
    SF2 -->|LOW/unavailable| RP
    M --> SC["node_summarize_context<br/>Phase 11a: Compress debug_history"]
    SC --> AP
    RP --> RL["node_run_lint<br/>Phase 12b: Ruff on modified_files"]
    RL --> LR["node_llm_review<br/>Phase 12c: LLM spec review (v3.1: debug_summary injection)"]
    LR --> VD["node_verify_decision<br/>Phase 12d: Compose + hallucination guard"]
    VD --> RT3{"route_after_verify"}
    RT3 -->|verification_passed| O["node_report<br/>Phase 13: Report"]
    RT3 -->|failed| S["END<br/>Failed"]
    O --> P["node_git_commit<br/>Phase 14: Commit"]
    P --> PU["node_push<br/>Phase 15a: Push"]
    PU --> CPR["node_create_pr<br/>Phase 15b: Create PR"]
    CPR --> MPR["node_merge_pr<br/>Phase 15c: Auto-merge (terminal)"]
    MPR --> Q["node_distill_memory<br/>Phase 16: Memory"]
    Q --> R["node_create_skill<br/>Phase 17: Skill (v3.1.2: importlib smoke-test + git commit)"]
    R --> S["END<br/>Success"]
```

**Conditional routes:**
- `route_after_classify` — `feature`/`fix`/`refactor`/`edit`/`audit` → `node_brainstorm`; `create_skill` → `node_create_skill` (bypasses TDD).
- `route_after_write_files` — `fix`/`refactor`/`improve`/`feature`/`audit`/`edit` → `node_analyze_impact`; other → `node_run_pytest`. **[Hardening P1.5]** short-circuits to `node_run_pytest` when `status=="error"`.
- `route_after_run_tests` — `pass` → `node_run_pytest`; `fail` → `node_systematic_debug`; `stuck` → `node_run_pytest` (skips doomed debug). **[v3.1 #48]** When `tdd_status == "max_retries_exceeded"` AND `cfg.autocode_swarm_debug_fallback` is ON, routes to `node_swarm_fallback` (3-way conditional from `node_run_tests`). `node_swarm_fallback` itself has a 2-way conditional out: HIGH confidence → `node_systematic_debug` (one more debug cycle with swarm verdict injected); LOW/MEDIUM/unavailable → `node_run_pytest` (proceed to verify chain, will fail). **[Hardening P1.5]** short-circuits on `status=="error"`.
- `route_after_verify` — `pass` → `node_report`; `fail` → **`END`** (does NOT re-enter the debug loop — the debug loop already exhausted its retries by the time the verify chain runs; re-entering would loop forever).

**Debug loop:** `node_systematic_debug` → `node_summarize_context` → `node_apply_patches` → `node_write_new_files` → `node_persist_artifacts` → `node_analyze_impact` → `node_run_tests` → (back to `node_systematic_debug` until tests pass, `MAX_RETRIES` exceeded, `tdd_status="stuck"`, OR the architecture-question exit fires — 3+ consecutive `tests_passed=False`). **[v3.1 #48]** On `max_retries_exceeded` + flag ON, `node_swarm_fallback` may inject a fresh diagnosis and re-enter the debug loop one more time (HIGH confidence only).

---

## 💡 Key Design Decisions

- **29-node LangGraph StateGraph** — 26 active nodes + 3 backward-compat wrappers (registered, NOT wired) + `node_summarize_context` (Phase 4, debug-loop compression) + `node_swarm_fallback` (Phase 11b, v3.1 swarm escalation). The 3 wrappers preserve `import`-compatibility for external callers + tests; they are excluded from `WORKFLOW_METADATA["nodes"]` so MCP clients render only the 28 active-node entries.
- **Facade is `run_workflow("autocode")` — NOT the removed v1.0 facade shim** — **[v3.1.2 #34]** The autocode-specific backward-compat facade shim in `workflows/autocode.py` was REMOVED (no production callers, only test refs). All callers — internal and external — use `run_workflow(workflow_type="autocode", goal="...", **kwargs)` from `workflows/base.py` directly. `workflows/autocode.py` now exports only `build_graph`, `get_graph`, `WORKFLOW_METADATA`, `AutocodeState`, `_default_state`, `_shape_artifacts`, `_resolve_files_input`.
- **Mode-driven** — The task type (`feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, `create_skill`, `audit`) determines the workflow path. `node_classify_task` uses the Router LLM to classify (with mode override).
- **TDD-first** — For `feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, and `audit` modes, tests are generated before implementation. (`create_skill` bypasses TDD; `audit` currently keeps TDD but F7 full-audit mode would bypass it — see [INSTRUCTIONS.md](INSTRUCTIONS.md) § "Deferred Roadmap Items → F7".)
- **Iterative debug loop** — `node_systematic_debug` accumulates `debug_history` across iterations (closes the #37 prerequisite); `node_summarize_context` compresses it before re-entering the loop. Last 5 entries injected into the LLM user prompt under a `PRIOR DEBUG ATTEMPTS (do NOT repeat these)` block. New architecture-question exit fires on 3+ consecutive `tests_passed=False` → `tdd_status="max_retries_exceeded"` + procedural memory store (different from #39 stuck detection — fires on DIFFERENT errors each iteration, suggesting architectural bug).
- **Impact analysis** — `node_analyze_impact` analyzes blast radius using the dependency graph. Prevents unintended side effects.
- **Git integration** — `node_git_branch` creates a new branch (optionally pulls first via `AUTOCODE_PULL_BEFORE_BRANCH`); `node_git_commit` commits changes with a descriptive message. `node_write_plan` appends `trace_id` suffix (`autocode/{slug}-{tid_suffix}`) for branch-name uniqueness.
- **GitHub integration** — `node_push` → `node_create_pr` → `node_merge_pr` (all gated on config flags + `is_configured()`, all default OFF). With all flags OFF, the 3 nodes are no-ops — autocode behaves identically to a local-only workflow.
- **Swarm debug integration** — Two independent paths: (1) `node_systematic_debug` optionally uses swarm (2-run pattern: `consensus` → `vote`) INSIDE the debug loop via `AUTOCODE_SWARM_DEBUG=1`. Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split). Non-blocking — fix is ALWAYS applied regardless of confidence. LOW confidence surfaces as a PR comment (if `AUTOCODE_DEBUG_COMMENT_PR=1`), not as a workflow block. (2) **[v3.1]** `node_swarm_fallback` consults the swarm AFTER the debug loop is exhausted via `AUTOCODE_SWARM_DEBUG_FALLBACK=1`. HIGH confidence → inject verdict + reset `tdd_status` (one more debug cycle); LOW/unavailable → proceed to verify chain. The two flags are independent — they can be enabled together or separately.
- **Parallel subagent debug (v3.5 F1)** — `node_systematic_debug` optionally dispatches N subagents in parallel — one per hypothesis — via `concurrent.futures.ThreadPoolExecutor`. Gated on `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` (default OFF). Pipeline: (1) planner LLM generates `AUTOCODE_PARALLEL_SUBAGENT_COUNT` (default 3) distinct hypotheses via `PARALLEL_HYPOTHESES_SYSTEM`; (2) `ThreadPoolExecutor(max_workers=N)` dispatches one `agent(action="subagent")` per hypothesis using `SUBAGENT_VALIDATE_SYSTEM`; (3) aggregate by highest `hypothesis_confidence`; (4) store ALL verdicts in `debug.parallel_verdicts` for observability; (5) mirror winner into `debug.subagent_verdict`. Falls through to single-LLM on hypothesis-generation failure OR all-subagents-failed. Mutually exclusive with `AUTOCODE_SWARM_DEBUG` and `AUTOCODE_SUBAGENT_DEBUG` (NEVER DO #40 updated). See [API.md](API.md) § "Parallel Subagent Debug".
- **Memory integration** — `node_distill_memory` stores procedural knowledge for future recall. Non-fatal — code is already committed by the time distill runs.
- **Skill creation** — `node_create_skill` creates a reusable skill file. Atomic write (`tempfile` + `os.replace`) + AST validation. **[v3.1.2 #36]** After write: (a) `importlib.util.spec_from_file_location` smoke-test (catches missing deps that AST parse misses); (b) `_git_commit(message=f"skill(autocode): {skill_name}")` commits the new skill file. **[v3.1.2 P1]** Empty-file rejection with fallback keys (`skill_file` → `skill_code` → `code`). **[v3.2 P1-4]** `sys.path.insert` leak removed (was never cleaned up after the smoke-test).
- **Filelock + atomic writes** — `node_write_new_files` uses `FileLock` and atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) to prevent race conditions and data corruption.
- **Lazy Dev / YAGNI Ladder** — `CODER_SYSTEM` includes the 7-rung minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code). `DEBUG_SYSTEM` Phase 4 ("fix") also applies the ladder. `ponytail:` comment convention marks deliberate simplifications with known ceilings.
- **Adaptive timeout** — **[v3.1.2 #40]** `invoke_with_timeout()` consults `cfg.autocode_adaptive_timeout` (env: `AUTOCODE_ADAPTIVE_TIMEOUT=1`, default OFF). When ON, per-task-type timeout map overrides `cfg.autocode_graph_timeout`: `create_skill`=120s, `audit`=300s, `feature`=900s, `fix`/`refactor`/`edit`=600s. See [API.md](API.md) § "Adaptive Timeout".
- **Result compression** — The final result is compressed via `compress_result()` before being returned.

### `node_publish` is a separate node — NOT folded into `node_commit`
`node_commit` is local-only and always runs (TDD code is committed even on failure). `node_publish` (now `node_push` + `node_create_pr` + `node_merge_pr`) is opt-in (config flags), remote-touching, and may fail (network, GitHub API, permissions) — its failure must NOT flip a successful workflow to failed.

### `_is_path_safe()` guards LLM-generated paths
The `node_validate_input` path traversal check only covers user-supplied paths. LLM-generated paths (`patches[].path`, `new_files{}` keys) are validated via `_is_path_safe(base_path, rel_path) -> bool` in `apply_patches.py` (imported by `write_new_files.py`) — uses `Path.resolve().is_relative_to()` to verify the resolved target stays inside `base_path`.

### `_call()` retries 2× with exponential backoff + interruptible sleep
`_call(role, system, user, ..., retries=2, trace_id="")` loops `retries + 1` times, sleeping `2 ** attempt` seconds between attempts. **[Hardening P1.7]** sleep uses `threading.Event.wait(timeout=...)` so `request_cancellation()` from a timeout aborts the backoff immediately (was `time.sleep(...)` — uninterruptible, blocked the timeout). **[v3.1.2 P1]** All 8 in-tree callers pass `trace_id=tid` — retry-exhaustion errors are attributed to the workflow's trace (was: unattributed `trace_id=""`). **[v3.2 P1-6]** Unreachable `raise last_error` after the retry loop removed (dead code — the loop body always returns or raises within the loop).

### 6 v1.3 config flags + 1 v2.0.2 + 1 v3.1 + 1 v3.1.2 + 1 v3.4 + 2 v3.5 default OFF
`AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG` (v1.3 — pre-2.0 GitHub + Swarm integration); `AUTOCODE_SUBAGENT_DEBUG` (v2.0.2); `AUTOCODE_SWARM_DEBUG_FALLBACK` (v3.1); `AUTOCODE_ADAPTIVE_TIMEOUT` (v3.1.2 #40); `AUTOCODE_HITL_ENABLED` (v3.4 #38); `AUTOCODE_PARALLEL_SUBAGENT_DEBUG` (v3.5 F1). `AUTOCODE_PARALLEL_SUBAGENT_COUNT` (v3.5 F1, default 3) tunes the parallel hypothesis count. With all flags OFF, autocode behaves identically to v1.1 (local-only, single-LLM debug, no swarm fallback on exhaustion, static graph timeout, no HiTL gate, no parallel subagent dispatch).

### v3.2 collective-review hardening (5 P0 + 6 P1 + 8 P2)

The v3.2 release shipped 19 fixes from a 6-LLM collective code review. The four design-level changes:

- **`threading.Lock` on `get_graph()` singleton (P2-3)** — wraps the check-then-set pattern so concurrent invocations don't both call `build_graph()` and clobber each other.
- **`_cleanup_old_autocode_runs` wired to `invoke_with_timeout()` (P2-2)** — was never invoked anywhere (silent disk leak); now called at start of each run, non-fatal on failure.
- **`_blast_radius_warning()` helper extracted (P2-1)** — was duplicated between `plan.py` and `debug.py` with drifted truncation thresholds; now in `helpers.py`.
- **Named `route_after_swarm_fallback()` in `routes.py` (P2-5)** — was an untestable inline lambda; now a named function with a focused unit test.

The remaining 15 v3.2 fixes are localized to single nodes — see [NODES.md](NODES.md) per-node entries + [CHANGELOG.md](CHANGELOG.md) § v3.2.

### v3.4 HiTL approval gate (#38) — async-checkpoint-resume over sync-pause

The v3.4 release added an opt-in Human-in-the-Loop (HiTL) approval gate (`node_hitl_gate`) between `node_report` and `node_commit`. The design decision: chose **async-checkpoint-resume** over **sync-pause** (`threading.Event` block) because the gateway's worker pool assumes stateless workers — a sync-paused worker would consume a worker slot for the entire review duration (could be hours), eventually exhausting the pool under load. The async pattern adds one extra call but preserves the worker pool, works with the existing checkpoint infrastructure, and is testable in isolation.

Two gates are wired: (1) **TDD path** — `node_hitl_gate` between `node_report` and `node_commit`, routed via `route_after_hitl_gate(state)` (`status == "awaiting_approval"` → `END`; else → `node_commit`); (2) **create_skill path** — HiTL check at the TOP of `node_create_skill`.

**Opt-in via `AUTOCODE_HITL_ENABLED=1` (default OFF).** Checkpoint failure is non-fatal (wrapped in `try/except`). See [API.md](API.md) § "HiTL Approval Gate" for the pause/resume flow + Resume API. End-to-end param threading: `hitl_approved: bool` flows through `AutocodeState` → `_default_state()` → `tools/workflow_ops/actions/run.py` → `tools/workflow_ops/types/autocode.py` → `tools/workflow_ops/helpers.py` → `workflows/base.py::run_workflow()` (merges from kwargs on resume). Graph: 29 → 30 nodes.

### v3.5 F1 — Parallel subagent debug (4th debug chain path)

The v3.5 release added a 4th debug path inside `node_systematic_debug`, gated on `AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1` (default OFF). The new path is inserted **between the swarm path and the single-subagent path** so the chain is now: swarm → parallel subagent → single subagent → single-LLM. All three opt-in flags are mutually exclusive (NEVER DO #40). The chain is fall-through: each path's failure leads to the next.

**Design decisions:**

- **`ThreadPoolExecutor` over `asyncio`** — autocode is sync (LangGraph invokes nodes one at a time, `_call()` blocks). `ThreadPoolExecutor` parallelizes the N subagent `_call()` invocations (each I/O-bound on the LLM API) without touching the sync structure.
- **`hypothesis_confidence` (planner-supplied) as the aggregation key** — keeps aggregation deterministic; subagents only validate/refine the fix, they don't re-score.
- **All verdicts stored, not just the winner** — `debug.parallel_verdicts` holds every surviving verdict so operators can inspect why the winner was chosen. The winner is mirrored into `debug.subagent_verdict` so downstream readers (e.g., `_shape_artifacts`) don't need a parallel-aware code path.
- **Fall-through on failure** — if hypothesis generation fails OR all N subagents fail, `_parallel_subagent_debug()` returns `None` and the chain continues with single-subagent / single-LLM. The workflow never hard-fails because of the parallel path.

See [API.md](API.md) § "Parallel Subagent Debug" for the full pipeline + fallback table. Graph: unchanged (30 nodes — the parallel path is a branch inside `node_systematic_debug`).

### v3.6 #35 — Cancellation-aware subprocess (incremental zombie fix)

The v3.6 release added cancellation-aware `subprocess.run(...)` wrappers in `node_run_pytest`, `node_run_lint`, and `node_run_tests`. Three hooks per subprocess call: pre-check `is_cancellation_requested()` (bail if graph already timed out), deadline-aware `timeout=` via `_remaining_timeout(default)` (cap at remaining graph budget), post-check `is_cancellation_requested()` (discard results so the daemon thread exits promptly).

**Why incremental:** Python's `threading.Thread` doesn't support `Thread.kill()`. The v3.6 fix bounds the daemon-thread zombie linger to ≤1s past the graph deadline — but the daemon thread can still linger for ~1s. Full process-level termination (the `multiprocessing.Process` rewrite) is still deferred (see [CHANGELOG.md](CHANGELOG.md) roadmap § #35) because it requires re-architecting `invoke_with_timeout()` — pickling state across the process boundary, IPC for the result dict, SIGTERM handling, `spawn`-safe imports on Windows.

New helpers in `helpers.py`: `set_graph_start_time()` (called by `invoke_with_timeout()` at run start), `_remaining_timeout(default)` (computes remaining budget), `_cancelled()` (shortcut). See [API.md](API.md) § "Cancellation-Aware Subprocess" for the helper signatures + tests.

### v3.7 F7 — Audit mode bypasses TDD
- `task_type="audit"` routes to `node_audit_scan → node_audit_report → END` (read-only, no TDD, no commit)
- `node_audit_scan` uses AST analysis (not kgraph-dependent — kgraph is optional enhancement)
- Audit is the only task_type that skips the TDD pipeline entirely

### Dead-code deletions — do NOT re-add
- `node_write_files_with_flag_reset` — was registered but never wired; reset a non-existent `step_attempt` field.
- `route_after_analyze_impact` — was a conditional router that ALWAYS returned `"node_run_tests"`. Replaced with a direct edge.
- `"node_brainstorm"` mapping in `route_after_classify` — never returned; removed from conditional_edges.
- `mermaid.py`, `test_mapper.py`, `test_runner.py` — never called. **[v3.1.2]** The `/autocode/graph` HTTP endpoint in `core/gateway_backend/routes/metrics.py` that imported the deleted `mermaid.py` is also removed.

---

## 🧭 [v3.0] Sub-state Architecture

The autocode state is split into 8 focused sub-state TypedDicts behind an accessor layer. **[v3.0]** Track M1 (v2.1–v2.7 + v3.0) is ✅ COMPLETE — all 8 accessors are the ONLY read path for sub-state fields. Legacy flat-field mirrors were removed; accessor legacy-fallback branches were removed (each is now a 4-line sub-state-only read).

> **[v3.0] Migration status: ✅ COMPLETE — Track M1 shipped.** All 8 sub-states
> (`plan_state`, `tdd`, `files_state`, `impact`, `debug`, `verify`, `vcs`,
> `memory`) are the PRIMARY (and ONLY) storage for their fields. Every node
> writes via read-modify-write (RMW); every reader uses the corresponding
> accessor. The v2.0.5 split-brain warning is lifted. Ephemeral flat fields
> (test_results, test_code, _pytest_output, lint_output, etc.) stay flat by
> design.

**For the full sub-state reference** — TypedDicts, writer/reader node lists, the 8 accessor signatures, the RMW pattern, migration history — **see [SUBSTATE.md](SUBSTATE.md).**

### The 8 sub-state TypedDicts (summary)

| Sub-state | TypedDict | Representative fields |
|-----------|-----------|----------------------|
| Plan | `PlanState` | `brainstorm_notes`, `plan`, `plan_accepted`, `spec`, `current_step` |
| TDD | `TDDState` | `iteration`, `source_code`, `error`, `status`, `max_retries`, `last_test_error`, `tests_written`, `debug_history`, `debug_summary` |
| Files | `FilesState` | `files_map`, `modified_files` (`input_files` removed in v3.0 — use core `files` flat field) |
| Impact | `ImpactState` | `warnings`, `targeted_test_cmd`, `failed` |
| Debug | `DebugState` | `notes`, `root_cause`, `defense_notes`, `swarm_verdict`, `subagent_verdict`, `parallel_verdicts` |
| Verify | `VerifyState` | `notes`, `report`, `passed` |
| VCS | `VCSState` | `commit_sha`, `branch`, `branch_name`, `pushed`, `pr_number`, `pr_url` |
| Memory | `MemoryState` | `notes`, `context` |

### The 8 accessor functions

Each accessor reads from the corresponding sub-state dict — NO legacy flat-field fallback (removed in v3.0). Signature pattern (see [SUBSTATE.md](SUBSTATE.md) for all 8):

```python
# [v3.0] Signature pattern (state.py) — 4 lines, sub-state-only
def _get_vcs(state: dict, key: str, default: Any = None) -> Any:
    """Read `key` from state["vcs"] if present, else return `default`."""
    sub = state.get("vcs")
    if isinstance(sub, dict) and key in sub:
        return sub[key]
    return default
```

The 8 accessors: `_get_plan`, `_get_tdd`, `_get_files`, `_get_impact`, `_get_debug`, `_get_verify`, `_get_vcs`, `_get_memory`.

**Design rationale:** The accessor layer decouples node code from the storage layout. Nodes call `_get_vcs(state, "branch", "")` instead of `state.get("branch", "")` or `state["vcs"]["branch"]` — the accessor is free to evolve (it was the backward-compat bridge during v2.1–v2.7, then simplified in v3.0) without breaking callers. Every read goes through the accessor; every write goes through RMW; ephemeral flat fields (test_results, test_code, _pytest_output, lint_output, etc.) stay flat because they're inter-node scratch space, not part of any sub-state.

For the v2.0 → v3.0 migration narrative, see [CHANGELOG.md](CHANGELOG.md) § "Track M1". For per-version details, see git history.

### Cancellation flag

Phase 1 added a module-level cancellation flag to `helpers.py`:

```python
def request_cancellation() -> None: ...
def clear_cancellation() -> None: ...
def is_cancellation_requested() -> bool: ...
```

`_call()` checks `is_cancellation_requested()` before each retry. `invoke_with_timeout()` (in `workflows/autocode_impl/graph.py`, called from `run_workflow()` in `base.py`) calls `clear_cancellation()` at start and `request_cancellation()` on timeout — the in-flight `_call()` retries notice and abort instead of sleeping through exponential backoff. **[Hardening P0.3]** graph exceptions in the daemon thread are now surfaced as `"Autocode graph crashed: <exception>"` (was swallowed and misreported as timeout). Full process-level termination deferred to post-2.0 (`# TODO(2.0-post):` — see [INSTRUCTIONS.md](INSTRUCTIONS.md) § "Deferred Roadmap Items → #35").

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
├── test_facade.py         # imports + run_workflow + #44 artifacts + #46 git-diff + #47 dry-run + distill (v3.1.2: legacy facade shim removal test)
├── test_execute.py        # node_execute_step + node_write_files + .bak checks
├── test_run_tests.py      # #39 stuck detection + file-existence + budget wiring
├── test_debug.py          # debug loop routing + JSON parsing + max-retries
├── test_verify.py         # node_verify + lint + commit + defense_notes
├── test_branch.py         # node_git_branch + git scoping + dry-run + no-snapshot (v3.1.2: ast.Str → ast.Constant)
├── test_create_skill.py   # name sanitization + syntax validation + skill_created flag (v3.1.2: mock-key fix + empty-file rejection + importlib smoke-test)
├── test_helpers.py        # path helpers + patch + protected files + path traversal
├── test_safety.py         # dry-run mode + protected files + memory callbacks + TDD loop + dead routes
└── test_analyze_impact.py # AST parser
```

---

*Last updated: 2026-07-19 (v3.7). See [CHANGELOG.md](CHANGELOG.md) for version history.*
