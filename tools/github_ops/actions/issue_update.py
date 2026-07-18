"""GitHub action: issue_update — Update an issue's state or fields.

Calls PATCH /repos/{owner}/{repo}/issues/{number}. Unifies close/reopen
(via the `state` param) with field edits (title, body, labels, assignees)
in a single action — follows the pr_review event-param precedent.

At least one of: state, title, body, labels, assignees must be provided.
If a field is empty/omitted, it is NOT included in the PATCH payload, so
GitHub leaves it unchanged.

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


@register_action(
    "github", "issue_update",
    help_text="""issue_update — Update a GitHub issue (close, reopen, or edit fields).

Required: number (int)
Optional: state (str: "open" or "closed" — empty = don't change),
          title (str — new title),
          body (str — new body),
          labels (str — comma-separated, replaces all labels),
          assignees (str — comma-separated, replaces all assignees)

At least one optional field must be provided. Empty fields are left unchanged.

Returns: {number, title, state, url}""",
    examples=[
        'github(action="issue_update", number=42, state="closed")',
        'github(action="issue_update", number=42, state="open", title="Reopened with new info")',
        'github(action="issue_update", number=7, labels="bug,priority")',
    ],
)
def _action_issue_update(
    number: Any = None,
    state: str = "",
    title: str = "",
    body: str = "",
    labels: str = "",
    assignees: str = "",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Update an issue via PATCH.

    Args:
        number: Issue number (required). Coerced to int if a numeric str is passed.
        state: "open" or "closed" to change state. Empty = don't change.
        title: New title. Empty = don't change.
        body: New body. Empty = don't change.
        labels: Comma-separated label names. Empty = don't change.
        assignees: Comma-separated login names. Empty = don't change.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for issue_update", trace_id=trace_id)

    issue_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

    # Validate state if provided
    if state and state not in ("open", "closed"):
        return fail(
            f"state must be 'open' or 'closed' — got {state!r}",
            trace_id=trace_id,
        )

    # Build payload — only include fields that are explicitly set
    payload: dict[str, Any] = {}
    if state:
        payload["state"] = state
    if title:
        payload["title"] = title
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
    if assignees:
        payload["assignees"] = [a.strip() for a in assignees.split(",") if a.strip()]

    if not payload:
        return fail(
            "At least one of state, title, body, labels, assignees must be provided",
            trace_id=trace_id,
        )

    resp, err = github_request(
        "patch",
        f"{repo_path()}/issues/{issue_number}",
        trace_id,
        json=payload,
        not_found_msg=f"Issue #{issue_number} not found",
    )
    if err:
        return err

    data = resp.json()
    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "url": data.get("html_url"),
    }, trace_id=trace_id)
