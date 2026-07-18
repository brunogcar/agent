"""GitHub action: release_create — Create a GitHub release from a tag.

v1.3.1 (P2-1 cross-LLM): Rewrote error handling to match the v1.0/v1.2
3-stage pattern. v1.1 used an ambiguous single try/except.

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
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )
    if not tag:
        return fail("tag is required for release_create", trace_id=trace_id)

    payload: dict[str, Any] = {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
    }
    if title:
        payload["name"] = title
    if body:
        payload["body"] = body

    client = get_client()
    try:
        resp = client.post(f"{repo_path()}/releases", json=payload, timeout=30)
    except Exception as e:
        return fail(f"release_create request failed: {e}", trace_id=trace_id)

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
        return fail(f"release_create returned non-JSON response: {e}", trace_id=trace_id)

    return ok({
        "id": data.get("id"),
        "tag": data.get("tag_name"),
        "name": data.get("name", ""),
        "url": data.get("html_url"),
        "draft": data.get("draft", False),
        "prerelease": data.get("prerelease", False),
        "created_at": data.get("created_at", ""),
    }, trace_id=trace_id)
