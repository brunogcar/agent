"""tools/parallel_ops/actions/race.py — 'race' action for the parallel meta-tool.

Action semantics:
  Execute all tasks in parallel; the first task to return a non-error
  result wins. Remaining tasks are cancelled if they haven't started yet
  (already-running tasks cannot be preempted — Python threads are not
  cancellable mid-execution).

Returns: ok({"winner": {...}|None, "cancelled": [names], "failed": [...],
              "duration_ms": int}). The envelope status is "success" even
  when all tasks fail (the race itself completed) — callers should check
  winner is not None.

Use cases:
  - Send the same query to multiple search endpoints, use whichever
    returns first.
  - Redundant fetches: hit a primary + fallback URL concurrently, take
    the first that succeeds.
"""
from __future__ import annotations

from core.contracts import fail
from tools.parallel_ops._registry import register_action
from tools.parallel_ops.tool_map import PARALLEL_SAFE, _get_tool_fn
from tools.parallel_ops.actions.run import _validate_tasks
from tools.parallel_ops.executor import dispatch_race


@register_action(
    "parallel", "race",
    help_text="""race — Execute all tasks in parallel, first successful result wins.
Required: tasks=[{"name": str, "args": dict}, ...]
Optional: max_workers (1-8, default 4), allow_unsafe (default False), timeout (-1 = cfg.worker_timeout)
Returns: {winner: {...}|None, cancelled: [str], failed: [...], duration_ms: int}
Note: envelope status is "success" even if all tasks fail; check winner != None.""",
    examples=[
        'parallel(action="race", tasks=[{"name": "web", "args": {"action": "search", "query": "x"}}, {"name": "tavily", "args": {"query": "x"}}], allow_unsafe=True)',
        'parallel(action="race", tasks=[{"name": "web", "args": {"action": "fetch", "url": "primary"}}, {"name": "web", "args": {"action": "fetch", "url": "fallback"}}])',
    ],
)
def _action_race(
    tasks: list[dict] = [],
    max_workers: int = 4,
    allow_unsafe: bool = False,
    timeout: int = -1,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Race all tasks in parallel; first success wins, rest cancelled."""
    calls, err = _validate_tasks(tasks, trace_id=trace_id)
    if err is not None:
        return err

    if not allow_unsafe:
        for name, _, _ in calls:
            if name not in PARALLEL_SAFE:
                return fail(
                    f"Tool '{name}' is not parallel-safe. Set allow_unsafe=True to override.",
                    trace_id=trace_id,
                )

    return dispatch_race(calls, max_workers=max_workers, timeout=timeout, trace_id=trace_id)
