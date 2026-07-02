"""Prune action — remove stale or low-importance memories."""
from __future__ import annotations

from core.contracts import ok

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem

HELP_PRUNE = """
prune — Remove stale or low-importance memories.

Defaults to dry_run=True for safety. Review results before setting dry_run=False.

Parameters:
  max_age_days (default 30): Max age before removal.
  min_importance (default 3): Minimum importance to keep.
  dry_run (default True): Preview deletions without executing.
  collections: Filter to specific collections. Omit for all.
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="prune", dry_run=True)
  memory(action="prune", max_age_days=7, min_importance=5, dry_run=False)
"""


@register_action(
    "memory", "prune",
    help_text=HELP_PRUNE,
    examples=[
        'memory(action="prune", dry_run=True)',
        'memory(action="prune", max_age_days=7, min_importance=5, dry_run=False)',
    ],
)
def run_prune(
    max_age_days: int = 30,
    min_importance: int = 3,
    dry_run: bool = True,
    collections=None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Prune stale or low-importance memories."""
    store = _mem()
    result = store.prune(
        max_age_days=max_age_days,
        min_importance=min_importance,
        dry_run=dry_run,
        collections=collections,
    )

    return ok(result, trace_id=trace_id)
