"""
tools/git_ops.py - Git meta-tool.

Replaces: old git_ops.py (hardcoded D:\\mcp\\python-tool) + @cyanheads/git-mcp-server
          for the most common operations inside the agent workflow.
The LLM sees ONE tool: git(operation, ...)

Operations:
  snapshot  - stage all + commit (creates safe rollback point before changes)
  commit    - stage all + commit after successful change
  rollback  - hard reset to HEAD (undo all uncommitted changes)
  log       - recent commit history
  status    - current working tree status
  diff      - show unstaged diff

Key fixes over old git_ops.py:
  - No FORBIDDEN_TOKENS check on git commands (that was a bug - blocked valid commit messages)
  - Paths use pathlib throughout
  - root parameter: "workspace" | "agent" | any absolute path string
  - Works on both Windows and Linux
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import cfg
from registry import tool


# -- Git runner ----------------------------------------------------------------

def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """
    Run a git command in the given directory.
    Returns (returncode, stdout, stderr). Never raises.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "git not found on PATH - install Git"
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out after 30s"
    except Exception as e:
        return -1, "", str(e)


def _resolve_root(root_str: str) -> tuple[Optional[Path], str]:
    """
    Resolve root parameter to an absolute Path.
    root: "workspace" | "agent" | absolute path string
    Returns (path, error).
    """
    if root_str == "workspace":
        return cfg.workspace_root, ""
    if root_str == "agent":
        return cfg.agent_root, ""

    p = Path(root_str)
    if not p.is_absolute():
        return None, f"root must be 'workspace', 'agent', or an absolute path. Got: '{root_str}'"
    if not p.exists():
        return None, f"root path does not exist: {p}"
    return p, ""


