<- Back to [GitHub Overview](../GITHUB.md)

# 🛡️ AI Instructions

These rules apply to any AI assistant (or human editor) modifying the github tool, its action handlers, its client singleton, or its documentation. Follow them strictly — deviations have caused real bugs in similar meta-tools (`git`, `swarm`, `web`).

## ❌ NEVER DO

1. **Never hardcode a GitHub token in source code.** The token is read from `GITHUB_TOKEN` env var via `core.config.cfg.github_token`. Never embed a real or fake token in any `.py` file, test fixture, or docstring. Tests use `mock_cfg` (sets a fake `ghp_test_token_abc123`) or `mock_not_configured` (sets empty string) — never a real token. Hardcoded tokens in source = security incident.

2. **Never use PyGithub.** The github tool uses `httpx.Client` directly to call the GitHub REST API. PyGithub is a heavy abstraction that hides the raw HTTP request shape, adds a transitive dependency, and is inconsistent with the rest of the project (which uses httpx for all HTTP). See ARCHITECTURE.md → Key Design Decisions #1. If you need a higher-level abstraction, use `tools/github_ops/helpers.py:github_request()` — but keep using httpx under the hood.

3. **Never add a `push` or `pull` action to the `git` tool.** Both `push` and `pull` live in `github_ops/`, NOT `git_ops/`. They're the **remote-sync pair** for the GitHub PR workflow — `pull` before branching (fetch latest remote state) → `push` after committing (publish the branch so a PR can be opened). Adding either to `git_ops/` would split the workflow across two tools and break the discoverability rule. If you need to push a branch, use `github(action="push", branch="...")`. If you need to pull recent commits, use `github(action="pull")` or `github(action="pull", branch="main")`.

4. **Never add `push` or `pull` to `PARALLEL_SAFE` in `core/parallel_executor.py`.** Both spawn git subprocesses (`git push` / `git pull`); concurrent operations on the same repo will fail with lock contention on `.git/index.lock`. The facade declares `_NOT_PARALLEL_SAFE = frozenset({"push", "pull"})` (v1.3 — `pull` added) — do not remove this. All 14 API actions (`pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `issue_create`, `issue_list`, `issue_get`, `issue_update`, `issue_comment`, `release_create`, `release_list`, `release_get`) ARE parallel-safe and can be in `PARALLEL_SAFE` if desired.

5. **Never use `--force` (bare) for push.** Use `--force-with-lease` instead. `--force-with-lease` checks the remote ref against the local tracking ref before overwriting — if the remote has moved since your last fetch, the push is rejected. `--force` would silently overwrite, destroying teammates' commits. The `force=True` param on `push` already maps to `--force-with-lease` — do not change this. There's no scenario where bare `--force` is the right choice.

6. **Never use `shell=True` in the `push` subprocess call.** `subprocess.run(["git", "push", ..., remote, branch], ...)` — the list form is mandatory. `shell=True` would expose the process to shell injection if `branch` or `remote` contained metacharacters (git branch names cannot contain these, but defense in depth is non-negotiable). The shell-metacharacter rejection in `push.py` is a secondary check — the primary defense is the list-form subprocess call.

7. **Never skip the `is_configured()` check at the start of an API action.** Every API action (`pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `issue_create`, `issue_list`, `issue_get`, `issue_update`, `issue_comment`, `release_create`, `release_list`, `release_get`) must call `is_configured()` BEFORE making any API call. Failing fast with `fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env")` is much friendlier than a confusing 401/404 from GitHub. The `push` and `pull` actions are the ONLY exceptions — they don't use the GitHub API (local subprocess). v1.4: prefer `helpers._check_configured(trace_id)` for new actions — same check, less duplication.

8. **Never remove the `Authorization: Bearer ...` header from the httpx.Client.** `get_client()` in `client.py` builds the client with `Authorization`, `Accept`, `X-GitHub-Api-Version`, and `Content-Type` headers. All four are required by the GitHub API. Removing any of them will cause 401/403/415 errors.

