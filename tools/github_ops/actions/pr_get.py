"""GitHub action: pr_get — Fetch a single pull request's details.

Calls GET /repos/{owner}/{repo}/pulls/{number} and returns a detailed
view of one PR (state, merge status, draft flag, full body, timestamps).

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
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for pr_get", trace_id=trace_id)

    pr_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

    resp, err = github_request(
        "get",
        f"{repo_path()}/pulls/{pr_number}",
        trace_id,
        not_found_msg=f"PR #{pr_number} not found",
    )
    if err:
        return err

    data = resp.json()
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