def _check_repo(cwd: Path) -> tuple[bool, str]:
    """
    Check whether cwd is inside a git repository.
    Returns (is_repo, error_message).
    Does NOT auto-initialise -- use git(operation="init") explicitly.
    workspace/ is intentionally NOT auto-inited: it is a container for
    multiple independent project repos, not a repo itself.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"], cwd)
    if code == 0:
        return True, ""
    return False, (
        f"'{cwd}' is not a git repository. "
        "Use git(operation='init', root=...) to initialise, "
        "or point root at a project subfolder that already has a repo."
    )


# -- Meta-tool -----------------------------------------------------------------

@tool
def git(
    operation: str,
    message:   str = "",
    root:      str = "workspace",
    n:         int = 10,
    path:      str = "",
) -> dict:
    """
    Git version control operations.

    operation: "init" | "snapshot" | "commit" | "rollback" | "log" | "status" | "diff"

    init
        Initialise a new git repository in the target directory.
        Creates a .gitignore and an initial commit automatically.
        Call this once when starting a new project folder.
        Will error if the directory is already a git repo.
        Optional: root
        Returns:  {status, path, commit_hash}

    snapshot
        Stage all changes and create a timestamped commit.
        Call BEFORE making any automated changes - creates a safe rollback point.
        Optional: message (appended to timestamp), root
        Returns:  {commit_hash, message, status}

    commit
        Stage all changes and commit with a message.
        Call AFTER successful automated changes.
        Required: message
        Optional: root
        Returns:  {commit_hash, status}

    rollback
        Hard reset to HEAD - discards ALL uncommitted changes.
        Call when a patch or edit fails testing.
        Also cleans untracked files created by failed changes.
        Optional: root
        Returns:  {head, status}

    log
        Show recent commit history.
        Optional: n (number of commits, default 10), root
        Returns:  {commits: [{hash, date, message}], count}

    status
        Show current working tree status (modified, added, deleted files).
        Optional: root
        Returns:  {changes: [{flag, file}], clean, head}

    diff
        Show unstaged diff. Optional: path (specific file), root
        Returns:  {diff, has_changes}

    root parameter:
        "workspace"     - D:/mcp/workspace  (default, for work output)
        "agent"         - D:/mcp/agent      (for agent code changes)
        "/absolute/path" - any absolute path

    Examples:
        git(operation="snapshot", message="before editing memory.py")
        git(operation="commit",   message="fix: correct decay scoring in memory store")
        git(operation="rollback")
        git(operation="log",      n=5)
        git(operation="status")
        git(operation="diff",     path="tools/memory_tool.py")
        git(operation="snapshot", root="agent")
    """
    operation = operation.strip().lower()

    cwd, err = _resolve_root(root)
    if err:
        return {"status": "error", "error": err}

    # -- init ----------------------------------------------------------------
    if operation == "init":
        ok, _ = _check_repo(cwd)
        if ok:
            _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
            return {
                "status": "already_a_repo",
                "path":   str(cwd),
                "head":   head,
                "note":   "Directory is already a git repository",
            }

        code, _, err = _git(["init"], cwd)
        if code != 0:
            return {"status": "error", "error": f"git init failed: {err}"}

        # Create sensible .gitignore
        gi = cwd / ".gitignore"
        if not gi.exists():
            gi.write_text(
                "__pycache__/\n*.pyc\n*.pyo\n*.bak\n"
                ".env\nlogs/\n*.db\n*.lock\n",
                encoding="utf-8",
            )

        _git(["add", "-A"], cwd)
        code, _, err = _git(
            ["commit", "-m", "initial commit",
             "--author", "agent <agent@local>"],
            cwd,
        )
        if code != 0 and "nothing to commit" not in err:
            return {"status": "error", "error": f"Initial commit failed: {err}"}

        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status":      "initialised",
            "path":        str(cwd),
            "commit_hash": head,
        }

    # -- snapshot -------------------------------------------------------------
    if operation == "snapshot":
        ok, err = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err}

        ts       = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_msg = f"snapshot [{ts}]" + (f": {message}" if message else "")

        _git(["add", "-A"], cwd)

        code, porcelain, _ = _git(["status", "--porcelain"], cwd)
        if not porcelain:
            _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
            return {
                "status":      "nothing_to_commit",
                "commit_hash": head,
                "message":     full_msg,
                "root":        str(cwd),
            }

        code, _, err = _git(
            ["commit", "-m", full_msg, "--author", "agent <agent@local>"], cwd
        )
        if code != 0:
            return {"status": "error", "error": f"Snapshot commit failed: {err}"}

        _, hash_, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {"status": "committed", "commit_hash": hash_, "message": full_msg, "root": str(cwd)}

    # -- commit ----------------------------------------------------------------
    if operation == "commit":
        if not message:
            return {"status": "error", "error": "message is required for commit"}

        ok, err = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err}

        _git(["add", "-A"], cwd)

        code, _, err = _git(
            ["commit", "-m", message, "--author", "agent <agent@local>"], cwd
        )
        if code != 0:
            if "nothing to commit" in err:
                _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
                return {"status": "nothing_to_commit", "commit_hash": head}
            return {"status": "error", "error": err}

        _, hash_, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {"status": "committed", "commit_hash": hash_, "root": str(cwd)}

    # -- rollback --------------------------------------------------------------
    if operation == "rollback":
        code, _, err = _git(["reset", "--hard", "HEAD"], cwd)
        if code != 0:
            return {"status": "error", "error": f"git reset failed: {err}"}

        # Remove untracked files too
        _git(["clean", "-fd"], cwd)

        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status":  "rolled_back",
            "head":    head,
            "message": "Working tree reset to HEAD - all uncommitted changes discarded",
            "root":    str(cwd),
        }

    # -- log -------------------------------------------------------------------
    if operation == "log":
        code, out, err = _git(
            ["log", f"--max-count={n}", "--pretty=format:%h|%ai|%s"], cwd
        )
        if code != 0:
            return {"status": "error", "error": err or "No commits yet"}

        commits = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})

        return {"status": "ok", "commits": commits, "count": len(commits), "root": str(cwd)}

    # -- status ----------------------------------------------------------------
    if operation == "status":
        code, out, err = _git(["status", "--short"], cwd)
        if code != 0:
            return {"status": "error", "error": err}

        changes = []
        for line in out.splitlines():
            if len(line) >= 3:
                changes.append({"flag": line[:2].strip(), "file": line[3:]})

        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status":  "ok",
            "head":    head,
            "changes": changes,
            "clean":   len(changes) == 0,
            "count":   len(changes),
            "root":    str(cwd),
        }

    # -- diff ------------------------------------------------------------------
    if operation == "diff":
        args = ["diff"]
        if path:
            p = Path(path)
            if not p.is_absolute():
                p = cwd / path
            args.append(str(p))

        code, out, err = _git(args, cwd)
        if code != 0:
            return {"status": "error", "error": err}

        return {
            "status":      "ok",
            "diff":        out[:10_000] if out else "",
            "has_changes": bool(out),
            "root":        str(cwd),
        }

    return {
        "status": "error",
        "error":  f"Unknown operation '{operation}'. Use: init | snapshot | commit | rollback | log | status | diff",
    }
