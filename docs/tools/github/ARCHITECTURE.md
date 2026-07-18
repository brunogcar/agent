<- Back to [GitHub Overview](../GITHUB.md)

# 🏗️ Architecture

## Source Code Reference

| File | Purpose |
|------|---------|
| `tools/github.py` | `@tool` facade: action dispatch, kwargs forwarding, exception capture, `duration_ms` timing, `trace_id` injection |
| `tools/github_ops/client.py` | Singleton `httpx.Client` (auth headers, connection pooling), `is_configured()`, `repo_path()`, `parse_link_header()`, `atexit.register(close_client)` (v1.4) |
| `tools/github_ops/helpers.py` | v1.4 — `github_request()` (core/net retry + error_code), `_check_configured()`, `_coerce_int()`. Foundation for action refactor. |
| `tools/github_ops/_registry.py` | `DISPATCH` dict + `@register_action` decorator (duplicate-action detection) |
| `tools/github_ops/actions/*.py` | 16 action handlers (one file per action). v1.4: all 14 API actions use `fail()` without `status=<int>` (default `status="error"`). |
| `core/contracts.py` | `ok()` / `fail()` — standardized return shape. `fail(status: str = "error", error_code: str = "")` |
| `core/net/default.py` | v1.4: `GITHUB_TIMEOUT = 30` (used by `helpers.github_request`) |
| `core/net/retry.py` | `retry_sync(fn, *, max_retries, base_delay, max_delay, jitter, is_retryable)` — wraps `helpers._do_request` |
| `core/net/errors.py` | `classify_http_error(e)` → `TIMEOUT`/`RATE_LIMITED`/`SERVER_ERROR`/`CLIENT_ERROR`/`NETWORK_ERROR`/`CONNECT_ERROR`/`BOT_BLOCKED`/`UNKNOWN` |
| `core/config.py` | `cfg.github_token` / `github_owner` / `github_repo` |

## Module Tree

```text
tools/github.py                        # @tool facade
tools/github_ops/
├── __init__.py                        # Auto-imports actions/*.py
├── _registry.py                       # DISPATCH + @register_action
├── client.py                          # httpx.Client singleton, is_configured, repo_path, parse_link_header, atexit.register(close_client)
├── helpers.py                         # v1.4 — github_request(), _check_configured(), _coerce_int()
└── actions/
    ├── pr_create.py  pr_list.py  pr_get.py  pr_review.py  pr_merge.py  pr_comment.py
    ├── issue_create.py  issue_list.py  issue_get.py  issue_update.py  issue_comment.py
    ├── release_create.py  release_list.py  release_get.py
    └── push.py  pull.py               # subprocess (NOT API)
```

## Dispatch Flow

```
github(action="pr_create", title=..., head=...)
  → action.strip().lower()
  → empty? → fail("action is required")
  → DISPATCH["github"][action] lookup → unknown? → fail("Unknown action. Use: ...")
  → kwargs = {all 24 params} → handler(**kwargs)
  → exception? → fail("GitHub action failed: {e}")
  → inject trace_id + duration_ms → return
```

**API action handler flow** (14 of 16 actions — v1.4 contract: `fail()` defaults to `status="error"`, no int):
```
handler(number, ...)
  → is_configured()? no → fail("GitHub not configured...")
  → validate params (state/event/merge_method allowlists; number int-coercion; XOR path/line)
  → client = get_client()
  → client.get/post/put/patch(url, ..., timeout=30) → network error? → fail("... request failed: {e}")
  → status == 404? → fail("PR #N not found")             # no status= kwarg (v1.4)
  → status == 405 (pr_merge)? → fail("not mergeable")     # no status= kwarg (v1.4)
  → status == 409 (pr_merge)? → fail("head not up to date") # no status= kwarg (v1.4)
  → status >= 400? → fail(f"GitHub API error {code}: {msg}")  # HTTP code in error text
  → resp.json() → parse error? → fail("... returned non-JSON: {e}")
  → ok({compact fields}, trace_id=trace_id)
```

