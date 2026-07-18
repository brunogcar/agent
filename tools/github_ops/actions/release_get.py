"""GitHub action: release_get — Fetch a single release's details.

Calls GET /repos/{owner}/{repo}/releases/tags/{tag} (by tag name) or
GET /repos/{owner}/{repo}/releases/{id} (by numeric ID). Tag-based lookup
is the default — it's more user-friendly since you know the tag from
release_list or git tags.

v1.4 (2026-07-15):
  - URL-encode the tag with `quote(tag, safe="")` so tags containing
    URL-unsafe characters (spaces, slashes, `+`, `#`, `?`, etc.) don't
    produce malformed request URLs. Real-world example: a `v1.0.0+build.5`
    semver tag previously hit `GET /releases/tags/v1.0.0+build.5` — the
    `+` is technically valid in a path segment but the resulting 404 was
    indistinguishable from a missing release. With quote(), the request
    becomes `GET /releases/tags/v1.0.0%2Bbuild.5`.
  - Removed `status=` kwarg from all fail() calls (fail() contract: status
    is a string, not an int — see core/contracts.py).

[v1.5] Migrated to github_request() helper — eliminates inline 3-stage
error handling pattern (network → HTTP → JSON parse). The helper also
adds retry/backoff for transient errors and structured error_code.
The v1.4 `quote(tag, safe="")` URL-encoding fix is preserved.
"""
from __future__ import annotations
from typing import Any
from urllib.parse import quote

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import repo_path
from tools.github_ops.helpers import _check_configured, _coerce_int, github_request


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
    err = _check_configured(trace_id)
    if err:
        return err

    if not tag and not number:
        return fail(
            "tag or number is required for release_get",
            trace_id=trace_id,
        )

    # Build the URL — tag takes priority.
    # v1.4: URL-encode the tag so URL-unsafe chars (+, #, ?, /, space) don't
    # produce malformed requests. safe="" encodes everything that's not
    # unreserved (alnum + - _ . ~) — same as JavaScript's encodeURIComponent.
    if tag:
        url_path = f"{repo_path()}/releases/tags/{quote(tag, safe='')}"
        not_found_msg = f"Release tag {tag!r} not found"
    else:
        release_id, err = _coerce_int(number, "number", trace_id)
        if err:
            return err
        url_path = f"{repo_path()}/releases/{release_id}"
        not_found_msg = f"Release ID {number!r} not found"

    resp, err = github_request(
        "get",
        url_path,
        trace_id,
        not_found_msg=not_found_msg,
    )
    if err:
        return err

    data = resp.json()

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
