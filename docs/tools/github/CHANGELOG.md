<- Back to [GitHub Overview](../GITHUB.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.1 | 2026-07-10 | **Issues + Releases:** 5 new actions (`issue_create`, `issue_list`, `issue_comment`, `release_create`, `release_list`). Issues support labels + assignees. Releases support draft + prerelease flags. `issue_comment` works on both issues and PRs (shared endpoint). Facade updated with `labels`, `assignees`, `tag`, `draft`, `prerelease` params. |
| v1.0 | 2026-07-10 | Initial release — 7 actions (`pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `push`), `@meta_tool` + `github_ops/` pattern, httpx direct (not PyGithub), `--force-with-lease` for safe force-push |

---

## ⚠️ Breaking Changes

### (none — new tool)

GitHub is a brand-new tool introduced in v1.0. There are no prior versions to break compatibility with. The first version's API is the baseline.

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| `github()` tool facade | ✅ v1.0 | `@tool` + `@meta_tool` + manual dispatch; `action: str` (not `Literal`); `_NOT_PARALLEL_SAFE = frozenset({"push"})` |
| `github_ops/` subpackage | ✅ v1.0 | `_registry.py` + `client.py` + `actions/` (auto-imported by `__init__.py`). No `helpers.py` — each handler is self-contained |
| `pr_create` action | ✅ v1.0 | POST `/repos/{owner}/{repo}/pulls` — required `title` + `head`; optional `base` (default "main") + `body` |
| `pr_list` action | ✅ v1.0 | GET `/repos/{owner}/{repo}/pulls?state=...&per_page=...` — `state` filter + client-side slice for `limit` (capped at 100) |
| `pr_get` action | ✅ v1.0 | GET `/repos/{owner}/{repo}/pulls/{number}` — single PR details; 404 → "PR #N not found" |
| `pr_review` action | ✅ v1.0 | POST `/repos/{owner}/{repo}/pulls/{number}/reviews` — `event` validated client-side against `APPROVE` / `REQUEST_CHANGES` / `COMMENT` |
| `pr_merge` action | ✅ v1.0 | PUT `/repos/{owner}/{repo}/pulls/{number}/merge` — default `merge_method="squash"`; specific handling for 404 / 405 (not mergeable) / 409 (stale head) |
| `pr_comment` action | ✅ v1.0 | Dual-mode: general (`/issues/{n}/comments`) OR line-level (`/pulls/{n}/comments` with `subject_type=line`); XOR validation on `path` / `line` |
| `push` action | ✅ v1.0 | Local `git push` subprocess — `--force-with-lease` when `force=True`; 120s timeout; shell-metacharacter rejection (defense in depth) |
| `client.py` singleton httpx.Client | ✅ v1.0 | `get_client()` / `close_client()` / `is_configured()` / `repo_path()` / `GITHUB_API_BASE`; double-checked locking with `threading.Lock` |
| `is_configured()` short-circuit | ✅ v1.0 | `bool(cfg.github_token and cfg.github_owner and cfg.github_repo)` — first empty value triggers fail-fast with env-var hint |
| `duration_ms` timing | ✅ v1.0 | Wall-clock timing at facade level; injected into every successful result |
| `trace_id` propagation | ✅ v1.0 | Auto-injected into result dict if missing |
| `GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` env vars | ✅ v1.0 | Added to `core/config.py`; all commented out by default in `.env` |
| PARALLEL_SAFE for API actions | ✅ v1.0 | 6 API actions are stateless HTTP calls — safe to parallelize. `push` excluded (subprocess → lock contention) |
| Test suite (16 tests) | ✅ v1.0 | `conftest.py` (3 fixtures) + `test_dispatch.py` (5 tests) + `test_pr_create.py` (4) + `test_pr_list.py` (3) + `test_push.py` (4). All pass with `mock_cfg` / `mock_not_configured` / `mock_httpx_client` fixtures |
| Documentation (5-file standard) | ✅ v1.0 | GITHUB.md landing + API.md + ARCHITECTURE.md + CHANGELOG.md + INSTRUCTIONS.md |
| `docs/TOOLS.md` integration | ✅ v1.0 | Tool count 16 → 17; added to summary table, module map, detailed catalog (#17) |

---

## 🔄 Roadmap — Phase 2: Issues + Releases

| Feature | Notes | Priority |
|---------|-------|----------|
| `issue_create` action | POST `/repos/{owner}/{repo}/issues` — open a new issue. Params: `title`, `body`, `labels` (list), `assignees` (list). | P1 |
| `issue_list` action | GET `/repos/{owner}/{repo}/issues?state=...&labels=...` — list issues. Reuse `pr_list` pagination pattern. | P1 |
| `issue_get` action | GET `/repos/{owner}/{repo}/issues/{number}` — single issue details. Mirror `pr_get` shape. | P1 |
| `issue_comment` action | POST `/repos/{owner}/{repo}/issues/{number}/comments` — comment on an issue. Note: this is the SAME endpoint as general `pr_comment` (PRs are issues). Consider unifying. | P1 |
| `issue_close` / `issue_reopen` actions | PATCH `/repos/{owner}/{repo}/issues/{number}` with `state: "closed"` or `state: "open"`. | P2 |
| `release_create` action | POST `/repos/{owner}/{repo}/releases` — create a release from a tag. Params: `tag_name`, `name`, `body` (release notes), `target_commitish`, `draft`, `prerelease`. | P2 |
| `release_list` action | GET `/repos/{owner}/{repo}/releases` — list releases. | P2 |
| `release_get` action | GET `/repos/{owner}/{repo}/releases/{id}` — single release details. | P2 |
| Pagination support for `pr_list` / `issue_list` | Currently capped at 100 (GitHub API per_page max). Add `page` param + Link-header parsing for multi-page iteration. | P2 |
| `mergeable` state in `pr_get` response | GitHub returns `mergeable` (bool/null) and `mergeable_state` (clean / blocked / unstable / dirty) — currently NOT surfaced. Add to `pr_get` return shape. | P2 |
| Test coverage for `pr_get`, `pr_review`, `pr_merge`, `pr_comment` | Phase 1 only covers `pr_create` / `pr_list` / `push`. Add 4 test files mirroring the existing pattern. | P2 |

---

## 🔄 Roadmap — Phase 3: Autocode Integration

| Feature | Notes | Priority |
|---------|-------|----------|
| Autocode workflow → `github(pr_create)` after `autocode(branch)` | When autocode completes a fix on a branch, automatically open a PR via `github(action="pr_create", head=branch_name, title=fix_summary, body=diff_summary)`. Wire into `workflows/autocode_impl/nodes/branch.py` or a new `open_pr.py` node. | P1 |
| Autocode debug loop → `github(pr_review, event="COMMENT")` | When the autocode debug node identifies a root cause, post it as a review comment on the PR for human review. Wire into `workflows/autocode_impl/nodes/debug.py`. | P2 |
| Autocode merge gate → `github(pr_merge)` after `verify` node passes | If autocode verification passes, automatically merge the PR via `github(action="pr_merge", merge_method="squash")`. Add a config flag `AUTOCODE_AUTO_MERGE=false` (default off — human approval required). | P2 |
| Autocode status reporting via `github(pr_comment)` | Post progress comments on the PR as autocode moves through nodes (branch → execute → verify → merge). Long-running autocode runs benefit from visible progress on the PR. | P3 |
| `github(action="push")` integration in autocode branch node | Currently autocode's branch node uses raw `subprocess.run(["git", "push", ...])` — replace with `github(action="push", branch=..., force=True)` for consistent `--force-with-lease` safety + structured result. | P2 |

---

## 🔄 Roadmap — Phase 4+ (Out of Scope for v1.0)

| Feature | Notes | Priority |
|---------|-------|----------|
| GitHub Enterprise (GHE) support | `GITHUB_API_BASE` env var to override `https://api.github.com` → `https://github.<company>.com/api/v3`. Requires updating `client.py` to read from env. | P3 |
| Per-action rate limit tracking | GitHub returns rate-limit headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`). Track per-token + surface in result dict. Currently relies on GitHub's 403 response. | P3 |
| GraphQL API support | GitHub's REST API is used throughout v1.0. For complex queries (e.g. "all PRs reviewed by user X with status Y"), GraphQL is more efficient. Add `github(action="graphql", query=...)` action. | P4 |
| Webhook receiver for PR events | Out of scope for a tool (passive). Would belong in `core/gateway_backend/routes/` as a new endpoint. | P4 |
| `pr_close` action | PATCH `/repos/{owner}/{repo}/pulls/{number}` with `state: "closed"`. Useful for closing PRs without merging. | P3 |
| `pr_update` action | PATCH `/repos/{owner}/{repo}/pulls/{number}` — update title / body / base / state. Useful for converting drafts to ready-for-review. | P3 |
| `branch_create_remote` action | POST `/repos/{owner}/{repo}/git/refs` — create a remote branch via API (no local push needed). Edge case — usually you push a local branch instead. | P4 |
| `pr_review` with line-level comments payload | Currently `pr_review` submits a review without line-level comments. Adding `comments=[{path, line, body, side}]` would let reviews include inline comments in one submit. | P3 |

---

## 🚫 Deferred / Out of Scope

| Feature | Why deferred |
|---------|--------------|
| PyGithub as the API client | By design — direct httpx is consistent with all other HTTP tools in the project (`web`, `tavily`, swarm). PyGithub adds a heavy abstraction layer with little value. See ARCHITECTURE.md → Key Design Decisions. |
| `push` action in `git_ops/` (instead of `github_ops/`) | By design — `push` is the prerequisite for the PR workflow, grouping it with PR actions makes the workflow discoverable. `git_ops/` stays focused on local repo inspection. See ARCHITECTURE.md → Key Design Decisions. |
| `--force` (bare) option | By design — `--force-with-lease` is strictly safer. There's no scenario where bare `--force` is the right choice over `--force-with-lease`. If you need to overwrite remote refs, fetch first then force-with-lease. |
| Configurable `GITHUB_API_BASE` via env | Deferred to Phase 4+ — GHE support. v1.0 hardcodes `https://api.github.com` because GitHub.com is the only target in the project's scope. Adding env override later is a one-line change in `client.py`. |
| `--force` flag for API actions | N/A — API actions are idempotent at the action level. `pr_create` always creates a new PR; `pr_merge` is idempotent (returns 409 if already merged). No force flag needed. |
| Async httpx client | All other tools use sync httpx. Concurrency is achieved via `parallel()` (ThreadPoolExecutor) for API actions. Async would add complexity without clear benefit. |
| Streaming uploads for large `body` payloads | GitHub API has a 65,536 character limit on PR/issue bodies. Streaming is unnecessary. |

---

*Last updated: 2026-07-10. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
