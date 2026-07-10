"""GitHub action: push — Push a local branch to the remote via `git push`.

This is a LOCAL git operation (subprocess), NOT a GitHub API call. It
lives in the github_ops tool because pushing a local branch to origin is
the prerequisite for any PR workflow — you must push before you can call
github(action="pr_create", ...).

WHY NOT IN git_ops:
  The push step is conceptually part of the GitHub PR workflow (push →
  open PR → review → merge). Grouping it with the other PR actions keeps
  the workflow discoverable: every step from local commit to merged PR
  is reachable via github(action=...). The git_ops tool remains focused
  on local repo inspection (status, diff, log, etc.).

NOT PARALLEL-SAFE:
  This action spawns a git subprocess. Concurrent `git push` to the same
  remote on the same branch will fail (lock contention). Do not include
  push in parallel() batches. It is intentionally NOT in
  PARALLEL_SAFE in core/parallel_executor.py.

FORCE PUSH:
  force=True uses `--force-with-lease` (NOT `--force`), which is safer —
  it refuses to overwrite remote refs that have been updated since your
  last fetch. This prevents accidental history destruction when a
  teammate has pushed in the meantime. Use force=True only when you
  intend to rewrite remote branch history (e.g. after a rebase).
"""
from __future__ import annotations
import subprocess
from typing import Any

from core.contracts import ok, fail
from tools.github_ops._registry import register_action


@register_action(
    "github", "push",
    help_text="""push — Push a local branch to the remote (git push origin <branch>).

Required: branch (str — local branch name to push)
Optional: remote (str, default "origin"), force (bool, default False → --force-with-lease)

Returns: {status, branch, remote, pushed: true, output}

LOCAL git operation (subprocess), NOT a GitHub API call. Does NOT require
GITHUB_TOKEN — uses the repo's configured git remote (SSH or HTTPS).

NOT parallel-safe: do not include in parallel() batches. Concurrent
pushes to the same branch will fail with lock contention.

force=True uses --force-with-lease (NOT --force) for safety — it refuses
to overwrite remote refs that have been updated since your last fetch.""",
    examples=[
        'github(action="push", branch="fix/timeout")',
        'github(action="push", branch="fix/timeout", remote="origin")',
        'github(action="push", branch="feat/rebase", force=True)',
    ],
)
def _action_push(
    branch: str = "",
    remote: str = "origin",
    force: bool = False,
    trace_id: str = "",
    **kwargs: Any,
) -> dict:
    """Push a local branch to the configured git remote via subprocess.

    Args:
        branch: Local branch name to push (required).
        remote: Remote name to push to (default "origin").
        force: If True, use --force-with-lease (safer than --force).
        trace_id: Trace ID forwarded to ok()/fail().
    """
    if not branch:
        return fail("branch is required for push", trace_id=trace_id)
    if not remote:
        return fail("remote cannot be empty (default is 'origin')", trace_id=trace_id)

    # Build the git command. Using a list (not shell=True) for safety —
    # branch/remote names are validated as best-effort below and never
    # reach a shell.
    # Reject names containing shell metacharacters as a defense-in-depth
    # measure. Git branch names cannot contain these anyway, so this
    # catches programming errors rather than security issues.
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

    cmd: list[str] = ["git", "push", remote, branch]
    if force:
        # --force-with-lease refuses to overwrite refs that have moved
        # on the remote since the last fetch. Safer than --force.
        cmd.insert(2, "--force-with-lease")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return fail(
            f"git push timed out after 120s (branch={branch!r}, remote={remote!r})",
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
            f"git push subprocess failed: {e}",
            branch=branch,
            remote=remote,
            trace_id=trace_id,
        )

    # Combine stdout + stderr for diagnostic output. git push writes
    # progress and ref-update info to stderr by default.
    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip()

    if result.returncode != 0:
        return fail(
            f"git push failed (exit {result.returncode}): {output}",
            branch=branch,
            remote=remote,
            exit_code=result.returncode,
            output=output,
            trace_id=trace_id,
        )

    return ok({
        "status": "ok",
        "branch": branch,
        "remote": remote,
        "pushed": True,
        "output": output,
        "forced": bool(force),
    }, trace_id=trace_id)
