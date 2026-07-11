<- Back to [GitHub Overview](../GITHUB.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(DISPATCH["github"], doc_sections=[...])
def github(
    action: str,
    title: str = "",
    head: str = "",
    base: str = "main",
    body: str = "",
    number: int = 0,
    state: str = "",
    limit: int = 30,
    page: int = 1,
    event: str = "",
    merge_method: str = "squash",
    commit_title: str = "",
    commit_message: str = "",
    path: str = "",
    line: int = 0,
    side: str = "RIGHT",
    branch: str = "",
    remote: str = "origin",
    force: bool = False,
    labels: str = "",
    assignees: str = "",
    tag: str = "",
    draft: bool = False,
    prerelease: bool = False,
    trace_id: str = "",
) -> dict:
    """GitHub API meta-tool — PR + issue + release operations and git push."""
```

> **Note:** Like `swarm()`, the github facade uses `action: str` and dispatches manually via `DISPATCH["github"][action]`. Unknown actions return a `fail()` result listing all 15 valid actions, rather than being rejected by a `Literal` schema layer. The `@meta_tool` decorator is applied (for `doc_sections` and metadata) but the `Literal` enum patch is **not** generated.

> **v1.2 facade changes:** `state` default changed from `"open"` to `""` (list actions `pr_list`/`issue_list` internally default to `"open"` when empty — no caller-visible behavior change; `issue_update` treats `""` as "don't change" to enable the unified close/reopen/edit design). New `page: int = 1` param added (used by `pr_list`/`issue_list` for pagination).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** One of: `pr_create` \| `pr_list` \| `pr_get` \| `pr_review` \| `pr_merge` \| `pr_comment` \| `push` \| `issue_create` \| `issue_list` \| `issue_get` \| `issue_update` \| `issue_comment` \| `release_create` \| `release_list` \| `release_get`. Lowercased + stripped before dispatch |
| `title` | `str` | `""` | PR/issue title (used by `pr_create`, `issue_create`, `issue_update`) |
| `head` | `str` | `""` | Source branch name — what to merge FROM (used by `pr_create`) |
| `base` | `str` | `"main"` | Target branch name — what to merge INTO (used by `pr_create`) |
| `body` | `str` | `""` | Markdown body / description (used by `pr_create`, `pr_review`, `pr_comment`, `issue_create`, `issue_update`) |
| `number` | `int` | `0` | PR/issue/release number (used by `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `issue_get`, `issue_update`, `release_get` when `tag` is empty). Coerced to int — numeric str accepted |
| `state` | `str` | `""` | Filter for `pr_list`/`issue_list` (internally defaults to `"open"` when empty; one of `open`/`closed`/`all`). For `issue_update`: `"open"`/`"closed"` changes state; `""` = don't change |
| `limit` | `int` | `30` | Max items to return per page (used by `pr_list`, `issue_list`). Capped at 100 per GitHub API per_page maximum |
| `page` | `int` | `1` | Page number for pagination (used by `pr_list`, `issue_list`). Use when a repo has >100 items — the response includes `has_next`/`next_page` from the Link header |
| `event` | `str` | `""` | Review event: `APPROVE`, `REQUEST_CHANGES`, `COMMENT` (used by `pr_review`) |
| `merge_method` | `str` | `"squash"` | Merge method: `merge`, `squash`, `rebase` (used by `pr_merge`) |
| `commit_title` | `str` | `""` | Custom merge commit title (used by `pr_merge`) |
| `commit_message` | `str` | `""` | Custom merge commit body (used by `pr_merge`) |
| `path` | `str` | `""` | File path — triggers line-level comment mode when paired with `line` (used by `pr_comment`) |
| `line` | `int` | `0` | Line number — triggers line-level comment mode when paired with `path` (used by `pr_comment`) |
| `side` | `str` | `"RIGHT"` | Diff side: `LEFT` (base) or `RIGHT` (head) — only used in line-level mode (used by `pr_comment`) |
| `branch` | `str` | `""` | Local branch name to push (used by `push`) |
| `remote` | `str` | `"origin"` | Remote name to push to (used by `push`) |
| `force` | `bool` | `False` | If True, use `--force-with-lease` (NOT `--force`) — safer (used by `push`) |
| `labels` | `str` | `""` | Comma-separated labels (used by `issue_create`, `issue_list`, `issue_update`) |
| `assignees` | `str` | `""` | Comma-separated logins (used by `issue_create`, `issue_update`) |
| `tag` | `str` | `""` | Tag name for release lookup/creation (used by `release_create`, `release_get`) |
| `draft` | `bool` | `False` | If True, create a draft release (used by `release_create`) |
| `prerelease` | `bool` | `False` | If True, mark release as prerelease (used by `release_create`) |
| `trace_id` | `str` | `""` | Trace identifier for observability. Auto-injected into the result dict |

