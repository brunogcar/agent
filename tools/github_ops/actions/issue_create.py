"""GitHub action: issue_create — Create a new issue.

v1.3.1 (P2-1 cross-LLM): Rewrote error handling to match the v1.0/v1.2
3-stage pattern (network call → HTTP error → JSON parse), with `status=`
and `trace_id=` on all fail()/ok() calls. v1.1 used an ambiguous single
try/except that couldn't distinguish network errors from parse errors.

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
from tools.github_ops.helpers import _check_configured, github_request


@register_action(
    "github", "issue_create",
    help_text="""issue_create — Create a new GitHub issue.
Required: title
Optional: body (description), labels (comma-separated), assignees (comma-separated)
Returns: {number, title, url, state}""",
    examples=[
        'github(action="issue_create", title="Bug: timeout on large files")',
        'github(action="issue_create", title="Feature: add dark mode", body="Users want dark mode", labels="enhancement,ui")',
    ],
)
def _action_issue_create(
    title: str = "",
    body: str = "",
    labels: str = "",
    assignees: str = "",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    err = _check_configured(trace_id)
    if err:
        return err
    if not title:
        return fail("title is required for issue_create", trace_id=trace_id)

    payload: dict[str, Any] = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
    if assignees:
        payload["assignees"] = [a.strip() for a in assignees.split(",") if a.strip()]

    resp, err = github_request(
        "post",
        f"{repo_path()}/issues",
        trace_id,
        json=payload,
    )
    if err:
        return err

    data = resp.json()
    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "url": data.get("html_url"),
        "state": data.get("state"),
    }, trace_id=trace_id)
