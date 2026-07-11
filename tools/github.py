"""tools/github.py — GitHub API operations meta-tool.

Routes all github actions to handlers in github_ops/actions/ via DISPATCH dict.
Auto-discovered by registry.py via @tool decorator.

Provides PR operations (create, list, get, review, merge, comment) and
git push (prerequisite for PR creation). Uses GitHub REST API via httpx.

PARALLEL_SAFE = True for API actions. push action is NOT parallel-safe
(subprocess) but is handled via a NOT_PARALLEL_SAFE set in the actions.
"""
from __future__ import annotations

import time

from core.contracts import fail
from core.tracer import tracer
from registry import tool
from tools._meta_tool import meta_tool

from tools import github_ops  # noqa: F401 — triggers DISPATCH auto-discovery
from tools.github_ops._registry import DISPATCH

# push action uses subprocess — NOT parallel-safe
_NOT_PARALLEL_SAFE = frozenset({"push"})


@tool
@meta_tool(
    DISPATCH.get("github", {}),
    doc_sections=[
        "GITHUB TOOL — GitHub API operations:",
        " | Need | Action | Why |",
        " |------|--------|-----|",
        " | Open a PR | github(pr_create) | Create pull request from branch",
        " | List PRs | github(pr_list) | List open/closed/all pull requests",
        " | Get PR details | github(pr_get) | Get single PR (status, CI, reviews)",
        " | Review a PR | github(pr_review) | APPROVE / REQUEST_CHANGES / COMMENT",
        " | Merge a PR | github(pr_merge) | merge / squash / rebase",
        " | Comment on PR | github(pr_comment) | General or line-level comment",
        " | Push branch | github(push) | git push origin branch (local subprocess)",
        " | Create issue | github(issue_create) | Create GitHub issue with labels + assignees",
        " | List issues | github(issue_list) | List open/closed/all issues (paginated)",
        " | Get issue | github(issue_get) | Get single issue details",
        " | Update issue | github(issue_update) | Close / reopen / edit issue fields",
        " | Comment on issue | github(issue_comment) | Comment on issue or PR",
        " | Create release | github(release_create) | Create release from tag",
        " | List releases | github(release_list) | List GitHub releases",
        " | Get release | github(release_get) | Get single release by tag or ID",
        "",
        "Requires GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env.",
        "push action is NOT parallel-safe (subprocess).",
    ],
)
def github(
    action: str,
    title: str = "",
    head: str = "",
    base: str = "main",
    body: str = "",
    number: int = 0,
    state: str = "",
    limit: int = 30,
    page: int = 1,
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
    # v1.1 — Issues + Releases
    labels: str = "",
    assignees: str = "",
    tag: str = "",
    draft: bool = False,
    prerelease: bool = False,
    # v1.2 — Pagination + issue_get/update + release_get
    trace_id: str = "",
) -> dict:
    """GitHub API meta-tool — PR operations and git push."""
    action = action.strip().lower() if action else ""

    if not action:
        return fail("action is required", trace_id=trace_id)

    dispatch = DISPATCH.get("github", {})
    op_info = dispatch.get(action)

    if op_info is None:
        valid_actions = " | ".join(sorted(dispatch.keys()))
        return fail(
            f"Unknown action '{action}'. Use: {valid_actions}",
            trace_id=trace_id,
        )

    handler = op_info["func"]

    kwargs = {
        "title": title,
        "head": head,
        "base": base,
        "body": body,
        "number": number,
        "state": state,
        "limit": limit,
        "page": page,
        "event": event,
        "merge_method": merge_method,
        "commit_title": commit_title,
        "commit_message": commit_message,
        "path": path,
        "line": line,
        "side": side,
        "branch": branch,
        "remote": remote,
        "force": force,
        # v1.1 — Issues + Releases
        "labels": labels,
        "assignees": assignees,
        "tag": tag,
        "draft": draft,
        "prerelease": prerelease,
        "trace_id": trace_id,
    }

    start = time.time()
    try:
        result = handler(**kwargs)
    except Exception as e:
        return fail(f"GitHub action failed: {e}", trace_id=trace_id)

    if trace_id and "trace_id" not in result:
        result["trace_id"] = trace_id

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