**Dispatch behavior:**
1. `action` is lowercased + stripped; empty → `fail("action is required")`.
2. `DISPATCH["github"][action]` lookup; unknown → `fail(f"Unknown action '<x>'. Use: {sorted valid actions}")`.
3. All kwargs forwarded to the handler (`**kwargs` absorbs unused params per handler).
4. Handler exceptions caught and returned as `fail(f"GitHub action failed: {e}")`.
5. `duration_ms` (total wall time) appended to every result.
6. `trace_id` injected into the result if missing.

---

## ⚡ Actions

### Summary Table

| Action | Required Params | Optional Params | Purpose |
|--------|-----------------|-----------------|---------|
| `pr_create` | `title`, `head` | `base`, `body` | Open a new pull request from a head branch into a base branch |
| `pr_list` | — | `state`, `limit`, `page` | List pull requests filtered by state (open / closed / all), paginated |
| `pr_get` | `number` | — | Fetch detailed info for a single pull request (incl. `mergeable` + `mergeable_state`) |
| `pr_review` | `number`, `event` | `body`, `commit_id` | Submit a review (APPROVE / REQUEST_CHANGES / COMMENT) |
| `pr_merge` | `number` | `merge_method`, `commit_title`, `commit_message` | Merge a pull request (squash / merge / rebase) |
| `pr_comment` | `number`, `body` | `path`, `line`, `side` | Post a comment — general OR line-level (dual-mode) |
| `issue_create` | `title` | `body`, `labels`, `assignees` | Open a new issue |
| `issue_list` | — | `state`, `labels`, `limit`, `page` | List issues filtered by state + labels, paginated |
| `issue_get` | `number` | — | Fetch detailed info for a single issue |
| `issue_update` | `number` + at least one field | `state`, `title`, `body`, `labels`, `assignees` | Close / reopen / edit an issue (unified) |
| `issue_comment` | `number`, `body` | — | Comment on an issue or PR (shared endpoint) |
| `release_create` | `tag` | `name`, `body`, `draft`, `prerelease` | Create a release from a tag |
| `release_list` | — | `limit` | List releases |
| `release_get` | `tag` OR `number` | — | Fetch a single release by tag (preferred) or numeric ID |
| `push` | `branch` | `remote`, `force` | Push a local branch to the remote via `git push` (subprocess) |

---

### `pr_create` — Open a New Pull Request

**Purpose:** Open a new PR on the configured GitHub repo from a head branch into a base branch. The head branch must already exist on the remote — call `github(action="push", branch="...")` first if you've only committed locally.

**Required params:** `title`, `head`

**Optional params:** `base` (default `"main"`), `body` (markdown description)

**Example:**
```python
github(action="pr_create", title="Fix timeout bug", head="fix/timeout", base="main")
github(action="pr_create", title="Add login page", head="feat/login",
       body="Closes #12. Implements OAuth2 login flow with session refresh.")
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "number": 42,
    "title": "Fix timeout bug",
    "url": "https://github.com/owner/repo/pull/42",
    "state": "open",
    "head": "fix/timeout",
    "base": "main"
  },
  "error": null,
  "duration_ms": 845
}
```

**Notes:**
- Calls `POST /repos/{owner}/{repo}/pulls`.
- The `body` field is omitted from the API payload if empty (GitHub treats absent vs empty body identically).
- On HTTP 4xx/5xx, returns `fail(f"GitHub API error {status_code}: {message}")` with the GitHub error message extracted from the JSON response body.

---

### `pr_list` — List Pull Requests

**Purpose:** Fetch a list of PRs on the configured repo, filtered by state and capped at a caller-supplied limit. Supports pagination via the `page` param for repos with more than 100 PRs.

**Required params:** none

**Optional params:** `state` (default `"open"` — pass `""`, `"open"`, `"closed"`, or `"all"`; empty defaults to `"open"`), `limit` (default `30`, capped at 100), `page` (default `1` — for pagination beyond 100 items)

