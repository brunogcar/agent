"""tools/parallel_ops/actions/pipeline.py — 'pipeline' action for the parallel meta-tool.

Action semantics:
  Execute tasks SEQUENTIALLY (NOT parallel despite the tool name). Each
  task's result may be fed into the next task's args via the per-task
  `feed` key. Pipeline stops on first failure (no upstream result to
  feed downstream).

Feed syntax (in each task spec, optional):
  - "feed": "result.text"
      Dot-path into the previous result. The resolved value REPLACES the
      next call's args entirely (only valid if resolved value is a dict).
      Example: prev result {"result": {"text": "print('hi')"}} → next call
      runs with args = the resolved dict.

  - "feed": {"code": "result.text"}
      Map of next-call-arg-name → dot-path into previous result. Base args
      are kept; fed values override matching keys.
      Example: prev result {"result": {"text": "x"}} + base args {"action": "run"}
      → next call args {"action": "run", "code": "x"}.

  - "feed" omitted / None
      Next call uses its own args as-is. Use this when a step doesn't
      depend on the previous result (rare in pipelines but supported).

Returns: ok({"results": [...], "errors": [...], "completed": N, "failed": M,
              "duration_ms": int}) — same shape as run/race for uniformity.

Pipeline does NOT enforce PARALLEL_SAFE — tasks run sequentially so there
is no concurrency hazard regardless of which tool is called.
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.parallel_ops._registry import register_action
from tools.parallel_ops.tool_map import _get_tool_fn
from tools.parallel_ops.executor import dispatch_pipeline


def _validate_pipeline_tasks(tasks: list[dict], trace_id: str = ""):
    """Validate pipeline task specs and resolve to (name, fn, args, feed) tuples.

    Pipeline-specific: extracts the optional `feed` key from each spec
    (None | str | dict) and validates its type.
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
        feed = spec.get("feed")

        if not name:
            return None, fail(f"Task spec at index {i} missing 'name'", trace_id=trace_id)

        if not isinstance(args, dict):
            return None, fail(f"Task spec at index {i} args must be a dict", trace_id=trace_id)

        if feed is not None and not isinstance(feed, (str, dict)):
            return None, fail(
                f"Task spec at index {i} feed must be str | dict | None (got {type(feed).__name__})",
                trace_id=trace_id,
            )

        fn = _get_tool_fn(name)
        if fn is None:
            return None, fail(f"Tool '{name}' not found", trace_id=trace_id)

        calls.append((name, fn, args, feed))

    return calls, None


@register_action(
    "parallel", "pipeline",
    help_text="""pipeline — Execute tasks sequentially, each result feeds the next call's args.
Required: tasks=[{"name": str, "args": dict, "feed"?: str|dict}, ...]
Optional: timeout (-1 = cfg.worker_timeout)
NOT parallel — sequential by design. Stops on first failure.
Feed: str replaces args entirely; dict merges fed values into args; omitted = no feed.
Returns: {results: [...], errors: [...], completed: int, failed: int, duration_ms: int}""",
    examples=[
        'parallel(action="pipeline", tasks=[{"name": "web", "args": {"action": "search", "query": "x"}}, {"name": "python", "args": {"action": "run"}, "feed": {"code": "result.text"}}])',
        'parallel(action="pipeline", tasks=[{"name": "file", "args": {"action": "read", "path": "x.txt"}}, {"name": "consult", "args": {"question": "review this"}, "feed": {"context": "result.text"}}])',
    ],
)
def _action_pipeline(
    tasks: list[dict] = [],
    allow_unsafe: bool = False,
    timeout: int = -1,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Run tasks sequentially, feeding each result into the next call's args.

    `allow_unsafe` is accepted for API symmetry with run/race but ignored —
    pipeline is sequential so PARALLEL_SAFE does not apply.
    """
    calls, err = _validate_pipeline_tasks(tasks, trace_id=trace_id)
    if err is not None:
        return err

    return dispatch_pipeline(calls, timeout=timeout, trace_id=trace_id)
