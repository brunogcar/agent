"""GitHub action: pr_merge — Merge a pull request.

Calls PUT /repos/{owner}/{repo}/pulls/{number}/merge. Requires the PR to
be mergeable (status checks passing if required, no conflicts, approvals
satisfied). Default merge method is "squash" to keep history clean —
override with merge_method="merge" or "rebase" as needed.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


_VALID_MERGE_METHODS = ("merge", "squash", "rebase")


@register_action(
    "github", "pr_merge",
    help_text="""pr_merge — Merge a pull request on GitHub.

Required: number (int)
Optional: merge_method (str: "merge", "squash", "rebase"; default "squash"),
          commit_title (str — custom merge commit title),
          commit_message (str — custom merge commit body)

Returns: {merged: true, sha, message}

NOTE: The PR must be mergeable (no conflicts, required checks passing,
required reviews satisfied). If you get a 405 error, the PR is not
mergeable — call pr_get first to check the mergeable state.

Default merge_method is "squash" to keep history clean. Use "merge" to
preserve all commits, or "rebase" to add commits on top of the base.""",
    examples=[
        'github(action="pr_merge", number=42)',
        'github(action="pr_merge", number=42, merge_method="squash")',
        'github(action="pr_merge", number=42, merge_method="merge", commit_title="Merge PR #42")',
    ],
)
def _action_pr_merge(
    number: Any = None,
    merge_method: str = "squash",
    commit_title: str = "",
    commit_message: str = "",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Merge a pull request via the GitHub API.

    Args:
        number: PR number (required). Coerced to int if a numeric str is passed.
        merge_method: One of "merge", "squash", "rebase" (default "squash").
        commit_title: Custom merge commit title (optional).
        commit_message: Custom merge commit body (optional).
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not number:
        return fail("number is required for pr_merge", trace_id=trace_id)
    try:
        pr_number = int(number)
    except (TypeError, ValueError):
        return fail(f"number must be an int — got {number!r}", trace_id=trace_id)

    if merge_method not in _VALID_MERGE_METHODS:
        return fail(
            f"merge_method must be one of {_VALID_MERGE_METHODS} — got {merge_method!r}",
            trace_id=trace_id,
        )

    payload: dict[str, Any] = {"merge_method": merge_method}
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message

    client = get_client()
    try:
        resp = client.put(
            f"{repo_path()}/pulls/{pr_number}/merge", json=payload, timeout=30
        )
    except Exception as e:
        return fail(f"pr_merge request failed: {e}", trace_id=trace_id)

    if resp.status_code == 404:
        return fail(f"PR #{pr_number} not found", status=404, trace_id=trace_id)
    if resp.status_code == 405:
        return fail(
            f"PR #{pr_number} is not mergeable (conflict, blocked, or required checks not satisfied)",
            status=405,
            trace_id=trace_id,
        )
    if resp.status_code == 409:
        return fail(
            f"PR #{pr_number} head commit is not up to date — rebase and push again",
            status=409,
            trace_id=trace_id,
        )
    if resp.status_code >= 400:
        try:
            err_body = resp.json()
            msg = err_body.get("message", resp.text)
        except Exception:
            msg = resp.text
        return fail(
            f"GitHub API error {resp.status_code}: {msg}",
            status=resp.status_code,
            trace_id=trace_id,
        )

    try:
        data = resp.json()
    except Exception as e:
        return fail(f"pr_merge returned non-JSON response: {e}", trace_id=trace_id)

    return ok({
        "merged": True,
        "sha": data.get("sha"),
        "message": data.get("message"),
    }, trace_id=trace_id)