**Example:**
```python
github(action="pr_list")
github(action="pr_list", state="closed", limit=10)
github(action="pr_list", state="all", page=2)  # second page of results
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "count": 2,
    "pulls": [
      {
        "number": 42,
        "title": "Fix timeout bug",
        "state": "open",
        "head": "fix/timeout",
        "base": "main",
        "url": "https://github.com/owner/repo/pull/42",
        "draft": false
      },
      {
        "number": 41,
        "title": "Add login page",
        "state": "open",
        "head": "feat/login",
        "base": "main",
        "url": "https://github.com/owner/repo/pull/41",
        "draft": true
      }
    ],
    "page": 1,
    "has_next": true,
    "next_page": 2
  },
  "error": null,
  "duration_ms": 412
}
```

**Notes:**
- Calls `GET /repos/{owner}/{repo}/pulls?state=...&per_page=...&page=...`.
- The GitHub API caps `per_page` at 100 for this endpoint. `pr_list` computes `per_page = min(limit, 100)` and slices `items[:limit]` after extraction — the returned count never exceeds the caller's request even if GitHub returns more.
- Results are returned in GitHub's default order (newest first by `created_at` descending).
- Invalid `state` values are rejected before any API call: `fail(f"state must be one of 'open', 'closed', 'all' — got {state!r}")`.
- **Pagination (v1.2):** when `page > 1` is passed, the same `per_page`/`limit` slice applies to that page's results. The `Link` response header is parsed by `parse_link_header()` (in `client.py`) and surfaced as `has_next` (bool) + `next_page` (int or `None`). If `has_next` is `True`, call again with `page=next_page` to fetch the next page. If the response has no `Link` header (e.g. a single-page result), `has_next=False` and `next_page=None`.

---

### `pr_get` — Get a Single Pull Request

**Purpose:** Fetch detailed info for a single PR — useful for checking mergeable state, draft flag, full body, and timestamps before merging or reviewing.

**Required params:** `number`

**Optional params:** none

**Example:**
```python
github(action="pr_get", number=42)
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "number": 42,
    "title": "Fix timeout bug",
    "state": "open",
    "merged": false,
    "mergeable": true,
    "mergeable_state": "clean",
    "draft": false,
    "head": "fix/timeout",
    "base": "main",
    "url": "https://github.com/owner/repo/pull/42",
    "body": "Resolves issue #42 by adding exponential backoff.",
    "user": "octocat",
    "created_at": "2026-07-09T14:32:11Z",
    "updated_at": "2026-07-10T08:15:42Z"
  },
  "error": null,
  "duration_ms": 287
}
```

**Notes:**
- Calls `GET /repos/{owner}/{repo}/pulls/{number}`.
- 404 → `fail(f"PR #{pr_number} not found", status=404)` (specific message + status code).
- `number` is coerced to int — numeric strings like `"42"` are accepted.
- The `merged` boolean reflects whether the PR has been merged (GitHub returns `false` for unmerged PRs, including closed-without-merge ones).
- **`mergeable` + `mergeable_state` (v1.2):** surfaced directly from the GitHub API response. `mergeable` is `true`/`false`/`null` — `null` means GitHub is still computing it (rare; usually right after a push). If you see `null`, wait a moment and call `pr_get` again. `mergeable_state` is one of `"clean"` / `"blocked"` / `"unstable"` / `"dirty"` / `"unknown"`:
  - `"clean"` — no conflicts, all required checks/reviews satisfied → safe to merge.
  - `"blocked"` — required reviews or status checks not satisfied.
  - `"unstable"` — failing non-required status checks (e.g. CI red, but mergeable).
  - `"dirty"` — merge conflict; the head branch needs a rebase.
  - `"unknown"` — GitHub hasn't computed it yet (similar to `mergeable=null`).
- Use this BEFORE `pr_merge` to pre-check the `mergeable` state and avoid the 405 "not mergeable" failure.

---

### `pr_review` — Submit a Review

**Purpose:** Submit a review on a PR — `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`. Requires push access to the repo for `APPROVE` / `REQUEST_CHANGES`; `COMMENT` works for any authenticated user.

**Required params:** `number`, `event` (one of `APPROVE`, `REQUEST_CHANGES`, `COMMENT`)

**Optional params:** `body` (markdown review text), `commit_id` (SHA of specific commit to review)

