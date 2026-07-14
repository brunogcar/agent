"""[v2.0] LLM review node — spec coverage + cleanliness check.

Split from node_verify (Phase 3.2). This node calls the LLM to review the
implementation against the spec + test output + lint output. The final
decision (pass/fail) is handled by node_verify_decision (next in graph).
"""
from __future__ import annotations

from workflows.autocode_impl.state import AutocodeState, EXECUTOR_TIMEOUT, _get_plan, _get_tdd  # [v2.2+v3.0] accessors
from workflows.autocode_impl.constants import VERIFY_SYSTEM
from workflows.autocode_impl.helpers import _call, _parse_json
from core.tracer import tracer


def node_llm_review(state: AutocodeState) -> dict:
    """[v2.0] LLM spec review of the implementation.

    Returns partial state update with:
      - llm_review_data: dict with {automated_checks_passed, checks, summary}
    """
    tid = state.get("trace_id", "")
    if state.get("status") in ("needs_clarification", "failed"):
        return {}

    # Build implementation context from generated code artifacts
    # [v2.0.5] P3-3: Was `json.loads(...)` — fails on markdown-fenced JSON.
    # Now uses `_parse_json` for consistency with apply_patches.py + write_new_files.py.
    impl_ctx = ""
    try:
        code_data = _parse_json(_get_tdd(state, "source_code", "{}"))  # [v3.0] accessor (was flat field)
        if not code_data:
            code_data = {}
        parts = []
        for patch in code_data.get("patches", []):
            parts.append(f"# Patch: {patch.get('path', '')}\n```python\n{patch.get('new', '')[:1500]}\n```")
        for path, content in code_data.get("new_files", {}).items():
            parts.append(f"# New file: {path}\n```python\n{str(content)[:1500]}\n```")
        impl_ctx = "\n\n".join(parts) if parts else _get_tdd(state, "source_code", "")[:3000]  # [v3.0] accessor
    except Exception:
        impl_ctx = _get_tdd(state, "source_code", "")[:3000]  # [v3.0] accessor

    # Get pytest + lint output from previous nodes (stored in state)
    tests_passed = state.get("tests_passed", False)
    fresh_output = state.get("_pytest_output", state.get("test_results", {}).get("stderr", ""))
    lint_output = state.get("lint_output", "")

    try:
        raw = _call(
            role="executor",
            system=VERIFY_SYSTEM,
            user=(
                f"Spec:\n{_get_plan(state, 'spec', '')}\n\n"  # [v2.2] accessor
                f"Implementation:\n```python\n{impl_ctx[:3000]}\n```\n\n"
                f"Tests:\n```python\n{state.get('test_code', '')[:1000]}\n```\n\n"
                f"FRESH PYTEST OUTPUT (exit code {'0' if tests_passed else '1'}):\n"
                f"{fresh_output[:2000]}\n\n"
                f"RUFF OUTPUT:\n{lint_output[:500]}"
            ),
            timeout=EXECUTOR_TIMEOUT,
        )
        data = _parse_json(raw) if raw else {}
    except Exception as e:
        tracer.error(tid, "llm_review", f"LLM verification failed: {e}")
        data = {"automated_checks_passed": False, "checks": {}, "summary": "LLM verification error"}

    return {"llm_review_data": data}
