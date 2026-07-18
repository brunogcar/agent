"""GitHub action: pr_comment — Post a comment on a pull request.

Two modes:

  (1) General PR comment — POST /repos/{owner}/{repo}/issues/{number}/comments
      Triggered when `path` and `line` are NOT provided. This is the standard
      "leave a comment on the PR" flow (GitHub treats PRs as issues for
      general comments).

  (2) Line-level (review) comment — POST /repos/{owner}/{repo}/pulls/{number}/comments
      Triggered when `path` AND `line` are provided. Comments inline on a
      specific line of a specific file. Requires `side` (LEFT or RIGHT,
      default RIGHT) and the PR's diff must contain that line.

  Note: line-level comments via this endpoint are NOT part of a review and
  will appear as "pending" until someone submits them via the UI. For
  proper review-thread comments, use pr_review with event="COMMENT" and
  pass line-level comments as part of the review payload (deferred — not
  in this action).

v1.4 (2026-07-15): Removed `status=` kwarg from all fail() calls (fail()
contract: status is a string, not an int — see core/contracts.py). The
HTTP code remains in the error message text. Structured classification
belongs in error_code (see tools/github_ops/helpers.py github_request).

[v1.5] Migrated to github_request() helper — eliminates inline 3-stage
error handling pattern (network → HTTP → JSON parse). The helper also
adds retry/backoff for transient errors and structured error_code.
"""
from __future__ import annotations
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action
from tools.github_ops.client import repo_path
from tools.github_ops.helpers import _check_configured, _coerce_int, github_request


@register_action(
    "github", "pr_comment",
    help_text="""pr_comment — Post a comment on a pull request.

Required: number (int), body (str — comment text, markdown)
Optional: path (str — file path for line-level comment),
          line (int — line number for line-level comment),
          side (str: "LEFT" or "RIGHT"; default "RIGHT")

If path AND line are both provided → line-level (pulls/{number}/comments) comment.
Otherwise → general PR comment (issues/{number}/comments).

Returns: {id, url, body} for general comments,
         {id, url, body, path, line} for line-level comments.""",
    examples=[
        'github(action="pr_comment", number=42, body="This needs a null check")',
        'github(action="pr_comment", number=42, body="Missing error handling here", path="src/main.py", line=42)',
        'github(action="pr_comment", number=42, body="Pre-commit hook fails on this line", path="tests/test_main.py", line=17, side="LEFT")',
    ],
)
def _action_pr_comment(
    number: Any = None,
    body: str = "",
    path: str = "",
    line: Any = None,
    side: str = "RIGHT",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Post a comment on a pull request.

    Args:
        number: PR number (required). Coerced to int if a numeric str is passed.
        body: Comment text as markdown (required).
        path: File path — triggers line-level mode when paired with `line`.
        line: Line number — triggers line-level mode when paired with `path`.
        side: "LEFT" or "RIGHT" (default "RIGHT") — only used in line-level mode.
        trace_id: Trace ID forwarded to ok()/fail().
    """
    err = _check_configured(trace_id)
    if err:
        return err

    if not number:
        return fail("number is required for pr_comment", trace_id=trace_id)
    pr_number, err = _coerce_int(number, "number", trace_id)
    if err:
        return err

    if not body:
        return fail("body is required for pr_comment", trace_id=trace_id)

    # Determine line-level vs general comment mode.
    # If exactly one of (path, line) is provided, that's a misuse — both or neither.
    # Use bool() for both — the facade passes line=0 by default, and 0 is not None
    # but bool(0) is False, so bool() correctly treats 0 as "not set".
    path_set = bool(path)
    line_set = bool(line)
    if path_set != line_set:
        return fail(
            "path and line must be provided together for line-level comments "
            f"(got path={path!r}, line={line!r})",
            trace_id=trace_id,
        )

    is_line_level = path_set and line_set
    if is_line_level:
        try:
            line_int = int(line)
        except (TypeError, ValueError):
            return fail(f"line must be an int — got {line!r}", trace_id=trace_id)
        if line_int < 1:
            return fail(f"line must be >= 1 — got {line_int}", trace_id=trace_id)
        if side not in ("LEFT", "RIGHT"):
            return fail(
                f"side must be 'LEFT' or 'RIGHT' — got {side!r}",
                trace_id=trace_id,
            )

    payload: dict[str, Any] = {"body": body}

    if is_line_level:
        # Line-level comment on a PR diff
        payload["path"] = path
        payload["line"] = line_int
        payload["side"] = side
        # subject_type=line tells GitHub this is a line-anchored comment.
        payload["subject_type"] = "line"
        url_path = f"{repo_path()}/pulls/{pr_number}/comments"
    else:
        # General PR comment — PRs are issues for this endpoint
        url_path = f"{repo_path()}/issues/{pr_number}/comments"

    resp, err = github_request(
        "post",
        url_path,
        trace_id,
        json=payload,
        not_found_msg=f"PR #{pr_number} not found",
    )
    if err:
        return err

    data = resp.json()
    result: dict[str, Any] = {
        "id": data.get("id"),
        "url": data.get("html_url"),
        "body": data.get("body"),
    }
    if is_line_level:
        result["path"] = data.get("path", path)
        result["line"] = data.get("line", line_int)

    return ok(result, trace_id=trace_id)
