"""tools/memory_ops/actions/janitor.py — Janitor action handler.
CRITICAL: This file must NEVER import helpers.py or call _mem().
It operates on the filesystem and isolated collections, not the main store.
v1.1: Added exception handling and non-dict return guards.
"""
from __future__ import annotations

from core.memory_backend.janitor import archive_old_episodes
from core.sleep_learn.janitor import purge_stale_rules
from tools.memory_ops._registry import register_action
from core.contracts import ok


@register_action("memory", "janitor", help_text="Run memory maintenance (archive + purge) — no store load")
def run_janitor(trace_id: str = "", **kwargs):
    try:
        epi_stats = archive_old_episodes()
    except Exception as e:
        epi_stats = {"archived": 0, "error": str(e)}

    try:
        rule_stats = purge_stale_rules()
    except Exception as e:
        rule_stats = {"purged": 0, "error": str(e)}

    if not isinstance(epi_stats, dict):
        epi_stats = {"archived": 0, "error": f"Unexpected return type: {type(epi_stats).__name__}"}
    if not isinstance(rule_stats, dict):
        rule_stats = {"purged": 0, "error": f"Unexpected return type: {type(rule_stats).__name__}"}

    errors = []
    epi_err = epi_stats.get("error")
    rule_err = rule_stats.get("error")
    if epi_err:
        errors.append(epi_err)
    if rule_err:
        errors.append(rule_err)

    return ok({
        "episodic_archived": epi_stats.get("archived", 0),
        "rules_purged": rule_stats.get("purged", 0),
        "errors": errors,
    }, trace_id=trace_id)
