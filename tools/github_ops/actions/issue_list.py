"""GitHub action: issue_list — List issues in the repository.

Calls GET /repos/{owner}/{repo}/issues and returns a compact list filtered
by state. Supports pagination via the `page` param — the GitHub API caps
per_page at 100, so use `page` for repos with >100 issues.

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
    "github", "issue_list",
    help_text="""issue_list — List GitHub issues.
Optional: state (open/closed/all, default "open"), limit (default 30, max 100 per page),
          labels (comma-separated filter), page (default 1 — for pagination)
Returns: {count, issues: [{number, title, state, url, labels, assignee}],
          page, has_next, next_page}

The GitHub API caps per_page at 100. For repos with >100 issues, use page=2,
page=3, etc. The `has_next` and `next_page` fields come from the Link header.""",
    examples=[
        'github(action="issue_list", state="open")',
        'github(action="issue_list", state="all", limit=10, labels="bug,enhancement")',
        'github(action="issue_list", page=2)',
    ],
)
def _action_issue_list(
    state: str = "",
    limit: int = 30,
    labels: str = "",
    page: int = 1,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
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

    params: dict = {
        "state": state,
        "per_page": min(limit_int, 100),
        "page": page_int,
        "sort": "created",
        "direction": "desc",
    }
    if labels:
        params["labels"] = labels

    client = get_client()
    try:
        resp = client.get(f"{repo_path()}/issues", params=params, timeout=30)
    except Exception as e:
        return fail(f"issue_list request failed: {e}", trace_id=trace_id)

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
        return fail(f"issue_list returned non-JSON response: {e}", trace_id=trace_id)

    # Parse Link header for pagination info
    link_header = resp.headers.get("link", "")
    page_info = parse_link_header(link_header)

    issues = []
    for item in data[:limit_int]:
        issues.append({
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "url": item.get("html_url"),
            "labels": [l.get("name", "") for l in item.get("labels", [])],
            "assignee": (item.get("assignee") or {}).get("login", ""),
        })
    return ok({
        "count": len(issues),
        "issues": issues,
        "page": page_int,
        "has_next": page_info["next"] is not None,
        "next_page": page_info["next"],
    }, trace_id=trace_id)
