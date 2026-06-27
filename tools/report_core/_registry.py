"""Auto-registration registry for report actions.

This module defines the central DISPATCH dictionary that maps
(tool_name, action_name) pairs to their handler functions and metadata.

The @register_action decorator is used by individual action modules
to automatically register themselves in DISPATCH at import time.
This eliminates manual wiring in a central dispatcher, making the
system fully extensible: to add a new report action, simply:
 1. Create a new file in tools/report_core/actions/
 2. Define a handler decorated with @register_action("report", "action_name")
 3. The action is immediately available via the report() tool

Thread Safety:
 DISPATCH is populated at import time (single-threaded during module load).
 No locking is required for registration. Handlers should be thread-safe
 if called concurrently.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Global dispatch table: {"report": {"chart": {"func": ..., "help": ..., "examples": [...]}}}
# Populated automatically via @register_action decorators at import time.
DISPATCH: Dict[str, Dict[str, Dict[str, Any]]] = {}


def register_action(
    tool_name: str,
    action_name: str,
    help_text: str = "",
    examples: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator to register a report action handler function with metadata.

    Args:
        tool_name: Tool namespace. Always "report" for report actions.
        action_name: Action identifier exposed to the LLM (e.g., "chart", "dashboard").
        help_text: Help block to be included in the tool's dynamic docstring.
        examples: List of example strings for LLM reference.

    Returns:
        The original function, unmodified, after registration.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if tool_name not in DISPATCH:
            DISPATCH[tool_name] = {}
        DISPATCH[tool_name][action_name] = {
            "func": func,
            "help": help_text,
            "examples": examples or [],
        }
        return func
    return decorator


# ── Static metadata for each action (param docs, config keys) ────────────────
# Kept separate from DISPATCH so @register_action stays simple and identical
# to the git/file registry pattern.
DISPATCH_METADATA: Dict[str, Dict[str, Any]] = {
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
    "list": {
        "description": "List all available report actions",
        "required_params": ["action"],
        "optional_params": [],
        "config_keys": [],
    },
    "help": {
        "description": "Get detailed help for a specific report action",
        "required_params": ["action"],
        "optional_params": ["data"],
        "config_keys": [],
    },
}


# ── Presets ──────────────────────────────────────────────────────────────────
# Global presets that merge into config before dispatch. Each preset defines
# default template, theme, accent, chart engine, and section layout.
PRESETS: Dict[str, Dict[str, Any]] = {
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
