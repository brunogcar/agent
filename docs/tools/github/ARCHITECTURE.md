<- Back to [GitHub Overview](../GITHUB.md)

# 🏗️ Architecture

## Source Code Reference

| File | Purpose |
|------|---------|
| `tools/github.py` | `@tool` facade: action dispatch, kwargs forwarding, exception capture, `duration_ms` timing, `trace_id` injection |
| `tools/github_ops/client.py` | Singleton `httpx.Client` (auth headers, connection pooling), `is_configured()`, `repo_path()`, `parse_link_header()` |
| `tools/github_ops/_registry.py` | `DISPATCH` dict + `@register_action` decorator (duplicate-action detection) |
| `tools/github_ops/actions/*.py` | 16 action handlers (one file per action) |
| `core/contracts.py` | `ok()` / `fail()` — standardized return shape |
| `core/config.py` | `cfg.github_token` / `github_owner` / `github_repo` |

## Module Tree

```text
tools/github.py                        # @tool facade
tools/github_ops/
├── __init__.py                        # Auto-imports actions/*.py
├── _registry.py                       # DISPATCH + @register_action
├── client.py                          # httpx.Client singleton, is_configured, repo_path, parse_link_header
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

**API action handler flow** (14 of 16 actions):
```
handler(number, ...)
  → is_configured()? no → fail("GitHub not configured...")
  → validate params (state/event/merge_method allowlists; number int-coercion; XOR path/line)
  → client = get_client()
  → client.get/post/put/patch(url, ...) → network error? → fail("... request failed: {e}")
  → status >= 400? → fail("GitHub API error {code}: {msg}", status=code)
  → resp.json() → parse error? → fail("... returned non-JSON: {e}")
  → ok({compact fields}, trace_id=trace_id)
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

5. **`is_configured()` short-circuits on first empty value.** `bool(cfg.github_token and cfg.github_owner and cfg.github_repo)` — if any is empty, returns False without making an API call. `push`/`pull` skip this check (subprocess, not API).

6. **Singleton `httpx.Client` with `is_closed` check.** Double-checked locking in `get_client()`. If the client was closed (e.g. by a test), it's rebuilt on the next call. Token read once at construction; restart agent or call `close_client()` after changing `.env`.

7. **`pr_comment` dual-mode (XOR validation on `path`/`line`).** Both provided → line-level comment (`/pulls/{n}/comments` with `subject_type=line`). Neither → general comment (`/issues/{n}/comments`). Exactly one → `fail("path and line must be provided together")`.

8. **`issue_update` unifies close/reopen/edit (v1.2).** Single PATCH action. `state=""` (facade default) = don't change. Empty fields omitted from payload (GitHub leaves unchanged). At least one field required.

9. **Pagination via `parse_link_header()` + `page` param (v1.2, extended v1.3.1).** `pr_list`, `issue_list`, `release_list` (v1.3.1) support `page` param. Response includes `page` / `has_next` / `next_page` from the parsed `Link` header. `per_page = min(limit, 100)` (GitHub API hard cap). v1.3.1 (P2-2): `release_list` was missing pagination — fixed.

10. **`if not number:` (not `if number is None:`) (v1.2).** Facade defaults `number: int = 0` and `line: int = 0`. `is None` checks don't catch missing-arg (handler sees `0`). Always use `if not x:` or `bool(x)`. Was a real v1.0/v1.1 bug.

11. **3-stage error handling (v1.0/v1.2 pattern, v1.3.1 applied to v1.1 actions).** Network call (try/except) → HTTP error (status check) → JSON parse (try/except). Distinguishes network errors from parse errors. `fail(status=resp.status_code)` propagates HTTP code so callers can route on 404 vs 422 vs 500. v1.3.1 (P2-1): `issue_create`, `issue_comment`, `release_create`, `release_list` rewritten to match.

12. **`duration_ms` at facade level.** Single source of truth for wall-clock timing. Handlers don't time themselves.

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

---

*Last updated: 2026-07-13 (v1.3.1). See [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
