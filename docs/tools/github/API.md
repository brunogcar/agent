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
    state: str = "open",
    limit: int = 30,
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
    trace_id: str = "",
) -> dict:
    """GitHub API meta-tool — PR operations and git push."""
```

> **Note:** Like `swarm()`, the github facade uses `action: str` and dispatches manually via `DISPATCH["github"][action]`. Unknown actions return a `fail()` result listing all 7 valid actions, rather than being rejected by a `Literal` schema layer. The `@meta_tool` decorator is applied (for `doc_sections` and metadata) but the `Literal` enum patch is **not** generated.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** One of: `pr_create` \| `pr_list` \| `pr_get` \| `pr_review` \| `pr_merge` \| `pr_comment` \| `push`. Lowercased + stripped before dispatch |
| `title` | `str` | `""` | PR title (used by `pr_create`) |
| `head` | `str` | `""` | Source branch name — what to merge FROM (used by `pr_create`) |
| `base` | `str` | `"main"` | Target branch name — what to merge INTO (used by `pr_create`) |
| `body` | `str` | `""` | Markdown body / description (used by `pr_create`, `pr_review`, `pr_comment`) |
| `number` | `int` | `0` | PR number (used by `pr_get`, `pr_review`, `pr_merge`, `pr_comment`). Coerced to int — numeric str accepted |
| `state` | `str` | `"open"` | Filter: `open`, `closed`, or `all` (used by `pr_list`) |
| `limit` | `int` | `30` | Max PRs to return (used by `pr_list`). Capped at 100 per GitHub API per_page maximum |
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
| `trace_id` | `str` | `""` | Trace identifier for observability. Auto-injected into the result dict |

**Dispatch behavior:**
1. `action` is lowercased + stripped; empty → `fail("action is required")`.
2. `DISPATCH["github"][action]` lookup; unknown → `fail("Unknown action '<x>'. Use: pr_comment | pr_create | pr_get | pr_list | pr_merge | pr_review | push")`.
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
| `pr_list` | — | `state`, `limit` | List pull requests filtered by state (open / closed / all) |
| `pr_get` | `number` | — | Fetch detailed info for a single pull request |
| `pr_review` | `number`, `event` | `body`, `commit_id` | Submit a review (APPROVE / REQUEST_CHANGES / COMMENT) |
| `pr_merge` | `number` | `merge_method`, `commit_title`, `commit_message` | Merge a pull request (squash / merge / rebase) |
| `pr_comment` | `number`, `body` | `path`, `line`, `side` | Post a comment — general OR line-level (dual-mode) |
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

**Purpose:** Fetch a list of PRs on the configured repo, filtered by state and capped at a caller-supplied limit.

**Required params:** none

**Optional params:** `state` (default `"open"`, one of `open`/`closed`/`all`), `limit` (default `30`, capped at 100)

**Example:**
```python
github(action="pr_list")
github(action="pr_list", state="closed", limit=10)
github(action="pr_list", state="all")
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
    ]
  },
  "error": null,
  "duration_ms": 412
}
```

**Notes:**
- Calls `GET /repos/{owner}/{repo}/pulls?state=...&per_page=...`.
- The GitHub API caps `per_page` at 100 for this endpoint. `pr_list` computes `per_page = min(limit, 100)` and slices `items[:limit]` after extraction — the returned count never exceeds the caller's request even if GitHub returns more.
- Results are returned in GitHub's default order (newest first by `created_at` descending).
- Invalid `state` values are rejected before any API call: `fail(f"state must be one of 'open', 'closed', 'all' — got {state!r}")`.

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
- Use this BEFORE `pr_merge` to check `mergeable` state (returned by GitHub but not surfaced here — see CHANGELOG.md roadmap).

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
| `Unknown action '<x>'. Use: pr_comment \| pr_create \| ...` | Action not in DISPATCH | — |
| `GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env` | API action called with empty token/owner/repo | — |
| `<param> is required for <action>` | Missing required param (validated client-side) | — |
| `state must be one of 'open', 'closed', 'all'` | Invalid `state` on `pr_list` | — |
| `event must be one of ('APPROVE', 'REQUEST_CHANGES', 'COMMENT')` | Invalid `event` on `pr_review` | — |
| `merge_method must be one of ('merge', 'squash', 'rebase')` | Invalid `merge_method` on `pr_merge` | — |
| `path and line must be provided together for line-level comments` | XOR violation on `pr_comment` | — |
| `PR #{number} not found` | HTTP 404 on `pr_get` / `pr_review` / `pr_merge` / `pr_comment` | `status: 404` |
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

**`PARALLEL_SAFE` — API actions only.** The 6 API actions are stateless HTTP calls (safe to parallelize in `parallel()`). `push` is a subprocess and is NOT parallel-safe — concurrent pushes to the same branch will fail with lock contention. The github facade declares `_NOT_PARALLEL_SAFE = frozenset({"push"})` and `push` is excluded from `PARALLEL_SAFE` in `core/parallel_executor.py`.

---

*Last updated: 2026-07-10. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
