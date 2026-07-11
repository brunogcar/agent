<- Back to [GitHub Overview](../GITHUB.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.3 | 2026-07-10 | **Pull action + autocode integration:** 1 new action (`pull`). Pull is the remote-sync counterpart to `push` — `git pull origin <branch>` as a local subprocess. Lives in `github_ops` (NOT `git_ops`) for the same reason as `push` — it's part of the remote workflow (pull before branching → push after committing). NOT parallel-safe: `_NOT_PARALLEL_SAFE` updated from `frozenset({"push"})` → `frozenset({"push", "pull"})`. Facade `doc_sections` gains a `Pull commits | github(pull)` row. **Documentation bug fix:** corrected the stale Phase 3 roadmap row that claimed autocode v1.2 used raw `subprocess.run(["git", "push", ...])` — autocode v1.2 had NO push at all (branch + commit were local-only); the corrected row now describes the net-new push capability shipped in autocode v1.3 via `github(action="push")` with `--force-with-lease` safety. **Autocode v1.3 integration landed:** `node_publish` + `workflows/autocode_impl/github_ops.py` helper wire in `push` / `pr_create` / `pr_merge` (gated by `AUTOCODE_PUSH_ON_COMMIT` / `AUTOCODE_OPEN_PR` / `AUTOCODE_AUTO_MERGE`); `node_systematic_debug` wires in `pr_comment` for low-confidence swarm verdicts (`AUTOCODE_DEBUG_COMMENT_PR`); `node_git_branch` wires in `pull` (`AUTOCODE_PULL_BEFORE_BRANCH`). All gated off by default — autocode v1.3 behaves identically to v1.2 when no GitHub env vars or flags are set. Tests: 78 → 85 (+7 new tests in `test_pull.py`; `test_dispatch.py` updated 15 → 16 actions; `conftest.py` notes push + pull both as subprocess, neither in `_API_ACTION_MODULES`). |
| v1.2 | 2026-07-10 | **Issue / Release reads + pagination + mergeable:** 3 new actions (`issue_get`, `issue_update`, `release_get`). `issue_update` unifies close/reopen/edit (replaces roadmap's `issue_close`/`issue_reopen` split). Pagination on `pr_list` + `issue_list` via `page` param + `parse_link_header()` helper in `client.py` (returns `page`/`has_next`/`next_page`). `mergeable` + `mergeable_state` surfaced in `pr_get`. Facade `state` default changed `"open"` → `""` (list actions default to "open" internally; `issue_update` treats `""` as "don't change"). New `page: int = 1` param. Bug fixes: `pr_get`/`pr_review`/`pr_merge`/`pr_comment` use `if not number:` (was `is None`) to catch facade default `number=0`; `pr_comment` uses `bool(line)` (was `is not None`) to catch facade default `line=0`. Tests: 32 → 78 (+4 new test files for pr_get/pr_review/pr_merge/pr_comment; +16 new tests in `test_issues_releases.py` / `test_pr_list.py`; `test_dispatch.py` updated 12 → 15 actions). |
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
| `pull` action | ✅ v1.3 | Local `git pull <remote> [<branch>]` subprocess — fetches + merges recent commits from the remote. Optional `branch` (empty = current branch), `remote` (default `"origin"`). Returns `{status, branch, remote, pulled: true, output}`. 120s timeout; shell-metacharacter rejection (defense in depth — same as `push`). Does NOT require `GITHUB_TOKEN`. Lives in `github_ops/` (NOT `git_ops/`) for the same reason as `push` — it's the remote-sync counterpart in the PR workflow (pull before branching → push after committing). Added specifically for autocode v1.3 integration (`AUTOCODE_PULL_BEFORE_BRANCH`). |
| `_NOT_PARALLEL_SAFE` includes `pull` | ✅ v1.3 | Facade `_NOT_PARALLEL_SAFE` updated from `frozenset({"push"})` to `frozenset({"push", "pull"})`. Both `push` and `pull` are subprocess actions — concurrent `git pull` on the same repo races on `.git/index.lock` (same lock-contention reason as `push`). Neither is in `PARALLEL_SAFE`. |
| Facade `doc_sections` includes `pull` row | ✅ v1.3 | `@meta_tool` `doc_sections` list gains `" | Pull commits | github(pull) | git pull origin branch (local subprocess)"` — placed right after the `push` row so the remote-sync pair is visually grouped. |
| `pull` action — `--force-with-lease` N/A | ✅ v1.3 | `pull` has no `force` param (force-push semantics don't apply to pull). It runs plain `git pull <remote> [<branch>]`. Conflict resolution is left to git's default (merge); a conflicting pull returns non-zero exit → `fail(f"git pull failed (exit {code}): {output}")` with the stderr text. |
| Autocode v1.3 — `github(action="push")` integration (was Phase 3, P2) | ✅ v1.3 | Autocode v1.2 had **NO push** — `node_git_branch` and `node_commit` only touched the local VCS via the `git()` facade (verified by A1 research). v1.3 adds net-new push capability via `workflows/autocode_impl/github_ops.py:_github_push()` → `github(action="push", branch=..., remote="origin", force=False)`. Gated by `AUTOCODE_PUSH_ON_COMMIT=1`. Wired in `workflows/autocode_impl/nodes/publish.py:node_publish` (runs after `node_commit`, before `node_distill_memory`). Uses `--force-with-lease` safety via the github tool. **(Corrected the stale v1.2 CHANGELOG row — see Phase 3 section below.)** |
| Autocode v1.3 — `github(action="pr_create")` after push (was Phase 3, P1) | ✅ v1.3 | Wired in `node_publish` after a successful push via `_github_pr_create(branch, title, body)`. Gated by `AUTOCODE_OPEN_PR=1`. PR body built from autocode state (task, commit_sha, verification_passed, root_cause, swarm_verdict) by `_build_pr_body()` in `publish.py`. The PR `number` is captured in autocode state and used by the debug-comment + auto-merge hooks. |
| Autocode v1.3 — `github(action="pr_merge")` auto-merge gate (was Phase 3, P2) | ✅ v1.3 | Wired in `node_publish` after a successful `pr_create` via `_github_pr_merge(number)`. Gated by `AUTOCODE_AUTO_MERGE=1` (default OFF — dangerous). Uses `merge_method="squash"` (matches the github tool default). # TODO(2.0): make merge method configurable via `AUTOCODE_AUTO_MERGE_METHOD` env var. |
| Autocode v1.3 — `github(action="pr_comment")` for low-confidence debug (was Phase 3, P3) | ✅ v1.3 | Wired in `node_systematic_debug` (`workflows/autocode_impl/nodes/debug.py`). When `AUTOCODE_SWARM_DEBUG=1` produces a LOW-confidence swarm verdict AND `AUTOCODE_DEBUG_COMMENT_PR=1` AND a PR number exists in state, posts the root_cause + agreement + provider count as a PR comment via `_github_pr_comment(number, body)`. Surfaces the disagreement for human review instead of silently applying the fix. |
| Autocode v1.3 — `github(action="pull")` before branching (new in v1.3) | ✅ v1.3 | Wired in `node_git_branch` via `_github_pull(tid)` before `_git_create_branch()`. Gated by `AUTOCODE_PULL_BEFORE_BRANCH=1`. Non-blocking — pull failure doesn't abort the workflow (defensive: a missing remote shouldn't break local autocode runs). Ensures the branch is based on the latest remote state. # TODO(2.0): consider making pull failure configurable (abort vs warn). |
| Autocode v1.3 — `github_ops.py` workflow helper module | ✅ v1.3 | New `workflows/autocode_impl/github_ops.py` module mirrors the existing `git_ops.py` pattern (lazy imports, project_root scoping, `tracer.step` logging, structured returns). Provides `_github_is_configured()`, `_github_pull()`, `_github_push()`, `_github_pr_create()`, `_github_pr_comment()`, `_github_pr_merge()`, `_swarm_debug_consensus()`. All functions graceful-skip (return False / None) if GitHub is not configured — autocode works identically to v1.2 when no GitHub env vars are set. # TODO(2.0): consider merging git_ops.py + github_ops.py into a unified vcs_ops.py module. |
| Autocode v1.3 — new env vars in `core/config.py` | ✅ v1.3 | 6 new env vars (all default OFF): `AUTOCODE_PULL_BEFORE_BRANCH`, `AUTOCODE_PUSH_ON_COMMIT`, `AUTOCODE_OPEN_PR`, `AUTOCODE_AUTO_MERGE`, `AUTOCODE_DEBUG_COMMENT_PR`, `AUTOCODE_SWARM_DEBUG`. All read as `os.getenv("<NAME>", "0") == "1"` — boolean flags, no value parsing. |
| Documentation bug fix — stale Phase 3 push row | ✅ v1.3 | The v1.2 CHANGELOG Phase 3 roadmap row at line ~92 claimed "Currently autocode's branch node uses raw `subprocess.run(['git', 'push', ...])`" — this was **factually wrong** (verified by A1 research: autocode v1.2 had NO push call anywhere in the workflow). Corrected to: "Add net-new push capability to autocode (autocode v1.2 had NO push — branch + commit were local-only). Replaced with `github(action='push')` for structured result + `--force-with-lease` safety." See Phase 3 section below. |
| `test_pull.py` (7 tests) | ✅ v1.3 | New test file mirroring `test_push.py`: success with branch, success on current branch (empty branch), custom remote, subprocess non-zero exit, timeout, git-not-found, forbidden shell chars in branch. All tests patch `tools.github_ops.actions.pull.subprocess.run` — no real git remote touched. |
| `test_dispatch.py` updated 15 → 16 actions | ✅ v1.3 | `test_dispatch_has_15_actions` renamed to `test_dispatch_has_16_actions`; `test_unknown_action` now asserts `"pull"` appears in the error message alongside the other 15 action names. Phase-3 push/pull integration comment updated to reflect that these integrations are now SHIPPED in autocode v1.3 (not future). |
| `conftest.py` notes `pull` as subprocess (excluded from `_API_ACTION_MODULES`) | ✅ v1.3 | `_API_ACTION_MODULES` unchanged (still 14 modules — pull doesn't use httpx). Docstring updated: "`push.py` + `pull.py` are intentionally NOT in this list — they use subprocess, not httpx." Mock strategy section notes that `pull` tests patch `subprocess.run` directly (same as `push`). |
| Test suite (85 tests) | ✅ v1.3 | `conftest.py` + `test_dispatch.py` (4 tests) + `test_pr_create.py` (4) + `test_pr_list.py` (5) + `test_pr_get.py` (6) + `test_pr_review.py` (7) + `test_pr_merge.py` (7) + `test_pr_comment.py` (7) + `test_issues_releases.py` (26) + `test_push.py` (4) + `test_pull.py` (7). All pass with `mock_cfg` / `mock_not_configured` / `mock_httpx_client` fixtures. |
| `issue_get` action | ✅ v1.2 | GET `/repos/{owner}/{repo}/issues/{number}` — single issue details (number, title, state, body, url, labels, assignee, user, created_at, updated_at, closed_at). 404 → "Issue #N not found". |
| `issue_update` action | ✅ v1.2 | PATCH `/repos/{owner}/{repo}/issues/{number}` — unified close/reopen/edit (replaces roadmap's `issue_close`/`issue_reopen` split). `state="open"`/`"closed"`/`""` (empty = don't change); also edits `title`, `body`, `labels`, `assignees`. At least one field required. |
| `release_get` action | ✅ v1.2 | GET `/repos/{owner}/{repo}/releases/tags/{tag}` (by tag, preferred) OR GET `/repos/{owner}/{repo}/releases/{id}` (by numeric ID). Returns id, tag, name, url, draft, prerelease, created_at, published_at, body, assets list. |
| Pagination on `pr_list` + `issue_list` | ✅ v1.2 | New `page` param (default 1) on both list actions. New `parse_link_header()` helper in `client.py` parses the GitHub `Link` header. Response shape gains `page`, `has_next`, `next_page`. Lets callers iterate repos with >100 PRs/issues. |
| `mergeable` + `mergeable_state` in `pr_get` | ✅ v1.2 | `pr_get` response now surfaces `mergeable` (true/false/null — null = still computing, retry) and `mergeable_state` ("clean"/"blocked"/"unstable"/"dirty"/"unknown"). Use BEFORE `pr_merge` to pre-check. |
| `parse_link_header()` in `client.py` | ✅ v1.2 | New module-level helper — extracts `next`/`last` page numbers from a GitHub `Link` header. Returns `{"next": int|None, "last": int|None}`. Used by `pr_list` + `issue_list`. |
| Facade `state` default `"open"` → `""` | ✅ v1.2 | `pr_list`/`issue_list` internally default to `"open"` when empty (no behavior change for callers). `issue_update` treats `""` as "don't change" — enables the unified close/reopen/edit design without a separate no-op sentinel. |
| New `page: int = 1` facade param | ✅ v1.2 | Added to the `github()` facade signature + forwarded in `kwargs`. Used by `pr_list`/`issue_list`; ignored by other actions via `**kwargs`. |
| Bug fix — `number=0` facade default not caught | ✅ v1.2 | `pr_get`/`pr_review`/`pr_merge`/`pr_comment` previously checked `if number is None:` but the facade defaults `number=0`, so `github(action="pr_get")` (no number) passed validation and hit the API with `number=0`. Changed to `if not number:` — fails fast with `"number is required for <action>"`. |
| Bug fix — `line=0` facade default not caught in `pr_comment` | ✅ v1.2 | `pr_comment` previously computed `line_set = line is not None` but the facade defaults `line=0`, so `line=0` was treated as "set" and triggered XOR-failure when `path` was also empty. Changed to `line_set = bool(line)` — `0` is treated as "not set", matching `path=""` semantics. |
| Test coverage for `pr_get` / `pr_review` / `pr_merge` / `pr_comment` | ✅ v1.2 | 4 new test files: `test_pr_get.py` (6 tests), `test_pr_review.py` (7 tests), `test_pr_merge.py` (7 tests), `test_pr_comment.py` (7 tests). Mirrors the existing `test_pr_create.py` / `test_pr_list.py` pattern. |
| Test coverage for `issue_get` / `issue_update` / `release_get` | ✅ v1.2 | `test_issues_releases.py` extended: +TestIssueGet (4 tests), +TestIssueUpdate (7 tests), +TestReleaseGet (5 tests). +1 pagination test for `issue_list`. |
| Test coverage for `pr_list` pagination | ✅ v1.2 | `test_pr_list.py` extended: +2 pagination tests (Link header parsed → `has_next`/`next_page` populated; no Link header → `has_next=False`, `next_page=None`). |
| `test_dispatch.py` updated 12 → 15 actions | ✅ v1.2 | `test_dispatch_has_15_actions` (was `_12_`); `test_unknown_action` now asserts all 15 action names appear in the error message. |
| `conftest.py` updated for 14 API modules | ✅ v1.2 | `_API_ACTION_MODULES` gains `issue_get`, `issue_update`, `release_get` (12 → 14 API modules; `push` still excluded). Default mock `headers = {}` so `pr_list`/`issue_list` `resp.headers.get("link", "")` works without per-test setup. |
| Test suite (78 tests) | ✅ v1.2 | `conftest.py` + `test_dispatch.py` (4 tests) + `test_pr_create.py` (4) + `test_pr_list.py` (5) + `test_pr_get.py` (6) + `test_pr_review.py` (7) + `test_pr_merge.py` (7) + `test_pr_comment.py` (7) + `test_issues_releases.py` (26) + `test_push.py` (4). All pass with `mock_cfg` / `mock_not_configured` / `mock_httpx_client` fixtures. |
| `github()` tool facade | ✅ v1.0 (updated v1.3) | `@tool` + `@meta_tool` + manual dispatch; `action: str` (not `Literal`); `_NOT_PARALLEL_SAFE = frozenset({"push"})` in v1.0 → `frozenset({"push", "pull"})` in v1.3 |
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

## 🔄 Roadmap — Phase 2: Issues + Releases (shipped in v1.1 + v1.2)

Phase 2 is **complete**. The remaining items below are tracked for history; see the ✅ Completed section above for implementation notes.

| Feature | Status | Notes |
|---------|-------|-------|
| `issue_create` action | ✅ v1.1 | POST `/repos/{owner}/{repo}/issues` — open a new issue. Params: `title`, `body`, `labels` (comma-separated), `assignees` (comma-separated). |
| `issue_list` action | ✅ v1.1 (+ v1.2 pagination) | GET `/repos/{owner}/{repo}/issues?state=...&labels=...` — list issues. v1.2 added `page` param + Link-header parsing. |
| `issue_get` action | ✅ v1.2 | GET `/repos/{owner}/{repo}/issues/{number}` — single issue details. Mirrors `pr_get` shape. |
| `issue_comment` action | ✅ v1.1 | POST `/repos/{owner}/{repo}/issues/{number}/comments` — comment on an issue. SAME endpoint as general `pr_comment` (PRs are issues); kept as a separate action for caller clarity. |
| `issue_close` / `issue_reopen` actions | ✅ v1.2 (unified as `issue_update`) | Originally planned as two separate actions; **shipped as a single unified `issue_update`** that handles close/reopen via the `state` param AND edits title/body/labels/assignees. See ARCHITECTURE.md → Key Design Decisions for rationale. |
| `release_create` action | ✅ v1.1 | POST `/repos/{owner}/{repo}/releases` — create a release from a tag. Params: `tag_name`, `name`, `body`, `target_commitish`, `draft`, `prerelease`. |
| `release_list` action | ✅ v1.1 | GET `/repos/{owner}/{repo}/releases` — list releases. |
| `release_get` action | ✅ v1.2 | GET `/repos/{owner}/{repo}/releases/tags/{tag}` (by tag, preferred) OR GET `/repos/{owner}/{repo}/releases/{id}` (by numeric ID). Tag-based lookup is more user-friendly. |
| Pagination support for `pr_list` / `issue_list` | ✅ v1.2 | `page` param + `parse_link_header()` helper in `client.py`. Response gains `page`, `has_next`, `next_page`. |
| `mergeable` state in `pr_get` response | ✅ v1.2 | `mergeable` (true/false/null) + `mergeable_state` ("clean"/"blocked"/"unstable"/"dirty"/"unknown") now surfaced in `pr_get`. |
| Test coverage for `pr_get`, `pr_review`, `pr_merge`, `pr_comment` | ✅ v1.2 | 4 new test files (27 tests total across the four actions). |

---

## 🔄 Roadmap — Phase 3 (v1.3): Autocode Integration — shipped in v1.3

Phase 3 is **complete** (shipped in autocode v1.3). The remaining items below are tracked for history; see the ✅ Completed section above for implementation notes. All integrations are gated by opt-in env vars (default OFF) so autocode behaves identically to v1.2 when no GitHub env vars or flags are set.

| Feature | Status | Notes |
|---------|-------|-------|
| Autocode workflow → `github(pr_create)` after `autocode(branch)` | ✅ v1.3 | Wired in `node_publish` (between `node_commit` and `node_distill_memory`) via `_github_pr_create(branch, title, body)`. Gated by `AUTOCODE_OPEN_PR=1`. PR body auto-built from autocode state. See ✅ Completed above. |
| Autocode debug loop → `github(pr_review, event="COMMENT")` (now `pr_comment`) | ✅ v1.3 (revised shape) | Originally planned as `pr_review(event="COMMENT")`; shipped as `pr_comment` instead (simpler — general comment vs. formal review). Wired in `node_systematic_debug` for LOW-confidence swarm verdicts. Gated by `AUTOCODE_DEBUG_COMMENT_PR=1` (requires `AUTOCODE_SWARM_DEBUG=1` + a PR `number` in state — the chain dependency flagged in A2 research was respected). `defense_notes` is the most useful field surfaced, as A2 predicted. |
| Autocode merge gate → `github(pr_merge)` after `verify` node passes | ✅ v1.3 | Wired in `node_publish` after a successful `pr_create`. Gated by `AUTOCODE_AUTO_MERGE=1` (default OFF — dangerous). `AUTOCODE_AUTO_MERGE` was a NEW env var (not in v1.2 `core/config.py`) — flagged by A2 research, added in v1.3. Uses `merge_method="squash"`. |
| Autocode status reporting via `github(pr_comment)` | ✅ v1.3 (partial — debug-only) | Status reporting via `tracer.step` already happens per node. v1.3 ships the debug-comment subset (low-confidence swarm verdict → PR comment). The broader progress-comment hook (branch → execute → verify → merge) is deferred — see Phase 4+. |
| **[BUG FIX]** Add net-new `github(action="push")` integration in autocode | ✅ v1.3 | **CORRECTED ROW.** The original v1.2 roadmap row claimed: *"Currently autocode's branch node uses raw `subprocess.run(['git', 'push', ...])` — replace with `github(action="push", branch=..., force=True)`"* — this was **factually wrong** (verified by A1 research: autocode v1.2 had NO `git push` call anywhere in the workflow; `node_git_branch` and `node_commit` only touched the local VCS via the `git()` facade). The correct description: **autocode v1.2 had NO push capability — branch + commit were local-only. v1.3 adds net-new push** via `workflows/autocode_impl/github_ops.py:_github_push()` → `github(action="push", branch=..., force=False)`, wired in `node_publish`. Uses `--force-with-lease` safety via the github tool's `force=True` path (autocode uses `force=False` by default — non-destructive). Gated by `AUTOCODE_PUSH_ON_COMMIT=1`. |
| `github(action="pull")` before branching (NEW in v1.3) | ✅ v1.3 | Not on the original Phase 3 roadmap — added specifically for v1.3. Wired in `node_git_branch` via `_github_pull(tid)` before `_git_create_branch()`. Gated by `AUTOCODE_PULL_BEFORE_BRANCH=1`. Non-blocking. See ✅ Completed above. |

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
| `push` action in `git_ops/` (instead of `github_ops/`) | By design — `push` is the prerequisite for the PR workflow, grouping it with PR actions makes the workflow discoverable. `git_ops/` stays focused on local repo inspection. See ARCHITECTURE.md → Key Design Decisions. **v1.3:** `pull` follows the same convention for the same reason — together they form the remote-sync pair (`pull` before branching → `push` after committing). |
| `--force` (bare) option | By design — `--force-with-lease` is strictly safer. There's no scenario where bare `--force` is the right choice over `--force-with-lease`. If you need to overwrite remote refs, fetch first then force-with-lease. **v1.3:** `pull` has no `force` param at all — force semantics don't apply to pull. |
| Configurable `GITHUB_API_BASE` via env | Deferred to Phase 4+ — GHE support. v1.0 hardcodes `https://api.github.com` because GitHub.com is the only target in the project's scope. Adding env override later is a one-line change in `client.py`. |
| `--force` flag for API actions | N/A — API actions are idempotent at the action level. `pr_create` always creates a new PR; `pr_merge` is idempotent (returns 409 if already merged). No force flag needed. |
| Async httpx client | All other tools use sync httpx. Concurrency is achieved via `parallel()` (ThreadPoolExecutor) for API actions. Async would add complexity without clear benefit. |
| Streaming uploads for large `body` payloads | GitHub API has a 65,536 character limit on PR/issue bodies. Streaming is unnecessary. |

---

*Last updated: 2026-07-10 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
