"""GitHub action: issue_create — Create a new issue.

v1.3.1 (P2-1 cross-LLM): Rewrote error handling to match the v1.0/v1.2
3-stage pattern (network call → HTTP error → JSON parse), with `status=`
and `trace_id=` on all fail()/ok() calls. v1.1 used an ambiguous single
try/except that couldn't distinguish network errors from parse errors.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


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
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )
    if not title:
        return fail("title is required for issue_create", trace_id=trace_id)

    payload: dict[str, Any] = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
    if assignees:
        payload["assignees"] = [a.strip() for a in assignees.split(",") if a.strip()]

    client = get_client()
    try:
        resp = client.post(f"{repo_path()}/issues", json=payload, timeout=30)
    except Exception as e:
        return fail(f"issue_create request failed: {e}", trace_id=trace_id)

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
        return fail(f"issue_create returned non-JSON response: {e}", trace_id=trace_id)

    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "url": data.get("html_url"),
        "state": data.get("state"),
    }, trace_id=trace_id)
