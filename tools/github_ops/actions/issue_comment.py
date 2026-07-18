"""GitHub action: issue_comment — Comment on an issue or PR.

v1.3.1 (P2-1 cross-LLM): Rewrote error handling to match the v1.0/v1.2
3-stage pattern. v1.1 used an ambiguous single try/except.
v1.3.1 (P3-2 cross-LLM): Added int(number) coercion for parity with
issue_get/issue_update/pr_get/pr_review/pr_merge/pr_comment.

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
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not number:
        return fail("number is required for issue_comment", trace_id=trace_id)
    try:
        issue_number = int(number)
    except (TypeError, ValueError):
        return fail(f"number must be an int — got {number!r}", trace_id=trace_id)

    if not body:
        return fail("body is required for issue_comment", trace_id=trace_id)

    client = get_client()
    try:
        resp = client.post(
            f"{repo_path()}/issues/{issue_number}/comments",
            json={"body": body},
            timeout=30,
        )
    except Exception as e:
        return fail(f"issue_comment request failed: {e}", trace_id=trace_id)

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
        return fail(f"issue_comment returned non-JSON response: {e}", trace_id=trace_id)

    return ok({
        "id": data.get("id"),
        "url": data.get("html_url"),
        "body": data.get("body", ""),
        "created_at": data.get("created_at", ""),
    }, trace_id=trace_id)
