"""
Shared helpers used by all git operation plugins.

This module centralizes all git-specific infrastructure to ensure consistent
behavior across all action handlers:
  - Git executable detection (handles Windows service PATH limitations)
  - Subprocess environment (suppresses prompts, sets safe defaults)
  - Cross-platform subprocess flags (CREATE_NO_WINDOW on Windows)
  - Core command runner (_git) with timeout and error isolation
  - Root resolution & repository validation

All helpers are stateless except for the cached git executable path, which is
resolved once at import time for performance.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
from core.config import cfg

# ─────────────────────────────────────────────────────────────────────────────
# 1. Git Executable Detection
# ─────────────────────────────────────────────────────────────────────────────
def _get_git_exe() -> str:
    """
    Return absolute path to git executable, handling Windows service PATH limitations.

    WHY: On Windows, git is often NOT in the MCP server process's PATH even
    though it works in a terminal. Terminal inherits registry PATH; MCP server
    inherits a minimal service PATH. shutil.which() covers the normal case;
    the candidate list covers the "service PATH is stripped" edge case.

    Returns:
        str: Absolute path to git.exe or fallback "git" string.
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

    # Last resort: rely on system PATH at runtime
    return "git"

# Resolve once at import time for performance
GIT_EXE: str = _get_git_exe()

# ─────────────────────────────────────────────────────────────────────────────
# 2. Subprocess Environment & Flags
# ─────────────────────────────────────────────────────────────────────────────
_GIT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "echo",
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=no",
    "GIT_AUTHOR_NAME": "agent",
    "GIT_AUTHOR_EMAIL": "agent@local",
    "GIT_COMMITTER_NAME": "agent",
    "GIT_COMMITTER_EMAIL": "agent@local",
}

_POPEN_FLAGS: dict = {}
if sys.platform == "win32":
    _POPEN_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW

# ─────────────────────────────────────────────────────────────────────────────
# 3. Core Git Runner
# ─────────────────────────────────────────────────────────────────────────────
def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """
    Run a git command in cwd. Returns (returncode, stdout, stderr). Never raises.

    Key safety properties:
      - stdin=DEVNULL (prevents blocking on interactive input)
      - GIT_TERMINAL_PROMPT=0 (fails fast on auth/network issues)
      - CREATE_NO_WINDOW on Windows (clean background execution)
      - timeout=15s (prevents hangs from locked repos or bad remotes)

    Args:
        args (list[str]): Git command arguments (e.g., ["status", "--porcelain"])
        cwd (Path): Working directory for the command.

    Returns:
        tuple[int, str, str]: (returncode, stdout_stripped, stderr_stripped)
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

# ─────────────────────────────────────────────────────────────────────────────
# 4. Path & Repo Resolution
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_root(root_str: str, path_str: str = "") -> tuple[Optional[Path], str]:
    """
    Resolve the repo directory from the root (and optional path alias) parameters.

    Logic:
      - "agent"      → cfg.agent_root
      - "workspace"  → cfg.workspace_root
      - absolute dir → used as-is (validated)
      - relative dir → rejected (must be explicit)

    Backward-Compat Alias:
      If root="workspace" and path_str is an absolute existing directory,
      the function overrides root_str with path_str. This preserves legacy
      prompts that pass an absolute path via the `path=` parameter.

    Args:
        root_str (str): "agent", "workspace", or absolute path.
        path_str (str): Optional backward-compat alias for absolute repo path.

    Returns:
        tuple[Path | None, str]: (resolved_cwd, error_message)
    """
    # Backward-compat alias handling
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
    Verify cwd is inside a git repo. Only called before write/modify operations.

    Args:
        cwd (Path): Directory to validate.

    Returns:
        tuple[bool, str]: (is_valid_repo, error_message)
    """
    code, _, _ = _git(["rev-parse", "--git-dir"], cwd)
    if code == 0:
        return True, ""
    return False, (
        f"'{cwd}' is not a git repository. "
        "Use git(operation='init', root=...) to initialise one, "
        "or point root at a subdirectory that already has a repo."
    )