**Example:**
```python
github(action="pr_review", number=42, event="APPROVE", body="LGTM 🚢")
github(action="pr_review", number=42, event="REQUEST_CHANGES",
       body="Need a null check on line 17")
github(action="pr_review", number=42, event="COMMENT", body="Just a note")
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "id": 12345678,
    "state": "APPROVED",
    "url": "https://github.com/owner/repo/pull/42#pullrequestreview-12345678"
  },
  "error": null,
  "duration_ms": 521
}
```

**Notes:**
- Calls `POST /repos/{owner}/{repo}/pulls/{number}/reviews`.
- `event` is validated client-side against `_VALID_REVIEW_EVENTS = ("APPROVE", "REQUEST_CHANGES", "COMMENT")` — invalid values fail fast with `fail(f"event must be one of {...} — got {event!r}")` before any API call. This avoids a 422 from GitHub.
- `body` and `commit_id` are omitted from the payload if empty.
- GitHub blocks self-approval in most configurations — you cannot review your own PR.
- 404 → `fail(f"PR #{pr_number} not found", status=404)`.

---

### `pr_merge` — Merge a Pull Request

**Purpose:** Merge a PR via `squash`, `merge`, or `rebase`. Requires the PR to be mergeable (status checks passing if required, no conflicts, required reviews satisfied).

**Required params:** `number`

**Optional params:** `merge_method` (default `"squash"`, one of `merge`/`squash`/`rebase`), `commit_title`, `commit_message`

**Example:**
```python
github(action="pr_merge", number=42)
github(action="pr_merge", number=42, merge_method="squash")
github(action="pr_merge", number=42, merge_method="merge",
       commit_title="Merge PR #42: Fix intermittent search timeout")
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "merged": true,
    "sha": "6dcb09b5b57875f334f61aebed695e2e4193db5e",
    "message": "Pull request successfully merged"
  },
  "error": null,
  "duration_ms": 1102
}
```

**Notes:**
- Calls `PUT /repos/{owner}/{repo}/pulls/{number}/merge`.
- Default `merge_method="squash"` keeps history clean — one commit per PR on the base branch. Use `"merge"` to preserve all commits (creates a merge commit), or `"rebase"` to add commits on top of the base without a merge commit.
- Specific HTTP error handling:
  - 404 → `fail(f"PR #{pr_number} not found", status=404)`
  - 405 → `fail(f"PR #{pr_number} is not mergeable (conflict, blocked, or required checks not satisfied)", status=405)` — call `pr_get` first to check the `mergeable` state.
  - 409 → `fail(f"PR #{pr_number} head commit is not up to date — rebase and push again", status=409)` — head has moved; rebase onto base and `github(action="push", force=True)`.
- `commit_title` and `commit_message` are omitted from the payload if empty (GitHub uses defaults).

---

### `pr_comment` — Post a Comment (Dual-Mode)

**Purpose:** Post a comment on a PR. Two modes:

1. **General PR comment** — POST `/repos/{owner}/{repo}/issues/{number}/comments` — triggered when `path` and `line` are NOT both provided. This is the standard "leave a comment on the PR" flow (GitHub treats PRs as issues for general comments).
2. **Line-level (review) comment** — POST `/repos/{owner}/{repo}/pulls/{number}/comments` — triggered when `path` AND `line` are BOTH provided. Comments inline on a specific line of a specific file. Requires `side` (LEFT or RIGHT, default RIGHT) and the PR's diff must contain that line.

**Required params:** `number`, `body`

**Optional params:** `path` (file path for line-level), `line` (line number for line-level), `side` (default `"RIGHT"`)

**Example:**
```python
# General comment
github(action="pr_comment", number=42, body="This needs a null check")

# Line-level comment
github(action="pr_comment", number=42,
       body="Missing error handling here",
       path="src/main.py", line=42)

# Line-level on the LEFT (base) side of the diff
github(action="pr_comment", number=42,
       body="Pre-commit hook fails on this line",
       path="tests/test_main.py", line=17, side="LEFT")
```

**Return format (general):**
```json
{
  "status": "success",
  "data": {
    "id": 987654321,
    "url": "https://github.com/owner/repo/issues/42#issuecomment-987654321",
    "body": "This needs a null check"
  },
  "error": null,
  "duration_ms": 398
}
```

