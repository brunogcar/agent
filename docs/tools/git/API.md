<- Back to [Git Overview](../GIT.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(DISPATCH["git"])
def git(
    action: Literal[
        "status", "log", "diff", "commit", "add", "init",
        "restore", "rollback", "snapshot", "show",
        "branch_list", "branch_create", "branch_delete",
        "tag_list", "tag_create", "tag_delete",
        "checkout_branch", "checkout_new",
    ],
    message: str = "",
    root: str = "agent",
    n: int = 10,
    path: str = "",
    force: bool = False,
    target: str = "",
    trace_id: str = "",
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `Literal[...]` | — | **Required.** Atomic action name. See Actions table below |
| `message` | `str` | `""` | Human-readable text (commit message, snapshot note) |
| `root` | `str` | `"agent"` | Repo directory: `"agent"` \| `"workspace"` \| `"/absolute/path"` |
| `n` | `int` | `10` | Limit for `log` (number of commits) |
| `path` | `str` | `""` | File path for `diff`, `restore`, `add`. Backward-compat alias for absolute dirs |
| `force` | `bool` | `False` | Destructive flag for `rollback`, `branch_delete` |
| `target` | `str` | `""` | Entity name: branch, tag, commit hash, ref |
| `trace_id` | `str` | `""` | Trace identifier for observability |

**Removed in v1:** `operation` parameter. Use `action` only.

---

## ⚡ Actions

### Read-Only Actions

| Action | Required Params | Optional Params | Description |
|--------|-----------------|-----------------|-------------|
| `status` | — | `root` | Working tree status: branch, changes, clean flag |
| `log` | — | `n` (default 10), `root` | Recent commit history |
| `diff` | — | `path`, `max_lines`, `root` | Unstaged diff, optionally filtered by file |
| `show` | — | `target` (default HEAD), `root` | Commit/tag/tree details, capped at 10KB |
| `branch_list` | — | `root` | List local branches with current marker |
| `tag_list` | — | `root` | List all lightweight tags |

### Write Actions (require valid repo)

| Action | Required Params | Optional Params | Description |
|--------|-----------------|-----------------|-------------|
| `branch_create` | `target` | `root` | Create branch at current HEAD (does NOT switch) |
| `branch_delete` | `target` | `force`, `root` | Delete merged branch. `force=True` for unmerged |
| `tag_create` | `target` | `root` | Create lightweight tag at current HEAD |
| `tag_delete` | `target` | `root` | Delete a local tag |
| `checkout_branch` | `target` | `root` | Switch to existing branch/tag/commit |
| `checkout_new` | `target` | `root` | Create and switch to new branch (`git checkout -b`) |
| `commit` | `message` | `root` | Stage all + commit. Returns `nothing_to_commit` if clean |
| `add` | — | `path`, `all_files`, `root` | Stage specific file or all changes |
| `init` | — | `root` | Init repo + .gitignore + initial commit |
| `restore` | `path` | `message` (commit ref), `root` | Restore file to HEAD or specified commit |
| `rollback` | — | `force`, `root` | Reset to HEAD. Safe stash or force discard |
| `snapshot` | — | `message`, `root` | Stage all + timestamped commit (safe rollback point) |

### Clone Action (v1.1)

```python
git(action="clone", target="https://github.com/user/repo.git")
git(action="clone", target="https://github.com/user/repo.git", path="my_folder")
```

| Param | Required | Description |
|-------|----------|-------------|
| `target` | ✅ | Remote repository URL |
| `path` | ❌ | Local directory name (defaults to repo name from URL) |

**Restrictions:**
- Clone target must be within `WORKSPACE_ROOT`.
- Cannot clone into an existing directory.
- Returns: `{status: "cloned", path, url, root}`

---

### Action Details

#### `branch_create` vs `checkout_new`

```python
# Creates branch pointer only — does NOT switch
git(action="branch_create", target="experiment")

# Creates AND switches — equivalent to `git checkout -b`
git(action="checkout_new", target="experiment")
```

#### `branch_delete` — Safe vs Force

```python
# Safe delete — only if merged
git(action="branch_delete", target="old-fix")

# Force delete — even if unmerged (destructive)
git(action="branch_delete", target="wip", force=True)
```

#### `tag_create` — Lightweight Only

```python
# Lightweight tag (current behavior)
git(action="tag_create", target="v1.0")

# Annotated tags = future `tag_annotate` action (not yet implemented)
```

#### `show` — Target Parameter (not message)

```python
# v1: use target for commit hash/tag name
git(action="show", target="abc1234")
git(action="show", target="v1.0")

# Default: shows HEAD
git(action="show")
```

---

## 🔒 Security

### Path Resolution

All paths are resolved through `core.path_guard.resolve_path()` before any git operation:

| Path Type | Behavior |
|-----------|----------|
| **Relative** | Resolved against `default_root` ("agent" or "workspace") |
| **Absolute** | Allowed only if within `AGENT_ROOT` |
| **Traversal** (`../..`) | Blocked if resolves outside `AGENT_ROOT` |
| **Null bytes** | Blocked immediately |
| **Symlinks** | Followed via `Path.resolve()` — escapes caught by `_is_within()` |

**Git scoping:** `init` and `clone` MUST be within `WORKSPACE_ROOT`. All other operations must be within `AGENT_ROOT`.

**v1.1 fix:** `check_git_operation()` no longer silently falls back from `require_exists=True` to `False`. A non-existent `cwd` now fails fast with a clear error.

**v1.1:** `clone` target is a remote URL, not a filesystem path. The handler validates the derived local directory path.

### Safety Features

| Feature | Implementation |
|---------|---------------|
| **Path guard** | `check_git_operation()` validates cwd is within `agent_root`/`workspace_root` |
| **Cancellation guard** | `ensure_not_cancelled(trace_id)` aborts before mutations |
| **Repo validation** | `needs_repo=True` actions call `_check_repo()` before handler |
| **Excluded commands** | `fetch`, `pull`, `merge`, `rebase`, `push` — require human judgement |
| **Safe rollback** | `rollback` stashes changes before reset (recoverable) |
| **Force flag** | `force=True` required for destructive operations |
| **Result compression** | `compress_result()` prevents MCP context overflow |
| **Timeout** | All git commands timeout at 15s |

---

## 📤 Output

All actions return standardized `dict` via `compress_result()`.

*(Fill this section with relevant info from edits and refactors. Add output format details as they are learned.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
