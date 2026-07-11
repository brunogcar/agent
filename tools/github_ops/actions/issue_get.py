"""GitHub action: issue_get — Fetch a single issue's details.

Calls GET /repos/{owner}/{repo}/issues/{number} and returns a detailed
view of one issue (state, body, labels, assignee, timestamps).
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


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
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not number:
        return fail("number is required for issue_get", trace_id=trace_id)

    try:
        issue_number = int(number)
    except (TypeError, ValueError):
        return fail(f"number must be an int — got {number!r}", trace_id=trace_id)

    client = get_client()
    try:
        resp = client.get(f"{repo_path()}/issues/{issue_number}", timeout=30)
    except Exception as e:
        return fail(f"issue_get request failed: {e}", trace_id=trace_id)

    if resp.status_code == 404:
        return fail(f"Issue #{issue_number} not found", status=404, trace_id=trace_id)
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
        return fail(f"issue_get returned non-JSON response: {e}", trace_id=trace_id)

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
