"""GitHub action: release_create — Create a GitHub release from a tag."""
from __future__ import annotations
from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


@register_action(
    "github", "release_create",
    help_text="""release_create — Create a GitHub release from a tag.
Required: tag (tag name, e.g. "v1.0.0")
Optional: title (release name), body (release notes), draft (bool, default False), prerelease (bool, default False)
Returns: {id, tag, name, url, draft, prerelease, created_at}""",
    examples=[
        'github(action="release_create", tag="v1.0.0", title="First stable release")',
        'github(action="release_create", tag="v2.0.0-beta", title="Beta", prerelease=True, body="## Changes\\n- New feature X\\n- Bug fixes")',
    ],
)
def _action_release_create(
    tag: str = "",
    title: str = "",
    body: str = "",
    draft: bool = False,
    prerelease: bool = False,
    **kwargs,
) -> dict:
    if not is_configured():
        return fail("GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env.")
    if not tag:
        return fail("tag is required for release_create")

    payload: dict = {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
    }
    if title:
        payload["name"] = title
    if body:
        payload["body"] = body

    try:
        resp = get_client().post(f"{repo_path()}/releases", json=payload, timeout=30)
        if resp.status_code >= 400:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
            return fail(f"GitHub API error {resp.status_code}: {err.get('message', resp.text[:200])}")
        data = resp.json()
        return ok({
            "id": data.get("id"),
            "tag": data.get("tag_name"),
            "name": data.get("name", ""),
            "url": data.get("html_url"),
            "draft": data.get("draft", False),
            "prerelease": data.get("prerelease", False),
            "created_at": data.get("created_at", ""),
        })
    except Exception as e:
        return fail(f"release_create failed: {e}")
