"""tools/python_ops/actions/lint.py — ruff/flake8 pre-check (NEW in v1.0).

Writes the code to a temp file and runs `ruff check --select E,F --no-cache`
to surface syntax errors (E) and pyflakes errors (F) before execution. Falls
back to `flake8` if ruff is not installed.

If neither ruff nor flake8 is available, returns fail with install hint.

Linting is fast and isolated — a 10s hard timeout is enforced. json_schema
is ignored (lint output is not user data).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.contracts import ok, fail
from tools.python_ops._registry import register_action


_LINT_TIMEOUT = 10  # seconds — linting should be fast


def _has_executable(name: str) -> bool:
    """True if `name` is on PATH."""
    return shutil.which(name) is not None


def _run_lint(code: str, trace_id: str) -> dict:
    """Run ruff (preferred) or flake8 on the given code.

    Returns ok(lint_output, mode="lint") on success (even if lint reports
    issues — those are content of the lint output), or fail on tool failure.
    """
    # Pick the linter
    if _has_executable("ruff"):
        cmd_builder = lambda tmp_path: ["ruff", "check", "--select", "E,F", "--no-cache", str(tmp_path)]
        tool_name = "ruff"
    elif _has_executable("flake8"):
        cmd_builder = lambda tmp_path: ["flake8", str(tmp_path)]
        tool_name = "flake8"
    else:
        return fail(
            "Neither ruff nor flake8 is installed. Install with: pip install ruff",
            trace_id=trace_id,
            mode="lint",
        )

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        ) as f:
            f.write(code)
            tmp = Path(f.name)

        cmd = cmd_builder(tmp)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_LINT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return fail(
                f"{tool_name} timed out after {_LINT_TIMEOUT}s.",
                trace_id=trace_id,
                mode="lint",
            )

        # Combine stdout + stderr — flake8 writes issues to stdout, ruff to stderr.
        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout.strip())
        if result.stderr:
            output_parts.append(result.stderr.strip())
        lint_output = "\n".join(output_parts).strip()

        if not lint_output:
            lint_output = f"({tool_name} reported no issues — clean)"

        # Exit code 0 = clean; 1 = lint issues found (still a successful run);
        # >1 = tool error.
        if result.returncode > 1:
            return fail(
                f"{tool_name} exited with code {result.returncode}: {lint_output}",
                trace_id=trace_id,
                mode="lint",
            )

        return ok(lint_output, mode="lint")
    except Exception as e:
        return fail(str(e), trace_id=trace_id, mode="lint")
    finally:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


@register_action(
    "python", "lint",
    help_text="""lint — ruff/flake8 pre-check (syntax + pyflakes errors).
Required: code
Optional: trace_id. json_schema ignored. timeout fixed at 10s.
Returns: {data: lint output (errors/warnings), mode: "lint"}""",
    examples=[
        'python(action="lint", code="import os\\nprint(os.getcwd())")',
        'python(action="lint", code="def f(x)\\n  return x")',
    ],
)
def _action_lint(
    code: str = "",
    trace_id: str = "",
    timeout: int = -1,
    json_schema: str = "",
    **kwargs: Any,
) -> dict:
    """Lint code with ruff (preferred) or flake8. 10s hard timeout."""
    if not code or not code.strip():
        return fail("No code provided", trace_id=trace_id, mode="lint")

    # Note: `timeout` param is intentionally ignored — linting always uses
    # the 10s hard cap. Documented for callers who pass `timeout=-1`.
    result = _run_lint(code, trace_id)
    if trace_id and isinstance(result, dict) and "trace_id" not in result:
        result["trace_id"] = trace_id
    return result
