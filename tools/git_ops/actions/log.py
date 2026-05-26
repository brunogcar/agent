"""
Log – show recent commit history.

Returns recent commit history with hash, date, and message.
Read-only action; safely handles empty repositories.
"""
from tools.git_ops._registry import register_action
from tools.git_ops.helpers import _git

HELP_LOG = """
log
Recent commit history.
Optional: n (default 10), root
Returns: {commits: [{hash, date, message}], count}
"""

@register_action(
    "git", "log",
    help_text=HELP_LOG,
    needs_repo=False,
    examples=[
        'git(action="log")        # last 10 commits',
        'git(action="log", n=5)   # last 5 commits',
    ],
)
def run_log(cwd, n: int = 10, **kwargs) -> dict:
    """Show recent commit history. Optional: n (default 10), root."""
    code, out, err = _git(
        ["log", f"--max-count={n}", "--pretty=format:%h|%ai|%s"],
        cwd,
    )
    if code != 0:
        return {"status": "error", "error": err or "No commits yet (empty repo?)"}
    
    commits = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})

    return {"status": "ok", "commits": commits, "count": len(commits), "root": str(cwd)}