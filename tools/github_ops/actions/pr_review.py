"""GitHub action: pr_review — Submit a review on a pull request.

Calls POST /repos/{owner}/{repo}/pulls/{number}/reviews. Used to APPROVE,
REQUEST_CHANGES, or leave a COMMENT review on a PR. Requires push access
to the repo (the GITHUB_TOKEN must belong to a collaborator).

v1.4 (2026-07-15): Removed `status=` kwarg from all fail() calls (fail()
contract: status is a string, not an int — see core/contracts.py). The
HTTP code remains in the error message text. Structured classification
belongs in error_code (see tools/github_ops/helpers.py github_request).

[v1.5] Migrated to github_request() helper — eliminates inline 3-stage
error handling pattern (network → HTTP → JSON parse). The helper also
adds retry/backoff for transient errors and structured error_code.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import repo_path
from tools.github_ops.helpers import _check_configured, _coerce_int, github_request


_VALID_REVIEW_EVENTS = ("APPROVE", "REQUEST_CHANGES", "COMMENT")


@register_action(
    "github", "pr_review",
    help_text="""pr_review — Submit a review (APPROVE / REQUEST_CHANGES / COMMENT) on a PR.

Required: number (int), event (str: "APPROVE", "REQUEST_CHANGES", "COMMENT")
Optional: body (str — review comment text, markdown),
          commit_id (str — SHA of the specific commit to review)

Returns: {id, state, url}

NOTE: APPROVE / REQUEST_CHANGES require push access to the repo.
COMMENT works for any authenticated user. You cannot review your own PR
in most configurations (GitHub blocks self-approval).""",
    examples=[
        'github(action="pr_review", number=42, event="APPROVE", body="LGTM")',
        'github(action="pr_review", number=42, event="REQUEST_CHANGES", body="Needs null check on line 17")',
        'github(action="pr_review", number=42, event="COMMENT", body="Just a note")',
    ],
)
def _action_pr_review(
    number: Any = None,
    event: str = "",
    body: str = "",
    commit_id: str = "",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Submit a review on a pull request.

    Args:
        number: PR number (required). Coerced to int if a numeric str is passed.
        event: One of "APPROVE", "REQUEST_CHANGES", "COMMENT" (required).
        body: Review body text as markdown (optional).
        commit_id: Specific commit SHA to review (optional). If omitted,
            GitHub reviews the latest commit on the PR head.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for pr_review", trace_id=trace_id)
    pr_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

    if not event:
        return fail("event is required for pr_review", trace_id=trace_id)
    if event not in _VALID_REVIEW_EVENTS:
        return fail(
            f"event must be one of {_VALID_REVIEW_EVENTS} — got {event!r}",
            trace_id=trace_id,
        )

    payload: dict[str, Any] = {"event": event}
    if body:
        payload["body"] = body
    if commit_id:
        payload["commit_id"] = commit_id

    resp, err = github_request(
        "post",
        f"{repo_path()}/pulls/{pr_number}/reviews",
        trace_id,
        json=payload,
        not_found_msg=f"PR #{pr_number} not found",
    )
    if err:
        return err

    data = resp.json()
    return ok({
        "id": data.get("id"),
        "state": data.get("state"),
        "url": data.get("html_url"),
    }, trace_id=trace_id)
