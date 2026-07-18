"""GitHub action: pr_merge — Merge a pull request.

Calls PUT /repos/{owner}/{repo}/pulls/{number}/merge. Requires the PR to
be mergeable (status checks passing if required, no conflicts, approvals
satisfied). Default merge method is "squash" to keep history clean —
override with merge_method="merge" or "rebase" as needed.

v1.4 (2026-07-15):
  - Removed `status=` kwarg from all fail() calls (contract violation: fail()
    expects status: str = "error", not an int — see core/contracts.py).
    Structured classification belongs in error_code, not status. The
    inline 3-stage pattern is preserved; migration to github_request()
    is a follow-up commit.
  - Fixed `merged: True` (hardcoded) → `data.get("merged", True)` so the
    action honors GitHub's response (some merge methods return merged:false
    even on a 200 when the merge was a no-op).

[v1.5] Migrated to github_request() helper — eliminates inline 3-stage
error handling pattern (network → HTTP → JSON parse). The helper also
adds retry/backoff for transient errors and structured error_code.
The `data.get("merged", True)` fix from v1.4 is preserved.

BEHAVIOR CHANGE: The v1.4 inline pattern had custom 405 ("not mergeable")
and 409 ("head commit not up to date") error messages. With github_request,
those now fall through to the generic `"GitHub API error <code>: <gh_msg>"`
branch — the HTTP code is still in the message text, and the underlying
GitHub `message` field is preserved, but the friendly "up to date" /
"not mergeable" phrasing is gone. Callers should rely on the HTTP code
(in error_code="CLIENT_ERROR") and GitHub's own message string instead.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import repo_path
from tools.github_ops.helpers import _check_configured, _coerce_int, github_request


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
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for pr_merge", trace_id=trace_id)
    pr_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

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

    resp, err = github_request(
        "put",
        f"{repo_path()}/pulls/{pr_number}/merge",
        trace_id,
        json=payload,
        not_found_msg=f"PR #{pr_number} not found",
    )
    if err:
        return err

    data = resp.json()
    return ok({
        "merged": data.get("merged", True),
        "sha": data.get("sha"),
        "message": data.get("message"),
    }, trace_id=trace_id)
