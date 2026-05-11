"""
tools/git_ops.py - Git meta-tool for the MCP agent.

Replaces: old git_ops.py (hardcoded D:\\mcp\\python-tool) + @cyanheads/git-mcp-server
          for the most common operations inside the agent workflow.
The LLM sees ONE tool: git(operation, ...)

Operations:
  init      - initialise a new git repo + initial commit + .gitignore
  snapshot  - stage all + timestamped commit (safe rollback point before changes)
  commit    - stage all + commit after successful change
  rollback  - hard reset to HEAD (undo all uncommitted changes)
  log       - recent commit history
  status    - current working tree status
  diff      - show unstaged diff
  branch    - list branches: message="list"
  checkout  - switch branches or commits: message="target_branch_or_commit"
  restore   - restore files from a specific commit: message="target_commit"
  tag       - create or list tags: message="list" or "tag_name"
  show      - show commit details: message="commit_hash"

--- ARCHITECTURE DECISIONS (read before touching this file) ---

DECISION 1: path alias -> root
  Agents (and Claude) sometimes call git(operation="status", path="D:/mcp/agent")
  because they see "path" in the diff operation and assume it's the repo directory.
  root is the correct parameter, but we alias path->root when root=="workspace"
  AND path looks like an absolute directory path, to avoid silent wrong-repo bugs.
  This was the PRIMARY cause of MCP timeout: git ran on workspace/ (no repo) instead
  of agent/ (has repo), causing _check_repo() to spin on rev-parse with no .git.

DECISION 2: Remove redundant _check_repo() pre-flight from read-only ops
  status/log/diff called _check_repo() (one subprocess) THEN the actual command
  (another subprocess). On Windows, each subprocess.run() costs ~200-500ms spawn
  time. Two subprocesses = 400-1000ms just in overhead. Multiply by 4 for snapshot
  (check + add + status --porcelain + commit) = easily 2-4s overhead alone.
  FIX: skip _check_repo() for status/log/diff. Let git itself return "not a repo"
  error -- the error message is equally useful and we save one round-trip.
  Keep _check_repo() only for write ops (snapshot/commit/rollback) where we want
  a clean error before touching the working tree.

DECISION 3: Per-subprocess timeout = 15s (was 30s)
  MCP server kills the entire tool call after ~30s. If one subprocess uses
  the full 30s timeout, the chain (e.g. snapshot: add + status + commit) blows
  the MCP budget. 15s is generous for any local git operation; if git hangs for
  15s something is deeply wrong (index lock, credential prompt, etc.).

DECISION 4: CREATE_NO_WINDOW on Windows
  Without this flag, git spawns a hidden console window (Win32 subsystem quirk).
  That console window can block if git tries to write to it. More critically,
  it inherits the parent process's stdin, which on an MCP server is the JSON-RPC
  pipe -- git reading from stdin causes a deadlock that looks like a timeout.
  subprocess.DEVNULL for stdin + CREATE_NO_WINDOW together prevent this.

DECISION 5: stdin=DEVNULL always
  Any git operation that tries to read from stdin (credential prompts, merge
  conflict editors, etc.) will block the subprocess forever unless stdin is
  closed. We set stdin=DEVNULL unconditionally. GIT_TERMINAL_PROMPT=0 is the
  git-level guard; DEVNULL is the OS-level guard. Belt + suspenders.

DECISION 6: GIT_TERMINAL_PROMPT=0 on Windows via _GIT_ENV
  The old code skipped env override on Windows to preserve PATH. But we already
  use an absolute git path (GIT_EXE), so we don't need PATH for git. We can
  safely set GIT_TERMINAL_PROMPT=0 on Windows too, preventing any credential
  prompt from blocking the subprocess. We still inherit **os.environ so other
  vars (USERPROFILE, APPDATA, etc.) remain available.

DECISION 7: root="agent" default for status/log/diff
  The most common agent use-case is inspecting the agent repo itself.
  workspace/ is intentionally NOT a git repo (it's a container for multiple
  independent project repos). Defaulting to "workspace" for read ops causes
  "not a repo" errors. Default kept as "workspace" for write ops (snapshot/commit)
  to match autocode.py expectations, but document this clearly.

DECISION 8: No auto-init
  workspace/ is NOT auto-inited because it holds multiple independent project repos.
  git(operation='init') must be called explicitly. This prevents accidentally
  creating a monorepo wrapper around the workspace container.
"""

