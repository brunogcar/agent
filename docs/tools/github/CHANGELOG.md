<- Back to [GitHub Overview](../GITHUB.md)

# 🗺️ Changelog

## Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.3.1 | 2026-07-13 | Cross-LLM review hardening: 2 P2 + 4 P3 fixes + doc trim. See Completed. |
| v1.3 | 2026-07-10 | `pull` action (remote-sync counterpart to `push`) + autocode integration (6 opt-in env vars). 16 actions. |
| v1.2 | 2026-07-10 | `issue_get` + `issue_update` (unified close/reopen/edit) + `release_get`. Pagination on `pr_list`/`issue_list`. `mergeable`/`mergeable_state` in `pr_get`. Bug fix: `if not number:` (was `is None`). |
| v1.1 | 2026-07-10 | Issues + releases: `issue_create`/`issue_list`/`issue_comment`/`release_create`/`release_list`. 12 actions. |
| v1.0 | 2026-07-10 | Initial release — 7 actions (6 PR + `push`), httpx direct, `--force-with-lease`. |

## Breaking Changes

**None.** GitHub is a brand-new tool (v1.0). All subsequent versions are additive.

**v1.3.1 additive changes:**
- `release_list` gains `page` param + `page`/`has_next`/`next_page` in result (was missing pagination — P2-2 fix)
- v1.1 actions (`issue_create`/`issue_comment`/`release_create`/`release_list`) now propagate `status=<http_code>` in `fail()` on API errors (was missing — P2-1 fix). Callers checking `result["status"]` now see the HTTP int code instead of `"error"` for API failures.
- `issue_comment` now coerces `number` to int (P3-2 fix) — non-numeric values fail fast with `"must be an int"` instead of hitting the API.

## Completed

| Feature | Status | Notes |
|---------|--------|-------|
| **v1.3.1 fixes** | | |
| v1.1 error-handling consistency (P2-1) | ✅ v1.3.1 | `issue_create`/`issue_comment`/`release_create`/`release_list` rewritten to match v1.0/v1.2 3-stage pattern (network → HTTP → JSON parse) with `status=` + `trace_id=` on all fail()/ok() |
| `release_list` pagination (P2-2) | ✅ v1.3.1 | Added `page` param + `parse_link_header` — parity with `pr_list`/`issue_list`. Was capped at 100 items. |
| `issue_comment` int coercion (P3-2) | ✅ v1.3.1 | Now coerces `number` to int for parity with 6 other actions |
| `_make_response()` headers fix (P3-3) | ✅ v1.3.1 | Conftest helper now sets `resp.headers = {}` so pagination tests using `_make_response()` work correctly |
| INSTRUCTIONS numbering fix (P3-1) | ✅ v1.3.1 | ALWAYS DO rules renumbered to start at #21 (was #19, duplicating NEVER DO #19-20) |
| INSTRUCTIONS rule #9 stale "v1.0" (P3-4) | ✅ v1.3.1 | Changed "in v1.0" → "in v1.x" |
| Doc trim | ✅ v1.3.1 | API.md 817→~230 lines, ARCHITECTURE.md 305→~110, GITHUB.md 152→~80, CHANGELOG.md 145→~90 |
| **v1.3 — pull + autocode** | | |
| `pull` action | ✅ v1.3 | `git pull origin <branch>` subprocess. `branch` empty = current. 120s timeout. NOT parallel-safe. |
| Autocode integration | ✅ v1.3 | 6 opt-in env vars: `AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`. All default OFF. |
| **v1.2 — issue/release reads + pagination** | | |
| `issue_get` / `issue_update` / `release_get` | ✅ v1.2 | 3 new actions. `issue_update` unifies close/reopen/edit. |
| Pagination (`pr_list`/`issue_list`) | ✅ v1.2 | `page` param + `parse_link_header()`. Response gains `page`/`has_next`/`next_page`. |
| `mergeable`/`mergeable_state` in `pr_get` | ✅ v1.2 | Pre-merge checks. `null` = still computing (retry). |
| `if not number:` bug fix | ✅ v1.2 | Was `is None` — facade defaults `number=0`, so missing-arg hit API with `number=0`. Fixed across 4 actions. |
| **v1.1 — issues + releases** | | |
| `issue_create`/`issue_list`/`issue_comment`/`release_create`/`release_list` | ✅ v1.1 | 5 new actions. v1.3.1: error handling upgraded to 3-stage pattern. |
| **v1.0 — PR + push** | | |
| 7 actions (6 PR + `push`) | ✅ v1.0 | httpx direct, `--force-with-lease`, singleton client, `is_configured()` short-circuit |
| Test suite | ✅ v1.0→v1.3.1 | 16 → 78 → 85 → 92 tests. All mock httpx + subprocess — no real API/git calls. |

## Roadmap — Phase 4+

| Feature | Notes | Priority |
|---------|-------|----------|
| `push`/`pull` `root` param (cwd scoping) | Add `root: str = ""` to scope subprocess to `agent`/`workspace`/`/abs/path` (mirrors `git()` tool). Currently runs in CWD. | P2 |
| GitHub Enterprise (GHE) support | `GITHUB_API_BASE` env override → `https://github.<company>.com/api/v3`. One-line change in `client.py`. | P3 |
| Rate-limit tracking | Surface `X-RateLimit-Remaining`/`X-RateLimit-Reset` headers in result. Currently relies on 403 response. | P3 |
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

---

*Last updated: 2026-07-13 (v1.3.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