**Return format (line-level):**
```json
{
  "status": "success",
  "data": {
    "id": 1234567890,
    "url": "https://github.com/owner/repo/pull/42#discussion_r1234567890",
    "body": "Missing error handling here",
    "path": "src/main.py",
    "line": 42
  },
  "error": null,
  "duration_ms": 441
}
```

**Notes:**
- XOR validation on `path` / `line` — providing one without the other returns `fail("path and line must be provided together for line-level comments (got path=..., line=...)")`. Both or neither, never just one.
- Line-level payload includes `subject_type: "line"` per GitHub API v3 spec.
- `side` is validated against `("LEFT", "RIGHT")` ONLY in line-level mode.
- Line-level comments via this endpoint are NOT part of a review and will appear as "pending" until someone submits them via the UI. For proper review-thread comments, use `pr_review` with `event="COMMENT"` (deferred — see CHANGELOG.md roadmap).
- 404 → `fail(f"PR #{pr_number} not found", status=404)`.

---

### `push` — Push a Local Branch to the Remote

**Purpose:** Push a local branch to a git remote (default `origin`) via `git push`. This is a **local subprocess operation**, NOT a GitHub API call — it does NOT require `GITHUB_TOKEN`. It's grouped under the `github` tool because pushing a local branch to `origin` is the prerequisite for any PR workflow.

**Required params:** `branch`

**Optional params:** `remote` (default `"origin"`), `force` (default `False` → uses `--force-with-lease`)

**Example:**
```python
github(action="push", branch="fix/timeout")
github(action="push", branch="fix/timeout", remote="origin")
github(action="push", branch="feat/rebase", force=True)  # uses --force-with-lease
```

**Return format (success):**
```json
{
  "status": "success",
  "data": {
    "status": "ok",
    "branch": "fix/timeout",
    "remote": "origin",
    "pushed": true,
    "output": "To github.com:owner/repo.git\n   abc1234..def5678  fix/timeout -> fix/timeout",
    "forced": false
  },
  "error": null,
  "duration_ms": 1843
}
```

**Return format (non-zero exit):**
```json
{
  "status": "error",
  "data": null,
  "error": "git push failed (exit 1): ! [rejected] fix/timeout -> fix/timeout (fetch first)\n...",
  "branch": "fix/timeout",
  "remote": "origin",
  "exit_code": 1,
  "output": "! [rejected] fix/timeout -> fix/timeout (fetch first)\n...",
  "duration_ms": 412
}
```

**Notes:**
- Uses `subprocess.run(["git", "push", [--force-with-lease], remote, branch])` — **list form, NOT `shell=True`** for safety.
- `force=True` uses `--force-with-lease` (NOT `--force`), which refuses to overwrite remote refs that have moved since the last fetch. Safer than bare `--force` — prevents accidental history destruction when a teammate has pushed in the meantime.
- 120-second subprocess timeout. On timeout → `fail(f"git push timed out after 120s (branch=..., remote=...)")`.
- `FileNotFoundError` (git not installed) → `fail("git executable not found — install git and ensure it is on PATH")`.
- Defense-in-depth: rejects branch/remote names containing shell metacharacters (`;`, `&`, `|`, `$`, backtick, `(`, `)`, `<`, `>`, `\n`, `\r`). Git branch names cannot contain these anyway, so this catches programming errors.
- Combined `stdout + stderr` in the output field — git push writes progress and ref-update info to stderr by default.
- NOT parallel-safe — concurrent `git push` to the same branch will fail with lock contention. Excluded from `PARALLEL_SAFE`.

---

### `issue_list` — List Issues

**Purpose:** Fetch a list of issues on the configured repo, filtered by state and (optionally) labels. Supports pagination via the `page` param for repos with more than 100 issues.

**Required params:** none

**Optional params:** `state` (default `"open"` — pass `""`, `"open"`, `"closed"`, or `"all"`; empty defaults to `"open"`), `labels` (comma-separated label names — only issues with ALL of these labels are returned), `limit` (default `30`, capped at 100), `page` (default `1` — for pagination beyond 100 items)

