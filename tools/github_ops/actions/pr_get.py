"""GitHub action: pr_get — Fetch a single pull request's details.

Calls GET /repos/{owner}/{repo}/pulls/{number} and returns a detailed
view of one PR (state, merge status, draft flag, full body, timestamps).
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


@register_action(
    "github", "pr_get",
    help_text="""pr_get — Fetch detailed info for a single pull request.

Required: number (int — PR number)

Returns: {number, title, state, merged, mergeable, mergeable_state, draft,
          head, base, url, body, user, created_at, updated_at}

mergeable: true/false/null — null means GitHub is still computing (retry).
mergeable_state: "clean" / "blocked" / "unstable" / "dirty" / "unknown".

Use pr_list first if you don't know the PR number.""",
    examples=[
        'github(action="pr_get", number=42)',
        'github(action="pr_get", number=7)',
    ],
)
def _action_pr_get(
    number: Any = None,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Fetch a single pull request by number.

    Args:
        number: PR number (required). Coerced to int if a numeric str is passed.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not number:
        return fail("number is required for pr_get", trace_id=trace_id)

    try:
        pr_number = int(number)
    except (TypeError, ValueError):
        return fail(f"number must be an int — got {number!r}", trace_id=trace_id)

    client = get_client()
    try:
        resp = client.get(f"{repo_path()}/pulls/{pr_number}", timeout=30)
    except Exception as e:
        return fail(f"pr_get request failed: {e}", trace_id=trace_id)

    if resp.status_code == 404:
        return fail(f"PR #{pr_number} not found", status=404, trace_id=trace_id)
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
        return fail(f"pr_get returned non-JSON response: {e}", trace_id=trace_id)

    user_obj = data.get("user") or {}
    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "merged": bool(data.get("merged")),
        "mergeable": data.get("mergeable"),
        "mergeable_state": data.get("mergeable_state"),
        "draft": bool(data.get("draft")),
        "head": (data.get("head") or {}).get("ref"),
        "base": (data.get("base") or {}).get("ref"),
        "url": data.get("html_url"),
        "body": data.get("body"),
        "user": user_obj.get("login"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }, trace_id=trace_id)
