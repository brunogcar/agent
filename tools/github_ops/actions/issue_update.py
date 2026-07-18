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
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


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
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not number:
        return fail("number is required for issue_update", trace_id=trace_id)

    try:
        issue_number = int(number)
    except (TypeError, ValueError):
        return fail(f"number must be an int — got {number!r}", trace_id=trace_id)

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

    client = get_client()
    try:
        resp = client.patch(
            f"{repo_path()}/issues/{issue_number}", json=payload, timeout=30
        )
    except Exception as e:
        return fail(f"issue_update request failed: {e}", trace_id=trace_id)

    if resp.status_code == 404:
        return fail(f"Issue #{issue_number} not found", trace_id=trace_id)
    if resp.status_code >= 400:
        try:
            err_body = resp.json()
            msg = err_body.get("message", resp.text)
        except Exception:
            msg = resp.text
        return fail(
            f"GitHub API error {resp.status_code}: {msg}",
            trace_id=trace_id,
        )

    try:
        data = resp.json()
    except Exception as e:
        return fail(f"issue_update returned non-JSON response: {e}", trace_id=trace_id)

    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "url": data.get("html_url"),
    }, trace_id=trace_id)
