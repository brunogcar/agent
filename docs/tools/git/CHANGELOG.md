<- Back to [Git Overview](../GIT.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.3 | 2026-07-22 | **Docstring clarification — `workflows/autocode_impl/git_ops.py` aliases are name-only, NOT signature-compatible** (consumed by **autocode v3.11 B7**). The pre-v3.11 docstring called it a "backward-compat wrapper" — misleading. The `_git_commit`/`_git_create_branch` aliases point at the NEW function objects (with `project_root` first), so callers using the alias get the NEW signature. All in-tree callers (commit.py, create_skill.py, branch.py) were updated in v1.2; external callers using `_git_commit(message, tid, project_root)` must update to `_git_commit(project_root, message, target_file, tid)`. No code change to the actual `commit`/`create_branch`/`reset_hard` functions in `workflow_helpers.py` — this is a documentation fix only. |
| v1.2 | 2026-07-25 | **Workflow helpers module added.** New `tools/git_ops/workflow_helpers.py` with 3 internal library functions (NOT LLM-facing actions): `commit(project_root, message, target_file="", tid="") -> dict`, `create_branch(project_root, branch, tid="") -> bool`, `reset_hard(project_root, tid="") -> bool`. Extracted from duplicated workflow git code (centralize-workflow-utils Phase B): autocode `vcs_ops.py::_git_commit` + `_git_create_branch`, autoresearch `decide.py::_git_commit` + `_git_reset_hard`, autoresearch `setup.py::_git_create_branch`. All use the `tools.git_ops.helpers._git()` runner (same runner the LLM-facing git tool uses) — same git executable detection, same subprocess environment, same 15s timeout, same never-raise contract. `reset_hard` includes toplevel-verify safety (qwen P1-4 / minimax B3 preserved). 9 unit tests in `tests/tools/git/test_workflow_helpers.py`. |
| v1.1 | — | Clone action, path_guard hardening, `check_git_operation()` fail-fast fix |
| v1 | — | Un-multiplex git: 8 atomic actions, `@meta_tool`, semantic params, test restructure |

---

## ⚠️ Breaking Changes

### v1 → v1.1

| Change | Impact |
|--------|--------|
| `clone` action added | New action: clones remote repos into `WORKSPACE_ROOT` |
| `clone` added to `GIT_WORKSPACE_ONLY` | Clone target directory must be within `WORKSPACE_ROOT` |
| `check_git_operation()` silent fallback removed | Non-existent `cwd` now fails fast with clear error instead of silently falling back from `require_exists=True` to `False` |
| Target validation removed from `check_git_operation()` for clone | `clone` target is a remote URL, not a filesystem path |
| `operation` parameter removed | Use `action` only |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Un-multiplex git | ✅ v1 | 8 atomic actions, `@meta_tool`, semantic params, test restructure |
| `@meta_tool` integration | ✅ v1 | Auto-generated `Literal` enum and docstring from DISPATCH |
| Path guard integration | ✅ v1 | `check_git_operation()` validates cwd is within `agent_root`/`workspace_root` |
| Cancellation guard | ✅ v1 | `ensure_not_cancelled(trace_id)` aborts before mutations |
| Repo validation | ✅ v1 | `needs_repo=True` actions call `_check_repo()` before handler |
| Result compression | ✅ v1 | `compress_result()` prevents MCP context overflow |
| Clone action | ✅ v1.1 | Clones remote repos into `WORKSPACE_ROOT` |
| `check_git_operation()` fail-fast | ✅ v1.1 | Non-existent `cwd` now fails fast with clear error |
| `GIT_WORKSPACE_ONLY` scoping | ✅ v1.1 | `init` and `clone` must be within `WORKSPACE_ROOT` |
| Test restructure | ✅ v1 | One test file per action, mirrors source structure |
| `test_git_clone.py` | ✅ v1.1 | Clone action coverage |
| `test_path_guard.py` updated | ✅ v1.1 | Path guard tests for new clone behavior |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Per-action param filtering | Dispatcher only passes params the handler accepts. `@meta_tool` generates param-to-action matrix. | P2 |
| Roll `@meta_tool` to `browser` | `browser` already has clean DISPATCH — low effort, high value | P2 |
| Roll `@meta_tool` to `file` | `file` has DISPATCH from `_registry` — mechanical refactor | P2 |
| Roll `@meta_tool` to `web` | Requires DISPATCH refactor first, then mechanical | P2 |
| Evaluate `memory`, `agent`, `report` | Complex dispatch patterns — may need different approach | P3 |
| Role-aware action visibility | Per-role action filters in router prompt (not schema — FastMCP limitation) | P3 |
| Action telemetry | Automatic usage tracking per action: calls, errors, avg duration | P3 |
| `git push` action | Requires explicit remote name for safety. Enables GitHub tool integration. | P4 |
| GitHub tool | PR/Issue/Release CRUD via GitHub API. Separate tool from git. | P4 |
| Composite action hints | `@meta_tool` exposes "suggested next actions" in metadata for planner guidance | P5 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add here as they are identified.)*

---

*Last updated: 2026-07-22 (v1.3 — git_ops.py docstring clarification). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