9. **Never make `GITHUB_API_BASE` configurable via env in v1.x.** It's hardcoded to `https://api.github.com`. Phase 4+ roadmap item is GHE support (`GITHUB_API_BASE` env override). Don't add it prematurely — the hardcoded value is part of the security contract (no SSRF surface, see API.md → Security).

10. **Never add a new action without registering it via `@register_action("github", "<name>", ...)`.** The `__init__.py` auto-imports `actions/*.py` to trigger registration; an unregistered handler is invisible to the dispatcher and returns "Unknown action".

11. **Never use `print()` or write to `sys.stdout` inside any github code.** MCP protocol uses stdout for JSON-RPC — writing to it corrupts the payload and crashes the server. Use `core.tracer` or `sys.stderr` for logging. Same rule as every other tool in the project.

12. **Never assume `resp.json()` will succeed.** Always wrap it in try/except — GitHub can return non-JSON responses (HTML error pages, empty 204 responses, etc.). The pattern `data = resp.json()` must be followed by `except Exception as e: return fail(f"{action} returned non-JSON response: {e}")`.

13. **Never remove the per-action validation that fails fast on invalid params.** `pr_list` / `issue_list` validate `state in ("open", "closed", "all")`. `issue_update` validates `state in ("open", "closed")` (empty allowed = don't change). `pr_review` validates `event in ("APPROVE", "REQUEST_CHANGES", "COMMENT")`. `pr_merge` validates `merge_method in ("merge", "squash", "rebase")`. `pr_comment` validates the XOR of `path`/`line`. `issue_update` rejects no-op PATCHes (all fields empty). `release_get` requires `tag` OR `number`. These checks happen BEFORE the API call — failing fast with a clear message is better than letting GitHub return a 422 with a cryptic error.

14. **Never forget to forward ALL kwargs to the handler.** The facade builds `kwargs = {title, head, base, body, number, state, limit, page, event, merge_method, commit_title, commit_message, path, line, side, branch, remote, force, labels, assignees, tag, draft, prerelease, trace_id}` (23 params — v1.2 added `page`) and passes them to `handler(**kwargs)`. Handlers absorb unused params via `**kwargs`. Removing a kwarg from the facade breaks handlers that read it; adding a kwarg to the facade without updating handlers silently no-ops (handler just ignores it via `**kwargs`).

15. **Never log or return the `GITHUB_TOKEN` in any result dict.** The token is read once at httpx.Client construction time and embedded in the `Authorization` header. It must never appear in error messages, success payloads, trace logs, or test output. If you add debug logging, mask the token as `ghp_****`.

16. **Never modify the github result schema without updating `API.md`.** The return shapes (e.g. `pr_create` returns `{number, title, url, state, head, base}`) are part of the public contract. Schema changes are breaking changes — bump the version in CHANGELOG.md and update API.md.

17. **Never add github's `push` or `pull` action to `tools/parallel.py` `_TOOL_MAP`.** Same reason as #4 — both are subprocess actions and not parallel-safe. The `_TOOL_MAP` is the allowlist for parallel-safe tools; including push or pull would cause intermittent lock-contention failures in `parallel()` batches.

18. **Never patch `tools.github_ops.client.get_client` in tests AFTER the actions are imported.** Each action module imports `get_client` by name at module load time — patching the source attribute after import doesn't intercept the local reference. Use `mock_httpx_client` from `conftest.py` which patches `get_client` at every action module's namespace (`tools.github_ops.actions.<name>.get_client`) across all 14 API modules. v1.4: same applies to `tools.github_ops/helpers.py` — if you test `github_request()` directly, patch `tools.github_ops.helpers.get_client` (NOT the source). See ARCHITECTURE.md → Testing.

19. **Never use `if number is None:` to detect a missing `number` (or `line`) param in a v1.2+ action.** The facade defaults `number: int = 0` and `line: int = 0`, so `is None` checks DON'T catch the missing-arg case — the handler would proceed with `number=0` / `line=0` and either hit the API with an invalid identifier or trigger an XOR failure when `path` is also empty. Always use `if not number:` (or `bool(line)`) — catches `0`, `None`, `""`, and any other falsy value. This was a real bug fixed in v1.2 for `pr_get` / `pr_review` / `pr_merge` / `pr_comment`. v1.4: prefer `helpers._coerce_int(number, "number", trace_id)` for new actions — same check, less duplication.

20. **Never add a `force` param to `pull` (v1.3).** Force-push semantics don't apply to pull — `pull` always runs plain `git pull <remote> [<branch>]`. If a caller wants `git pull --rebase` instead of merge, they should use the `cli` tool or a direct subprocess call (the github tool intentionally exposes only the plain-merge shape of pull). # TODO(2.0): consider adding `rebase=True` param to `pull` if there's caller demand. Don't add `force` — it's semantically meaningless for pull.

21. **Never pass `status=<int>` to `fail()` (v1.4 — contract violation).** `core/contracts.py:fail()` is typed `fail(error, trace_id="", status: str = "error", error_code="", **meta)`. The `status` param expects one of the strings in `Literal["success", "error", "routed", "needs_clarification", "sent", "scheduled"]`. Passing an int (e.g. `fail("...", status=404)`) silently breaks every downstream `result["status"] == "error"` check (int 404 ≠ string `"error"`). v1.3.1 introduced this pattern on 14 API actions; v1.4 removed it. The HTTP code goes in the error message text (`f"GitHub API error {code}: {msg}"`) — never in `status`. For structured classification, use `error_code` (set by `helpers.github_request()`).

22. **Never URL-build a GitHub path with an unencoded tag/branch/ref name.** Tag names can contain URL-unsafe characters (`+`, `#`, `?`, `/`, spaces, non-ASCII). Always URL-encode with `urllib.parse.quote(value, safe="")` before interpolating into a path. v1.4 fixed `release_get` (was `f"/releases/tags/{tag}"` — now uses `quote(tag, safe="")`). Same rule for any future action that takes a tag/branch/ref name.

---

## ✅ ALWAYS DO

23. **Use `httpx.Client` directly for all GitHub API calls.** Obtain via `get_client()` (singleton). Build URLs via `repo_path()`. Pass `timeout=GITHUB_TIMEOUT` (from `core/net/default.py`, v1.4) per request — inline actions still use the literal `timeout=30` until they migrate to `github_request()`.

24. **Call `is_configured()` at the start of every API action.** False → `fail("GitHub not configured...")`. `push`/`pull` skip this (subprocess, not API). v1.4: prefer `err = _check_configured(trace_id); if err: return err` from `helpers.py` for new actions.

25. **Use `--force-with-lease` for force-push.** The `force=True` param already maps to it. Don't change.

26. **Use `subprocess.run(cmd, ...)` with list args (not `shell=True`).** Shell-metacharacter rejection is a secondary defense.

27. **Validate params client-side BEFORE the API call.** `state`/`event`/`merge_method`/`side` validated against allowlists. `title`/`head`/`number`/`body`/`branch` validated for non-empty. XOR on `path`/`line` for `pr_comment`. v1.4: prefer `helpers._coerce_int(value, name, trace_id)` for int coercion in new actions.

28. **Use the 3-stage error-handling pattern** (v1.3.1 P2-1): network call (try/except) → HTTP error (status check) → JSON parse (try/except). Distinguishes network errors from parse errors. v1.4: `fail()` calls use the default `status="error"` — no `status=<int>` kwarg (see NEVER DO #21).

29. **Use `helpers.github_request()` for new API actions (v1.4).** New actions written from scratch SHOULD use `github_request(method, url_path, trace_id, *, params, json, not_found_msg)` instead of the inline 3-stage pattern. It wraps the call in `core.net.retry.retry_sync` (max_retries=2, base_delay=1.0, max_delay=5.0), classifies errors via `core.net.errors.classify_http_error` → `error_code`, and reads `X-RateLimit-Remaining` into the fail dict. Existing 14 actions retain the inline pattern in v1.4 — migration is a follow-up commit.

30. **Set `error_code` on `fail()` for structured classification (v1.4).** When using `github_request()`, the helper sets `error_code` automatically (TIMEOUT/RATE_LIMITED/SERVER_ERROR/CLIENT_ERROR/NOT_FOUND/NETWORK_ERROR/CONNECT_ERROR/BOT_BLOCKED/UNKNOWN). When writing inline `fail()` calls in new actions, set `error_code` explicitly for known categories (e.g. `error_code="NOT_FOUND"` for 404). Inline actions in v1.4 do NOT set `error_code` — they will once migrated.

31. **Use `ok()` / `fail()` from `core.contracts`.** Don't hand-roll the status field. v1.4: `fail(error, trace_id=..., error_code=...)` — never `fail(error, status=<int>, ...)`.

32. **Extract nested fields safely.** `(data.get("head") or {}).get("ref")` — handles `null` for deleted branches. Same for `user.login`.

33. **Forward `**kwargs` in handler signatures.** Facade passes all 24 params; `push` ignores API params via `**kwargs`.

34. **Register new actions via `@register_action("github", "<name>", help_text=..., examples=[...])`.** Keep `help_text`/`examples` accurate — surfaced to the LLM.

35. **Include `timeout=GITHUB_TIMEOUT` (API) or `timeout=120` (`push`/`pull`) on all external calls.** Without it, a hung API/git op blocks the agent indefinitely. v1.4: prefer `GITHUB_TIMEOUT` from `core/net/default.py` over the literal `30`.

36. **Update `API.md` and `CHANGELOG.md` when adding/changing an action.** New action = new Summary Table row + new API.md section + CHANGELOG version bump.

37. **Test with `mock_cfg` / `mock_not_configured` / `mock_httpx_client` fixtures.** Never real API or git calls. For `push`/`pull`, patch `subprocess.run` directly. For `helpers.github_request()` (v1.4), patch `tools.github_ops.helpers.get_client` — same direct-reference pattern as the action modules.

38. **Use `if not x:` (not `if x is None:`) for params with facade default `0`.** Facade uses `number: int = 0` and `line: int = 0`. `is None` doesn't catch missing-arg. See NEVER DO #19. v1.4: prefer `helpers._coerce_int()`.

39. **Treat `mergeable=null` from `pr_get` as "retry".** GitHub is still computing. `mergeable_state` (`clean`/`blocked`/`unstable`/`dirty`/`unknown`) is more useful in practice.

40. **Treat `pull` as the remote-sync counterpart to `push` (v1.3).** Workflow: `pull` → branch → commit → `push` → `pr_create`. Follow the `push`/`pull` pattern for new remote ops: list-form subprocess, 120s timeout, metachar rejection, NOT parallel-safe.

41. **URL-encode tag/branch/ref names before interpolating into a URL path (v1.4).** Use `urllib.parse.quote(value, safe="")`. See NEVER DO #22. `release_get` does this; any new action that takes a tag/branch/ref must too.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*The first entry was added in v1.2:)*

> - **What happened:** v1.0/v1.1 `pr_get`/`pr_review`/`pr_merge`/`pr_comment` checked `if number is None:` — but the facade defaults `number: int = 0`. Calling `github(action="pr_get")` with no `number` arg passed the check and hit the GitHub API with `number=0`, returning a confusing 404.
> - **Why it matters:** This is a silent failure — the caller gets a misleading "PR #0 not found" instead of "number is required for pr_get". The same anti-pattern affected `pr_comment`'s `line` param (`line: int = 0`).
> - **Fix:** Use `if not number:` (and `bool(line)` for `pr_comment`'s `line_set`) — catches `0`, `None`, `""`, and any other falsy value. Documented as NEVER DO rule #19. Fixed in v1.2 across all 4 affected actions. v1.4: `helpers._coerce_int()` makes this idiomatic for new actions.

> - **What happened:** v1.0/v1.1 `pr_list` and `issue_list` were capped at 100 items (GitHub's `per_page` max) with no way to fetch the next page. Repos with >100 PRs/issues returned truncated results.
> - **Why it matters:** Callers couldn't enumerate the full set — silently wrong results.
> - **Fix:** v1.2 added a `page` param + `parse_link_header()` helper in `client.py`. The response now includes `page` (current page), `has_next` (bool), `next_page` (int or `None`) from the parsed `Link` header. Callers iterate: `while result["data"]["has_next"]: result = github(action="pr_list", page=result["data"]["next_page"])`. See ARCHITECTURE.md → Key Design Decisions #14.

> - **What happened (v1.4 Bug 2):** v1.2's `parse_link_header()` regex was `<[^>]*\?page=(\d+)>` — requiring `?page=` to be the FIRST query parameter in the URL. But GitHub's Link header always carries other params first: `<https://api.github.com/...?per_page=100&page=2>; rel="next"`. The regex failed to match, silently returning `{"next": None, "last": None}` — pagination was broken on every list action whenever `per_page` was non-default.
> - **Why it matters:** Every `pr_list` / `issue_list` / `release_list` call with `limit != 30` silently returned `has_next=False` even when more pages existed. Repos with >100 items appeared to have only the first page.
> - **Fix:** v1.4 changed the regex to `<[^>]*[?&]page=(\d+)>` — accepts `?` OR `&` as the leading separator. See ARCHITECTURE.md → Key Design Decisions #9.

> - **What happened (v1.4 Bug 1 — contract violation):** v1.3.1 introduced `fail(status=resp.status_code)` on API errors so callers could "distinguish 404 from 422 from 500". But `core/contracts.py:fail()` types `status` as `Literal["success", "error", "routed", "needs_clarification", "sent", "scheduled"]` — a string. Passing an int silently broke every `if result["status"] == "error":` check downstream (int 404 ≠ string `"error"`).
> - **Why it matters:** Every GitHub API failure (404, 405, 409, 422, 500) returned `status: <int>`, not `status: "error"`. Any caller branching on `status == "error"` would skip the error-handling branch and proceed as if the call succeeded. This is a contract violation, not just a stylistic issue.
> - **Fix:** v1.4 removed `status=<int>` from all 14 API actions. `fail()` now uses the default `status="error"`. The HTTP code remains in the error message text (`"GitHub API error 404: Not Found"`). Structured classification belongs in `error_code` (set by `helpers.github_request()` — see ALWAYS DO #30). Documented as NEVER DO #21.

> - **What happened (v1.4 Bug 3 — `pr_merge` hardcoded `merged:True`):** `pr_merge` returned `{"merged": True, ...}` unconditionally on any 200 response. But GitHub's merge endpoint can return `merged: false` even on a 200 (e.g. when the PR was already merged, or the merge was a no-op for some merge methods).
> - **Why it matters:** The action's `merged` field lied — callers checking `result["data"]["merged"]` to decide whether to proceed would always see `True`, masking no-op merges as successful new merges.
> - **Fix:** v1.4 changed `"merged": True` to `"merged": data.get("merged", True)` — honors GitHub's response, defaults to `True` only if the field is missing (backward compat for older GitHub API responses).

> - **What happened (v1.4 Bug 4 — `release_get` URL-unsafe tag):** `release_get` interpolated the tag directly into the URL: `f"/releases/tags/{tag}"`. Tags with URL-unsafe characters (`+`, `#`, `?`, `/`, spaces, non-ASCII) produced malformed request URLs — `v1.0.0+build.5` became `GET /releases/tags/v1.0.0+build.5` which 404'd indistinguishably from a missing release.
> - **Why it matters:** Real-world semver tags like `1.0.0+build.42` (build metadata) or `v1.0.0-rc.1` (pre-release) couldn't be fetched. The 404 looked identical to "tag doesn't exist".
> - **Fix:** v1.4 URL-encodes the tag with `urllib.parse.quote(tag, safe="")` — encodes everything except unreserved characters (alnum + `-_.~`). Documented as NEVER DO #22 + ALWAYS DO #41.

---

*Last updated: 2026-07-15 (v1.4). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
