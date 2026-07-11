<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v1.3 | 2026-07-10 | **GitHub + Swarm integration:** New `node_publish` (push + PR create + optional auto-merge). New `github_ops.py` helper module. Swarm 2-run debug (consensus → vote, confidence HIGH/MEDIUM/LOW). 6 new config flags (all default OFF). 4 new state fields (`pushed`, `pr_number`, `pr_url`, `swarm_verdict`). Fix TypedDict drift (`branch` field). All operations graceful-skip if GitHub not configured — zero behavior change unless opted in. |
| v1.2 | 2026-07-08 | **JSON schema enforcement:** `debug.py` now passes `json_schema` via `_call()` helper. Schema: `{root_cause: str, defense_notes: str, fix: str}`. `_call()` helper updated to accept `json_schema` param. LM Studio enforces at generation time. Defensive JSON parsing stays as fallback. |
| v1.1.2 | 2026-07-06 | **Small-fix batch:** #39 (stuck detection — same error signature on consecutive iterations bails to verify), #44 (structured artifacts in return dict), #46 (multi-file git-diff input via `files={"all changed": ""}` + `git_diff=True`), #47 (dry-run guards on write_files/commit/branch). Also folded in v1.1.1: `TestPartialDictReturns` + changelog cleanup. |
| v1.1 | 2026-07-06 | **Facade fix + WORKFLOW_METADATA + routing fixes.** Fixed the broken facade (was unreachable for 2 versions due to 4 dead imports + double-compile + uncompiled-graph crash in base.py). Added `WORKFLOW_METADATA` (17 nodes, loops, branches, safety_features). Fixed `route_after_write_files` to include `audit`/`edit` (was skipping impact analysis). Made `distill_memory` non-fatal (`tracer.warning` not `tracer.error`). Added facade contract tests. Based on cross-LLM review (Gemini, DeepSeek, Mistral, Qwen, Kimi). |
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch (18 items — see Completed) |
| v1.0.1 | 2026-07-05 | P0 bugfix batch (11 items — see Completed) |
| v1.0 | — | Released — 17-node LangGraph StateGraph |

---

## ⚠️ Breaking Changes

