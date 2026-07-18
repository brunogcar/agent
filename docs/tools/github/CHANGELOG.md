<- Back to [GitHub Overview](../GITHUB.md)

# 🗺️ Changelog

## Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.4 | 2026-07-15 | core/net adoption (helpers.py + github_request), 4 bug fixes, fail() contract fix. See Completed. |
| v1.3.1 | 2026-07-13 | Cross-LLM review hardening: 2 P2 + 4 P3 fixes + doc trim. |
| v1.3 | 2026-07-10 | `pull` action (remote-sync counterpart to `push`) + autocode integration (6 opt-in env vars). 16 actions. |
| v1.2 | 2026-07-10 | `issue_get` + `issue_update` (unified close/reopen/edit) + `release_get`. Pagination on `pr_list`/`issue_list`. `mergeable`/`mergeable_state` in `pr_get`. Bug fix: `if not number:` (was `is None`). |
| v1.1 | 2026-07-10 | Issues + releases: `issue_create`/`issue_list`/`issue_comment`/`release_create`/`release_list`. 12 actions. |
| v1.0 | 2026-07-10 | Initial release — 7 actions (6 PR + `push`), httpx direct, `--force-with-lease`. |

## Breaking Changes

**v1.4 (2026-07-15) — partial revert of v1.3.1's `status=<int>` convention.**

The v1.3.1 changelog claimed that callers checking `result["status"]` for
GitHub API failures would "see the HTTP int code instead of `"error"`".
This was a contract violation: `core/contracts.py` types `status` as a
`Literal["success", "error", "routed", "needs_clarification", "sent",
"scheduled"]` — passing `status=404` (an int) silently broke every
downstream `if result["status"] == "error":` check (the int 404 is not
equal to the string `"error"`). v1.4 removes the `status=<int>` kwarg
from all 14 API actions' `fail()` calls; the HTTP code is still in the
error message text (`"GitHub API error 404: Not Found"`) so callers
needing to distinguish 4xx from 5xx can substring-match the message, or
migrate to `error_code` (set by `github_request()` — see below).

Migration: replace `result["status"] == 404` with `result["status"] == "error"
and ("404" in result["error"] or result.get("error_code") == "NOT_FOUND")`.

**v1.3.1 additive changes (preserved in v1.4):**
- `release_list` gains `page` param + `page`/`has_next`/`next_page` in result.
- `issue_comment` now coerces `number` to int (P3-2 fix).
- v1.1 actions rewritten to the 3-stage error-handling pattern (network → HTTP → JSON parse).

## Completed

| Feature | Status | Notes |
|---------|--------|-------|
| **v1.4 — core/net adoption + 4 bug fixes** | | |
| `tools/github_ops/helpers.py` (NEW) | ✅ v1.4 | `github_request(method, url_path, trace_id, *, params, json, not_found_msg)` wraps httpx in `core.net.retry.retry_sync` (max_retries=2, base_delay=1.0, max_delay=5.0) and classifies errors via `core.net.errors.classify_http_error` → `error_code` (TIMEOUT/RATE_LIMITED/SERVER_ERROR/CLIENT_ERROR/NOT_FOUND/NETWORK_ERROR/CONNECT_ERROR/BOT_BLOCKED/UNKNOWN). Reads `X-RateLimit-Remaining` header into the fail dict. Also exports `_check_configured()` and `_coerce_int()` helpers. Actions NOT yet refactored to use it — follow-up commit. |
| `GITHUB_TIMEOUT=30` in `core/net/default.py` | ✅ v1.4 | Exported from `core/net/__init__.py`. Used by `github_request()`; actions still use the inline `timeout=30` literal (parity until refactored). |
| fail() contract fix (Bug 1) | ✅ v1.4 | Removed `status=resp.status_code` / `status=404` / `status=405` / `status=409` from all 14 API actions. `fail()` now uses default `status="error"`. HTTP code remains in error message text. |
| `parse_link_header` regex fix (Bug 2) | ✅ v1.4 | Was `<[^>]*\?page=(\d+)>` — required `?page=` to be the FIRST query param. GitHub actually sends `?per_page=100&page=2`, so pagination was silently broken. New regex: `<[^>]*[?&]page=(\d+)>` (accepts `?` or `&` prefix). |
| `pr_merge` hardcoded `merged:True` fix (Bug 3) | ✅ v1.4 | `"merged": True` → `"merged": data.get("merged", True)`. Some merge methods return `merged:false` even on 200 (no-op); the action now honors GitHub's response. |
| `release_get` URL-unsafe tag fix (Bug 4) | ✅ v1.4 | Tag now URL-encoded via `quote(tag, safe="")` — tags with `+`, `#`, `?`, `/`, spaces no longer produce malformed request URLs. |
| `atexit.register(close_client)` in `client.py` | ✅ v1.4 | Parity with `core/net/client.py`. Prevents "Unclosed client" warnings in long-running processes (autocode loop, parallel() batches). |
| **v1.3.1 fixes** | | |
| v1.1 error-handling consistency (P2-1) | ✅ v1.3.1 | `issue_create`/`issue_comment`/`release_create`/`release_list` rewritten to match v1.0/v1.2 3-stage pattern. v1.4 note: `status=` removed from these too. |
| `release_list` pagination (P2-2) | ✅ v1.3.1 | Added `page` param + `parse_link_header`. v1.4 note: regex bug in `parse_link_header` fixed. |
| `issue_comment` int coercion (P3-2) | ✅ v1.3.1 | Now coerces `number` to int for parity with 6 other actions. |
| `_make_response()` headers fix (P3-3) | ✅ v1.3.1 | Conftest helper sets `resp.headers = {}` so pagination tests work. |
| INSTRUCTIONS numbering fix (P3-1) | ✅ v1.3.1 | ALWAYS DO rules renumbered to start at #21. |
| INSTRUCTIONS rule #9 stale "v1.0" (P3-4) | ✅ v1.3.1 | Changed "in v1.0" → "in v1.x". |
| Doc trim | ✅ v1.3.1 | API.md 817→~230 lines, ARCHITECTURE.md 305→~110, GITHUB.md 152→~80, CHANGELOG.md 145→~90. |
| **v1.3 — pull + autocode** | | |
| `pull` action | ✅ v1.3 | `git pull origin <branch>` subprocess. `branch` empty = current. 120s timeout. NOT parallel-safe. |
| Autocode integration | ✅ v1.3 | 6 opt-in env vars: `AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`. All default OFF. |
| **v1.2 — issue/release reads + pagination** | | |
| `issue_get` / `issue_update` / `release_get` | ✅ v1.2 | 3 new actions. `issue_update` unifies close/reopen/edit. |
| Pagination (`pr_list`/`issue_list`) | ✅ v1.2 | `page` param + `parse_link_header()`. Response gains `page`/`has_next`/`next_page`. v1.4 note: regex bug fixed. |
| `mergeable`/`mergeable_state` in `pr_get` | ✅ v1.2 | Pre-merge checks. `null` = still computing (retry). |
| `if not number:` bug fix | ✅ v1.2 | Was `is None` — facade defaults `number=0`. Fixed across 4 actions. |
| **v1.1 — issues + releases** | | |
| `issue_create`/`issue_list`/`issue_comment`/`release_create`/`release_list` | ✅ v1.1 | 5 new actions. v1.3.1: error handling upgraded to 3-stage pattern. v1.4: `status=` removed. |
| **v1.0 — PR + push** | | |
| 7 actions (6 PR + `push`) | ✅ v1.0 | httpx direct, `--force-with-lease`, singleton client, `is_configured()` short-circuit. v1.4: `status=` removed. |
| Test suite | ✅ v1.0→v1.4 | 16 → 78 → 85 → 92 tests. v1.4: 7 assertions updated (`status == <int>` → `status == "error"`). All mock httpx + subprocess — no real API/git calls. |

