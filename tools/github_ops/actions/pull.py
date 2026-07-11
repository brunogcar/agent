"""GitHub action: pull — Pull recent commits from the remote via `git pull`.

This is a LOCAL git operation (subprocess), NOT a GitHub API call. It
lives in the github_ops tool alongside `push` — together they cover the
remote sync workflow (pull before branching → push after committing).

WHY NOT IN git_ops:
  Same rationale as `push`: pull is conceptually part of the remote
  workflow. Grouping it with push + PR actions keeps the full remote
  workflow discoverable via github(action=...). The git_ops tool remains
  focused on local repo inspection (status, diff, log, etc.).

NOT PARALLEL-SAFE:
  This action spawns a git subprocess. Concurrent `git pull` on the same
  repo will fail (lock contention). Do not include pull in parallel()
  batches. It is intentionally NOT in PARALLEL_SAFE.

[v1.3] Added for autocode integration — autocode can optionally pull
recent commits before creating a feature branch (AUTOCODE_PULL_BEFORE_BRANCH).
"""
from __future__ import annotations
import subprocess
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action


@register_action(
    "github", "pull",
    help_text="""pull — Fetch and merge recent commits from the remote (git pull origin <branch>).

Optional: branch (str — branch to pull; empty = current branch),
          remote (str, default "origin")

Returns: {status, branch, remote, pulled: true, output}

LOCAL git operation (subprocess), NOT a GitHub API call. Does NOT require
GITHUB_TOKEN — uses the repo's configured git remote (SSH or HTTPS).

NOT parallel-safe: do not include in parallel() batches.""",
    examples=[
        'github(action="pull")',
        'github(action="pull", branch="main", remote="origin")',
    ],
)
def _action_pull(
    branch: str = "",
    remote: str = "origin",
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Pull recent commits from the configured git remote via subprocess.

    Args:
        branch: Branch to pull (empty = current branch).
        remote: Remote name to pull from (default "origin").
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not remote:
        return fail("remote cannot be empty (default is 'origin')", trace_id=trace_id)

    # Defense in depth: reject shell metacharacters (same as push action).
    # Branch/remote names cannot contain these anyway.
    for char in (";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r"):
        if char in branch:
            return fail(
                f"branch contains forbidden character {char!r}",
                branch=branch,
                trace_id=trace_id,
            )
        if char in remote:
            return fail(
                f"remote contains forbidden character {char!r}",
                remote=remote,
                trace_id=trace_id,
            )

    # Build command: git pull <remote> [<branch>]
    if branch:
        cmd: list[str] = ["git", "pull", remote, branch]
    else:
        cmd: list[str] = ["git", "pull", remote]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return fail(
            f"git pull timed out after 120s (branch={branch!r}, remote={remote!r})",
            branch=branch,
            remote=remote,
            trace_id=trace_id,
        )
    except FileNotFoundError:
        return fail(
            "git executable not found — install git and ensure it is on PATH",
            branch=branch,
            remote=remote,
            trace_id=trace_id,
        )
    except Exception as e:
        return fail(
            f"git pull subprocess failed: {e}",
            branch=branch,
            remote=remote,
            trace_id=trace_id,
        )

    # Combine stdout + stderr — git pull writes progress to stderr.
    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip()

    if result.returncode != 0:
        return fail(
            f"git pull failed (exit {result.returncode}): {output}",
            branch=branch,
            remote=remote,
            exit_code=result.returncode,
            output=output,
            trace_id=trace_id,
        )

    return ok({
        "status": "ok",
        "branch": branch or "(current)",
        "remote": remote,
        "pulled": True,
        "output": output,
    }, trace_id=trace_id)