from __future__ import annotations

import subprocess
import sys
import shutil
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import cfg
from registry import tool


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

    # Last resort -- if this fails, error message in _git() will explain why
    return "git"


GIT_EXE = _get_git_exe()


# ---------------------------------------------------------------------------
# Subprocess environment
# ---------------------------------------------------------------------------

# WHY: We set GIT_TERMINAL_PROMPT=0 on ALL platforms now (see DECISION 6).
# We inherit os.environ so USERPROFILE, APPDATA, etc. are available to git
# for reading global .gitconfig. Only adding/overriding, never wiping.
#
# DECISION 9: Identity via env vars, NOT -c flags
#   The old approach passed -c user.name=agent -c user.email=agent@local on the
#   commit command line. This breaks on newer git versions (2.39+) on Windows:
#   "fatal: options '-m' and '-c' cannot be used together"
#   The correct, version-agnostic way is GIT_AUTHOR_*/GIT_COMMITTER_* env vars.
#   These are honoured by all git versions and take priority over .gitconfig.
#   This also removes two args from every commit call, slightly reducing subprocess
#   overhead and eliminating the version-specific flag interaction entirely.
_GIT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT":   "0",       # prevents credential prompts (git-level guard)
    "GIT_ASKPASS":           "echo",    # non-interactive askpass fallback
    "GIT_SSH_COMMAND":       "ssh -o BatchMode=yes -o StrictHostKeyChecking=no",
    # Identity -- set here so commit never needs -c user.name/email on cmdline
    "GIT_AUTHOR_NAME":       "agent",
    "GIT_AUTHOR_EMAIL":      "agent@local",
    "GIT_COMMITTER_NAME":    "agent",
    "GIT_COMMITTER_EMAIL":   "agent@local",
}

# Extra subprocess flags for Windows (see DECISION 4)
_POPEN_FLAGS: dict = {}
if sys.platform == "win32":
    _POPEN_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW


