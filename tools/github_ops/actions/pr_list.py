"""GitHub action: pr_list — List pull requests on the configured repo.

Calls GET /repos/{owner}/{repo}/pulls and returns a compact list of PRs
filtered by state. Supports pagination via the `page` param — the GitHub
API caps per_page at 100, so use `page` for repos with >100 PRs.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path, parse_link_header


@register_action(
    "github", "pr_list",
    help_text="""pr_list — List pull requests on the configured GitHub repo.

Optional: state (str: "open", "closed", "all"; default "open"),
          limit (int, default 30 — client-side cap, max 100 per page),
          page (int, default 1 — for pagination beyond 100 items)

Returns: {count, pulls: [...], page, has_next, next_page}

The GitHub API caps per_page at 100. For repos with >100 PRs, use page=2,
page=3, etc. The `has_next` and `next_page` fields come from the Link
header — if has_next is true, call again with page=next_page.""",
    examples=[
        'github(action="pr_list")',
        'github(action="pr_list", state="closed", limit=10)',
        'github(action="pr_list", state="all", page=2)',
    ],
)
def _action_pr_list(
    state: str = "",
    limit: int = 30,
    page: int = 1,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """List pull requests on the configured repo.

    Args:
        state: One of "open", "closed", "all" (default "open").
        limit: Max number of PRs to return (default 30). Capped at 100
            per the GitHub API per_page maximum.
        page: Page number for pagination (default 1). Use when a repo has
            more than 100 PRs — the Link header indicates if more pages exist.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    # Default state to "open" if not provided (facade passes "" by default)
    if not state:
        state = "open"
    if state not in ("open", "closed", "all"):
        return fail(
            f"state must be one of 'open', 'closed', 'all' — got {state!r}",
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

    # GitHub API caps per_page at 100
    per_page = min(limit_int, 100)

    params = {"state": state, "per_page": per_page, "page": page_int}

    client = get_client()
    try:
        resp = client.get(f"{repo_path()}/pulls", params=params, timeout=30)
    except Exception as e:
        return fail(f"pr_list request failed: {e}", trace_id=trace_id)

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
        items = resp.json()
    except Exception as e:
        return fail(f"pr_list returned non-JSON response: {e}", trace_id=trace_id)

    if not isinstance(items, list):
        return fail(
            f"pr_list expected a list from GitHub API — got {type(items).__name__}",
            trace_id=trace_id,
        )

    # Parse Link header for pagination info
    link_header = resp.headers.get("link", "")
    page_info = parse_link_header(link_header)

    pulls = [
        {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "head": (pr.get("head") or {}).get("ref"),
            "base": (pr.get("base") or {}).get("ref"),
            "url": pr.get("html_url"),
            "draft": bool(pr.get("draft")),
        }
        for pr in items[:limit_int]
    ]

    return ok({
        "count": len(pulls),
        "pulls": pulls,
        "page": page_int,
        "has_next": page_info["next"] is not None,
        "next_page": page_info["next"],
    }, trace_id=trace_id)