**Example:**
```python
github(action="issue_list")
github(action="issue_list", state="closed", limit=10)
github(action="issue_list", labels="bug,priority", page=2)
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "count": 2,
    "issues": [
      {
        "number": 42,
        "title": "Search returns 500 on empty query",
        "state": "open",
        "url": "https://github.com/owner/repo/issues/42",
        "labels": ["bug", "priority"],
        "assignee": "octocat"
      },
      {
        "number": 41,
        "title": "Add dark mode toggle",
        "state": "open",
        "url": "https://github.com/owner/repo/issues/41",
        "labels": ["enhancement"],
        "assignee": ""
      }
    ],
    "page": 1,
    "has_next": false,
    "next_page": null
  },
  "error": null,
  "duration_ms": 388
}
```

**Notes:**
- Calls `GET /repos/{owner}/{repo}/issues?state=...&per_page=...&page=...&labels=...&sort=created&direction=desc`.
- The GitHub API caps `per_page` at 100. `issue_list` computes `per_page = min(limit, 100)` and slices `items[:limit]` after extraction.
- GitHub's `/issues` endpoint includes PRs (PRs are issues) — but with `labels` filtering and the default `state=open` filter, the result set is typically issues-only in practice. If you need to exclude PRs, filter client-side by checking the absence of a `pull_request` field on each item.
- Invalid `state` values are rejected before any API call: `fail(f"state must be one of 'open', 'closed', 'all' — got {state!r}")`.
- **Pagination (v1.2):** the `Link` response header is parsed by `parse_link_header()` (in `client.py`) and surfaced as `has_next` (bool) + `next_page` (int or `None`). If `has_next` is `True`, call again with `page=next_page` to fetch the next page.

---

### `issue_get` — Get a Single Issue

**Purpose:** Fetch detailed info for a single issue — useful for inspecting the body, labels, assignee, and timestamps before commenting or updating.

**Required params:** `number`

**Optional params:** none

**Example:**
```python
github(action="issue_get", number=42)
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "number": 42,
    "title": "Search returns 500 on empty query",
    "state": "open",
    "body": "Steps to reproduce: ...",
    "url": "https://github.com/owner/repo/issues/42",
    "labels": ["bug", "priority"],
    "assignee": "octocat",
    "user": "alice",
    "created_at": "2026-07-08T10:11:12Z",
    "updated_at": "2026-07-10T08:15:42Z",
    "closed_at": null
  },
  "error": null,
  "duration_ms": 244
}
```

**Notes:**
- Calls `GET /repos/{owner}/{repo}/issues/{number}`.
- 404 → `fail(f"Issue #{issue_number} not found", status=404)`.
- `number` is coerced to int — numeric strings like `"42"` are accepted.
- `closed_at` is `null` for open issues (GitHub returns the timestamp only when the issue is closed).
- PRs are issues in GitHub's data model — calling `issue_get` with a PR number returns the PR's "issue view" (no `mergeable` / `head` / `base` fields). Use `pr_get` for PR-specific details.

---

### `issue_update` — Update an Issue (close / reopen / edit, unified)

**Purpose:** Update an issue's state (close/reopen) and/or its fields (title, body, labels, assignees) in a single PATCH call. This action **unifies** the roadmap's planned `issue_close` + `issue_reopen` split — one endpoint, one action, one `state` param.

**Required params:** `number` AND at least one of: `state`, `title`, `body`, `labels`, `assignees`

**Optional params:** `state` (`"open"` / `"closed"` / `""`), `title`, `body`, `labels` (comma-separated), `assignees` (comma-separated)

**Example:**
```python
# Close an issue
github(action="issue_update", number=42, state="closed")

# Reopen with a new title
github(action="issue_update", number=42, state="open", title="Reopened with new info")

# Edit only the labels (state unchanged)
github(action="issue_update", number=7, labels="bug,priority")

# Reassign
github(action="issue_update", number=7, assignees="alice,bob")
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "number": 42,
    "title": "Reopened with new info",
    "state": "open",
    "url": "https://github.com/owner/repo/issues/42"
  },
  "error": null,
  "duration_ms": 514
}
```

**Notes:**
- Calls `PATCH /repos/{owner}/{repo}/issues/{number}`.
- **`state=""` = don't change (v1.2 design):** the facade defaults `state` to `""`. When `state` is empty, it is **omitted** from the PATCH payload — GitHub leaves the current state untouched. Pass `"open"` to reopen, `"closed"` to close. This is what enables the unified close/reopen/edit design: a single action handles all three use cases without needing a separate "no-op" sentinel.
- The same "omit-if-empty" rule applies to `title`, `body`, `labels`, `assignees` — only fields you explicitly set are included in the PATCH.
- `labels` and `assignees` are comma-separated strings, split + trimmed client-side before being sent as JSON arrays. They REPLACE the existing labels/assignees (not append). To append, call `issue_get` first, merge, then `issue_update`.
- Invalid `state` values (anything other than `""`, `"open"`, `"closed"`) → `fail(f"state must be 'open' or 'closed' — got {state!r}")`.
- If NO field is provided (everything empty), → `fail("At least one of state, title, body, labels, assignees must be provided")` — guard against no-op PATCHes.
- 404 → `fail(f"Issue #{issue_number} not found", status=404)`.