# ---------------------------------------------------------------------------
# Core git runner
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """
    Run a git command in cwd. Returns (returncode, stdout, stderr). Never raises.

    Key safety properties (see DECISIONS 3-6 in module docstring):
    - stdin=DEVNULL: prevents blocking on credential/merge prompts (OS-level)
    - GIT_TERMINAL_PROMPT=0: prevents blocking at git level
    - CREATE_NO_WINDOW: prevents Win32 console window blocking MCP stdio pipe
    - timeout=15: keeps total chain within MCP's ~30s budget
    """
    try:
        result = subprocess.run(
            [GIT_EXE] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            env=_GIT_ENV,
            stdin=subprocess.DEVNULL,   # DECISION 5: never read from MCP's stdin pipe
            timeout=15,                 # DECISION 3: 15s per command, not 30s
            **_POPEN_FLAGS,             # DECISION 4: CREATE_NO_WINDOW on Windows
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

    WHY path_str alias: agents frequently pass path="D:/mcp/agent" thinking it
    sets the working directory, because they see the diff operation's path param.
    When root is still the default ("workspace") and path_str is an absolute
    directory, we treat path_str as the intended root (DECISION 1).
    This avoids the silent "wrong repo" bug without breaking the diff use-case
    (diff passes path as a file path, which is never a bare drive root).
    """
    # Alias: if root is default and path looks like a directory, use it as root
    if root_str == "workspace" and path_str:
        p_candidate = Path(path_str)
        if p_candidate.is_absolute() and p_candidate.is_dir():
            root_str = path_str  # treat the path arg as the intended root

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

    WHY only write ops: status/log/diff skip this to save one subprocess call
    (DECISION 2). git itself returns a clear "not a git repository" error.
    We keep this guard for snapshot/commit/rollback so we fail cleanly before
    touching the working tree.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"], cwd)
    if code == 0:
        return True, ""
    return False, (
        f"'{cwd}' is not a git repository. "
        "Use git(operation='init', root=...) to initialise one, "
        "or point root at a subdirectory that already has a repo."
    )


# ---------------------------------------------------------------------------
# Meta-tool
# ---------------------------------------------------------------------------

@tool
def git(
    operation: str,
    message:   str  = "",
    root:      str  = "workspace",
    n:         int  = 10,
    path:      str  = "",
    force:     bool = False,
) -> dict:
    """
    Git version control operations.

    operation: "init" | "snapshot" | "commit" | "rollback" | "log" | "status" | "diff" | "branch" | "checkout" | "restore" | "tag" | "show"

    IMPORTANT - root vs path parameter:
      root  - the repo directory: "workspace" | "agent" | "/absolute/path"
              DEFAULT is "workspace". For agent code ops, pass root="agent".
      path  - ONLY used by diff to filter a specific file. NOT the repo directory.
              Exception: if you pass path="D:/mcp/agent" with root="workspace",
              the tool detects this and uses path as the root (backward-compat alias).

    init
        Initialise a new git repository. Creates .gitignore + initial commit.
        Call once when starting a new project folder. Errors if already a repo.
        Optional: root
        Returns: {status, path, commit_hash}

    snapshot
        Stage all + timestamped commit. Call BEFORE automated changes.
        Creates a safe rollback point. Returns nothing_to_commit if tree is clean.
        Optional: message (appended to timestamp), root
        Returns: {status: "committed"|"nothing_to_commit", commit_hash, message}

    commit
        Stage all + commit. Call AFTER successful automated changes.
        Required: message
        Optional: root
        Returns: {status: "committed"|"nothing_to_commit", commit_hash}

    rollback
        Reset to HEAD. Discards ALL uncommitted changes.
        Default (force=False): stashes changes first (recoverable via git stash pop).
        force=True: permanently discards changes + cleans untracked files.
        Optional: root, force
        Returns: {status, head, message, stash_ref}

    log
        Recent commit history.
        Optional: n (default 10), root
        Returns: {commits: [{hash, date, message}], count}

    status
        Working tree status. Tip: pass root="agent" to check agent repo.
        Optional: root
        Returns: {head, changes: [{flag, file}], clean, count}

    diff
        Unstaged diff. path filters to a specific file (relative or absolute).
        Optional: path (file to diff), root
        Returns: {diff, has_changes}

    branch
        Manage local branches. Branches allow isolating experimental work.
        Subcommands (via 'message' parameter):
          - list              (e.g. branch operation with no message)
          - create <name>     (e.g. message="create my-feature")
          - delete <name>     (e.g. message="delete old-branch") -- safe, only if merged
        Returns: {status, branches/created/deleted, ...}

    checkout
        Switch to a branch or commit. Can also create and switch in one step.
        Use 'message' to specify the target:
          - branch name       (e.g. checkout, message="main")
          - "-b new-branch"   (e.g. checkout, message="-b experiment")
        Returns: {status, to/branch, ...}

    restore
        Restore a specific file to HEAD (or a specified commit) discarding local changes.
        'path' parameter = file to restore (relative or absolute)
        'message' parameter = optional commit ref (e.g. "HEAD~2")
        Returns: {status, file, ...}

    tag
        List or create lightweight tags to mark milestones.
        Subcommands (via 'message'):
          - list              (default)
          - create <name>     (e.g. message="create v1.0")
        Returns: {status, tags/created, ...}

    show
        Show details of a commit, tag, or tree object.
        'message' = commit hash, tag name (default: "HEAD")
        Returns: {status, output (capped at 10KB), ...}
        

    Examples:
        git(operation="status",   root="agent")
        git(operation="log",      root="agent", n=5)
        git(operation="snapshot", root="agent", message="before editing memory.py")
        git(operation="commit",   root="agent", message="fix: correct decay scoring")
        git(operation="rollback", root="agent")
        git(operation="rollback", root="agent", force=True)
        git(operation="diff",     root="agent", path="tools/memory_tool.py")
        git(operation="snapshot")   # defaults to workspace

        git(operation="branch")                              # list local branches
        git(operation="branch", message="create experiment") # create branch "experiment"
        git(operation="branch", message="delete old-fix")    # delete merged branch "old-fix"
        git(operation="checkout", message="main")            # switch to main branch
        git(operation="checkout", message="-b new-idea")     # create and switch to "new-idea"
        git(operation="restore", path="tools/git_ops.py")    # restore file to HEAD
        git(operation="restore", path="README.md", message="HEAD~2") # restore from older commit
        git(operation="tag")                                 # list all tags
        git(operation="tag", message="create v1.0")          # create tag "v1.0"
        git(operation="show", message="HEAD")                # show latest commit details
        git(operation="show", message="abc1234")             # show specific commit
    """
    operation = operation.strip().lower()

    # DECISION 1: resolve root, with path alias for backward-compat
    cwd, err = _resolve_root(root, path)
    if err:
        return {"status": "error", "error": err}

    # -----------------------------------------------------------------------
    # init
    # -----------------------------------------------------------------------
    if operation == "init":
        # Check first: init on an existing repo is a no-op (not an error)
        ok, _ = _check_repo(cwd)
        if ok:
            _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
            return {
                "status": "already_a_repo",
                "path":   str(cwd),
                "head":   head,
                "note":   "Directory is already a git repository",
            }

        code, _, err2 = _git(["init"], cwd)
        if code != 0:
            return {"status": "error", "error": f"git init failed: {err2}"}

        gi = cwd / ".gitignore"
        if not gi.exists():
            # Standard ignores for this Python/MCP project stack
            gi.write_text(
                "__pycache__/\n*.pyc\n*.pyo\n*.bak\n"
                ".env\nlogs/\n*.db\n*.lock\n",
                encoding="utf-8",
            )

        _git(["add", "-A"], cwd)
        # Identity comes from _GIT_ENV (GIT_AUTHOR_*/GIT_COMMITTER_*) -- see DECISION 9
        code, _, err2 = _git(["commit", "-m", "initial commit"], cwd)
        if code != 0 and "nothing to commit" not in err2:
            return {"status": "error", "error": f"Initial commit failed: {err2}"}

        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {"status": "initialised", "path": str(cwd), "commit_hash": head}

    # -----------------------------------------------------------------------
    # snapshot
    # -----------------------------------------------------------------------
    if operation == "snapshot":
        # Keep _check_repo here: write op, want clean failure before touching tree
        ok, err2 = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err2}

        ts       = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_msg = f"snapshot [{ts}]" + (f": {message}" if message else "")

        _git(["add", "-A"], cwd)

        # Check if there's anything to commit AFTER staging
        _, porcelain, _ = _git(["status", "--porcelain"], cwd)
        if not porcelain:
            _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
            return {
                "status":      "nothing_to_commit",
                "commit_hash": head,
                "message":     full_msg,
                "root":        str(cwd),
            }

        # Identity comes from _GIT_ENV (GIT_AUTHOR_*/GIT_COMMITTER_*) -- see DECISION 9
        code, _, err2 = _git(["commit", "-m", full_msg], cwd)
        if code != 0:
            return {"status": "error", "error": f"Snapshot commit failed: {err2}"}

        _, hash_, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {"status": "committed", "commit_hash": hash_, "message": full_msg, "root": str(cwd)}

    # -----------------------------------------------------------------------
    # commit
    # -----------------------------------------------------------------------
    if operation == "commit":
        if not message:
            return {"status": "error", "error": "message is required for commit"}

        ok, err2 = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err2}

        _git(["add", "-A"], cwd)

        # Identity comes from _GIT_ENV (GIT_AUTHOR_*/GIT_COMMITTER_*) -- see DECISION 9
        code, _, err2 = _git(["commit", "-m", message], cwd)
        if code != 0:
            if "nothing to commit" in err2:
                _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
                return {"status": "nothing_to_commit", "commit_hash": head}
            return {"status": "error", "error": err2}

        _, hash_, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {"status": "committed", "commit_hash": hash_, "root": str(cwd)}

    # -----------------------------------------------------------------------
    # rollback
    # -----------------------------------------------------------------------
    if operation == "rollback":
        ok, err2 = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err2}

        if force:
            # Permanent discard -- used when stash is not wanted (e.g. failed autocode run)
            _git(["reset", "--hard", "HEAD"], cwd)
            _git(["clean", "-fd"], cwd)   # also removes untracked files
            _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
            return {
                "status":  "rolled_back",
                "head":    head,
                "message": "Force reset to HEAD (changes permanently discarded)",
                "root":    str(cwd),
            }

        # Safe path: stash changes first so they can be recovered
        # WHY stash instead of just reset: autocode.py may have written partial
        # changes that are valuable for debugging even after a test failure.
        import time as _t
        stash_msg = f"autocode-rollback-{int(_t.time())}"
        sr        = _git(["stash", "push", "-m", stash_msg], cwd)
        # sr[1] is stdout; "No local changes" means nothing was stashed
        stashed   = "No local changes" not in sr[1]

        code, _, err2 = _git(["reset", "--hard", "HEAD"], cwd)
        if code != 0:
            return {"status": "error", "error": f"git reset failed: {err2}"}

        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        msg = "Working tree reset to HEAD."
        if stashed:
            msg += f" Changes saved to stash '{stash_msg}' -- run 'git stash pop' to restore."
        return {
            "status":    "rolled_back",
            "head":      head,
            "message":   msg,
            "stash_ref": stash_msg if stashed else "",
            "root":      str(cwd),
        }

    # -----------------------------------------------------------------------
    # log
    # -----------------------------------------------------------------------
    if operation == "log":
        # DECISION 2: no _check_repo() here -- git log itself returns a clear error
        # if not in a repo, and we save one subprocess call (~200-500ms on Windows).
        code, out, err2 = _git(
            ["log", f"--max-count={n}", "--pretty=format:%h|%ai|%s"],
            cwd,
        )
        if code != 0:
            return {"status": "error", "error": err2 or "No commits yet (empty repo?)"}

        commits = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})

        return {"status": "ok", "commits": commits, "count": len(commits), "root": str(cwd)}

    # -----------------------------------------------------------------------
    # status
    # -----------------------------------------------------------------------
    if operation == "status":
        # DECISION 2: no _check_repo() pre-flight -- saves one subprocess.
        # git status --short already returns non-zero + clear message if not a repo.
        code, out, err2 = _git(["status", "--short"], cwd)
        if code != 0:
            return {"status": "error", "error": err2}

        changes = []
        for line in out.splitlines():
            if len(line) >= 3:
                changes.append({"flag": line[:2].strip(), "file": line[3:]})

        # Get HEAD separately; this will be empty string on an empty repo
        _, head, _ = _git(["rev-parse", "--short", "HEAD"], cwd)
        return {
            "status":  "ok",
            "head":    head,
            "changes": changes,
            "clean":   len(changes) == 0,
            "count":   len(changes),
            "root":    str(cwd),
        }

    # -----------------------------------------------------------------------
    # diff
    # -----------------------------------------------------------------------
    if operation == "diff":
        # DECISION 2: no _check_repo() pre-flight.
        args = ["diff"]
        # path here is a FILE path for filtering the diff (not the repo root)
        # _resolve_root() already consumed path if it looked like a directory root.
        # At this point, if path is set it must be a file path.
        if path:
            p = Path(path)
            if not p.is_absolute():
                p = cwd / path
            args.append(str(p))

        code, out, err2 = _git(args, cwd)
        if code != 0:
            return {"status": "error", "error": err2}

        return {
            "status":      "ok",
            "diff":        out[:10_000] if out else "",   # cap at 10KB to stay within MCP response limits
            "has_changes": bool(out),
            "root":        str(cwd),
        }

    # -------------------------------------------------------------------
    # branch (new)
    # -------------------------------------------------------------------
    if operation == "branch":
        # Subcommand is first word of message; rest is branch name.
        parts = message.strip().split(maxsplit=1) if message.strip() else []
        sub   = parts[0].lower() if parts else "list"
        name  = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            code, out, err2 = _git(["branch"], cwd)
            if code != 0:
                return {"status": "error", "error": err2}
            branches = []
            for line in out.splitlines():
                current = line.startswith("*")
                bname   = line[2:].strip()
                branches.append({"name": bname, "current": current})
            return {"status": "ok", "branches": branches, "root": str(cwd)}

        elif sub == "create":
            if not name:
                return {"status": "error", "error": "Branch name required (message='create <name>')"}
            ok, err2 = _check_repo(cwd)
            if not ok:
                return {"status": "error", "error": err2}
            code, _, err2 = _git(["branch", name], cwd)
            if code != 0:
                return {"status": "error", "error": err2}
            return {"status": "created", "branch": name, "root": str(cwd)}

        elif sub == "delete":
            if not name:
                return {"status": "error", "error": "Branch name required (message='delete <name>')"}
            ok, err2 = _check_repo(cwd)
            if not ok:
                return {"status": "error", "error": err2}
            # Safe delete: only if merged (-d). No --force.
            code, _, err2 = _git(["branch", "-d", name], cwd)
            if code != 0:
                return {"status": "error", "error": err2}
            return {"status": "deleted", "branch": name, "root": str(cwd)}

        else:
            return {"status": "error", "error": f"Unknown branch subcommand: '{sub}'. Use list, create <name>, delete <name>"}

    # -------------------------------------------------------------------
    # checkout (new)
    # -------------------------------------------------------------------
    if operation == "checkout":
        target = message.strip() if message else ""
        if not target:
            return {"status": "error", "error": "Branch or commit to checkout is required (message param)"}

        ok, err2 = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err2}

        # Support "checkout -b newbranch" shorthand via message = "-b newbranch"
        if target.startswith("-b"):
            parts = target.split(maxsplit=1)
            if len(parts) < 2:
                return {"status": "error", "error": "Branch name required after -b"}
            branch_name = parts[1].strip()
            code, _, err2 = _git(["checkout", "-b", branch_name], cwd)
            if code != 0:
                return {"status": "error", "error": err2}
            return {"status": "switched", "branch": branch_name, "root": str(cwd)}

        code, _, err2 = _git(["checkout", target], cwd)
        if code != 0:
            return {"status": "error", "error": err2}
        return {"status": "switched", "to": target, "root": str(cwd)}

    # -------------------------------------------------------------------
    # restore (new)
    # -------------------------------------------------------------------
    if operation == "restore":
        if not path:
            return {"status": "error", "error": "File path is required (use the 'path' parameter)"}

        ok, err2 = _check_repo(cwd)
        if not ok:
            return {"status": "error", "error": err2}

        # Resolve file path relative to cwd if not absolute
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = cwd / path

        args = ["restore"]
        # Optional source (commit) from `message`
        if message.strip():
            args.append(f"--source={message.strip()}")
        args.append(str(file_path))

        code, _, err2 = _git(args, cwd)
        if code != 0:
            return {"status": "error", "error": err2}
        return {"status": "restored", "file": str(file_path), "root": str(cwd)}

    # -------------------------------------------------------------------
    # tag (new)
    # -------------------------------------------------------------------
    if operation == "tag":
        parts = message.strip().split(maxsplit=1) if message.strip() else []
        sub   = parts[0].lower() if parts else "list"
        name  = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            code, out, err2 = _git(["tag", "-l"], cwd)
            if code != 0:
                return {"status": "error", "error": err2}
            tags = [t.strip() for t in out.splitlines() if t.strip()]
            return {"status": "ok", "tags": tags, "root": str(cwd)}

        elif sub == "create":
            if not name:
                return {"status": "error", "error": "Tag name required (message='create <name>')"}
            ok, err2 = _check_repo(cwd)
            if not ok:
                return {"status": "error", "error": err2}
            code, _, err2 = _git(["tag", name], cwd)
            if code != 0:
                return {"status": "error", "error": err2}
            return {"status": "created", "tag": name, "root": str(cwd)}

        else:
            return {"status": "error", "error": f"Unknown tag subcommand: '{sub}'. Use list, create <name>"}

    # -------------------------------------------------------------------
    # show (new)
    # -------------------------------------------------------------------
    if operation == "show":
        target = message.strip() if message.strip() else "HEAD"
        code, out, err2 = _git(["show", target], cwd)
        if code != 0:
            return {"status": "error", "error": err2}
        # Cap output to 10KB like diff
        return {"status": "ok", "output": out[:10_000], "root": str(cwd)}

    # -----------------------------------------------------------------------
    # unknown operation
    # -----------------------------------------------------------------------
    return {
        "status": "error",
        "error":  (
            f"Unknown operation '{operation}'. "
            "Valid: init | snapshot | commit | rollback | log | status | diff"
        ),
    }

# ---------------------------------------------------------------------------
# Commands intentionally excluded from the git meta‑tool
# ---------------------------------------------------------------------------
#
# The following operations are NOT exposed to the autonomous agent because they
# either involve remote repositories, are destructive to shared history, or
# require human judgement for conflict resolution:
#
#   fetch       – touches a remote; can update remote‑tracking branches and
#                 potentially introduce unwanted refs. The agent runs in an
#                 isolated, local‑first environment and does not need remote
#                 awareness by default.
#
#   pull        – fetch + merge. Combines network access with automatic
#                 merging that can produce conflicts. Unsuitable for
#                 unsupervised execution.
#
#   merge       – joins two branches. May create merge conflicts that the
#                 agent cannot resolve reliably. Branch‑per‑feature with
#                 explicit commits is preferred.
#
#   rebase      – rewrites commit history. Extremely dangerous for an
#                 autonomous agent; can lose work or corrupt the timeline.
#
#   push        – sends local commits to a remote. Explicitly excluded to
#                 maintain the agent's local‑only boundary.
#
# If a future use case requires any of these (e.g., a fully‑automated CI
# pipeline), add them behind a `allow_remote=True` flag and enforce
# additional safety guards (authentication, conflict detection, etc.).