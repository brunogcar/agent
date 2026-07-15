"""tools/parallel_ops/actions/run.py — 'run' action for the parallel meta-tool.

Action semantics:
  Execute all tasks in parallel using a ThreadPoolExecutor, wait for all
  to complete (barrier semantics). Failures in individual tasks do not
  abort the run — they're returned in `errors`.

This is the closest analogue to the pre-v1.0 `parallel()` behaviour. The
only differences are:
  - Param name `tools` → `tasks` (breaking change, documented in CHANGELOG).
  - New `timeout` param overrides cfg.worker_timeout per-call.
  - Result envelope now includes `duration_ms`.
  - Each per-task result includes `trace_id` when provided.

NOT parallel-safe enforcement: PARALLEL_SAFE tools run by default; unsafe
tools require allow_unsafe=True (mirrors pre-v1.0 behaviour).
"""
from __future__ import annotations

from core.contracts import fail
from tools.parallel_ops._registry import register_action
from tools.parallel_ops.tool_map import PARALLEL_SAFE, _get_tool_fn
from tools.parallel_ops.executor import dispatch_run


def _validate_tasks(tasks: list[dict], trace_id: str = ""):
    """Validate the tasks list and resolve each spec to (name, fn, args).

    Returns (calls, error_dict). If error_dict is non-None, the caller
    should return it immediately. Shared between run.py and race.py —
    pipeline.py has its own validation because it also extracts `feed`.
    """
    if not isinstance(tasks, list):
        return None, fail("tasks must be a list", trace_id=trace_id)

    if not tasks:
        return None, fail("No tasks provided", trace_id=trace_id)

    calls = []
    for i, spec in enumerate(tasks):
        if not isinstance(spec, dict):
            return None, fail(f"Task spec at index {i} must be a dict", trace_id=trace_id)

        name = spec.get("name")
        args = spec.get("args", {})
        if args is None:
            args = {}

        if not name:
            return None, fail(f"Task spec at index {i} missing 'name'", trace_id=trace_id)

        if not isinstance(args, dict):
            return None, fail(f"Task spec at index {i} args must be a dict", trace_id=trace_id)

        fn = _get_tool_fn(name)
        if fn is None:
            return None, fail(f"Tool '{name}' not found", trace_id=trace_id)

        calls.append((name, fn, args))

    return calls, None


@register_action(
    "parallel", "run",
    help_text="""run — Execute all tasks in parallel, wait for all to complete (barrier).
Required: tasks=[{"name": str, "args": dict}, ...]
Optional: max_workers (1-8, default 4), allow_unsafe (default False), timeout (-1 = cfg.worker_timeout)
Returns: {results: [...], errors: [...], completed: int, failed: int, duration_ms: int}""",
    examples=[
        'parallel(action="run", tasks=[{"name": "web", "args": {"action": "search", "query": "x"}}])',
        'parallel(action="run", tasks=[{"name": "web", "args": {...}}, {"name": "file", "args": {...}}], max_workers=4)',
    ],
)
def _action_run(
    tasks: list[dict] = [],
    max_workers: int = 4,
    allow_unsafe: bool = False,
    timeout: int = -1,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Run all tasks in parallel, wait for all to complete."""
    calls, err = _validate_tasks(tasks, trace_id=trace_id)
    if err is not None:
        return err

    # PARALLEL_SAFE enforcement (skip for run when allow_unsafe=True)
    if not allow_unsafe:
        for name, _, _ in calls:
            if name not in PARALLEL_SAFE:
                return fail(
                    f"Tool '{name}' is not parallel-safe. Set allow_unsafe=True to override.",
                    trace_id=trace_id,
                )

    return dispatch_run(calls, max_workers=max_workers, timeout=timeout, trace_id=trace_id)
