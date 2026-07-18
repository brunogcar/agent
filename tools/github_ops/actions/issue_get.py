"""GitHub action: issue_get — Fetch a single issue's details.

Calls GET /repos/{owner}/{repo}/issues/{number} and returns a detailed
view of one issue (state, body, labels, assignee, timestamps).

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
    "github", "issue_get",
    help_text="""issue_get — Fetch detailed info for a single GitHub issue.

Required: number (int — issue number)

Returns: {number, title, state, body, url, labels, assignee,
          user, created_at, updated_at, closed_at}

Use issue_list first if you don't know the issue number.""",
    examples=[
        'github(action="issue_get", number=42)',
        'github(action="issue_get", number=7)',
    ],
)
def _action_issue_get(
    number: Any = None,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Fetch a single issue by number.

    Args:
        number: Issue number (required). Coerced to int if a numeric str is passed.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for issue_get", trace_id=trace_id)

    issue_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

    resp, err = github_request(
        "get",
        f"{repo_path()}/issues/{issue_number}",
        trace_id,
        not_found_msg=f"Issue #{issue_number} not found",
    )
    if err:
        return err

    data = resp.json()
    user_obj = data.get("user") or {}
    assignee_obj = data.get("assignee") or {}
    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "body": data.get("body"),
        "url": data.get("html_url"),
        "labels": [l.get("name", "") for l in data.get("labels", [])],
        "assignee": assignee_obj.get("login", ""),
        "user": user_obj.get("login"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "closed_at": data.get("closed_at"),
    }, trace_id=trace_id)
