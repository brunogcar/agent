"""GitHub action: pr_list — List pull requests on the configured repo.

Calls GET /repos/{owner}/{repo}/pulls and returns a compact list of PRs
filtered by state. The GitHub API caps per_page at 100; the `limit` param
here is applied as a client-side slice for caller convenience.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import get_client, is_configured, repo_path


@register_action(
    "github", "pr_list",
    help_text="""pr_list — List pull requests on the configured GitHub repo.

Optional: state (str: "open", "closed", "all"; default "open"),
          limit (int, default 30 — client-side cap)

Returns: {count, pulls: [{number, title, state, head, base, url, draft}]}

The GitHub API caps per_page at 100. If you need more, call this action
with state="all" and a higher limit (capped at 100 per request).""",
    examples=[
        'github(action="pr_list")',
        'github(action="pr_list", state="closed", limit=10)',
        'github(action="pr_list", state="all")',
    ],
)
def _action_pr_list(
    state: str = "open",
    limit: int = 30,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """List pull requests on the configured repo.

    Args:
        state: One of "open", "closed", "all" (default "open").
        limit: Max number of PRs to return (default 30). Capped at 100
            per the GitHub API per_page maximum.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

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

    # GitHub API caps per_page at 100
    per_page = min(limit_int, 100)

    params = {"state": state, "per_page": per_page}

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

    return ok({"count": len(pulls), "pulls": pulls}, trace_id=trace_id)