---

### `release_get` — Get a Single Release

**Purpose:** Fetch detailed info for a single release — by tag name (preferred) or by numeric release ID. Tag-based lookup is the default since you usually know the tag from `release_list` or `git tag`.

**Required params:** `tag` (tag name) OR `number` (numeric release ID). `tag` takes priority if both are provided.

**Optional params:** none

**Example:**
```python
# By tag (preferred — user-friendly)
github(action="release_get", tag="v1.2.0")

# By numeric release ID (use when you have it from release_list)
github(action="release_get", number=12345)
```

**Return format:**
```json
{
  "status": "success",
  "data": {
    "id": 12345,
    "tag": "v1.2.0",
    "name": "v1.2.0 — Issue / Release reads + pagination",
    "url": "https://github.com/owner/repo/releases/tag/v1.2.0",
    "draft": false,
    "prerelease": false,
    "created_at": "2026-07-10T10:00:00Z",
    "published_at": "2026-07-10T11:00:00Z",
    "body": "## Changes\n- 3 new actions: issue_get, issue_update, release_get\n- Pagination on pr_list + issue_list\n- mergeable + mergeable_state in pr_get",
    "assets": [
      {
        "name": "agent-1.2.0.tar.gz",
        "url": "https://github.com/owner/repo/releases/download/v1.2.0/agent-1.2.0.tar.gz",
        "size": 1048576,
        "download_count": 42
      }
    ]
  },
  "error": null,
  "duration_ms": 311
}
```

**Notes:**
- Calls `GET /repos/{owner}/{repo}/releases/tags/{tag}` when `tag` is provided (preferred), OR `GET /repos/{owner}/{repo}/releases/{id}` when only `number` is provided.
- 404 → `fail(f"Release {label} not found", status=404)` where `label` is `f"tag {tag!r}"` or `f"ID {number!r}"` depending on which lookup was attempted.
- `tag` takes priority — if both `tag` and `number` are provided, the tag-based URL is used and `number` is ignored.
- If neither `tag` nor `number` is provided → `fail("tag or number is required for release_get")`.
- `number` is coerced to int — numeric strings like `"12345"` are accepted.
- `assets` is a list of `{name, url, size, download_count}` dicts. `size` is in bytes. `url` is the `browser_download_url` (direct download link). Empty releases return `assets: []`.
- `created_at` and `published_at` are empty strings for draft releases (not yet published).

---

## ❗ Error Handling

All errors return a standardized `fail()` dict:

```json
{
  "status": "error",
  "data": null,
  "error": "Descriptive message",
  "trace_id": "abc123"
}
```

