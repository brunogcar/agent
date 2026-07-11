<- Back to [GitHub Overview](../GITHUB.md)

# 🛡️ AI Instructions

These rules apply to any AI assistant (or human editor) modifying the github tool, its action handlers, its client singleton, or its documentation. Follow them strictly — deviations have caused real bugs in similar meta-tools (`git`, `swarm`, `web`).

## ❌ NEVER DO

1. **Never hardcode a GitHub token in source code.** The token is read from `GITHUB_TOKEN` env var via `core.config.cfg.github_token`. Never embed a real or fake token in any `.py` file, test fixture, or docstring. Tests use `mock_cfg` (sets a fake `ghp_test_token_abc123`) or `mock_not_configured` (sets empty string) — never a real token. Hardcoded tokens in source = security incident.

2. **Never use PyGithub.** The github tool uses `httpx.Client` directly to call the GitHub REST API. PyGithub is a heavy abstraction that hides the raw HTTP request shape, adds a transitive dependency, and is inconsistent with the rest of the project (which uses httpx for all HTTP). See ARCHITECTURE.md → Key Design Decisions #1. If you need a higher-level abstraction, write a helper function in `tools/github_ops/helpers.py` — but keep using httpx under the hood.

3. **Never add a `push` or `pull` action to the `git` tool.** Both `push` and `pull` live in `github_ops/`, NOT `git_ops/`. They're the **remote-sync pair** for the GitHub PR workflow — `pull` before branching (fetch latest remote state) → `push` after committing (publish the branch so a PR can be opened). Adding either to `git_ops/` would split the workflow across two tools and break the discoverability rule. If you need to push a branch, use `github(action="push", branch="...")`. If you need to pull recent commits, use `github(action="pull")` or `github(action="pull", branch="main")`.

