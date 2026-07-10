"""GitHub action: issue_comment — Comment on an issue or PR."""
from __future__ import annotations
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
    number: int = 0,
    body: str = "",
    **kwargs,
) -> dict:
    if not is_configured():
        return fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env.")
    if not number:
        return fail("number is required for issue_comment")
    if not body:
        return fail("body is required for issue_comment")

    try:
        resp = get_client().post(
            f"{repo_path()}/issues/{number}/comments",
            json={"body": body},
            timeout=30,
        )
        if resp.status_code >= 400:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
            return fail(f"GitHub API error {resp.status_code}: {err.get('message', resp.text[:200])}")
        data = resp.json()
        return ok({
            "id": data.get("id"),
            "url": data.get("html_url"),
            "body": data.get("body", ""),
            "created_at": data.get("created_at", ""),
        })
    except Exception as e:
        return fail(f"issue_comment failed: {e}")
