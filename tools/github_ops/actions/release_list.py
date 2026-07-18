"""GitHub action: release_list — List GitHub releases.

v1.3.1 (P2-1 cross-LLM): Rewrote error handling to match the v1.0/v1.2
3-stage pattern. v1.1 used an ambiguous single try/except.
v1.3.1 (P2-2 cross-LLM): Added pagination (page param + Link header parsing)
for parity with pr_list/issue_list. v1.1 was capped at 100 items (GitHub's
per_page max) with no way to fetch the next page — repos with >100 releases
returned silently truncated results.

v1.4 (2026-07-15): Removed `status=` kwarg from all fail() calls (fail()
contract: status is a string, not an int — see core/contracts.py). The
HTTP code remains in the error message text. Structured classification
belongs in error_code (see tools/github_ops/helpers.py github_request).
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path, parse_link_header


@register_action(
    "github", "release_list",
    help_text="""release_list — List GitHub releases (newest first).
Optional: limit (default 30, max 100 per page), page (default 1 — for pagination)
Returns: {count, releases: [{id, tag, name, url, draft, prerelease, published_at}],
          page, has_next, next_page}

The GitHub API caps per_page at 100. For repos with >100 releases, use page=2,
page=3, etc. The `has_next` and `next_page` fields come from the Link header.""",
    examples=[
        'github(action="release_list")',
        'github(action="release_list", limit=5)',
        'github(action="release_list", page=2)',
    ],
)
def _action_release_list(
    limit: int = 30,
    page: int = 1,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        return fail(f"limit must be an int — got {limit!r}", trace_id=trace_id)
    if limit_int < 1:
        return fail(f"limit must be >= 1 — got {limit_int}", trace_id=trace_id)

    try:
        page_int = int(page)
    except (TypeError, ValueError):
        return fail(f"page must be an int — got {page!r}", trace_id=trace_id)
    if page_int < 1:
        return fail(f"page must be >= 1 — got {page_int}", trace_id=trace_id)

    params = {"per_page": min(limit_int, 100), "page": page_int}

    client = get_client()
    try:
        resp = client.get(f"{repo_path()}/releases", params=params, timeout=30)
    except Exception as e:
        return fail(f"release_list request failed: {e}", trace_id=trace_id)

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
        return fail(f"release_list returned non-JSON response: {e}", trace_id=trace_id)

    # Parse Link header for pagination info
    link_header = resp.headers.get("link", "")
    page_info = parse_link_header(link_header)

    releases = []
    for item in data[:limit_int]:
        releases.append({
            "id": item.get("id"),
            "tag": item.get("tag_name"),
            "name": item.get("name", ""),
            "url": item.get("html_url"),
            "draft": item.get("draft", False),
            "prerelease": item.get("prerelease", False),
            "published_at": item.get("published_at", ""),
        })
    return ok({
        "count": len(releases),
        "releases": releases,
        "page": page_int,
        "has_next": page_info["next"] is not None,
        "next_page": page_info["next"],
    }, trace_id=trace_id)
