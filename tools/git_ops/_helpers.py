"""Shared helpers used by all git operation plugins."""

from __future__ import annotations

import subprocess
import sys
import shutil
import os
from pathlib import Path
from typing import Optional

from core.config import cfg


# ---------------------------------------------------------------------------
# Git executable detection
# ---------------------------------------------------------------------------

def _get_git_exe() -> str:
    """
    Return absolute path to git executable.

    WHY: On Windows, git is often NOT in the MCP server process's PATH even
    though it works in a terminal (terminal sets PATH from registry; MCP server
    inherits a minimal service PATH). shutil.which() covers the normal case;
    the candidate list covers the "service PATH is stripped" case.
    """
    git_path = shutil.which("git")
    if git_path:
        return git_path

    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\Git\bin\git.exe"),
            os.path.expandvars(r"%ProgramFiles%\Git\bin\git.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Git\bin\git.exe"),
        ]
        for cand in candidates:
            p = Path(cand)
            if p.exists():
                return str(p)

    # Last resort
    return "git"


GIT_EXE = _get_git_exe()


# ---------------------------------------------------------------------------
# Subprocess environment
# ---------------------------------------------------------------------------

_GIT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT":   "0",
    "GIT_ASKPASS":           "echo",
    "GIT_SSH_COMMAND":       "ssh -o BatchMode=yes -o StrictHostKeyChecking=no",
    "GIT_AUTHOR_NAME":       "agent",
    "GIT_AUTHOR_EMAIL":      "agent@local",
    "GIT_COMMITTER_NAME":    "agent",
    "GIT_COMMITTER_EMAIL":   "agent@local",
}

_POPEN_FLAGS: dict = {}
if sys.platform == "win32":
    _POPEN_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW


# ---------------------------------------------------------------------------
# Core git runner
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """
    Run a git command in cwd. Returns (returncode, stdout, stderr). Never raises.

    Key safety properties:
    - stdin=DEVNULL
    - GIT_TERMINAL_PROMPT=0
    - CREATE_NO_WINDOW on Windows
    - timeout=15s
    """
    try:
        result = subprocess.run(
            [GIT_EXE] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            env=_GIT_ENV,
            stdin=subprocess.DEVNULL,
            timeout=15,
            **_POPEN_FLAGS,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"git not found (tried: {GIT_EXE}) -- install Git and ensure it is in PATH"
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out after 15s (possible index lock or network hang)"
    except Exception as e:
        return -1, "", str(e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_root(root_str: str, path_str: str = "") -> tuple[Optional[Path], str]:
    """
    Resolve the repo directory from the root (and optional path alias) parameters.
    """
    if root_str == "workspace" and path_str:
        p_candidate = Path(path_str)
        if p_candidate.is_absolute() and p_candidate.is_dir():
            root_str = path_str

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
    Verify cwd is inside a git repo. Only called before write operations.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"], cwd)
    if code == 0:
        return True, ""
    return False, (
        f"'{cwd}' is not a git repository. "
        "Use git(operation='init', root=...) to initialise one, "
        "or point root at a subdirectory that already has a repo."
    )