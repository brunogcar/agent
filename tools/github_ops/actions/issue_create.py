"""GitHub action: issue_create — Create a new issue."""
from __future__ import annotations
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
    **kwargs,
) -> dict:
    if not is_configured():
        return fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env.")
    if not title:
        return fail("title is required for issue_create")

    payload: dict = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
    if assignees:
        payload["assignees"] = [a.strip() for a in assignees.split(",") if a.strip()]

    try:
        resp = get_client().post(f"{repo_path()}/issues", json=payload, timeout=30)
        if resp.status_code >= 400:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
            return fail(f"GitHub API error {resp.status_code}: {err.get('message', resp.text[:200])}")
        data = resp.json()
        return ok({
            "number": data.get("number"),
            "title": data.get("title"),
            "url": data.get("html_url"),
            "state": data.get("state"),
        })
    except Exception as e:
        return fail(f"issue_create failed: {e}")