| Error | Trigger | Includes |
|-------|---------|----------|
| `action is required` | Empty `action` param | — |
| `Unknown action '<x>'. Use: {sorted valid actions}` | Action not in DISPATCH | — |
| `GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env` | API action called with empty token/owner/repo | — |
| `<param> is required for <action>` | Missing required param (validated client-side) | — |
| `state must be one of 'open', 'closed', 'all'` | Invalid `state` on `pr_list` / `issue_list` | — |
| `state must be 'open' or 'closed'` | Invalid `state` on `issue_update` (only `"open"`/`"closed"`/`""` allowed; `""` = don't change) | — |
| `event must be one of ('APPROVE', 'REQUEST_CHANGES', 'COMMENT')` | Invalid `event` on `pr_review` | — |
| `merge_method must be one of ('merge', 'squash', 'rebase')` | Invalid `merge_method` on `pr_merge` | — |
| `path and line must be provided together for line-level comments` | XOR violation on `pr_comment` | — |
| `At least one of state, title, body, labels, assignees must be provided` | No-op PATCH on `issue_update` | — |
| `tag or number is required for release_get` | Neither `tag` nor `number` provided on `release_get` | — |
| `PR #{number} not found` | HTTP 404 on `pr_get` / `pr_review` / `pr_merge` / `pr_comment` | `status: 404` |
| `Issue #{number} not found` | HTTP 404 on `issue_get` / `issue_update` | `status: 404` |
| `Release {tag-or-ID} not found` | HTTP 404 on `release_get` | `status: 404` |
| `PR #{number} is not mergeable (conflict, blocked, or required checks not satisfied)` | HTTP 405 on `pr_merge` | `status: 405` |
| `PR #{number} head commit is not up to date — rebase and push again` | HTTP 409 on `pr_merge` | `status: 409` |
| `GitHub API error {status_code}: {message}` | HTTP 4xx/5xx on any API action | `status: <code>` |
| `<action> request failed: {exception}` | httpx exception (network/transport) | — |
| `<action> returned non-JSON response: {exception}` | `resp.json()` raises | — |
| `git push timed out after 120s (branch=..., remote=...)` | `subprocess.TimeoutExpired` | `branch`, `remote` |
| `git executable not found — install git and ensure it is on PATH` | `FileNotFoundError` from `subprocess.run` | `branch`, `remote` |
| `git push failed (exit {code}): {output}` | Non-zero exit code from `git push` | `branch`, `remote`, `exit_code`, `output` |
| `GitHub action failed: {exception}` | Unhandled exception in handler | — |

**Status code semantics:** `fail()` accepts a `status` kwarg that overrides the default `"error"` string. The github actions pass HTTP status codes (404, 405, 409, etc.) as `status` — callers can inspect `result["status"]` to distinguish "not found" (404) from "not mergeable" (405) from "stale head" (409) from a generic client error (4xx int).

---

## 🔒 Security

**No filesystem operations outside `git push`.** The github tool does NOT write to or read from the local filesystem. The only filesystem-affecting operation is `push` — and that's `git push`, which only updates remote refs (no local file writes).

**No path_guard needed.** The `path` param on `pr_comment` is a GitHub file path (relative to repo root), not a local filesystem path — it's sent to the GitHub API as-is. No local file is opened.

**No SSRF surface.** All outbound calls go to `https://api.github.com` (hardcoded in `tools/github_ops/client.py`). The base URL is NOT configurable via env (see CHANGELOG.md roadmap for GHE support). No user-supplied URLs are passed to httpx.

**Token handling.** `GITHUB_TOKEN` is read once at httpx.Client construction time (in `get_client()`) and embedded in the `Authorization: Bearer ...` header. The token is never logged, never returned in any result dict, never passed to subprocess (push uses the repo's git remote config, not the token). Restart the agent (or call `close_client()`) after rotating the token.

**Subprocess safety (`push` only).** `git push` is invoked with a list arg (`["git", "push", ..., remote, branch]`), NOT `shell=True`. Branch and remote names are validated against shell metacharacters as defense-in-depth — git branch names cannot contain these anyway, so this catches programming errors rather than security issues.

**`--force-with-lease` (not `--force`).** When `force=True`, push uses `--force-with-lease`, which checks the remote ref against the local tracking ref before overwriting. If the remote has been updated since the last fetch (e.g. a teammate pushed), the push is rejected. This prevents accidental history destruction. Use `force=True` only when you intend to rewrite remote branch history (e.g. after a rebase).

**API response data is untrusted.** JSON returned from GitHub API calls (PR titles, bodies, comments, user logins) is treated as untrusted and returned to the caller as-is. Callers are responsible for any downstream rendering safety. The github tool itself does NOT `eval()`, `exec()`, or `subprocess.run()` GitHub response data.

**Rate limiting.** GitHub API rate limits are 5000 req/hour for authenticated users. The github tool does NOT track or enforce client-side rate limits — GitHub will return HTTP 403 with a rate-limit error message, which surfaces as `fail("GitHub API error 403: ...")`. Per-action rate limit tracking is a roadmap item (see CHANGELOG.md).

**`PARALLEL_SAFE` — API actions only.** The 14 API actions are stateless HTTP calls (safe to parallelize in `parallel()`). `push` is a subprocess and is NOT parallel-safe — concurrent pushes to the same branch will fail with lock contention. The github facade declares `_NOT_PARALLEL_SAFE = frozenset({"push"})` and `push` is excluded from `PARALLEL_SAFE` in `core/parallel_executor.py`.

---

*Last updated: 2026-07-10 (v1.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
