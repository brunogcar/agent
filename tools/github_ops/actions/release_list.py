"""GitHub action: release_list — List GitHub releases."""
from __future__ import annotations
from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


@register_action(
    "github", "release_list",
    help_text="""release_list — List GitHub releases (newest first).
Optional: limit (default 10)
Returns: {count, releases: [{id, tag, name, url, draft, prerelease, published_at}]}""",
    examples=[
        'github(action="release_list")',
        'github(action="release_list", limit=5)',
    ],
)
def _action_release_list(
    limit: int = 10,
    **kwargs,
) -> dict:
    if not is_configured():
        return fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env.")

    try:
        resp = get_client().get(
            f"{repo_path()}/releases",
            params={"per_page": min(limit, 100)},
            timeout=30,
        )
        if resp.status_code >= 400:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
            return fail(f"GitHub API error {resp.status_code}: {err.get('message', resp.text[:200])}")
        data = resp.json()
        releases = []
        for item in data[:limit]:
            releases.append({
                "id": item.get("id"),
                "tag": item.get("tag_name"),
                "name": item.get("name", ""),
                "url": item.get("html_url"),
                "draft": item.get("draft", False),
                "prerelease": item.get("prerelease", False),
                "published_at": item.get("published_at", ""),
            })
        return ok({"count": len(releases), "releases": releases})
    except Exception as e:
        return fail(f"release_list failed: {e}")
