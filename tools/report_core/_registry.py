"""
report_core/_registry.py - Action dispatch registry.

Dispatcher pattern: action string -> builder function.
All builder imports are lazy (inside wrapper functions) to avoid
loading heavy deps (pandas, jinja2, plotly) at MCP startup time.
"""

from __future__ import annotations

from typing import Callable, Any


def _dispatch_chart(*args, **kwargs):
    from tools.report_core import charts
    return charts.build(*args, **kwargs)


def _dispatch_map(*args, **kwargs):
    from tools.report_core import maps
    return maps.build(*args, **kwargs)


def _dispatch_report(*args, **kwargs):
    from tools.report_core import html
    return html.build_report(*args, **kwargs)


def _dispatch_dashboard(*args, **kwargs):
    from tools.report_core import html
    return html.build_dashboard(*args, **kwargs)


def _dispatch_diagram(*args, **kwargs):
    from tools.report_core import diagrams
    return diagrams.build(*args, **kwargs)


def _dispatch_export(*args, **kwargs):
    from tools.report_core import export
    return export.run(*args, **kwargs)


def _dispatch_compare(*args, **kwargs):
    from tools.report_core import compare
    return compare.build(*args, **kwargs)

def _dispatch_timeline(*args, **kwargs):
    from tools.report_core import timeline
    return timeline.build(*args, **kwargs)

def _dispatch_scorecard(*args, **kwargs):
    from tools.report_core import scorecard
    return scorecard.build(*args, **kwargs)

DISPATCH: dict[str, Callable] = {
    "chart":      _dispatch_chart,
    "map":        _dispatch_map,
    "report":     _dispatch_report,
    "dashboard":  _dispatch_dashboard,
    "diagram":    _dispatch_diagram,
    "export":     _dispatch_export,
    "compare":    _dispatch_compare,
    "timeline":   _dispatch_timeline,
    "scorecard":  _dispatch_scorecard,
}

DISPATCH_METADATA: dict[str, dict] = {
    "chart": {
        "description": "Interactive Chart.js chart",
        "required_params": ["action", "title"],
        "optional_params": ["data", "config"],
        "config_keys": ["chart_type", "x_label", "y_label", "color", "theme"],
    },
    "map": {
        "description": "Interactive Leaflet map",
        "required_params": ["action", "title"],
        "optional_params": ["data", "config"],
        "config_keys": ["map_type", "center_lat", "center_lon", "zoom"],
    },
    "report": {
        "description": "Single-scroll HTML report with sections",
        "required_params": ["action", "title"],
        "optional_params": ["data", "config"],
        "config_keys": ["sections", "kpis", "sources", "theme"],
    },
    "dashboard": {
        "description": "Multi-panel dashboard with side nav and tabs",
        "required_params": ["action", "title"],
        "optional_params": ["data", "config"],
        "config_keys": ["tabs", "kpis", "charts", "theme", "columns"],
    },
    "diagram": {
        "description": "Mermaid.js architecture diagram",
        "required_params": ["action", "title"],
        "optional_params": ["data", "config"],
        "config_keys": ["diagram_type", "theme"],
    },
    "export": {
        "description": "Export existing HTML to PDF/PNG",
        "required_params": ["action", "data"],
        "optional_params": ["config"],
        "config_keys": ["format", "width", "height"],
    },
    "compare": {
        "description": "Side-by-side diff table with delta highlighting",
        "required_params": ["action", "title", "data"],
        "optional_params": ["config"],
        "config_keys": ["before_label", "after_label", "key_col", "theme"],
    },
    "timeline": {
        "description": "SVG Gantt/timeline chart",
        "required_params": ["action", "title", "data"],
        "optional_params": ["config"],
        "config_keys": ["width", "bar_height", "row_gap", "theme"],
    },
    "scorecard": {
        "description": "RAG status dashboard with radar chart",
        "required_params": ["action", "title", "data"],
        "optional_params": ["config"],
        "config_keys": ["theme", "accent"],
    },
}
PRESETS: dict[str, dict] = {
    "financial": {
        "template": "dashboard",
        "theme": "dark",
        "accent": "#0d9488",
        "chart_engine": "chartjs",
        "default_sections": ["overview", "charts", "data", "sources"],
    },
    "code_audit": {
        "template": "dashboard",
        "theme": "dark",
        "accent": "#6366f1",
        "default_sections": ["summary", "issues", "recommendations", "changes", "sources"],
    },
    "research": {
        "template": "report",
        "theme": "dark",
        "accent": "#3b82f6",
        "default_sections": ["overview", "findings", "data", "sources"],
    },
    "system_health": {
        "template": "dashboard",
        "theme": "dark",
        "accent": "#14b8a6",
        "default_sections": ["overview", "metrics", "issues", "logs"],
    },
    "compare": {
        "template": "compare",
        "theme": "dark",
        "accent": "#0d9488",
        "default_sections": ["diff"],
    },
    "timeline": {
        "template": "timeline",
        "theme": "dark",
        "accent": "#3b82f6",
        "default_sections": ["gantt", "events"],
    },
    "scorecard": {
        "template": "scorecard",
        "theme": "dark",
        "accent": "#14b8a6",
        "default_sections": ["overview", "radar", "details"],
    },
}  