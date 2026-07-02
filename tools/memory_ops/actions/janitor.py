"""Janitor action — memory compaction without loading the main store.

[DESIGN] JANITOR BYPASS — This file must NEVER import from helpers.py or call _mem().
The janitor action is deliberately isolated to avoid importing ChromaDB
(via memory_engine.py). Both archive_old_episodes() and purge_stale_rules()
are top-level imports here, NOT lazy imports, because they themselves do NOT
import ChromaDB at module level. The facade dispatches 'janitor' directly to
this handler BEFORE calling _mem() anywhere.

Verified: core/memory_backend/janitor.py and core/sleep_learn/janitor.py are
ChromaDB-free at module level.
DO NOT add any call to _mem() or store.* in this file under any circumstances.
"""
from __future__ import annotations

from core.contracts import ok
from core.memory_backend.janitor import archive_old_episodes
from core.sleep_learn.janitor import purge_stale_rules

from tools.memory_ops._registry import register_action

HELP_JANITOR = """
janitor — Run memory compaction without loading ChromaDB.

Archives old episodic memories and purges stale learned rules.
This is the fastest memory action because it bypasses the main store entirely.

Parameters:
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="janitor")
"""


@register_action(
    "memory", "janitor",
    help_text=HELP_JANITOR,
    examples=[
        'memory(action="janitor")',
    ],
)
def run_janitor(
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Run memory compaction: archive old episodes, purge stale rules."""
    epi_stats = archive_old_episodes()
    rule_stats = purge_stale_rules()

    return ok({
        "episodic_archived": epi_stats.get("archived", 0),
        "rules_purged": rule_stats.get("purged", 0),
        "errors": [
            e for e in [epi_stats.get("error"), rule_stats.get("error")] if e
        ],
    }, trace_id=trace_id)