**`github_request()` helper flow** (v1.4 — not yet used by actions; foundation for refactor):
```
github_request(method, url_path, trace_id, *, params, json, not_found_msg)
  → client = get_client()
  → retry_sync(lambda: _do_request(...), max_retries=2, base_delay=1.0, max_delay=5.0)
      → _do_request raises httpx.HTTPStatusError on status >= 400
      → retry_sync retries on RETRYABLE_STATUS_CODES {408, 429, 500, 502, 503, 504}
  → success → return (resp, None)
  → httpx.HTTPStatusError:
      → 404 + not_found_msg? → return (None, fail(not_found_msg, error_code="NOT_FOUND"))
      → else → classify_http_error(e) → return (None, fail(f"GitHub API error {code}: {msg}", error_code=...))
  → other Exception → classify_http_error(e) → return (None, fail(f"GitHub request failed: {e}", error_code=...))
```

**`push`/`pull` flow** (subprocess, NOT API):
```
handler(branch, remote, force, ...)
  → validate branch/remote for shell metacharacters
  → cmd = ["git", "push"|"pull", [--force-with-lease], remote, branch]
  → subprocess.run(cmd, capture_output=True, timeout=120)
  → TimeoutExpired? → fail("... timed out after 120s")
  → returncode != 0? → fail("... failed (exit {n}): {output}")
  → ok({status, branch, remote, pushed|pulled, output})
```

## Key Design Decisions

1. **`httpx` direct (NOT PyGithub).** Direct HTTPS calls to the GitHub REST API. PyGithub is a heavy abstraction that hides the raw request shape and adds a transitive dependency. Consistent with the rest of the project (httpx for all HTTP).

2. **`push` + `pull` live in `github_ops/` (NOT `git_ops/`).** Both are conceptually part of the GitHub PR workflow (pull → branch → commit → push → PR → review → merge). Grouping them with PR actions keeps the workflow discoverable. `git_ops` stays focused on local repo inspection.

3. **PARALLEL_SAFE for API actions, NOT for `push`/`pull`.** 14 API actions are stateless HTTP (safe to parallelize). `push`/`pull` spawn subprocesses — concurrent ops on the same repo fail with `.git/index.lock` contention. Facade declares `_NOT_PARALLEL_SAFE = frozenset({"push", "pull"})`.

