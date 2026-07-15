"""tools/python_ops/actions/profile.py — cProfile timing breakdown (NEW in v1.0).

Runs code under cProfile and returns the top-20 cumulative-time functions.

SECURITY NOTE: profile mode does NOT use the sandbox. Profiling requires
full builtins access (cProfile, pstats, io) and the profiled code may need
imports — restricting builtins would defeat the purpose. Use this action
only on code you trust (LLM-generated code that has already passed lint or
run/run_data validation).

Execution routing mirrors run_data:
  - If the code declares imports (any kind), runs in subprocess (isolated).
  - Otherwise, runs in-process with cProfile wrapping.

json_schema is ignored (output is profiling data, not user data).
"""
from __future__ import annotations

import ast
import cProfile
import io
import pstats
from typing import Any

from core.contracts import ok, fail
from tools.python_ops._registry import register_action
from tools.python_ops.imports import _parse_imports
from tools.python_ops.executors import _run_subprocess


_PROFILE_WRAPPER = """
import cProfile, io, pstats

profiler = cProfile.Profile()
profiler.enable()
try:
    exec(__code__, {{'__builtins__': __builtins__}}, {{}})
finally:
    profiler.disable()

s = io.StringIO()
ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
ps.print_stats(20)
print(s.getvalue())
"""


def _profile_inprocess(code: str) -> dict:
    """Run code under cProfile in the current process.

    Used when the code declares no imports. Captures the profiled output
    via pstats. Does NOT sandbox — profiling needs full builtins.
    """
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        exec(code, {"__builtins__": __builtins__}, {})
    except Exception as e:
        return fail(f"Profiled code raised: {e}", mode="profile")
    finally:
        profiler.disable()

    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    output = s.getvalue().strip()
    return ok(
        output if output else "(no profile output — code produced no function calls)",
        mode="profile",
    )


def _profile_subprocess(code: str, timeout_override: int) -> dict:
    """Run code under cProfile in a subprocess.

    Used when the code declares any imports (heavy or stdlib). Wraps the
    user code in a cProfile-enabling template and runs it via the
    standard _run_subprocess helper.
    """
    wrapped = _PROFILE_WRAPPER.replace("__code__", repr(code))
    result = _run_subprocess(wrapped, timeout_override=timeout_override)
    # Force mode="profile" regardless of which executor path was taken.
    if isinstance(result, dict):
        result["mode"] = "profile"
    return result


@register_action(
    "python", "profile",
    help_text="""profile — cProfile timing breakdown (top 20 cumulative).
Required: code
Optional: trace_id, timeout (-1 = default). json_schema ignored.
Returns: {data: pstats output, mode: "profile"}
NOTE: NOT sandboxed — profiling needs full builtins. Use only on trusted code.""",
    examples=[
        'python(action="profile", code="print(sum(range(10000)))")',
        'python(action="profile", code="import json; [json.dumps({{i: i}}) for i in range(100)]")',
    ],
)
def _action_profile(
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
    **kwargs: Any,
) -> dict:
    """Profile code with cProfile. Routes to subprocess if code has imports."""
    if not code or not code.strip():
        return fail("No code provided", trace_id=trace_id, mode="profile")

    # Syntax check
    try:
        ast.parse(code)
    except SyntaxError as e:
        return fail(
            f"SyntaxError line {e.lineno}: {e.msg}",
            trace_id=trace_id,
            mode="profile",
        )

    # Route to subprocess if code has any imports (stdlib or heavy).
    imports = _parse_imports(code)
    if imports:
        result = _profile_subprocess(code, timeout)
    else:
        result = _profile_inprocess(code)

    if trace_id and isinstance(result, dict) and "trace_id" not in result:
        result["trace_id"] = trace_id
    return result
