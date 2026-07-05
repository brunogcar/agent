<- Back to [Autocode Overview](../AUTOCODE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v1.0.2 | 2026-07-05 | P1/P2 bugfix batch: node_report type annotation (#2), create_skill project root + filename validation + syntax check + skill_created flag (#3/#15/#16/#17), removed dead route functions (#4), mermaid.py getattr guards (#5), test_runner protected_files arg (#6), lint_passed=None when ruff missing (#7), write_files error status on JSON parse (#9), git_branch error handling (#10), path traversal Windows/Unicode (#11), slug fallback (#12), FileLock retry (#13), run_tests file existence check (#14), classification dead code (#28), AUTOCODE_GRAPH_TIMEOUT wired (#30) |
| v1.0.1 | 2026-07-05 | P0 bugfix batch: removed .bak files (#1), removed git snapshot (#2), populate files_map (#3), sync analyze_impact (#4), fix files_context (#6), fix KG file merge (#7), fix impact_warnings type (#8), remove dead AGENT_ROOT (#9), fix defense_notes (#10/#11) |
| v1.0 | — | Released — 17-node LangGraph StateGraph with TDD-first, debug loop, impact analysis, git integration, memory storage |

---

## ⚠️ Breaking Changes

### v1.0.1 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| Removed `.bak` file creation | No more `.bak` backup files in the repo. Atomic writes (tempfile + os.replace) used instead. Git provides versioning. | No migration — strictly better. Clean up any existing `.bak` files: `git clean -f "*.bak"` |
| Removed `git(action="snapshot")` | `_git_snapshot()` function removed from `git_ops.py`. The branch itself is the safety net. | No migration — snapshot action was already broken (action deleted from git tool). |
| `files_map` now populated | `node_write_files` now sets `files_map` with file snapshots. `analyze_impact` will actually run. | No migration — was always empty before (bug fix). |
| `node_analyze_impact` converted to sync | Was `async def`, now `def` with `_run_async()` wrapper for async calls. LangGraph requires sync. | No migration — was broken (async in sync graph). |
| `impact_warnings` type changed | `list[str]` → `list[dict]` to match what `analyze_impact` actually returns. | No migration — nothing consumed it yet (was always empty). |
| `defense_note` → `defense_notes` | Commit and memory nodes now use `defense_notes` (plural) to match state field. | No migration — was always empty (singular never set). |
| `hypothesis` → `root_cause` in memory | Memory node now reads `root_cause` (set by debug node) instead of `hypothesis` (never set). | No migration — was always empty. |

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
| 1 | **Fix `node_write_files` `run_dir` NameError** | Reported as P0 but verified as FALSE POSITIVE. | ✅ Fixed (v1.0.1) |
| 2 | **Fix `node_report` type annotation wrong** | Changed `AutocodeState` → `dict`. | ✅ Fixed (v1.0.2) |
| 3 | **Fix `node_create_skill` writes to agent_root** | Now resolves via `project_root` or `workspace_root`. | ✅ Fixed (v1.0.2) |
| 4 | **Remove dead route functions** | Removed `route_after_brainstorm` and `route_after_debug`. | ✅ Fixed (v1.0.2) |
| 5 | **Fix `mermaid.py` uses LangGraph internals** | Added `getattr()` guards for all internal attributes. | ✅ Fixed (v1.0.2) |
| 6 | **Fix `test_runner.py` `_should_copy_file` wrong arg** | Now passes `cfg.protected_files` (frozenset) instead of workspace Path. | ✅ Fixed (v1.0.2) |
| 7 | **Fix `node_verify` `lint_passed=True` when ruff missing** | Changed to `None`. | ✅ Fixed (v1.0.2) |
| 8 | **Fix `node_report` `modified_files` empty** | Fixed in v1.0.1 (files_map populated). | ✅ Fixed (v1.0.1) |
| 9 | **Fix `node_write_files` doesn't return `status` on error** | Now returns `{"status": "error", "error": "..."}` on JSON parse failure. | ✅ Fixed (v1.0.2) |
| 10 | **Fix `node_git_branch` no error handling** | Now checks return value and returns error status on failure. | ✅ Fixed (v1.0.2) |
| 11 | **Fix `node_validate_input` path traversal incomplete** | Now catches Windows absolute, URL-encoded separators, and Unicode. | ✅ Fixed (v1.0.2) |
| 12 | **Fix `node_write_plan` slug may be empty** | Fallback to `"autocode"` when slug is empty. | ✅ Fixed (v1.0.2) |
| 13 | **Fix `node_write_files` `FileLock` no retry** | Added 1 retry on timeout. | ✅ Fixed (v1.0.2) |
| 14 | **Fix `node_run_tests` test file may not exist** | Now filters missing files before running pytest. | ✅ Fixed (v1.0.2) |
| 15 | **Fix `node_create_skill` no filename validation** | Added `_sanitize_skill_name()` — replaces non-alphanumeric with `_`. | ✅ Fixed (v1.0.2) |
| 16 | **Fix `node_create_skill` no syntax check** | Added `ast.parse()` validation before writing. | ✅ Fixed (v1.0.2) |
| 17 | **Fix `node_create_skill` `skill_created` never set** | Now sets `skill_created: True` on success. | ✅ Fixed (v1.0.2) |
| 28 | **Fix `node_distill_memory` `classification` dead code** | Removed — field never set in AutocodeState. | ✅ Fixed (v1.0.2) |
| 29 | **Test restructure** | Split test files into per-node modules + `conftest.py`. | P1 |
| 30 | **Configurable timeout** | Added `invoke_with_timeout()` wrapper using `cfg.autocode_graph_timeout`. | ✅ Fixed (v1.0.2) |
| 31 | **Remove `__all__` internal constants** | `MAX_RETRIES`, `MAX_FILE_CHARS` etc. are config values, not API surface. | P2 |
| 32 | **IDE integration** | LSP or VS Code extension for autocode. | P3 |

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
