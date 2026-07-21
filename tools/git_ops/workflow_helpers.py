"""tools/git_ops/workflow_helpers.py — Internal git helpers for workflows.

Three functions (NOT registered as LLM actions — internal library code):

  - `commit(project_root, message, target_file="", tid="") -> dict`
  - `create_branch(project_root, branch, tid="") -> bool`
  - `reset_hard(project_root, tid="") -> bool`

These consolidate the git operations that were duplicated across the
autocode + autoresearch workflows (Phase B of the centralize-workflow-utils
refactor — v1.2 of the git tool docs):

  - `workflows/autocode_impl/vcs_ops.py::_git_commit` — local commit (deleted;
    re-exported from `workflows.autocode_impl.git_ops` for backward compat).
  - `workflows/autocode_impl/vcs_ops.py::_git_create_branch` — branch creation
    (deleted; re-exported).
  - `workflows/autoresearch_impl/nodes/decide.py::_git_commit` — raw
    `subprocess.run` version (deleted; replaced by `commit`).
  - `workflows/autoresearch_impl/nodes/decide.py::_git_reset_hard` — raw
    `subprocess.run` version (deleted; replaced by `reset_hard`).
  - `workflows/autoresearch_impl/nodes/setup.py::_git_create_branch` —
    used `tools.git.git()` directly (deleted; replaced by `create_branch`).

All functions use the `tools.git_ops.helpers._git()` runner — same runner
the LLM-facing git tool uses. This means:
  - Same git executable detection (handles Windows service PATH limitations)
  - Same subprocess environment (GIT_TERMINAL_PROMPT=0, GIT_ASKPASS=echo)
  - Same timeout (15s per command)
  - Same never-raise contract (returns error tuples / dicts on failure)

They do NOT go through the LLM-facing `git()` facade (which adds compression
+ tracing that adds noise to tight workflow loops). Tracing is done inline
via `tracer.step(tid, "git_commit", ...)` etc., with the workflow's trace_id.

SAFETY GUARDS
-------------
`reset_hard` includes a toplevel-verify safety check: before resetting, it
runs `git rev-parse --show-toplevel` and verifies the returned path matches
`Path(project_root).resolve()`. If they don't match (e.g. project_root is a
junction/symlink to a different repo, or a subdirectory of another repo),
the reset is refused + a tracer warning is logged + `False` is returned.
This prevents accidentally nuking a DIFFERENT git repo's working tree.
"""
from __future__ import annotations

from pathlib import Path

from core.tracer import tracer
from tools.git_ops.helpers import _git


def commit(project_root: str, message: str, target_file: str = "", tid: str = "") -> dict:
    """Stage target_file (or -A) and commit. Returns a structured dict.

    Stages `target_file` if non-empty (mirrors the v1.2.1 autoresearch P3-1
    behavior — staging all changes risks committing unexpected artifacts from
    experiment subprocesses). When `target_file` is empty, stages all changes
    via `git add -A` (mirrors the autocode vcs_ops behavior).

    Returns:
        - `{"committed": True, "sha": sha}` on success
        - `{"committed": False, "sha": "", "reason": "nothing to commit"}` on
          clean tree (no staged changes after `git add`)
        - `{"committed": False, "sha": "", "reason": f"error: {e}"}` on
          exception (git not found, repo missing, etc.)

    The SHA is the SHORT form (`git rev-parse --short HEAD`) — matches both
    the old autocode + autoresearch `_git_commit` return shape.

    Traces via `tracer.step(tid, "git_commit", ...)` on every path (success,
    nothing-to-commit, failure). Non-raising — exceptions are caught + logged.
    """
    if not project_root:
        if tid:
            tracer.step(tid, "git_commit", "skipped — no project_root")
        return {"committed": False, "sha": "", "reason": "no project_root"}

    cwd = Path(project_root)
    try:
        # Stage target_file (or -A if not specified).
        add_args = ["add", target_file] if target_file else ["add", "-A"]
        rc, _, err = _git(add_args, cwd)
        if rc != 0:
            if tid:
                tracer.step(tid, "git_commit", f"git add failed: {err[:200]}")
            return {"committed": False, "sha": "", "reason": f"add error: {err}"}

        # Commit. Detect "nothing to commit" via the standard git output:
        #   - returncode=1 + stderr contains "nothing to commit" or "no changes"
        #     (git 2.x+ uses both phrases across versions / platforms).
        rc, out, err = _git(
            ["commit", "-m", message],
            cwd,
        )
        if rc != 0:
            combined = (out + " " + err).lower()
            if "nothing to commit" in combined or "no changes" in combined:
                if tid:
                    tracer.step(tid, "git_commit", f"nothing to commit @ {project_root}")
                return {"committed": False, "sha": "", "reason": "nothing to commit"}
            if tid:
                tracer.step(tid, "git_commit", f"commit failed: {err[:200]}")
            return {"committed": False, "sha": "", "reason": f"commit error: {err}"}

        # Get the short SHA of the new commit. Strip whitespace (the _git
        # runner already strips stdout, but be defensive — tests + real git
        # both produce clean SHAs, but trailing newlines are common).
        rc, out, err = _git(["rev-parse", "--short", "HEAD"], cwd)
        sha = out.strip() if rc == 0 else ""
        if tid:
            tracer.step(tid, "git_commit", f"committed {sha} @ {project_root}")
        return {"committed": True, "sha": sha}
    except Exception as e:
        if tid:
            tracer.step(tid, "git_commit", f"commit exception: {e}")
        return {"committed": False, "sha": "", "reason": f"error: {e}"}