### v1.1 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| `run_autocode_agent()` now delegates to `run_workflow("autocode")` | Was calling `get_graph().compile().invoke()` directly (crashed). Now goes through base.py for tracing/checkpointing/timeout. | No migration — the public API signature is unchanged. Callers get checkpoint/resume for free. |
| Removed 4 dead imports from facade (`AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot`) | These were already removed from `state.py`/`routes.py`/`git_ops.py` in v1.0.1/v1.0.2 but the facade still imported them → `ImportError`. | No migration — the facade was unreachable before. |
| `route_after_write_files` now routes `audit`/`edit` to `node_analyze_impact` | Was skipping impact analysis for these task types. | No migration — impact analysis is the correct path for audit/edit. |
| `distill_memory` uses `tracer.warning` (was `tracer.error`) | Distillation failure no longer logged as error (it's non-fatal — code already committed). | No migration — semantic change only. |
| `base.py` autocode branch uses `invoke_with_timeout` (was `graph.invoke()` on uncompiled graph) | Was crashing with `AttributeError: 'StateGraph' has no attribute 'invoke'`. | No migration — was broken before. |
| Removed internal constants from `__all__` (`MAX_RETRIES`, `MAX_FILE_CHARS`, `DEBUG`, etc.) | These are implementation details, not public API. | If external code imported them from `workflows.autocode`, import from `workflows.autocode_impl.state` instead. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 17-node LangGraph StateGraph | ✅ v1.0 | classify → validate → brainstorm → plan → branch → tests → execute → write → impact → run tests → debug → retry → verify → report → commit → memory → skill |
| Mode-driven workflow | ✅ v1.0 | fix_error, improve, add_feature, create_skill, unclear |
| TDD-first | ✅ v1.0 | Tests generated before implementation |
| Iterative debug loop | ✅ v1.0 | Debug → retry → run tests until pass or max retries |
| Impact analysis | ✅ v1.0 | Blast radius analysis using dependency graph |
| Git integration | ✅ v1.0 | Branch creation and commit |
| Memory integration | ✅ v1.0 | Procedural memory storage |
| Report generation | ✅ v1.0 | Structured report with result and metadata |
| Filelock + atomic writes | ✅ v1.0 | Prevents race conditions and data corruption |
| Result compression | ✅ v1.0 | compress_result() prevents oversized responses |
| #1 `node_write_files` `run_dir` NameError | ✅ v1.0.1 | False positive — not a bug |
| #2 `node_report` type annotation | ✅ v1.0.2 | Changed `AutocodeState` → `dict` |
| #3 `node_create_skill` writes to agent_root | ✅ v1.0.2 | Now resolves via `project_root` |
| #4 Dead route functions removed | ✅ v1.0.2 | `route_after_brainstorm`, `route_after_debug` |
| #5 `mermaid.py` LangGraph internals | ✅ v1.0.2 | Added `getattr()` guards |
| #6 `test_runner.py` `_should_copy_file` arg | ✅ v1.0.2 | Now passes `cfg.protected_files` |
| #7 `node_verify` `lint_passed=True` when ruff missing | ✅ v1.0.2 | Changed to `None` |
| #8 `node_report` `modified_files` empty | ✅ v1.0.1 | Fixed via `files_map` population |
| #9 `node_write_files` no `status` on error | ✅ v1.0.2 | Returns `{"status": "error"}` on JSON parse failure |
| #10 `node_git_branch` no error handling | ✅ v1.0.2 | Checks return value, returns error status |
| #11 `node_validate_input` path traversal | ✅ v1.0.2 | Catches Windows absolute, URL-encoded, Unicode |
| #12 `node_write_plan` slug may be empty | ✅ v1.0.2 | Fallback to `"autocode"` |
| #13 `node_write_files` `FileLock` no retry | ✅ v1.0.2 | Added 1 retry on timeout |
| #14 `node_run_tests` test file may not exist | ✅ v1.0.2 | Filters missing files |
| #15 `node_create_skill` no filename validation | ✅ v1.0.2 | Added `_sanitize_skill_name()` |
| #16 `node_create_skill` no syntax check | ✅ v1.0.2 | Added `ast.parse()` validation |
| #17 `node_create_skill` `skill_created` never set | ✅ v1.0.2 | Now sets `skill_created: True` |
| #28 `node_distill_memory` `classification` dead code | ✅ v1.0.2 | Removed — field never set |
| #29 Test restructure | ✅ v1.0.2 | Per-node tests already exist |
| #30 Configurable timeout | ✅ v1.0.2 | `invoke_with_timeout()` using `cfg.autocode_graph_timeout` |
| #31 Remove `__all__` internal constants | ✅ v1.1 | Facade `__all__` now only exports public API |
| **Facade fix (4 dead imports)** | ✅ v1.1 | `AGENT_ROOT`, `route_after_brainstorm`, `route_after_debug`, `_git_snapshot` removed |
| **Double-compile fix** | ✅ v1.1 | `base.py` uses `invoke_with_timeout` (was `graph.compile().invoke()` — crashed) |
| **`WORKFLOW_METADATA`** | ✅ v1.1 | 17 nodes, loops, branches, safety_features |
| **Facade contract tests** | ✅ v1.1 | `test_facade.py` — import + run_workflow + graph structure + routing |
| **`audit`/`edit` routing fix** | ✅ v1.1 | Now route to `analyze_impact` (was skipping it) |
| **`distill_memory` non-fatal** | ✅ v1.1 | `tracer.warning` not `tracer.error` (code already committed) |
| **#33 Partial-dict returns** | ✅ v1.1.1 | All 16 nodes already return partial dicts (done in v1.0.1/v1.0.2). Added `TestPartialDictReturns` to lock in the clean state. |
| **#2 Checkpoint/resume** | ✅ v1.1 | Facade delegates to `run_workflow("autocode")` which has checkpoint/resume infra. |
| **#39 Stuck detection in debug loop** | ✅ v1.1.2 | Same error signature on consecutive iterations → `tdd_status="stuck"` → routes to verify (skips doomed debug loop). `_error_signature()` normalizes stderr. |
| **#44 Structured artifacts** | ✅ v1.1.2 | `run_autocode_agent()` now returns an `artifacts` dict: `commit_sha`, `branch_name`, `modified_files`, `test_results`, `tdd_status`, `tdd_iteration`, `verification_passed`, `skill_created`, `skill_path`. |
| **#46 Multi-file git-diff input** | ✅ v1.1.2 | `files={"all changed": ""}` + `git_diff=True` resolves changed files via `git diff --name-only`. Merges with explicitly-passed files. |
| **#47 Dry-run actually dry** | ✅ v1.1.2 | `dry_run=True` now guards `node_write_files`, `node_commit`, `node_git_branch`. Guards run AFTER validation checks so dry_run still surfaces JSON/verification errors. |
| **#43 GitHub PR workflow** | ✅ v1.3 | New `node_publish` between `node_commit` and `node_distill_memory`. Push branch → create PR → optional auto-merge. Gated on `AUTOCODE_PUSH_ON_COMMIT` + `AUTOCODE_OPEN_PR` + `AUTOCODE_AUTO_MERGE` flags (all default OFF). Uses new `workflows/autocode_impl/github_ops.py` helper module. |
| **`node_publish`** | ✅ v1.3 | New node: push + PR create + optional auto-merge. All operations graceful-skip if GitHub not configured. PR body includes task, commit SHA, verification status, swarm verdict. |
| **`github_ops.py` helper** | ✅ v1.3 | New module mirroring `git_ops.py` pattern: `_github_push()`, `_github_pr_create()`, `_github_pr_comment()`, `_github_pr_merge()`, `_github_pull()`, `_swarm_debug_consensus()`. Lazy imports, tracer.step logging, structured returns. |
| **Swarm debug integration** | ✅ v1.3 | `node_systematic_debug` now optionally uses swarm (2-run pattern: consensus → vote). Confidence: HIGH (unanimous) / MEDIUM (majority) / LOW (split). Non-blocking: fix always applies. LOW confidence → optional PR comment. Falls back to single-LLM if swarm off/unavailable. |
| **6 new config flags** | ✅ v1.3 | `AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`. All default OFF — v1.3 behaves identically to v1.2 unless explicitly opted in. |
| **4 new state fields** | ✅ v1.3 | `pushed: bool`, `pr_number: int`, `pr_url: str`, `swarm_verdict: dict`. Plus fix: `branch: str` added to TypedDict (was read by `branch.py` but not declared — TypedDict drift). |
| **Optional pull before branch** | ✅ v1.3 | `node_git_branch` now optionally pulls recent commits before creating the branch (`AUTOCODE_PULL_BEFORE_BRANCH=1`). Uses `github(action="pull")`. Non-blocking — pull failure doesn't stop the workflow. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 32 | **IDE integration** | LSP or VS Code extension for autocode. | P3 |
| 34 | **Remove `run_autocode_agent()` backward-compat shim** | Once all callers use `run_workflow("autocode")` directly, remove the shim. Audit callers first. | P2 |
| 35 | **`invoke_with_timeout` daemon-thread zombie risk** | On timeout, daemon thread keeps running (Python can't kill threads). Consider `concurrent.futures` with cancellation or `multiprocessing`. | P2 |
| 36 | **`create_skill` smoke-test import + git commit** | Currently has AST syntax check (v1.0.2 #16) but no import test or git commit. Skills should be committed like all other code changes. | P2 |
| 37 | **Context summarization node** | Compress debug-loop history before it overflows the LLM context window. Add a `summarize_context` node before the debug loop re-enters. **v1.3 note:** Chonkie `SentenceChunker` is the right tool for this compression (reuses `_chunk_text()` from file tool v1.2). **Dependency:** Current `debug.py` is stateless per iteration (each debug call sees only current test output, no accumulated history). This item depends on autocode first being refactored to accumulate debug-loop history across iterations. See `docs/TOOLS.md` § "Chunking (chonkie)". **v1.3 note:** Swarm debug does NOT solve this — it only sees the current iteration's test output, not history. Still blocked on debug history accumulation. | P1 (depends on debug history accumulation) |
| 38 | **Human-in-the-Loop (HiTL) approval** | Pause graph before `commit` or `create_skill`. Send notification, wait for approve/reject via MCP. | P2 |
| 40 | **Adaptive timeout by task type** | `create_skill`=120s, `audit`=300s, `feature`=900s. Better than one global timeout. | P2 |
| 41 | **AST/linter pre-check before pytest** | Run `ruff`/`flake8` before `pytest`. Catch indentation errors instantly without booting the test runner. | P2 |
| 42 | **Goal sanitization** | Enforce max length + strip control chars on `goal`/`task` input. Defense in depth (path traversal, command injection, token budget). | P2 |
| 43 | **GitHub PR workflow** | ✅ Shipped in v1.3 — see Completed section above. | ~~P2~~ Done |
| 45 | **Streaming node transitions** | Stream `tracer.step` events to the client via WebSocket so the user sees progress instead of a 5-minute blank wait. Needs gateway integration. | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove TDD-first** | TDD ensures test coverage. | Skip |
| 2 | **Remove debug loop** | Single-pass code generation misses edge cases. | Skip |
| 3 | **Remove impact analysis** | Blast radius analysis prevents unintended side effects. | Skip |
| 4 | **Remove git integration** | Git branches and commits are essential. | Skip |
| 5 | **Remove memory integration** | Procedural memory improves future performance. | Skip |
| 6 | **Real-time collaboration** | Multi-user editing requires complex state sync. | Skip |
| 7 | **Support non-Python languages** | Workflow is designed for Python. Other languages need tree-sitter per-lang. | Skip |

---

## 🔍 2.0 Review Notes

This section documents known technical debt and design decisions in v1.3 that
should be reviewed during the 2.0 refactoring. All items are marked with
`# TODO(2.0):` in the source code.

### Architecture

| Item | Location | Notes |
|------|----------|-------|
| `git_ops.py` + `github_ops.py` split | `workflows/autocode_impl/` | v1.3 keeps them separate because git (local) and github (remote) are separate tools. In 2.0, consider merging into a unified `vcs_ops.py` module. |
| `node_publish` as single node | `nodes/publish.py` | Currently one node handling push + PR + merge. In 2.0, consider splitting into separate `node_push`, `node_pr_create`, `node_pr_merge` for finer-grained routing and retry. |
| Debug node statelessness | `nodes/debug.py` | Each debug call sees only current test output, no accumulated history. Blocks context summarization (#37). Swarm debug does NOT solve this. Must be refactored in 2.0. |
| Swarm verdict non-blocking | `nodes/debug.py` | Low-confidence swarm verdict applies fix anyway (non-blocking). In 2.0, consider `AUTOCODE_SWARM_BLOCK_ON_LOW_CONFIDENCE` flag for stricter gating. |
| Config flags are global | `core/config.py` | All 6 v1.3 flags are global. In 2.0, consider per-task overrides (e.g., different PR strategy for different task types). |

### Integration

| Item | Location | Notes |
|------|----------|-------|
| `AUTOCODE_AUTO_MERGE` hardcoded to squash | `nodes/publish.py` | In 2.0, add `AUTOCODE_AUTO_MERGE_METHOD` config (squash/merge/rebase). |
| Pull failure is non-blocking | `nodes/branch.py` | Pull failure doesn't stop the workflow. In 2.0, consider making this configurable (fail-fast vs graceful-skip). |
| Swarm confidence thresholds | `github_ops.py` | Currently: unanimous=HIGH, majority=MEDIUM, split/disagreement=LOW. In 2.0, review thresholds — maybe MEDIUM should require ≥3 providers. |
| PR body is minimal | `nodes/publish.py` | Currently includes task, commit SHA, verification status, swarm verdict. In 2.0, add test results, diff summary, impact warnings. |
| No retry on push/PR failure | `nodes/publish.py` | Push or PR creation failure is terminal. In 2.0, add retry logic for transient failures. |

### Documentation

| Item | Location | Notes |
|------|----------|-------|
| Stale env vars in AUTOCODE.md | `docs/workflows/AUTOCODE.md` | Lists `AUTOCODE_PLANNER_TIMEOUT` etc. which don't exist (timeouts come from `model_registry`). Fixed in v1.3 — verify the fix is complete. |
| `pull` action rebase param | `tools/github_ops/actions/pull.py` | `git pull --rebase` not supported. In 2.0, consider adding `rebase: bool` param. |

---

*Last updated: 2026-07-10 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