## Roadmap — Phase 4+

| Feature | Notes | Priority |
|---------|-------|----------|
| Refactor 14 actions to use `github_request()` | helpers.py is in place (v1.4); actions still use inline 3-stage pattern. Migration is mechanical: replace `client.get(...)` + `if status >= 400` block with `resp, err = github_request("get", url, trace_id, not_found_msg=...)`. P1 for next release. | P1 |
| Surface `error_code` from inline actions | Until actions migrate to `github_request()`, `error_code` is only set on `fail()` calls made via the helper. Inline actions only set `trace_id` + the HTTP code in the error text. | P2 |
| `push`/`pull` `root` param (cwd scoping) | Add `root: str = ""` to scope subprocess to `agent`/`workspace`/`/abs/path` (mirrors `git()` tool). Currently runs in CWD. | P2 |
| GitHub Enterprise (GHE) support | `GITHUB_API_BASE` env override → `https://github.<company>.com/api/v3`. One-line change in `client.py`. | P3 |
| Rate-limit tracking | v1.4 partially done — `github_request()` reads `X-RateLimit-Remaining` into the fail dict. Inline actions still don't surface it. Full fix requires action migration. | P3 |
| `pr_close` / `pr_update` actions | PATCH `/pulls/{n}` — close without merge; update title/body/base. | P3 |
| `pr_review` with line-level comments | Add `comments=[{path, line, body, side}]` payload for inline review comments in one submit. | P3 |
| GraphQL API | `github(action="graphql", query=...)` for complex queries. | P4 |
| Webhook receiver | PR event receiver — belongs in `core/gateway_backend/routes/`, not the tool. | P4 |

## Deferred / Out of Scope

| Feature | Why |
|---------|-----|
| PyGithub | Direct httpx is consistent with all other HTTP tools (`web`, `tavily`, swarm). PyGithub adds a heavy abstraction. |
| `push`/`pull` in `git_ops/` | They're the remote-sync pair for the PR workflow — grouping with PR actions keeps the workflow discoverable. |
| Bare `--force` | `--force-with-lease` is strictly safer. No scenario where bare `--force` is the right choice. |
| Async httpx | All tools use sync httpx. Concurrency via `parallel()` (ThreadPoolExecutor). |
| Configurable `GITHUB_API_BASE` (v1.x) | Hardcoded to `https://api.github.com` — no SSRF surface. GHE = Phase 4+. |
| Refactoring 14 actions in this commit | Too large a diff. helpers.py + 4 bug fixes + contract fix shipped in v1.4; action migration is a follow-up. |

---

*Last updated: 2026-07-15 (v1.4). See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