def create_branch(project_root: str, branch: str, tid: str = "") -> bool:
    """Create and checkout a git branch via `git checkout -b`.

    Falls back to `git checkout <branch>` ONLY if `checkout -b` fails because
    the branch already exists. All other errors (dirty working tree, invalid
    branch name, no commits) are logged and returned as failures.

    Args:
        project_root: Path to the git repo. Converted to a `Path` for the
            `_git()` call (which expects `cwd: Path`).
        branch: Branch name to create + checkout.
        tid: Trace ID for observability (passed to `tracer.step`).

    Returns:
        True on success (created OR switched to existing), False on any failure.

    Traces via `tracer.step(tid, "git_branch", ...)` on every path.
    """
    if not project_root or not branch:
        if tid:
            tracer.step(
                tid, "git_branch",
                f"skipped — missing project_root={project_root!r} or branch={branch!r}",
            )
        return False

    cwd = Path(project_root)
    try:
        # `git checkout -b` creates AND switches in one step.
        rc, out, err = _git(["checkout", "-b", branch], cwd)
        if rc == 0:
            if tid:
                tracer.step(tid, "git_branch", f"created and switched to {branch} @ {project_root}")
            return True

        # Fall back to `git checkout <branch>` (switch only) ONLY when the
        # branch already exists. Match common git phrasings across versions
        # + platforms (some say "already exists", some say "already a worktree").
        combined = (out + " " + err).lower()
        if "already exists" in combined or "already a worktree" in combined:
            rc2, out2, err2 = _git(["checkout", branch], cwd)
            if rc2 == 0:
                if tid:
                    tracer.step(tid, "git_branch", f"switched to existing {branch} @ {project_root}")
                return True
            if tid:
                tracer.step(tid, "git_branch", f"checkout existing failed: {err2[:200]}")
            return False

        # Any other error: log and fail
        if tid:
            tracer.step(tid, "git_branch", f"failed to create {branch} @ {project_root}: {err[:200]}")
        return False
    except Exception as e:
        if tid:
            tracer.step(tid, "git_branch", f"branch exception: {e}")
        return False


def reset_hard(project_root: str, tid: str = "") -> bool:
    """Discard uncommitted changes via `git reset --hard HEAD` + `git clean -fd`.

    Includes a toplevel-verify safety check (qwen P1-4 / minimax B3 from the
    autoresearch v1.9 hardening pass — preserved in this consolidated helper):
    before resetting, runs `git rev-parse --show-toplevel` and verifies the
    returned path matches `Path(project_root).resolve()`. If they don't match
    (e.g. project_root is a junction/symlink to a different repo, or a
    subdirectory of another repo), the reset is refused + a tracer warning
    is logged + `False` is returned. Prevents accidentally nuking a DIFFERENT
    git repo's working tree.

    Args:
        project_root: Path to the git repo. Refused if empty.
        tid: Trace ID for observability.

    Returns:
        True on success, False on any failure (no project_root, toplevel
        mismatch, git command failure, exception).
    """
    if not project_root:
        if tid:
            tracer.warning(tid, "git_reset", "skipped — no project_root")
        return False

    cwd = Path(project_root)
    try:
        # Safety check: verify git toplevel matches project_root. Prevents
        # resetting a DIFFERENT repo when project_root is a junction/symlink
        # (Windows) or a subdirectory of another repo.
        rc, out, err = _git(["rev-parse", "--show-toplevel"], cwd)
        if rc != 0:
            if tid:
                tracer.warning(
                    tid, "git_reset",
                    f"git rev-parse --show-toplevel failed — skipping reset: {err[:200]}",
                )
            return False
        toplevel = out.strip()
        try:
            toplevel_resolved = Path(toplevel).resolve()
            project_root_resolved = Path(project_root).resolve()
        except Exception:
            if tid:
                tracer.warning(
                    tid, "git_reset",
                    f"path resolution failed — toplevel={toplevel!r}, project_root={project_root!r}",
                )
            return False
        if toplevel_resolved != project_root_resolved:
            if tid:
                tracer.warning(
                    tid, "git_reset",
                    f"toplevel mismatch: git says {toplevel!r}, project_root resolves to "
                    f"{str(project_root_resolved)!r} (possible symlink/junction to a "
                    f"different repo — refusing to nuke its working tree)",
                )
            return False

        # Toplevel verified — safe to reset.
        rc1, _, err1 = _git(["reset", "--hard", "HEAD"], cwd)
        if rc1 != 0:
            if tid:
                tracer.warning(tid, "git_reset", f"reset --hard failed: {err1[:200]}")
            return False
        rc2, _, err2 = _git(["clean", "-fd"], cwd)
        if rc2 != 0:
            if tid:
                tracer.warning(tid, "git_reset", f"clean -fd failed: {err2[:200]}")
            return False

        if tid:
            tracer.step(tid, "git_reset", f"reset hard + clean @ {project_root}")
        return True
    except Exception as e:
        if tid:
            tracer.warning(tid, "git_reset", f"reset exception: {e}")
        return False


__all__ = ["commit", "create_branch", "reset_hard"]
