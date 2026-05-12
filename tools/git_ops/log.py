"""Log – show recent commit history."""

from ._base import register_git
from ._helpers import _git

HELP_LOG = """\
log
    Recent commit history.
    Optional: n (default 10), root
    Returns: {commits: [{hash, date, message}], count}
"""

@register_git(
    name="log",
    help_text=HELP_LOG,
    needs_repo=False,
    examples=[
        "git(operation=\"log\")        # last 10 commits",
        "git(operation=\"log\", n=5)   # last 5 commits",
    ],
)
def run_log(cwd, n: int = 10, **kwargs) -> dict:
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