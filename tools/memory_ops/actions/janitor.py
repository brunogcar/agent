"""tools/memory_ops/actions/janitor.py — Janitor action handler.
CRITICAL: This file must NEVER import helpers.py or call _mem().
It operates on the filesystem and isolated collections, not the main store.
v1.2: Force errors to strings for JSON safety.


[DESIGN] THE JANITOR BYPASS — read before adding any import to this file:

  The memory facade dispatches 'janitor' BEFORE calling _mem() anywhere.
  Purpose: run archival/purge WITHOUT paying the ChromaDB startup cost (~200-500ms).

  archive_old_episodes() -> core/memory_backend/janitor.py  (no ChromaDB at module level)
  purge_stale_rules()    -> core/sleep_learn/janitor.py      (no ChromaDB at module level)
  Both lazy-import ChromaDB internally, so they are safe to import at module load time.

  WHAT BREAKS if you add 'from tools.memory_ops.helpers import _mem':
    - Tests that verify janitor never touches the store will fail.
    - If _mem() is actually called -> ChromaDB opens -> optimization destroyed.

  HOW TO VERIFY the bypass is intact:
    with patch('tools.memory_ops.helpers._mem') as mock_mem:
        memory(action='janitor')
        mock_mem.assert_not_called()   # must pass
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
        errors.append(str(epi_err))
    if rule_err:
        errors.append(str(rule_err))

    return ok({
        "episodic_archived": epi_stats.get("archived", 0),
        "rules_purged": rule_stats.get("purged", 0),
        "errors": errors,
    }, trace_id=trace_id)
