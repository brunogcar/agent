# 🐙 GitHub Tool

The `github()` tool is a **PR-workflow meta-tool** that wraps the GitHub REST API (`httpx`) and a single local `git push` subprocess. It uses the same `@meta_tool` + `github_ops/` pattern as `git`, `file`, `web`, `swarm`, etc.

Where `git()` operates on the **local** VCS (`status`, `diff`, `commit`, `branch`, ...), `github()` operates on the **remote** — opening pull requests, listing/getting/reviewing/merging/commenting on PRs, and pushing a local branch to `origin` as the prerequisite for the PR workflow. The conceptual split: **`git` = local repo inspection, `github` = remote PR workflow**.

**Key characteristics:**
- **PR workflow in one tool** — `push` → `pr_create` → `pr_review` → `pr_merge` → `pr_comment` all reachable via `github(action=...)`. No need to leave the tool to complete a PR lifecycle.
- **7 actions** — `pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `push`
- **GitHub REST API via httpx** — Direct HTTPS calls to `https://api.github.com` (hardcoded base URL). No PyGithub dependency. Auth: Bearer token in `Authorization` header.
- **Singleton httpx.Client** — `tools/github_ops/client.py` lazily builds one `httpx.Client` with auth headers, reused across all API actions. Connection pooling via httpx.
- **`push` is a subprocess, not an API call** — Uses `subprocess.run(["git", "push", ...])` with list args (not `shell=True`). No `GITHUB_TOKEN` needed for push — uses the repo's configured git remote (SSH or HTTPS).
- **`--force-with-lease` (not `--force`)** — `force=True` on `push` uses `--force-with-lease`, which refuses to overwrite remote refs that have moved since the last fetch. Safer than bare `--force`.
- **PARALLEL_SAFE for API actions, NOT for push** — API actions are stateless HTTP calls (safe to parallelize). `push` spawns a subprocess and is excluded from `PARALLEL_SAFE` (lock contention on concurrent pushes to the same branch).
- **Requires `GITHUB_TOKEN` + `GITHUB_OWNER` + `GITHUB_REPO`** — All three must be set in `.env` for API actions to work. `is_configured()` short-circuits on the first empty value. `push` is the only action that does NOT require configuration.
- **Auto-discovered** — `@tool` + `@meta_tool` + `@register_action` = zero manual wiring in `server.py`

---

## 🚀 Quick Start

```python
# 1. Push a local branch to origin (prerequisite for pr_create)
github(action="push", branch="fix/timeout")

# 2. Open a PR from the pushed branch
github(action="pr_create", title="Fix intermittent search timeout",
       head="fix/timeout", base="main",
       body="Resolves issue #42 by adding exponential backoff to the retry loop.")

# 3. List open PRs on the configured repo
github(action="pr_list")

# 4. List closed PRs (state filter, capped at 10 results)
github(action="pr_list", state="closed", limit=10)

# 5. Get details of a specific PR
github(action="pr_get", number=42)

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
- All **API actions** (`pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`) require all three env vars. `is_configured()` returns `False` if any is empty — actions then return `fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env")` without making an API call.
- The **`push` action** does NOT require any env vars — it's a local `git push` to whatever remote (`origin` by default) the local repo is configured with. Auth for push comes from the repo's git remote config (SSH key or HTTPS credential helper).
- The `GITHUB_TOKEN` is read once at httpx.Client construction time and embedded in the `Authorization: Bearer ...` header. Restart the agent (or call `close_client()`) after changing the token in `.env`.
- The `GITHUB_OWNER` / `GITHUB_REPO` are read at every API call via `repo_path()` — no restart needed when changing repo.
- The GitHub API base URL (`https://api.github.com`) is hardcoded in `tools/github_ops/client.py`. GitHub Enterprise users would need to override `GITHUB_API_BASE` (not yet configurable via env — see CHANGELOG.md roadmap).

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Push a local branch to `origin` | `github(push)` | Subprocess `git push` — prerequisite for `pr_create`. Uses `--force-with-lease` when `force=True` |
| Open a pull request | `github(pr_create)` | POST `/repos/{owner}/{repo}/pulls` — opens PR from head → base |
| List open / closed / all PRs | `github(pr_list)` | GET `/repos/{owner}/{repo}/pulls?state=...` — client-side slice for `limit` |
| Get one PR's status (mergeable, reviews, CI) | `github(pr_get)` | GET `/repos/{owner}/{repo}/pulls/{number}` — single PR details |
| Approve / request changes / comment as a review | `github(pr_review)` | POST `/repos/{owner}/{repo}/pulls/{number}/reviews` |
| Merge a PR (squash / merge / rebase) | `github(pr_merge)` | PUT `/repos/{owner}/{repo}/pulls/{number}/merge` |
| Comment on a PR (general or line-level) | `github(pr_comment)` | POST `/issues/{number}/comments` (general) or `/pulls/{number}/comments` (line-level) |
| Local repo inspection (`status`, `diff`, `log`, `commit`, `branch`) | `git(action=...)` | Local VCS — does NOT touch the remote. Use this for everything before `push` |
| Clone a remote repo locally | `git(clone)` | Local clone operation — lives in `git` tool, NOT `github` |
| Create a local branch | `git(branch_create)` | Local VCS — `github(push)` only pushes an existing local branch |

**Key distinction — `github` vs `git`:**
- `git()` is **local VCS inspection and mutation** — `status`, `diff`, `log`, `commit`, `branch_create`, `add`, `restore`, `rollback`, `clone` (clone is local: creates a new local repo from a remote URL). Operates on the local `.git` directory via `subprocess.run(["git", ...])`.
- `github()` is **remote PR workflow** — `push` (push local commits to remote), `pr_create` / `pr_list` / `pr_get` / `pr_review` / `pr_merge` / `pr_comment` (GitHub REST API). The ONLY local operation in `github` is `push` — and it's only there because it's the prerequisite for `pr_create`.

**Why `push` lives in `github_ops/` (not `git_ops/`):**
The push step is conceptually part of the GitHub PR workflow (push → open PR → review → merge). Grouping it with the other PR actions keeps the workflow discoverable: every step from local commit to merged PR is reachable via `github(action=...)`. The `git_ops` tool remains focused on local repo inspection. See `docs/tools/github/ARCHITECTURE.md` → Key Design Decisions for the full rationale.

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [API.md](github/API.md) | Full tool signature, all 7 actions, parameter tables, error handling, security |
| [ARCHITECTURE.md](github/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions (httpx not PyGithub, push in github_ops not git_ops, PARALLEL_SAFE for API not push), source code reference, testing |
| [CHANGELOG.md](github/CHANGELOG.md) | v1.0 entry, breaking changes (none — new tool), completed, roadmap (Phase 2: issues + releases, Phase 3: autocode integration) |
| [INSTRUCTIONS.md](github/INSTRUCTIONS.md) | AI editing rules — NEVER DO (no hardcoded token, no PyGithub, no push in git_ops), ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-10. See subfiles for detailed documentation.*