4. **Never add `push` or `pull` to `PARALLEL_SAFE` in `core/parallel_executor.py`.** Both spawn git subprocesses (`git push` / `git pull`); concurrent operations on the same repo will fail with lock contention on `.git/index.lock`. The facade declares `_NOT_PARALLEL_SAFE = frozenset({"push", "pull"})` (v1.3 — `pull` added) — do not remove this. All 14 API actions (`pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `issue_create`, `issue_list`, `issue_get`, `issue_update`, `issue_comment`, `release_create`, `release_list`, `release_get`) ARE parallel-safe and can be in `PARALLEL_SAFE` if desired.

5. **Never use `--force` (bare) for push.** Use `--force-with-lease` instead. `--force-with-lease` checks the remote ref against the local tracking ref before overwriting — if the remote has moved since your last fetch, the push is rejected. `--force` would silently overwrite, destroying teammates' commits. The `force=True` param on `push` already maps to `--force-with-lease` — do not change this. There's no scenario where bare `--force` is the right choice.

6. **Never use `shell=True` in the `push` subprocess call.** `subprocess.run(["git", "push", ..., remote, branch], ...)` — the list form is mandatory. `shell=True` would expose the process to shell injection if `branch` or `remote` contained metacharacters (git branch names cannot contain these, but defense in depth is non-negotiable). The shell-metacharacter rejection in `push.py` is a secondary check — the primary defense is the list-form subprocess call.

7. **Never skip the `is_configured()` check at the start of an API action.** Every API action (`pr_create`, `pr_list`, `pr_get`, `pr_review`, `pr_merge`, `pr_comment`, `issue_create`, `issue_list`, `issue_get`, `issue_update`, `issue_comment`, `release_create`, `release_list`, `release_get`) must call `is_configured()` BEFORE making any API call. Failing fast with `fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env")` is much friendlier than a confusing 401/404 from GitHub. The `push` and `pull` actions are the ONLY exceptions — they don't use the GitHub API (local subprocess).

8. **Never remove the `Authorization: Bearer ...` header from the httpx.Client.** `get_client()` in `client.py` builds the client with `Authorization`, `Accept`, `X-GitHub-Api-Version`, and `Content-Type` headers. All four are required by the GitHub API. Removing any of them will cause 401/403/415 errors.

9. **Never make `GITHUB_API_BASE` configurable via env in v1.0.** It's hardcoded to `https://api.github.com`. Phase 4+ roadmap item is GHE support (`GITHUB_API_BASE` env override). Don't add it prematurely — the hardcoded value is part of the security contract (no SSRF surface, see API.md → Security).

10. **Never add a new action without registering it via `@register_action("github", "<name>", ...)`.** The `__init__.py` auto-imports `actions/*.py` to trigger registration; an unregistered handler is invisible to the dispatcher and returns "Unknown action".

11. **Never use `print()` or write to `sys.stdout` inside any github code.** MCP protocol uses stdout for JSON-RPC — writing to it corrupts the payload and crashes the server. Use `core.tracer` or `sys.stderr` for logging. Same rule as every other tool in the project.

12. **Never assume `resp.json()` will succeed.** Always wrap it in try/except — GitHub can return non-JSON responses (HTML error pages, empty 204 responses, etc.). The pattern `data = resp.json()` must be followed by `except Exception as e: return fail(f"{action} returned non-JSON response: {e}")`.

13. **Never remove the per-action validation that fails fast on invalid params.** `pr_list` / `issue_list` validate `state in ("open", "closed", "all")`. `issue_update` validates `state in ("open", "closed")` (empty allowed = don't change). `pr_review` validates `event in ("APPROVE", "REQUEST_CHANGES", "COMMENT")`. `pr_merge` validates `merge_method in ("merge", "squash", "rebase")`. `pr_comment` validates the XOR of `path`/`line`. `issue_update` rejects no-op PATCHes (all fields empty). `release_get` requires `tag` OR `number`. These checks happen BEFORE the API call — failing fast with a clear message is better than letting GitHub return a 422 with a cryptic error.

14. **Never forget to forward ALL kwargs to the handler.** The facade builds `kwargs = {title, head, base, body, number, state, limit, page, event, merge_method, commit_title, commit_message, path, line, side, branch, remote, force, labels, assignees, tag, draft, prerelease, trace_id}` (23 params — v1.2 added `page`) and passes them to `handler(**kwargs)`. Handlers absorb unused params via `**kwargs`. Removing a kwarg from the facade breaks handlers that read it; adding a kwarg to the facade without updating handlers silently no-ops (handler just ignores it via `**kwargs`).

15. **Never log or return the `GITHUB_TOKEN` in any result dict.** The token is read once at httpx.Client construction time and embedded in the `Authorization` header. It must never appear in error messages, success payloads, trace logs, or test output. If you add debug logging, mask the token as `ghp_****`.

16. **Never modify the github result schema without updating `API.md`.** The return shapes (e.g. `pr_create` returns `{number, title, url, state, head, base}`) are part of the public contract. Schema changes are breaking changes — bump the version in CHANGELOG.md and update API.md.

17. **Never add github's `push` or `pull` action to `tools/parallel.py` `_TOOL_MAP`.** Same reason as #4 — both are subprocess actions and not parallel-safe. The `_TOOL_MAP` is the allowlist for parallel-safe tools; including push or pull would cause intermittent lock-contention failures in `parallel()` batches.

18. **Never patch `tools.github_ops.client.get_client` in tests AFTER the actions are imported.** Each action module imports `get_client` by name at module load time — patching the source attribute after import doesn't intercept the local reference. Use `mock_httpx_client` from `conftest.py` which patches `get_client` at every action module's namespace (`tools.github_ops.actions.<name>.get_client`) across all 14 API modules. See ARCHITECTURE.md → Testing.

19. **Never use `if number is None:` to detect a missing `number` (or `line`) param in a v1.2+ action.** The facade defaults `number: int = 0` and `line: int = 0`, so `is None` checks DON'T catch the missing-arg case — the handler would proceed with `number=0` / `line=0` and either hit the API with an invalid identifier or trigger an XOR failure when `path` is also empty. Always use `if not number:` (or `bool(line)`) — catches `0`, `None`, `""`, and any other falsy value. This was a real bug fixed in v1.2 for `pr_get` / `pr_review` / `pr_merge` / `pr_comment`.

20. **Never add a `force` param to `pull` (v1.3).** Force-push semantics don't apply to pull — `pull` always runs plain `git pull <remote> [<branch>]`. If a caller wants `git pull --rebase` instead of merge, they should use the `cli` tool or a direct subprocess call (the github tool intentionally exposes only the plain-merge shape of pull). # TODO(2.0): consider adding `rebase=True` param to `pull` if there's caller demand. Don't add `force` — it's semantically meaningless for pull.

---

## ✅ ALWAYS DO

19. **Use `httpx.Client` directly for all GitHub API calls.** This is the canonical pattern. Obtain the client via `get_client()` (singleton, connection-pooled). Build URLs via `repo_path()` (returns `/repos/{owner}/{repo}`). Pass `timeout=30` per request. See any action in `tools/github_ops/actions/` for the pattern.

20. **Call `is_configured()` at the start of every API action.** Returns `bool(cfg.github_token and cfg.github_owner and cfg.github_repo)`. False → `fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env")`. The `push` and `pull` actions do NOT need this check (subprocess, not API).

21. **Use `--force-with-lease` for force-push.** The `force=True` param on `push` already maps to `--force-with-lease`. Do not change this. If a future feature needs bare `--force` (e.g. destructive history rewrite), add a separate `force_hard=True` param with a loud warning in the help_text — but default to `--force-with-lease`.

22. **Use `subprocess.run(cmd, ...)` with list args (not `shell=True`).** The `push` action builds `cmd = ["git", "push", [--force-with-lease], remote, branch]` and the `pull` action (v1.3) builds `cmd = ["git", "pull", remote, [branch]]` — both pass it as a list. This is the only safe way to call subprocess with user-influenced input. Shell-metacharacter rejection is a secondary defense, not the primary one.

23. **Validate params client-side BEFORE making the API call.** `state`, `event`, `merge_method`, `side` are validated against allowlists. `title`, `head`, `number`, `body`, `branch` are validated for non-empty. XOR on `path`/`line` for `pr_comment`. Failing fast with a clear message is better than letting GitHub return 422.

24. **Handle specific HTTP status codes with specific messages.** 404 → "PR #N not found". 405 on `pr_merge` → "not mergeable". 409 on `pr_merge` → "head commit is not up to date". Generic 4xx/5xx → `fail(f"GitHub API error {code}: {msg}", status=code)`. The `status` kwarg on `fail()` lets callers distinguish error types via `result["status"]`.

25. **Extract nested fields safely.** GitHub returns `head` and `base` as objects: `{"ref": "fix/timeout", ...}`. Use `(data.get("head") or {}).get("ref")` — handles the case where GitHub returns `null` for the head/base object (deleted branches). Same for `user.login`.

26. **Use `ok({...})` / `fail(...)` from `core.contracts` for return shapes.** Standardized `{"status": "success"|"error", "data": ..., "error": ..., "trace_id": ...}` dict. Don't hand-roll the status field. `ok()` nests the payload under `data`; `fail()` puts the message under `error`. See `tests/tools/github/` for assertion patterns.

27. **Forward `**kwargs` in handler signatures.** The facade passes all 18 params to every handler; `push` ignores all the API params via `def _action_push(branch, remote, force, trace_id, **kwargs)`. Don't add explicit params that aren't used — `**kwargs` absorbs the rest.

28. **Register new actions via `@register_action("github", "<name>", help_text=..., examples=[...])`.** The `help_text` and `examples` are surfaced through DISPATCH for documentation. Keep them accurate — they're shown to the LLM in the tool's `doc_sections`.

29. **Include `timeout=30` (or `timeout=120` for `push` / `pull`) on all external calls.** httpx and subprocess both accept a `timeout` kwarg. Without it, a hung GitHub API or hung git push/pull will block the agent indefinitely. `30` is appropriate for API calls (GitHub typically responds in < 2s); `120` for push AND pull (large repos can take 60s+ for either direction).

30. **Update `API.md` and `CHANGELOG.md` when adding or changing an action.** New action = new row in the Summary Table + new section in API.md + new Completed row in CHANGELOG.md with version bump. Same as every other tool's INSTRUCTIONS.md.

31. **Document WHY in code comments, not just WHAT.** The "httpx not PyGithub" decision, the "push in github_ops not git_ops" decision, the "--force-with-lease not --force" decision, the "dual-mode pr_comment XOR" decision — all are non-obvious. Future AI auditors need the rationale to avoid "fixing" them. See `push.py` module docstring for the gold standard.

32. **Test with `mock_cfg` / `mock_not_configured` / `mock_httpx_client` fixtures.** Never make real API calls in tests. Never make real `git push` or `git pull` calls in tests. The fixtures are in `tests/tools/github/conftest.py` — use them. For `push` tests, patch `tools.github_ops.actions.push.subprocess.run` directly. For `pull` tests (v1.3), patch `tools.github_ops.actions.pull.subprocess.run` directly (same pattern).

33. **Add `duration_ms` to every result via the facade.** The facade measures wall-clock time and injects `duration_ms` — handlers must NOT time themselves (double-counts). The injection happens after `handler(**kwargs)` returns, so handlers just need to return their result dict and the facade adds the timing.

34. **Cap `per_page` at 100 for `pr_list` and `issue_list` (and slice `items[:limit_int]` after extraction).** GitHub API hard-caps `per_page=100` for the `/pulls` and `/issues` endpoints. Compute `per_page = min(limit, 100)` and slice `items[:limit_int]` after extraction. This handles `limit=5` (per_page=5, slice is no-op) and `limit=200` (per_page=100, slice to 100). **For repos with >100 items, use the `page` param** (v1.2): `page=2`, `page=3`, etc. — the response includes `has_next` + `next_page` from the parsed `Link` header so callers can iterate without manual page counting.

35. **Use `if not x:` (not `if x is None:`) for params that have a facade default of `0`.** The facade uses default-zero for `number` and `line` (so the signature stays `int`, not `Optional[int]`). This means `is None` checks don't catch missing-arg cases — the handler sees `0` and proceeds. Always use `if not number:` / `bool(line)`. Documented as NEVER DO rule #19.

36. **Treat `mergeable=null` from `pr_get` as "retry".** GitHub returns `mergeable: null` while it's still computing the mergeability state (typically right after a push). If a caller sees `mergeable=null`, they should wait a moment and call `pr_get` again before deciding whether to `pr_merge`. The `mergeable_state` field is the more useful signal in practice: `"clean"`/`"blocked"`/`"unstable"`/`"dirty"`/`"unknown"`. Don't treat `null` as `false` — it doesn't mean "not mergeable", it means "GitHub hasn't told us yet".

37. **Treat `pull` as the remote-sync counterpart to `push` (v1.3).** The standard PR workflow is **`pull` before branching → branch → commit → `push` → `pr_create`**. When adding new remote-related actions, follow the `push`/`pull` pattern: list-form subprocess, 120s timeout, shell-metacharacter rejection, combined stdout+stderr in `output`, NOT parallel-safe. If a new remote operation doesn't fit the `push`/`pull` shape (e.g. `fetch` without merge, `clone`), consider whether it belongs in `git_ops` instead (clone already lives there). See ARCHITECTURE.md → Key Design Decisions #16.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*The first entry was added in v1.2:)*

> - **What happened:** v1.0/v1.1 `pr_get`/`pr_review`/`pr_merge`/`pr_comment` checked `if number is None:` — but the facade defaults `number: int = 0`. Calling `github(action="pr_get")` with no `number` arg passed the check and hit the GitHub API with `number=0`, returning a confusing 404.
> - **Why it matters:** This is a silent failure — the caller gets a misleading "PR #0 not found" instead of "number is required for pr_get". The same anti-pattern affected `pr_comment`'s `line` param (`line: int = 0`).
> - **Fix:** Use `if not number:` (and `bool(line)` for `pr_comment`'s `line_set`) — catches `0`, `None`, `""`, and any other falsy value. Documented as NEVER DO rule #19. Fixed in v1.2 across all 4 affected actions. See ARCHITECTURE.md → Key Design Decisions #15.

> - **What happened:** v1.0/v1.1 `pr_list` and `issue_list` were capped at 100 items (GitHub's `per_page` max) with no way to fetch the next page. Repos with >100 PRs/issues returned truncated results.
> - **Why it matters:** Callers couldn't enumerate the full set — silently wrong results.
> - **Fix:** v1.2 added a `page` param + `parse_link_header()` helper in `client.py`. The response now includes `page` (current page), `has_next` (bool), `next_page` (int or `None`) from the parsed `Link` header. Callers iterate: `while result["data"]["has_next"]: result = github(action="pr_list", page=result["data"]["next_page"])`. See ARCHITECTURE.md → Key Design Decisions #14.

---

*Last updated: 2026-07-10 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
