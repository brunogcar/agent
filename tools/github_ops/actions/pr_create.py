"""GitHub action: pr_create — Open a new pull request.

Calls POST /repos/{owner}/{repo}/pulls to create a PR from a head branch
into a base branch. The head branch must already be pushed to the remote
(use github(action="push", branch=...) first).

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
    "github", "pr_create",
    help_text="""pr_create — Open a new pull request on GitHub.

Required: title (str), head (str — source branch to merge FROM)
Optional: base (str, default "main" — target branch to merge INTO),
          body (str — PR description / markdown)

Returns: {number, title, url, state, head, base}

The head branch must already exist on the remote. Use
github(action="push", branch="...") first to push a local branch.""",
    examples=[
        'github(action="pr_create", title="Fix timeout bug", head="fix/timeout", base="main")',
        'github(action="pr_create", title="Add login page", head="feat/login", body="Closes #12")',
    ],
)
def _action_pr_create(
    title: str = "",
    head: str = "",
    base: str = "main",
    body: str = "",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Create a new pull request via the GitHub API.

    Args:
        title: PR title (required).
        head: Source branch name (required, e.g. "fix/timeout").
        base: Target branch name (default "main").
        body: PR description as markdown (optional).
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not is_configured():
        return fail(
            "GitHub not configured. Set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env",
            trace_id=trace_id,
        )

    if not title:
        return fail("title is required for pr_create", trace_id=trace_id)
    if not head:
        return fail("head (source branch) is required for pr_create", trace_id=trace_id)
    if not base:
        return fail("base (target branch) cannot be empty", trace_id=trace_id)

    payload: dict[str, Any] = {
        "title": title,
        "head": head,
        "base": base,
    }
    if body:
        payload["body"] = body

    client = get_client()
    try:
        resp = client.post(f"{repo_path()}/pulls", json=payload, timeout=30)
    except Exception as e:
        return fail(f"pr_create request failed: {e}", trace_id=trace_id)

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
        return fail(f"pr_create returned non-JSON response: {e}", trace_id=trace_id)

    return ok({
        "number": data.get("number"),
        "title": data.get("title"),
        "url": data.get("html_url"),
        "state": data.get("state"),
        "head": (data.get("head") or {}).get("ref"),
        "base": (data.get("base") or {}).get("ref"),
    }, trace_id=trace_id)
