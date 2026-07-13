# 🐙 GitHub Tool

The `github()` tool wraps the GitHub REST API (`httpx`) and two local git subprocesses (`git push` / `git pull`). Same `@meta_tool` + `github_ops/` pattern as `git`, `file`, `web`, `swarm`.

**`git` = local VCS inspection** (`status`, `diff`, `commit`, `branch`). **`github` = remote PR + issue + release workflow + remote sync** (`push`/`pull` + 14 API actions). The only local operations in `github` are `push`/`pull` — they're the remote-sync pair bookending the PR workflow (pull before branching → push after committing).

**16 actions:** `pr_create`/`pr_list`/`pr_get`/`pr_review`/`pr_merge`/`pr_comment`/`push` (v1.0) · `issue_create`/`issue_list`/`issue_comment`/`release_create`/`release_list` (v1.1) · `issue_get`/`issue_update`/`release_get` (v1.2) · `pull` (v1.3)

**Key points:**
- **httpx direct** (not PyGithub) — singleton `httpx.Client` with auth headers, connection pooling
- **Pagination** on `pr_list`/`issue_list`/`release_list` (v1.3.1) — `page` param + `has_next`/`next_page` from Link header
- **`push`/`pull` are subprocesses** (NOT API calls) — list-form args, `--force-with-lease` for `push`, 120s timeout, NOT parallel-safe
- **3-stage error handling** (v1.3.1) — network → HTTP → JSON parse, with `status=` propagating HTTP codes
- **Requires `GITHUB_TOKEN` + `GITHUB_OWNER` + `GITHUB_REPO`** for API actions; `push`/`pull` don't need them (local git remote)

## Quick Start

```python
# Remote sync (subprocess — no GITHUB_TOKEN needed)
github(action="pull")                                              # git pull origin (current branch)
github(action="push", branch="fix/timeout")                        # git push origin fix/timeout
github(action="push", branch="feat/rebase", force=True)            # --force-with-lease

# PRs
github(action="pr_create", title="Fix timeout", head="fix/timeout", base="main", body="...")
github(action="pr_list")                                           # open PRs, page 1
github(action="pr_list", state="closed", limit=10, page=2)         # paginated
github(action="pr_get", number=42)                                 # includes mergeable + mergeable_state
github(action="pr_review", number=42, event="APPROVE", body="LGTM")
github(action="pr_merge", number=42)                               # squash by default
github(action="pr_comment", number=42, body="General comment")
github(action="pr_comment", number=42, body="Line note", path="src/x.py", line=42)  # line-level

# Issues
github(action="issue_list", state="open", labels="bug")
github(action="issue_get", number=42)
github(action="issue_update", number=42, state="closed")           # close
github(action="issue_update", number=42, labels="duplicate")       # re-label only
github(action="issue_comment", number=42, body="Fixed in PR #43")

# Releases
github(action="release_list")
github(action="release_get", tag="v1.2.0")                         # by tag (preferred)
github(action="release_get", number=12345)                          # by ID
github(action="release_create", tag="v1.2.0", title="v1.2.0", body="...")
```

## Configuration

```ini
GITHUB_TOKEN=ghp_your_personal_access_token    # https://github.com/settings/tokens (scope: repo or public_repo)
GITHUB_OWNER=your-github-username-or-org
GITHUB_REPO=your-repo-name
```

All three required for API actions. `push`/`pull` use the local git remote config (SSH/HTTPS) — no env vars needed. Token read once at `httpx.Client` construction; restart agent after changing. Owner/repo read per-call (no restart needed). API base URL hardcoded to `https://api.github.com` (GHE support = Phase 4+ roadmap).

## `github` vs `git`

| Need | Tool |
|------|------|
| Local repo inspection (`status`, `diff`, `log`, `commit`, `branch`, `clone`) | `git(action=...)` |
| Push/pull remote sync | `github(push)` / `github(pull)` |
| PR/issue/release workflow | `github(action=...)` |

`push`/`pull` live in `github_ops/` (not `git_ops/`) because they're the remote-sync pair for the PR workflow — grouping them keeps the full workflow discoverable via `github(action=...)`.

## Documentation

| File | Description |
|------|-------------|
| [API.md](github/API.md) | Full signature, 16 actions, params, errors, security |
| [ARCHITECTURE.md](github/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, testing |
| [CHANGELOG.md](github/CHANGELOG.md) | Version history, roadmap |
| [INSTRUCTIONS.md](github/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-13 (v1.3.1). See subfiles for detailed documentation.*
