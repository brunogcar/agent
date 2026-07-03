<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v1.0 | — | Released — 17-node LangGraph StateGraph with TDD-first, debug loop, impact analysis, git integration, memory storage |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. This section is reserved for future releases.)*

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

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Remove `.bak` file creation** | `.bak` files violate user rule. Found in `patch.py`, `write_files.py`, `helpers.py`. | P0 |
| 2 | **Fix `git(action="snapshot")` doesn't exist** | `_git_snapshot` calls `git(action="snapshot")` which was removed in un-multiplex refactor. | P0 |
| 3 | **Fix `files_map` never populated — analyze_impact never runs** | No node sets `files_map`. `node_execute_step` sets `modified_files`, not `files_map`. | P0 |
| 4 | **Fix `node_analyze_impact` is async in sync graph** | LangGraph `StateGraph.add_node` expects sync. Async function may fail or hang. | P0 |
| 5 | **Fix `node_write_files` `run_dir` NameError** | If `test_code` missing but `tdd_source_code` exists, `run_dir` undefined when persisting generated code. | P0 |
| 6 | **Fix `node_execute_step` uses non-existent `files_context`** | `state.get("files_context", "")` — field doesn't exist in `AutocodeState`. | P0 |
| 7 | **Fix `node_brainstorm` loses KG files** | Merges `kg_files` into `files_update` but stores `state["files"]` (original) instead of merged. | P0 |
| 8 | **Fix `impact_warnings` type mismatch** | `state.py` says `list[str]`, `analyze_impact.py` returns `list[dict]`. | P0 |
| 9 | **Fix `AGENT_ROOT = None` never set** | `state.py` line 10: `AGENT_ROOT = None # Set via cfg`. Never actually set. | P0 |
| 10 | **Fix `node_commit` uses `defense_note` not `defense_notes`** | State field is `defense_notes` (plural). Always empty. | P0 |
| 11 | **Fix `node_distill_memory` uses `hypothesis`/`defense_note` never set** | Debug node sets `root_cause` and `defense_notes`, not `hypothesis` or `defense_note`. | P0 |
| 12 | **Fix `node_report` type annotation wrong** | Returns `AutocodeState` but returns `{}`. | P1 |
| 13 | **Fix `node_create_skill` writes to agent_root regardless of project** | Should use `project_root` or `workspace_root` for non-agent projects. | P1 |
| 14 | **Remove `route_after_debug` and `route_after_brainstorm` dead code** | Graph builder uses direct edges, not these route functions. | P1 |
| 15 | **Fix `mermaid.py` uses LangGraph internals** | `graph.nodes`, `graph.edges`, `graph.conditional_edges` are internal APIs. Fragile. | P1 |
| 16 | **Fix `test_runner.py` `_should_copy_file` wrong arg type** | Called with `Path` (workspace) instead of `frozenset` (protected files). | P1 |
| 17 | **Fix `node_verify` `lint_passed=True` when ruff missing** | Missing ruff should be `False` or `None`, not `True`. | P1 |
| 18 | **Fix `node_report` `modified_files` empty due to `files_map`** | `files_map` always empty. `modified_files` always empty. | P1 |
| 19 | **Fix `node_write_files` doesn't return `status` on error** | JSON parse failure returns `{}`. Workflow continues as if nothing happened. | P1 |
| 20 | **Fix `node_git_branch` no error handling** | Snapshot/branch creation failures not checked. Silent failures. | P1 |
| 21 | **Fix `node_validate_input` path traversal incomplete** | Doesn't catch absolute Windows paths or Unicode traversal. | P1 |
| 22 | **Fix `node_write_plan` slug may be empty** | If `task[:40]` is all non-alphanumeric, `slug` is `""`. Invalid branch name. | P1 |
| 23 | **Fix `node_write_files` `FileLock` no retry logic** | Timeout 10s, no retry. May skip writes under contention. | P2 |
| 24 | **Fix `node_run_tests` test file path may not exist** | `test_files` set by `node_write_files` but may not exist if write failed. | P2 |
| 25 | **Fix `node_create_skill` no filename validation** | `skill_name` with `/` or `\` may escape `skills/` directory. | P2 |
| 26 | **Fix `node_create_skill` no syntax check** | Skill code written without validating it's valid Python. | P2 |
| 27 | **Fix `node_create_skill` `skill_created` never set** | `autocode.py` checks for it but never set by any node. | P2 |
| 28 | **Fix `node_distill_memory` `classification` dead code** | `state.get("classification", {})` — field never set. | P2 |
| 29 | **Test restructure** | Split `test_autocode.py` into per-node files + `conftest.py` | P1 |
| 30 | **Configurable timeout** | Make `AUTOCODE_GRAPH_TIMEOUT` actually used in code | P2 |
| 31 | **Remove `__all__` internal constants** | `MAX_RETRIES`, `MAX_FILE_CHARS`, etc. are config values, not API surface. | P2 |
| 32 | **IDE integration** | LSP or VS Code extension for autocode | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove TDD-first** | TDD ensures test coverage. Removing it would degrade code quality. | Skip |
| 2 | **Remove debug loop** | Single-pass code generation would miss edge cases. Iteration is essential. | Skip |
| 3 | **Remove impact analysis** | Blast radius analysis prevents unintended side effects. Essential for safety. | Skip |
| 4 | **Remove git integration** | Git branches and commits are essential for version control. | Skip |
| 5 | **Remove memory integration** | Procedural memory improves future performance. | Skip |
| 6 | **Real-time collaboration** | Multi-user editing would require complex state synchronization. Out of scope. | Skip |
| 7 | **Support non-Python languages** | The workflow is designed for Python. Other languages would require significant changes. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