4. **`--force-with-lease` (not bare `--force`).** `force=True` on `push` maps to `--force-with-lease`, which refuses to overwrite remote refs that moved since the last fetch. Safer than `--force` (which silently destroys teammates' commits). `pull` has no `force` param (semantically meaningless).

5. **`is_configured()` short-circuits on first empty value.** `bool(cfg.github_token and cfg.github_owner and cfg.github_repo)` — if any is empty, returns False without making an API call. `push`/`pull` skip this check (subprocess, not API). `helpers._check_configured()` wraps this for new actions.

6. **Singleton `httpx.Client` with `is_closed` check + atexit cleanup (v1.4).** Double-checked locking in `get_client()`. If the client was closed (e.g. by a test), it's rebuilt on the next call. Token read once at construction; restart agent or call `close_client()` after changing `.env`. v1.4: `atexit.register(close_client)` (parity with `core/net/client.py`) prevents "Unclosed client" warnings in long-running processes.

7. **`pr_comment` dual-mode (XOR validation on `path`/`line`).** Both provided → line-level comment (`/pulls/{n}/comments` with `subject_type=line`). Neither → general comment (`/issues/{n}/comments`). Exactly one → `fail("path and line must be provided together")`.

8. **`issue_update` unifies close/reopen/edit (v1.2).** Single PATCH action. `state=""` (facade default) = don't change. Empty fields omitted from payload (GitHub leaves unchanged). At least one field required.

9. **Pagination via `parse_link_header()` + `page` param (v1.2, regex fix v1.4).** `pr_list`, `issue_list`, `release_list` support `page` param. Response includes `page` / `has_next` / `next_page` from the parsed `Link` header. `per_page = min(limit, 100)` (GitHub API hard cap). v1.4 (Bug 2): regex was `<[^>]*\?page=(\d+)>` — required `?page=` to be the FIRST query param. GitHub actually sends `?per_page=100&page=2`, so pagination silently failed on every multi-param Link header. Fixed: `<[^>]*[?&]page=(\d+)>` (accepts `?` or `&`).

10. **`if not number:` (not `if number is None:`) (v1.2).** Facade defaults `number: int = 0` and `line: int = 0`. `is None` checks don't catch missing-arg (handler sees `0`). Always use `if not x:` or `bool(x)`. Was a real v1.0/v1.1 bug.

11. **3-stage error handling (v1.0/v1.2 pattern, v1.3.1 applied to v1.1 actions).** Network call (try/except) → HTTP error (status check) → JSON parse (try/except). Distinguishes network errors from parse errors. v1.4: `fail()` no longer takes `status=<int>` (contract violation — `core/contracts.py` types `status` as a string Literal). The HTTP code remains in the error message text; structured classification goes in `error_code` (set by `github_request()` — actions don't set it yet).

12. **`duration_ms` at facade level.** Single source of truth for wall-clock timing. Handlers don't time themselves.

13. **`helpers.github_request()` is the core/net adoption surface (v1.4).** Wraps `httpx` in `core.net.retry.retry_sync` (max_retries=2, base_delay=1.0, max_delay=5.0 — tighter than the project-wide RETRY_BASE_DELAY=2.0 / RETRY_MAX_DELAY=30.0 because GitHub API calls are user-facing). Errors classified via `core.net.errors.classify_http_error` → `error_code`. Reads `X-RateLimit-Remaining` header into the fail dict. NOT yet used by the 14 actions (they retain the inline 3-stage pattern); migration is a follow-up commit. New actions written from scratch SHOULD use `github_request()` directly.

14. **`fail(status=<int>)` was a contract violation (v1.4 revert).** v1.3.1 introduced `fail(status=resp.status_code)` on API errors so callers could route on 404 vs 422 vs 500. But `core/contracts.py` types `status` as `Literal["success", "error", "routed", "needs_clarification", "sent", "scheduled"]` — passing an int silently broke `result["status"] == "error"` checks downstream (the int 404 is not equal to the string `"error"`). v1.4 removes `status=<int>` from all 14 API actions. The HTTP code remains in the error message text. Structured classification belongs in `error_code` (set by `github_request()`).

## Testing

```powershell
python -m pytest tests/tools/github/ -v -W error --tb=short
```

**Fixtures** (`tests/tools/github/conftest.py`):
- `mock_cfg` — patches `cfg.github_token/owner/repo` with test values (is_configured → True)
- `mock_not_configured` — patches `cfg.github_token` empty (is_configured → False)
- `mock_httpx_client` — patches `get_client` at all 14 API action modules' namespace (NOT at `client.get_client` source — action modules hold a direct reference after import)
- `_make_response(status, json_body, text, headers)` — builds mock `httpx.Response`

**`push`/`pull` tests** patch `tools.github_ops.actions.{push,pull}.subprocess.run` directly.

**v1.4 test changes:**
- 7 assertions across `test_pr_merge.py`, `test_pr_get.py`, `test_issues_releases.py` updated from `result["status"] == <int>` to `result["status"] == "error"`. The HTTP code is still verified via substring match on `result["error"]` (e.g. `assert "422" in result["error"]`).
- `TestV131ErrorHandling` class docstring updated to reflect v1.4 (status defaults to "error"; HTTP code in message text).
- `helpers.py` has no dedicated test file — `github_request()` isn't exercised by any test until actions migrate to use it. Testing it directly requires patching `tools.github_ops.helpers.get_client` (same direct-reference pattern as the action modules — see INSTRUCTIONS.md rule #18).

---

*Last updated: 2026-07-15 (v1.4). See [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
