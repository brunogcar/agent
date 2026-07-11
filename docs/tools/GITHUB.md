# 🐙 GitHub Tool

The `github()` tool is a **PR-workflow meta-tool** that wraps the GitHub REST API (`httpx`) and two local git subprocesses (`git push` / `git pull`). It uses the same `@meta_tool` + `github_ops/` pattern as `git`, `file`, `web`, `swarm`, etc.

Where `git()` operates on the **local** VCS (`status`, `diff`, `commit`, `branch`, ...), `github()` operates on the **remote** — pulling recent commits, opening pull requests, listing/getting/reviewing/merging/commenting on PRs, and pushing a local branch to `origin` as the prerequisite for the PR workflow. The conceptual split: **`git` = local repo inspection, `github` = remote PR workflow + remote sync**.

**Key characteristics:**
- **PR + issue + release workflow + remote sync in one tool** — `pull` (fetch latest) → `push` (publish local branch) → `pr_create` → `pr_review` → `pr_merge` → `pr_comment` → `issue_create`/`issue_list`/`issue_get`/`issue_update`/`issue_comment` → `release_create`/`release_list`/`release_get` all reachable via `github(action=...)`.
- **16 actions** (v1.3) — `pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `push` (v1.0, 7 actions) + `issue_create`, `issue_list`, `issue_comment`, `release_create`, `release_list` (v1.1, +5 actions) + `issue_get`, `issue_update`, `release_get` (v1.2, +3 actions) + `pull` (v1.3, +1 action)
- **GitHub REST API via httpx** — Direct HTTPS calls to `https://api.github.com` (hardcoded base URL). No PyGithub dependency. Auth: Bearer token in `Authorization` header.
- **Singleton httpx.Client** — `tools/github_ops/client.py` lazily builds one `httpx.Client` with auth headers, reused across all API actions. Connection pooling via httpx. v1.2 added `parse_link_header()` helper for pagination.
- **Pagination on `pr_list` + `issue_list`** (v1.2) — new `page` param + `Link` header parsing via `parse_link_header()`. Response includes `page` / `has_next` / `next_page` so callers iterate `while result["data"]["has_next"]: result = github(action="pr_list", page=result["data"]["next_page"])`.
- **`mergeable` + `mergeable_state` in `pr_get`** (v1.2) — surfaced for pre-merge checks. `mergeable` can be `true`/`false`/`null` (null = still computing, retry).
- **`push` + `pull` are subprocesses, NOT API calls** (v1.3 — `pull` added) — Both use `subprocess.run(["git", "push"|"pull", ...])` with list args (not `shell=True`). No `GITHUB_TOKEN` needed for either — they use the repo's configured git remote (SSH or HTTPS). Together they form the **remote-sync pair** (pull before branching → push after committing).
- **`--force-with-lease` (not `--force`) — `push` only** — `force=True` on `push` uses `--force-with-lease`, which refuses to overwrite remote refs that have moved since the last fetch. Safer than bare `--force`. `pull` has no `force` param (force semantics don't apply to pull).
- **PARALLEL_SAFE for API actions, NOT for `push`/`pull`** (v1.3 — `pull` added) — 14 API actions are stateless HTTP calls (safe to parallelize). Both `push` and `pull` spawn subprocesses and are excluded from `PARALLEL_SAFE` (lock contention on concurrent ops to the same repo). The facade declares `_NOT_PARALLEL_SAFE = frozenset({"push", "pull"})`.
- **`issue_update` unifies close/reopen/edit** (v1.2) — single PATCH action handles state changes AND field edits. `state=""` (the v1.2 facade default) means "don't change"; list actions normalize empty → `"open"`.
- **Requires `GITHUB_TOKEN` + `GITHUB_OWNER` + `GITHUB_REPO`** — All three must be set in `.env` for API actions to work. `is_configured()` short-circuits on the first empty value. `push` and `pull` are the only actions that do NOT require configuration (local subprocess).
- **Auto-discovered** — `@tool` + `@meta_tool` + `@register_action` = zero manual wiring in `server.py`

---

## 🚀 Quick Start

```python
# 0. Pull recent commits before branching (v1.3 — optional, ensures branch is based on latest remote state)
github(action="pull")                                  # git pull origin (current branch)
github(action="pull", branch="main")                    # git pull origin main

# 1. Push a local branch to origin (prerequisite for pr_create)
github(action="push", branch="fix/timeout")

# 2. Open a PR from the pushed branch
github(action="pr_create", title="Fix intermittent search timeout",
       head="fix/timeout", base="main",
       body="Resolves issue #42 by adding exponential backoff to the retry loop.")

# 3. List open PRs on the configured repo (paginated — v1.2)
github(action="pr_list")
# Get the next page when has_next is true:
github(action="pr_list", page=2)

# 4. List closed PRs (state filter, capped at 10 results)
github(action="pr_list", state="closed", limit=10)

# 5. Get details of a specific PR (includes mergeable + mergeable_state — v1.2)
github(action="pr_get", number=42)
# If mergeable is null, GitHub is still computing — retry after a moment.

# 6. Approve a PR (requires push access to the repo)
github(action="pr_review", number=42, event="APPROVE", body="LGTM 🚢")

# 7. Request changes on a PR
github(action="pr_review", number=42, event="REQUEST_CHANGES",
       body="Need a null check on `user` before accessing `user.login` on line 17.")

# 8. Merge a PR (squash by default — keeps history clean)
github(action="pr_merge", number=42)

# 9. Merge with a custom commit title (preserve all commits via "merge")
github(action="pr_merge", number=42, merge_method="merge",
       commit_title="Merge PR #42: Fix intermittent search timeout")

# 10. Leave a general comment on a PR
github(action="pr_comment", number=42, body="Deployed to staging — verifying now.")

# 11. Leave a line-level comment on a PR diff
github(action="pr_comment", number=42,
       body="This null check is the fix — was crashing on empty payloads.",
       path="src/search/retry.py", line=42)

# 12. Force-push a rebased branch (--force-with-lease, NOT --force)
github(action="push", branch="feat/rebase", force=True)

# 13. Issues — list, get, close, reopen, edit (v1.1 + v1.2)
github(action="issue_list", state="open", labels="bug,priority")
github(action="issue_get", number=42)
github(action="issue_update", number=42, state="closed")             # close
github(action="issue_update", number=42, state="open", title="New info")  # reopen + retitile
github(action="issue_update", number=42, labels="duplicate")         # re-label only (state unchanged)
github(action="issue_comment", number=42, body="Fixed in PR #43.")

# 14. Releases — list, get by tag, get by ID (v1.1 + v1.2)
github(action="release_list")
github(action="release_get", tag="v1.2.0")      # by tag (preferred)
github(action="release_get", number=12345)        # by numeric release ID
github(action="release_create", tag="v1.2.0", name="v1.2.0", body="Release notes here")
```

---

## ⚙️ Configuration

Add the following to `.env` (all three are commented out by default — uncomment and fill in):

```ini
# GitHub API (for github tool — PR operations, push)
# Get a token at: https://github.com/settings/tokens
# Required scopes: repo (for private repos) OR public_repo (for public repos only)
GITHUB_TOKEN=ghp_your_personal_access_token_here
GITHUB_OWNER=your-github-username-or-org
GITHUB_REPO=your-repo-name
```

**Rules:**
- All **API actions** (14 of them: `pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `issue_create`, `issue_list`, `issue_get`, `issue_update`, `issue_comment`, `release_create`, `release_list`, `release_get`) require all three env vars. `is_configured()` returns `False` if any is empty — actions then return `fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env")` without making an API call.
- The **`push` and `pull` actions** (v1.3) do NOT require any env vars — they're local `git push` / `git pull` to whatever remote (`origin` by default) the local repo is configured with. Auth for push/pull comes from the repo's git remote config (SSH key or HTTPS credential helper).
- The `GITHUB_TOKEN` is read once at httpx.Client construction time and embedded in the `Authorization: Bearer ...` header. Restart the agent (or call `close_client()`) after changing the token in `.env`.
- The `GITHUB_OWNER` / `GITHUB_REPO` are read at every API call via `repo_path()` — no restart needed when changing repo.
- The GitHub API base URL (`https://api.github.com`) is hardcoded in `tools/github_ops/client.py`. GitHub Enterprise users would need to override `GITHUB_API_BASE` (not yet configurable via env — see CHANGELOG.md roadmap).

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Pull recent commits from `origin` before branching | `github(pull)` | v1.3 — Subprocess `git pull`. Optional `branch` (empty = current branch). Used by autocode `AUTOCODE_PULL_BEFORE_BRANCH` |
| Push a local branch to `origin` | `github(push)` | Subprocess `git push` — prerequisite for `pr_create`. Uses `--force-with-lease` when `force=True` |
| Open a pull request | `github(pr_create)` | POST `/repos/{owner}/{repo}/pulls` — opens PR from head → base |
| List open / closed / all PRs | `github(pr_list)` | GET `/repos/{owner}/{repo}/pulls?state=...` — paginated (`page` + `has_next`/`next_page` from Link header) |
| Get one PR's status (mergeable, reviews, CI) | `github(pr_get)` | GET `/repos/{owner}/{repo}/pulls/{number}` — single PR details incl. `mergeable` + `mergeable_state` (v1.2) |
| Approve / request changes / comment as a review | `github(pr_review)` | POST `/repos/{owner}/{repo}/pulls/{number}/reviews` |
| Merge a PR (squash / merge / rebase) | `github(pr_merge)` | PUT `/repos/{owner}/{repo}/pulls/{number}/merge` |
| Comment on a PR (general or line-level) | `github(pr_comment)` | POST `/issues/{number}/comments` (general) or `/pulls/{number}/comments` (line-level) |
| Open / list / get / update / comment on issues | `github(issue_*)` | v1.1 (`issue_create`/`issue_list`/`issue_comment`) + v1.2 (`issue_get`/`issue_update`) |
| Create / list / get releases | `github(release_*)` | v1.1 (`release_create`/`release_list`) + v1.2 (`release_get` — by tag preferred, or numeric ID) |
| Local repo inspection (`status`, `diff`, `log`, `commit`, `branch`) | `git(action=...)` | Local VCS — does NOT touch the remote. Use this for everything before `push` |
| Clone a remote repo locally | `git(clone)` | Local clone operation — lives in `git` tool, NOT `github` |
| Create a local branch | `git(branch_create)` | Local VCS — `github(push)` only pushes an existing local branch |

**Key distinction — `github` vs `git`:**
- `git()` is **local VCS inspection and mutation** — `status`, `diff`, `log`, `commit`, `branch_create`, `add`, `restore`, `rollback`, `clone` (clone is local: creates a new local repo from a remote URL). Operates on the local `.git` directory via `subprocess.run(["git", ...])`.
- `github()` is **remote PR + issue + release workflow + remote sync** — `push` / `pull` (local subprocess — push local commits to remote / pull recent commits from remote), `pr_create` / `pr_list` / `pr_get` / `pr_review` / `pr_merge` / `pr_comment` (GitHub REST API), `issue_create` / `issue_list` / `issue_get` / `issue_update` / `issue_comment`, `release_create` / `release_list` / `release_get` (GitHub REST API). The ONLY local operations in `github` are `push` and `pull` — and they're only there because they're the remote-sync pair bookending the PR workflow (pull before branching → push after committing).

**Why `push` + `pull` live in `github_ops/` (not `git_ops/`):**
Both `push` and `pull` (v1.3) are conceptually part of the GitHub PR workflow (pull → branch → commit → push → open PR → review → merge). Grouping them with the other PR actions keeps the workflow discoverable: every step from local commit to merged PR is reachable via `github(action=...)`. The `git_ops` tool remains focused on local repo inspection. See `docs/tools/github/ARCHITECTURE.md` → Key Design Decisions for the full rationale.

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [API.md](github/API.md) | Full tool signature, all 16 actions, parameter tables, error handling, security |
| [ARCHITECTURE.md](github/ARCHITECTURE.md) | Module tree, dispatch flow (incl. v1.3 `pull` action flow), design decisions (httpx not PyGithub, push+pull in github_ops not git_ops, PARALLEL_SAFE for API not push/pull, v1.2 `issue_update` unification, v1.2 `state=""` facade default, v1.2 pagination, v1.3 pull/push symmetry), source code reference, testing |
| [CHANGELOG.md](github/CHANGELOG.md) | v1.0 / v1.1 / v1.2 / v1.3 entries, breaking changes (none — new tool), completed, roadmap (Phase 2 shipped in v1.1+v1.2, Phase 3 (v1.3): autocode integration — shipped in autocode v1.3) |
| [INSTRUCTIONS.md](github/INSTRUCTIONS.md) | AI editing rules — NEVER DO (no hardcoded token, no PyGithub, no push/pull in git_ops, no `if number is None:` checks, no `force` on `pull`), ALWAYS DO (pagination pattern, `if not x:` for default-zero params, mergeable=null retry, pull/push symmetry), anti-patterns |

---

*Last updated: 2026-07-10 (v1.3). See subfiles for detailed documentation.*
