"""GitHub action: issue_list — List issues in the repository."""
from __future__ import annotations
from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


@register_action(
    "github", "issue_list",
    help_text="""issue_list — List GitHub issues.
Optional: state (open/closed/all, default "open"), limit (default 30), labels (comma-separated filter)
Returns: {count, issues: [{number, title, state, url, labels, assignee}]}""",
    examples=[
        'github(action="issue_list", state="open")',
        'github(action="issue_list", state="all", limit=10, labels="bug,enhancement")',
    ],
)
def _action_issue_list(
    state: str = "open",
    limit: int = 30,
    labels: str = "",
    **kwargs,
) -> dict:
    if not is_configured():
        return fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env.")

    params: dict = {
        "state": state,
        "per_page": min(limit, 100),
        "sort": "created",
        "direction": "desc",
    }
    if labels:
        params["labels"] = labels

    try:
        resp = get_client().get(f"{repo_path()}/issues", params=params, timeout=30)
        if resp.status_code >= 400:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
            return fail(f"GitHub API error {resp.status_code}: {err.get('message', resp.text[:200])}")
        data = resp.json()
        issues = []
        for item in data[:limit]:
            issues.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "url": item.get("html_url"),
                "labels": [l.get("name", "") for l in item.get("labels", [])],
                "assignee": (item.get("assignee") or {}).get("login", ""),
            })
        return ok({"count": len(issues), "issues": issues})
    except Exception as e:
        return fail(f"issue_list failed: {e}")
