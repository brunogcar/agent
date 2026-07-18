<- Back to [GitHub Overview](../GITHUB.md)

# 📝 API Reference

## Tool Signature

```python
github(action: str, *, title, head, base, body, number, state, limit, page,
       event, merge_method, commit_title, commit_message, path, line, side,
       branch, remote, force, labels, assignees, tag, draft, prerelease,
       trace_id) -> dict
```

The facade uses `action: str` with manual `DISPATCH["github"][action]` dispatch (same pattern as `swarm`). `@meta_tool` is applied for `doc_sections`/metadata. Unknown actions return `fail("Unknown action '...'. Use: ...")` listing all 16 valid actions.

## Parameters

| Param | Default | Used by | Description |
|-------|---------|---------|-------------|
| `action` | — | all | **Required.** One of 16 actions (see Summary). Lowercased + stripped |
| `title` | `""` | pr_create, issue_create, issue_update, release_create | Title / name |
| `head` | `""` | pr_create | Source branch (merge FROM) |
| `base` | `"main"` | pr_create | Target branch (merge INTO) |
| `body` | `""` | pr_create, pr_review, pr_comment, issue_create, issue_update, release_create | Markdown text |
| `number` | `0` | pr_get/review/merge/comment, issue_get/update/comment, release_get | PR/issue/release ID. Coerced to int |
| `state` | `""` | pr_list, issue_list, issue_update | `open`/`closed`/`all` for lists; `open`/`closed` for update (empty = don't change) |
| `limit` | `30` | pr_list, issue_list, release_list | Max items per page (capped at 100) |
| `page` | `1` | pr_list, issue_list, release_list | Page number for pagination |
| `event` | `""` | pr_review | `APPROVE` / `REQUEST_CHANGES` / `COMMENT` |
| `merge_method` | `"squash"` | pr_merge | `merge` / `squash` / `rebase` |
| `commit_title` | `""` | pr_merge | Custom merge commit title |
| `commit_message` | `""` | pr_merge | Custom merge commit body |
| `path` | `""` | pr_comment | File path (triggers line-level mode with `line`) |
| `line` | `0` | pr_comment | Line number (triggers line-level mode with `path`) |
| `side` | `"RIGHT"` | pr_comment | `LEFT` (base) or `RIGHT` (head) — line-level only |
| `branch` | `""` | push, pull | Branch name. `pull`: empty = current branch |
| `remote` | `"origin"` | push, pull | Remote name |
| `force` | `False` | push | `True` → `--force-with-lease` (NOT bare `--force`) |
| `labels` | `""` | issue_create, issue_list, issue_update | Comma-separated |
| `assignees` | `""` | issue_create, issue_update | Comma-separated logins |
| `tag` | `""` | release_create, release_get | Tag name (takes priority over `number` in release_get). v1.4: URL-encoded in release_get |
| `draft` | `False` | release_create | Create as draft |
| `prerelease` | `False` | release_create | Mark as prerelease |
| `trace_id` | `""` | all | Auto-injected into result |

**Dispatch flow:** `action` lowercased → empty fails → `DISPATCH` lookup (unknown fails with valid list) → all kwargs forwarded → handler exception caught as `fail("GitHub action failed: {e}")` → `duration_ms` + `trace_id` injected.

## Actions — Summary Table

| Action | Required | Optional | Returns |
|--------|----------|----------|---------|
| `pr_create` | `title`, `head` | `base`, `body` | `{number, title, url, state, head, base}` |
| `pr_list` | — | `state`, `limit`, `page` | `{count, pulls, page, has_next, next_page}` |
| `pr_get` | `number` | — | `{number, title, state, merged, mergeable, mergeable_state, draft, head, base, url, body, user, created_at, updated_at}` |
| `pr_review` | `number`, `event` | `body` | `{id, state, url}` |
| `pr_merge` | `number` | `merge_method`, `commit_title`, `commit_message` | `{merged, sha, message}` (v1.4: `merged` from response, was hardcoded `True`) |
| `pr_comment` | `number`, `body` | `path`, `line`, `side` | `{id, url, body}` (+ `path`, `line` if line-level) |
| `issue_create` | `title` | `body`, `labels`, `assignees` | `{number, title, url, state}` |
| `issue_list` | — | `state`, `labels`, `limit`, `page` | `{count, issues, page, has_next, next_page}` |
| `issue_get` | `number` | — | `{number, title, state, body, url, labels, assignee, user, created_at, updated_at, closed_at}` |
| `issue_update` | `number` + ≥1 field | `state`, `title`, `body`, `labels`, `assignees` | `{number, title, state, url}` |
| `issue_comment` | `number`, `body` | — | `{id, url, body, created_at}` |
| `release_create` | `tag` | `title`, `body`, `draft`, `prerelease` | `{id, tag, name, url, draft, prerelease, created_at}` |
| `release_list` | — | `limit`, `page` | `{count, releases, page, has_next, next_page}` |
| `release_get` | `tag` OR `number` | — | `{id, tag, name, url, draft, prerelease, created_at, published_at, body, assets}` (v1.4: tag URL-encoded) |
| `push` | `branch` | `remote`, `force` | `{status, branch, remote, pushed, output, forced}` |
| `pull` | — | `branch`, `remote` | `{status, branch, remote, pulled, output}` |

## Action Details

### `pr_create`
```python
github(action="pr_create", title="Fix bug", head="fix/branch", base="main", body="...")
```
`{number, title, url, state, head, base}`. Head branch must exist on remote (call `push` first).

### `pr_list`
```python
github(action="pr_list")                          # open PRs, page 1
github(action="pr_list", state="closed", limit=10, page=2)
```
`{count, pulls: [{number, title, state, head, base, url, draft}], page, has_next, next_page}`. Iterate: `while has_next: github(action="pr_list", page=next_page)`. v1.4: `parse_link_header` regex fixed — was silently broken when Link header had `?per_page=100&page=2` (page= not the first query param).

### `pr_get`
```python
github(action="pr_get", number=42)
```
`{number, title, state, merged, mergeable, mergeable_state, draft, head, base, url, body, user, created_at, updated_at}`. `mergeable: null` = GitHub still computing (retry). `mergeable_state`: `clean`/`blocked`/`unstable`/`dirty`/`unknown`.

### `pr_review`
```python
github(action="pr_review", number=42, event="APPROVE", body="LGTM")
```
`{id, state, url}`. `event`: `APPROVE`/`REQUEST_CHANGES`/`COMMENT`. APPROVE/REQUEST_CHANGES require push access; can't review your own PR.

### `pr_merge`
```python
github(action="pr_merge", number=42)                                          # squash (default)
github(action="pr_merge", number=42, merge_method="merge", commit_title="...")
```
`{merged, sha, message}`. v1.4: `merged` field now read from GitHub's response (`data.get("merged", True)`) — was hardcoded `True`. 405 = not mergeable (conflict/blocked). 409 = head not up to date (rebase + push). Call `pr_get` first to check `mergeable_state`.

### `pr_comment`
```python
github(action="pr_comment", number=42, body="General comment")                # general
github(action="pr_comment", number=42, body="Line note", path="src/x.py", line=42, side="RIGHT")  # line-level
```
`{id, url, body}` (+ `path`, `line` if line-level). `path` + `line` must be both-or-neither (XOR validation). General comments use `/issues/{n}/comments`; line-level use `/pulls/{n}/comments` with `subject_type=line`.

### `issue_create`
```python
github(action="issue_create", title="Bug", body="...", labels="bug,ui", assignees="alice,bob")
```
`{number, title, url, state}`.

### `issue_list`
```python
github(action="issue_list", state="open", labels="bug", limit=30, page=1)
```
`{count, issues: [{number, title, state, url, labels, assignee}], page, has_next, next_page}`. v1.4: same `parse_link_header` regex fix as `pr_list`.

### `issue_get`
```python
github(action="issue_get", number=42)
```
`{number, title, state, body, url, labels, assignee, user, created_at, updated_at, closed_at}`.

### `issue_update`
```python
github(action="issue_update", number=42, state="closed")                      # close
github(action="issue_update", number=42, state="open", title="Reopened")      # reopen + retitile
github(action="issue_update", number=42, labels="duplicate")                  # re-label only
```
`{number, title, state, url}`. Unified close/reopen/edit. `state=""` = don't change. At least one field required.

### `issue_comment`
```python
github(action="issue_comment", number=42, body="Fixed in PR #43")
```
`{id, url, body, created_at}`. Shared endpoint for issues + PRs.

### `release_create`
```python
github(action="release_create", tag="v1.0.0", title="Release 1.0", body="...", prerelease=False)
```
`{id, tag, name, url, draft, prerelease, created_at}`.

### `release_list`
```python
github(action="release_list", limit=30, page=1)
```
`{count, releases: [{id, tag, name, url, draft, prerelease, published_at}], page, has_next, next_page}`. v1.3.1: pagination added. v1.4: `parse_link_header` regex fix.

### `release_get`
```python
github(action="release_get", tag="v1.0.0")           # by tag (preferred)
github(action="release_get", number=12345)            # by numeric ID
```
`{id, tag, name, url, draft, prerelease, created_at, published_at, body, assets: [{name, url, size, download_count}]}`. `tag` takes priority over `number`. v1.4: tag URL-encoded via `quote(tag, safe="")` so URL-unsafe characters (`+`, `#`, `?`, `/`, spaces) don't produce malformed request URLs.

### `push`
```python
github(action="push", branch="fix/timeout")                                  # git push origin fix/timeout
github(action="push", branch="feat/rebase", force=True)                      # --force-with-lease
```
`{status: "ok", branch, remote, pushed: true, output, forced}`. LOCAL subprocess (no GITHUB_TOKEN). `force=True` → `--force-with-lease` (safer than `--force`). NOT parallel-safe. 120s timeout.

### `pull`
```python
github(action="pull")                                                        # git pull origin (current branch)
github(action="pull", branch="main")                                         # git pull origin main
```
`{status: "ok", branch, remote, pulled: true, output}`. LOCAL subprocess. NOT parallel-safe. 120s timeout.

## Error Handling

**v1.4 contract:** `fail()` always uses the default `status="error"` — never an int HTTP code. The HTTP code remains in the error message text. Structured classification belongs in `error_code` (set by `helpers.github_request()` — not yet wired into the 14 inline actions; planned for next release).

All errors return `fail(error, trace_id=..., error_code=...)`:
- `result["status"]` → always `"error"` for any failure (v1.4 — was sometimes `<int>` in v1.3.1)
- `result["error"]` → human-readable message (often contains the HTTP code, e.g. `"GitHub API error 422: ..."`)
- `result["error_code"]` → structured code (only set by `github_request()` until actions migrate — see `core/contracts.py`)
- `result["trace_id"]` → trace ID
- `result["rate_limit_remaining"]` → present when `github_request()` saw an `X-RateLimit-Remaining` header (v1.4)

| Error | Trigger | `status` | `error_code` (when set by github_request) |
|-------|---------|----------|-------------------------------------------|
| `action is required` | empty `action` | `"error"` | — |
| `Unknown action '<x>'. Use: ...` | action not in DISPATCH | `"error"` | — |
| `<param> is required for <action>` | missing required param | `"error"` | — |
| `GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env` | `is_configured()` False | `"error"` | — |
| `GitHub API error <code>: <msg>` | GitHub returned ≥400 (inline actions) | `"error"` | — (set after action migration) |
| `PR #<n> not found` | 404 on pr_get/review/merge/comment (inline actions) | `"error"` | — (set to `"NOT_FOUND"` after migration) |
| `PR #<n> is not mergeable` | 405 on pr_merge | `"error"` | — |
| `PR #<n> head commit is not up to date` | 409 on pr_merge | `"error"` | — |
| `git push failed (exit <n>): <output>` | subprocess non-zero exit | `"error"` | — |
| `git push timed out after 120s` | subprocess timeout | `"error"` | — |
| `GitHub action failed: <exception>` | unhandled handler exception | `"error"` | — |

**`error_code` values** (from `core.net.errors.classify_http_error`, used by `github_request()`):
| Code | Meaning |
|------|---------|
| `TIMEOUT` | httpx.TimeoutException |
| `CONNECT_ERROR` | httpx.ConnectError |
| `NETWORK_ERROR` | httpx.ReadError / WriteError / RemoteProtocolError / NetworkError |
| `RATE_LIMITED` | HTTP 408 or 429 |
| `SERVER_ERROR` | HTTP ≥ 500 |
| `CLIENT_ERROR` | HTTP 4xx (non-retryable) |
| `NOT_FOUND` | HTTP 404 (set by `github_request()` when `not_found_msg` provided) |
| `BOT_BLOCKED` | Cloudflare/cf-ray in response body |
| `UNKNOWN` | Anything else |

**Retry behavior** (v1.4, only via `github_request()` — not yet wired into inline actions):
- `core.net.retry.retry_sync` wraps `_do_request` with `max_retries=2`, `base_delay=1.0`, `max_delay=5.0`, jitter enabled.
- Retries on: `RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}` + `RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, ConnectError, NetworkError, ReadError, WriteError, RemoteProtocolError)`.
- 3 total attempts max (initial + 2 retries). Backoff: ~1s, ~2s with ±25% jitter.

Per-provider error isolation: N/A (single API). Network errors and JSON-parse errors are distinguished by message prefix (`"request failed:"` vs `"returned non-JSON response:"`).

## Security

- **Auth:** `GITHUB_TOKEN` read from env via `cfg.github_token`, embedded in `Authorization: Bearer ...` header at httpx.Client construction. Never logged or returned in results.
- **No SSRF surface:** API base URL hardcoded to `https://api.github.com` (no user-supplied URLs). GHE support (`GITHUB_API_BASE` env override) is a Phase 4+ roadmap item.
- **Subprocess safety:** `push`/`pull` use `subprocess.run(["git", ...], ...)` with list args (NOT `shell=True`). Branch/remote names validated against shell metacharacters (`; & | $ \` ( ) < > \n \r`) as defense-in-depth.
- **`--force-with-lease`** (not bare `--force`): refuses to overwrite remote refs that moved since last fetch.
- **No filesystem writes** except via `git push`/`git pull` (which modify the local `.git` directory).
- **v1.4 retry/backoff:** `github_request()` uses `core.net.retry.retry_sync` with bounded retries (max 3 total attempts, max 5s backoff). No unbounded retry loops.

---

*Last updated: 2026-07-18 (v1.5 — all 14 actions migrated).*
