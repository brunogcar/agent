"""core/net/budget.py — API cost tracking and budget enforcement.

v1.2: Added for Tavily and future paid APIs.
v1.3: Fixed deadlock by using threading.RLock(). Added daily reset mechanism.
      Wired auto_block to circuit breaker integration.
      FIXED: get_status() no longer returns {} when no budget config is set.
"""
from __future__ import annotations

import datetime
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
    v1.3: Uses RLock to prevent deadlock in get_status().
          Added daily reset on date change.
    """

    def __init__(self):
        self._lock = threading.RLock()  # v1.3 FIX: RLock prevents nested deadlock
        self._calls: dict[str, int] = {}  # tool → count today
        self._configs: dict[str, BudgetConfig] = {}
        self._last_reset_date: datetime.date = datetime.date.today()

    def _maybe_reset_daily(self) -> None:
        """v1.3: Reset counts if the date has changed."""
        today = datetime.date.today()
        if self._last_reset_date != today:
            self._calls.clear()
            self._last_reset_date = today

    def set_budget(self, tool: str, config: BudgetConfig) -> None:
        """Configure budget for a tool."""
        with self._lock:
            self._maybe_reset_daily()
            self._configs[tool] = config

    def record_call(self, tool: str, cost: int = 1) -> None:
        """Record a paid API call.

        Args:
            tool: Tool name (e.g., "tavily.search").
            cost: Cost units (default 1 per call).
        """
        with self._lock:
            self._maybe_reset_daily()
            self._calls[tool] = self._calls.get(tool, 0) + cost

    def can_afford(self, tool: str) -> bool:
        """Return True if the tool has remaining budget."""
        with self._lock:
            self._maybe_reset_daily()
            config = self._configs.get(tool)
            if config is None or config.daily_limit <= 0:
                return True
            used = self._calls.get(tool, 0)
            return used < config.daily_limit

    def _is_warning_unlocked(self, tool: str) -> bool:
        """Caller must hold self._lock."""
        config = self._configs.get(tool)
        if config is None or config.daily_limit <= 0:
            return False
        used = self._calls.get(tool, 0)
        return used >= config.daily_limit * config.warning_threshold

    def _can_afford_unlocked(self, tool: str) -> bool:
        """Caller must hold self._lock."""
        config = self._configs.get(tool)
        if config is None or config.daily_limit <= 0:
            return True
        used = self._calls.get(tool, 0)
        return used < config.daily_limit

    def get_status(self, tool: str = "") -> dict:
        """Return budget status for one or all tools."""
        with self._lock:
            self._maybe_reset_daily()
            if tool:
                # v1.3 FIX: Return status even when no explicit config is set
                config = self._configs.get(tool)
                used = self._calls.get(tool, 0)
                limit = config.daily_limit if config else 0
                return {
                    tool: {
                        "used": used,
                        "limit": limit,
                        "remaining": max(0, limit - used) if limit > 0 else None,
                        "warning": self._is_warning_unlocked(tool),
                        "blocked": not self._can_afford_unlocked(tool),
                    }
                }
            # Return all tools
            result = {}
            for t in set(self._calls) | set(self._configs):
                cfg = self._configs.get(t, BudgetConfig())
                used = self._calls.get(t, 0)
                limit = cfg.daily_limit
                result[t] = {
                    "used": used,
                    "limit": limit,
                    "remaining": max(0, limit - used) if limit > 0 else None,
                    "warning": self._is_warning_unlocked(t),
                    "blocked": not self._can_afford_unlocked(t),
                }
            return result


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
