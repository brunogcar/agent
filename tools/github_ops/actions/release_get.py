"""GitHub action: release_get — Fetch a single release's details.

Calls GET /repos/{owner}/{repo}/releases/tags/{tag} (by tag name) or
GET /repos/{owner}/{repo}/releases/{id} (by numeric ID). Tag-based lookup
is the default — it's more user-friendly since you know the tag from
release_list or git tags.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


@register_action(
    "github", "release_get",
    help_text="""release_get — Fetch detailed info for a single GitHub release.

Required: tag (str — tag name, e.g. "v1.0.0") OR number (int — release ID)

If tag is provided → GET /releases/tags/{tag} (preferred — user-friendly).
If only number is provided → GET /releases/{id} (use when you have the
numeric release ID from release_list).

Returns: {id, tag, name, url, draft, prerelease, created_at, published_at,
          body, assets: [{name, url, size, download_count}]}

Use release_list first if you don't know the tag or ID.""",
    examples=[
        'github(action="release_get", tag="v1.0.0")',
        'github(action="release_get", number=12345)',
    ],
)
def _action_release_get(
    tag: str = "",
    number: Any = None,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Fetch a single release by tag name or numeric ID.

    Args:
        tag: Tag name (e.g. "v1.0.0"). Takes priority over number.
        number: Numeric release ID. Used only if tag is empty.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not tag and not number:
        return fail(
            "tag or number is required for release_get",
            trace_id=trace_id,
        )

    # Build the URL — tag takes priority
    if tag:
        url_path = f"{repo_path()}/releases/tags/{tag}"
    else:
        try:
            release_id = int(number)
        except (TypeError, ValueError):
            return fail(
                f"number must be an int — got {number!r}",
                trace_id=trace_id,
            )
        url_path = f"{repo_path()}/releases/{release_id}"

    client = get_client()
    try:
        resp = client.get(url_path, timeout=30)
    except Exception as e:
        return fail(f"release_get request failed: {e}", trace_id=trace_id)

    if resp.status_code == 404:
        label = f"tag {tag!r}" if tag else f"ID {number!r}"
        return fail(f"Release {label} not found", status=404, trace_id=trace_id)
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
        return fail(f"release_get returned non-JSON response: {e}", trace_id=trace_id)

    assets = [
        {
            "name": a.get("name"),
            "url": a.get("browser_download_url"),
            "size": a.get("size"),
            "download_count": a.get("download_count"),
        }
        for a in data.get("assets", [])
    ]

    return ok({
        "id": data.get("id"),
        "tag": data.get("tag_name"),
        "name": data.get("name", ""),
        "url": data.get("html_url"),
        "draft": bool(data.get("draft", False)),
        "prerelease": bool(data.get("prerelease", False)),
        "created_at": data.get("created_at", ""),
        "published_at": data.get("published_at", ""),
        "body": data.get("body", ""),
        "assets": assets,
    }, trace_id=trace_id)
