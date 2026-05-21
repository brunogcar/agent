"""
actions package — Individual action handlers for cli meta-tool.

Each module in this package provides action handlers for a specific tool domain.
All handlers are imported by tools/cli.py via the DISPATCH dict.
"""

from tools.cli_ops.actions.lms import (
    _lms_ls, _lms_ps, _lms_load, _lms_unload, _lms_log
)
from tools.cli_ops.actions.file import _file
from tools.cli_ops.actions.git import _git
from tools.cli_ops.actions.web import _web
from tools.cli_ops.actions.memory import _memory
from tools.cli_ops.actions.python import _python
from tools.cli_ops.actions.notify import _notify
from tools.cli_ops.actions.skill import _skill_call

# Whitelist: only these (tool_name:action) pairs can execute
DISPATCH: dict[str, Any] = {
    "file:read":     lambda **kw: _file("read",    **kw),
    "file:write":    lambda **kw: _file("write",   **kw),
    "file:list":     lambda **kw: _file("list",    **kw),
    "file:patch":    lambda **kw: _file("patch",   **kw),
    "file:search":   lambda **kw: _file("search",  **kw),
    "file:backup":   lambda **kw: _file("backup",  **kw),
    "git:status":    lambda **kw: _git("status",   **kw),
    "git:log":       lambda **kw: _git("log",      **kw),
    "git:diff":      lambda **kw: _git("diff",     **kw),
    "git:snapshot":  lambda **kw: _git("snapshot", **kw),
    "git:commit":    lambda **kw: _git("commit",   **kw),
    "git:rollback":  lambda **kw: _git("rollback", **kw),
    "web:search":    lambda **kw: _web("search",   **kw),
    "web:scrape":    lambda **kw: _web("scrape",   **kw),
    "web:read":      lambda **kw: _web("read",     **kw),
    "memory:recall": lambda **kw: _memory("recall",**kw),
    "memory:store":  lambda **kw: _memory("store", **kw),
    "memory:stats":  lambda **kw: _memory("stats"),
    "memory:prune":  lambda **kw: _memory("prune"),
    "python:run":    lambda **kw: _python(kw.get("code",""), mode="run"),
    "python:calc":   lambda **kw: _python(kw.get("code",""), mode="run"),
    "python:data":   lambda **kw: _python(kw.get("code",""), mode="run_data"),
    "notify:send":   lambda **kw: _notify(kw.get("message","")),
    "lms:ls":        lambda **kw: _lms_ls(),
    "lms:ps":        lambda **kw: _lms_ps(),
    "lms:load":      lambda **kw: _lms_load(kw.get("model","")),
    "lms:unload":    lambda **kw: _lms_unload(kw.get("model","")),
    "lms:log":       lambda **kw: _lms_log(),
    "skill:call":    lambda **kw: _skill_call(kw.get("domain",""), kw.get("mode",""), kw.get("arg","")),
    "system:health": lambda **kw: "MCP Agent Stack: all systems operational.",
    "system:help":   lambda **kw: (
        "cli quick commands:\n"
        "  git status | log [n] | diff | snapshot [msg] | commit <msg> | rollback [--force]\n"
        "  file read <path> | write <path> <content> | list [dir] | search <query>\n"
        "  web search <query> | scrape <url> | read <url>\n"
        "  memory recall <query> | store <text> | stats | prune\n"
        "  python run <code> | calc <expr>\n"
        "  notify <message>\n"
        "  lms ls | ps | load <model> | unload [model] | log\n"
        "  skill <domain> <mode>  -- e.g. skill b3_api status | skill b3_api sync\n"
        "  health | help\n"
        "Shell (zero tokens, real output):\n"
        "  python <script.py> [args] | python --version | pip --version\n"
        "  whoami | hostname | where <cmd> | dir [path] | type <file>\n"
        "  copy <src> <dst> | move <src> <dst> | mkdir <dir> | del <file>\n"
        "Anything else -> Router decides: direct dispatch or Executor escalation."
    ),
}