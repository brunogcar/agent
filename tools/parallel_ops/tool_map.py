"""Tool registry for parallel execution.

Maps tool names to their callable functions. Lazy imports for tools
that might not be installed or might cause circular imports.

[DESIGN] WHY LAZY IMPORTS: importing all 16 tools at module load time
would (a) slow startup, (b) trigger circular imports (parallel is itself
a tool), and (c) pull in optional dependencies (Playwright, ChromaDB,
tavily async client) that may not be installed in every environment.

We keep _TOOL_MAP values as None until first use, then cache the resolved
callable. Subsequent calls hit the cache without re-importing.

NOTE on `python_exec`: alias for `python` (kept for backwards-compat with
callers that used the older name). Both resolve to tools.python.python.
"""
from __future__ import annotations
from typing import Any, Callable, Optional

# Tools that are safe to run in parallel (no shared mutable state, no
# process-level resources, no internal threading that could deadlock).
PARALLEL_SAFE = frozenset({
    "web", "file", "python", "python_exec", "notify", "github",
    "consult", "vision", "report", "agent",
})

# Explicit mapping — no runtime discovery (avoids importing all tools at startup)
# All values start as None (lazy). _get_tool_fn() resolves and caches on first use.
_TOOL_MAP: dict[str, Optional[Callable]] = {
    "web": None,           # lazy
    "git": None,           # lazy — NOT parallel-safe (shared git state)
    "file": None,          # lazy
    "python": None,        # lazy
    "python_exec": None,   # alias for python
    "notify": None,        # lazy
    "memory": None,        # lazy — NOT parallel-safe (ChromaDB SQLite)
    "cli": None,           # lazy — NOT parallel-safe (shared shell)
    "github": None,        # lazy
    "consult": None,       # lazy
    "vision": None,        # lazy
    "report": None,        # lazy
    "agent": None,         # lazy
    "browser": None,       # lazy — NOT parallel-safe (Playwright session)
    "tavily": None,        # lazy — NOT parallel-safe (shared AsyncTavilyClient)
    "swarm": None,         # lazy — NOT parallel-safe (ThreadPoolExecutor internally)
    "workflow": None,      # lazy — NOT parallel-safe (long-running blocking calls)
    # NOTE: "parallel" intentionally omitted — nested parallel calls are
    # blocked by _parallel_depth in executor.py, so it cannot be dispatched
    # to itself. Attempting it returns "Tool 'parallel' not found".
}


def _get_tool_fn(name: str) -> Optional[Callable]:
    """Get a tool function by name, lazy-importing as needed.

    Returns None if the tool name is unknown or the tool module cannot be
    imported (caller decides how to surface the error).

    Caches the resolved callable back into _TOOL_MAP so subsequent lookups
    are zero-cost. Thread-safe under the GIL — worst case two threads race
    to import the same module; the second overwrites the cache with the
    same value, no corruption.
    """
    if name not in _TOOL_MAP:
        return None

    # Check if already imported (cached)
    fn = _TOOL_MAP[name]
    if fn is not None:
        return fn

    # Lazy import based on tool name. Each branch assigns `fn` so the
    # post-branch cache write works uniformly.
    if name == "web":
        from tools.web import web as fn
    elif name == "git":
        from tools.git import git as fn
    elif name == "file":
        from tools.file import file as fn
    elif name == "python":
        from tools.python import python as fn
    elif name == "python_exec":
        from tools.python import python as fn
    elif name == "notify":
        from tools.notify import notify as fn
    elif name == "memory":
        from tools.memory import memory as fn
    elif name == "cli":
        from tools.cli import cli as fn
    elif name == "github":
        from tools.github import github as fn
    elif name == "consult":
        from tools.consult import consult as fn
    elif name == "vision":
        from tools.vision import vision as fn
    elif name == "report":
        from tools.report import report as fn
    elif name == "agent":
        from tools.agent import agent as fn
    elif name == "browser":
        from tools.browser import browser as fn
    elif name == "tavily":
        from tools.tavily import tavily as fn
    elif name == "swarm":
        from tools.swarm import swarm as fn
    elif name == "workflow":
        from tools.workflow import workflow as fn
    else:
        return None

    _TOOL_MAP[name] = fn  # cache for subsequent calls
    return fn
