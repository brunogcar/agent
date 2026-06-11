"""
tools/report.py - Report meta-tool.

Thin @tool facade. Dispatches to report_core builders.
All heavy imports are lazy - inside action handlers.
"""

from __future__ import annotations

from typing import Any

from core.config import cfg
from core.contracts import ok, fail
from core.tracer import tracer
from registry import tool

from tools.report_core._registry import DISPATCH, DISPATCH_METADATA, PRESETS
from tools.report_core.contracts import report_ok, report_fail


@tool
def report(
    action: str,
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    preset: str = "",
) -> dict:
    """
    Report tool - create interactive charts, maps, reports, dashboards, and diagrams.
    All outputs are self-contained HTML files with client-side rendering (Chart.js,
    Leaflet, Mermaid). Open in any browser - no server required.

    action: "chart" | "map" | "report" | "dashboard" | "diagram" | "export"
    trace_id: optional trace ID (auto-generated if empty)
    title: report title
    data: inline dict/list, or a local file path string
    config: action-specific options (dict) - see docs/REPORT.md
    preset: "financial" | "code_audit" | "research" | "system_health"

    Examples:
      report(action="chart", title="Revenue",
             data={"x":["Q1","Q2"], "y":[100,150]},
             config={"chart_type":"bar"})

      report(action="dashboard", title="Q3 Analysis",
             data="workspace/data.csv", preset="financial")
    """
    action = (action or "").strip().lower()
    if not action:
        return report_fail("action is required", trace_id=trace_id)

    # Trace ID
    if not trace_id:
        trace_id = tracer.new_trace("report", goal=action)

    # Cancellation guard
    try:
        from core.cancellation import ensure_not_cancelled
        ensure_not_cancelled(trace_id)
    except Exception:
        pass  # If module not found, continue without guard

    # Apply preset
    config = dict(config) if config else {}
    if preset and preset in PRESETS:
        preset_cfg = dict(PRESETS[preset])
        preset_cfg.update(config)
        config = preset_cfg

    # Validate action
    handler = DISPATCH.get(action)
    if not handler:
        known = ", ".join(DISPATCH.keys())
        return report_fail(f"Unknown action '{action}'. Use: {known}", trace_id=trace_id)

    # Dispatch
    try:
        result = handler(
            trace_id=trace_id,
            title=title,
            data=data,
            config=config,
        )
        # Memory hook - store episodic record of report generation
        try:
            from core.memory import memory
            memory.store_episodic(
                text=f"Generated {action} report: '{title}' at {result.get('html_path', 'unknown')}",
                importance=5,
                goal=title,
                outcome="success",
                tools_used=f"report,{action}",
                trace_id=trace_id,
            )
        except Exception:
            pass  # Never fail the report if memory storage fails
        return report_ok(result, trace_id=trace_id)
    except Exception as e:
        return report_fail(f"{type(e).__name__}: {e}", trace_id=trace_id)