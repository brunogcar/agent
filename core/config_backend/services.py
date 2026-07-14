"""core/config_backend/services.py — Initialize external service configuration.

[v1.0] Extracted from ``Config.__init__`` as part of the config_backend split.

Env vars read:
    SearXNG:
        SEARXNG_URL   — default http://localhost:8080

    Tavily AI Research:
        TAVILY_API_KEY   — default "" (opt-in)
        TAVILY_TIMEOUT   — default 60 (range-checked in validators.py)

    Browser Fallback (Research Workflow):
        RESEARCH_BROWSER_FALLBACK_MAX      — default 3
        RESEARCH_BROWSER_FALLBACK_TIMEOUT  — default 15

    Deep Research Workflow:
        DEEP_RESEARCH_MAX_ITERATIONS            — default 10
        DEEP_RESEARCH_COMPLETENESS_THRESHOLD    — default 85
        DEEP_RESEARCH_MAX_API_CALLS             — default 20
        DEEP_RESEARCH_MAX_BROWSER_ACTIONS       — default 10
        DEEP_RESEARCH_TIMEOUT_SECONDS           — default 300
        DEEP_RESEARCH_CONVERGENCE_THRESHOLD     — default 0.85 (range-checked in validators.py)
"""

from __future__ import annotations

import os


def _init_services(cfg) -> None:
    """Initialize SearXNG, Tavily, browser fallback, and deep research config."""

    # -- External services -------------------------------------------------
    cfg.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")

    # -- Tavily AI Research -----------------------------------------------
    cfg.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    cfg.tavily_timeout = int(os.getenv("TAVILY_TIMEOUT", "60"))

    # -- Browser Fallback (Research Workflow) -----------------------------
    cfg.research_browser_fallback_max = int(os.getenv("RESEARCH_BROWSER_FALLBACK_MAX", "3"))
    cfg.research_browser_fallback_timeout = int(os.getenv("RESEARCH_BROWSER_FALLBACK_TIMEOUT", "15"))

    # -- Deep Research Workflow --------------------------------------------------
    cfg.deep_research_max_iterations = int(
        os.getenv("DEEP_RESEARCH_MAX_ITERATIONS", "10")
    )
    cfg.deep_research_completeness_threshold = float(
        os.getenv("DEEP_RESEARCH_COMPLETENESS_THRESHOLD", "85")
    )
    cfg.deep_research_max_api_calls = int(
        os.getenv("DEEP_RESEARCH_MAX_API_CALLS", "20")
    )
    cfg.deep_research_max_browser_actions = int(
        os.getenv("DEEP_RESEARCH_MAX_BROWSER_ACTIONS", "10")
    )
    cfg.deep_research_timeout_seconds = int(
        os.getenv("DEEP_RESEARCH_TIMEOUT_SECONDS", "300")
    )
    cfg.deep_research_convergence_threshold = float(
        os.getenv("DEEP_RESEARCH_CONVERGENCE_THRESHOLD", "0.85")
    )
    # Range check moved to validators.py::_validate_config (was inline here pre-v1.0).
