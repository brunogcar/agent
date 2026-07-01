"""core/net/budget.py — API cost tracking and budget enforcement.

v1.2: Added for Tavily and future paid APIs.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BudgetConfig:
    """Budget configuration for a single API tool."""
    daily_limit: int = 0  # 0 = unlimited
    warning_threshold: float = 0.8  # Warn at 80% of limit
    auto_block: bool = True  # Auto-open circuit breaker on exhaustion


class APICostTracker:
    """Track API usage and enforce budgets across paid tools.

    Thread-safe singleton. Call record_call() after every paid API invocation.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: dict[str, int] = {}  # tool → count today
        self._configs: dict[str, BudgetConfig] = {}

    def set_budget(self, tool: str, config: BudgetConfig) -> None:
        """Configure budget for a tool."""
        with self._lock:
            self._configs[tool] = config

    def record_call(self, tool: str, cost: int = 1) -> None:
        """Record a paid API call.

        Args:
            tool: Tool name (e.g., "tavily.search").
            cost: Cost units (default 1 per call).
        """
        with self._lock:
            self._calls[tool] = self._calls.get(tool, 0) + cost

    def can_afford(self, tool: str) -> bool:
        """Return True if the tool has remaining budget."""
        with self._lock:
            config = self._configs.get(tool)
            if config is None or config.daily_limit <= 0:
                return True
            used = self._calls.get(tool, 0)
            return used < config.daily_limit

    def is_warning(self, tool: str) -> bool:
        """Return True if tool is near budget limit (per threshold)."""
        with self._lock:
            config = self._configs.get(tool)
            if config is None or config.daily_limit <= 0:
                return False
            used = self._calls.get(tool, 0)
            return used >= config.daily_limit * config.warning_threshold

    def get_status(self, tool: str = "") -> dict:
        """Return budget status for one or all tools."""
        with self._lock:
            if tool:
                config = self._configs.get(tool)
                if config is None:
                    return {}
                used = self._calls.get(tool, 0)
                limit = config.daily_limit
                return {
                    tool: {
                        "used": used,
                        "limit": limit,
                        "remaining": max(0, limit - used) if limit > 0 else None,
                        "warning": self.is_warning(tool),
                        "blocked": not self.can_afford(tool),
                    }
                }
            # Return all tools
            return {
                t: {
                    "used": self._calls.get(t, 0),
                    "limit": self._configs.get(t, BudgetConfig()).daily_limit,
                    "remaining": max(0, self._configs.get(t, BudgetConfig()).daily_limit - self._calls.get(t, 0))
                    if self._configs.get(t, BudgetConfig()).daily_limit > 0 else None,
                }
                for t in set(self._calls) | set(self._configs)
            }


# ── Singleton ────────────────────────────────────────────────────────────────
_budget_tracker = APICostTracker()


def record_tool_call(tool: str, cost: int = 1) -> None:
    """Record a tool call against the global budget tracker."""
    _budget_tracker.record_call(tool, cost)


def check_budget(tool: str) -> bool:
    """Check if a tool has remaining budget."""
    return _budget_tracker.can_afford(tool)


def get_budget_status(tool: str = "") -> dict:
    """Get budget status for one or all tools."""
    return _budget_tracker.get_status(tool)


def set_tool_budget(tool: str, daily_limit: int = 0, warning_threshold: float = 0.8) -> None:
    """Set budget for a tool."""
    _budget_tracker.set_budget(tool, BudgetConfig(
        daily_limit=daily_limit,
        warning_threshold=warning_threshold,
    ))
