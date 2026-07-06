<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
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

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 32 | **IDE integration** | LSP or VS Code extension for autocode. | P3 |
| 33 | **Partial-dict returns across 16 nodes** | LangGraph best practice; matches research/understand/data/deep_research. | P1 |
| 34 | **Remove `run_autocode_agent()` backward-compat shim** | Once all callers use `run_workflow("autocode")` directly, remove the shim. Audit callers first. | P2 |
| 35 | **`invoke_with_timeout` daemon-thread zombie risk** | On timeout, daemon thread keeps running (Python can't kill threads). Consider `concurrent.futures` with cancellation or `multiprocessing`. | P2 |
| 36 | **`create_skill` smoke-test import + git commit** | Currently has AST syntax check (v1.0.2 #16) but no import test or git commit. Skills should be committed like all other code changes. | P2 |
| 37 | **Context summarization node** | Compress debug-loop history before it overflows the LLM context window. Add a `summarize_context` node before the debug loop re-enters. | P1 |
| 38 | **Human-in-the-Loop (HiTL) approval** | Pause graph before `commit` or `create_skill`. Send notification, wait for approve/reject via MCP. | P2 |
| 39 | **Stuck detection in debug loop** | If the same error appears on consecutive iterations, bail to `report` instead of looping. Saves tokens. | P2 |
| 40 | **Adaptive timeout by task type** | `create_skill`=120s, `audit`=300s, `feature`=900s. Better than one global timeout. | P2 |
| 41 | **AST/linter pre-check before pytest** | Run `ruff`/`flake8` before `pytest`. Catch indentation errors instantly without booting the test runner. | P2 |
| 42 | **Goal sanitization** | Enforce max length + strip control chars on `goal`/`task` input. Defense in depth (path traversal, command injection, token budget). | P2 |
| 43 | **GitHub PR workflow** | After github tool is created, wire autocode to create PRs (branch → commit → push → open PR) instead of just commits. | P2 |
| 44 | **Structured artifacts** | Return `{"commit_sha", "branch_name", "modified_files", "pr_url", "test_results"}` as a typed artifacts dict. | P3 |

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

*Last updated: 2026-07-06 (v1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
