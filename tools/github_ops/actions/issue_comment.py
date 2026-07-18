"""GitHub action: issue_comment — Comment on an issue or PR.

v1.3.1 (P2-1 cross-LLM): Rewrote error handling to match the v1.0/v1.2
3-stage pattern. v1.1 used an ambiguous single try/except.
v1.3.1 (P3-2 cross-LLM): Added int(number) coercion for parity with
issue_get/issue_update/pr_get/pr_review/pr_merge/pr_comment.

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
    "github", "issue_comment",
    help_text="""issue_comment — Comment on a GitHub issue or PR (issues and PRs share the comment endpoint).
Required: number (issue or PR number), body (comment text)
Returns: {id, url, body, created_at}""",
    examples=[
        'github(action="issue_comment", number=42, body="This is fixed in PR #45")',
        'github(action="issue_comment", number=7, body="Cannot reproduce — need more info")',
    ],
)
def _action_issue_comment(
    number: Any = None,
    body: str = "",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for issue_comment", trace_id=trace_id)
    issue_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

    if not body:
        return fail("body is required for issue_comment", trace_id=trace_id)

    resp, err = github_request(
        "post",
        f"{repo_path()}/issues/{issue_number}/comments",
        trace_id,
        json={"body": body},
    )
    if err:
        return err

    data = resp.json()
    return ok({
        "id": data.get("id"),
        "url": data.get("html_url"),
        "body": data.get("body", ""),
        "created_at": data.get("created_at", ""),
    }, trace_id=trace_id)
