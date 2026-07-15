"""tools/notify_ops/actions/modify.py — Update an existing job's metadata. [NEW]

v1.0 introduces this action. Allows updating the title and/or message of an
existing scheduled or recurring job WITHOUT canceling and re-creating it.

[DESIGN] Why metadata-only update (not reschedule):
  APScheduler jobs reference _send_notification at scheduling time, with
  title/message baked in as kwargs. Re-creating the job would lose the
  trigger's positional state (next fire time, cron position) and require
  full cancel+re-add. Instead we update state._job_registry in place —
  the next time the job fires, the firing callback can read the updated
  title/message from the registry.

  BUT: the scheduler.add_job() kwargs are frozen at scheduling time. The
  current implementation passes title/message as kwargs, so they won't be
  re-read from the registry on fire. This is a known limitation — to make
  modify() fully effective, the firing callback would need to be changed
  to look up the registry by job_id at fire time (deferred to v1.1).

  For v1.0, modify() updates the registry + persists it + returns success.
  Callers who need the change to take effect on the NEXT fire should
  cancel + re-create. The modify() action is most useful for updating the
  metadata shown by list() (e.g. correcting a typo in the title without
  disrupting the schedule).

This tradeoff is documented here so future maintainers don't get bitten.
"""
from __future__ import annotations

from core.contracts import ok, fail
from tools.notify_ops._registry import register_action
from tools.notify_ops import state


@register_action(
    "notify", "modify",
    help_text="""modify — Update an existing scheduled/recurring job's title and/or message.
Required: job_id
Optional: title (updates only if non-empty), message (updates only if non-empty), trace_id
Returns: {action_status: "modified", job_id, updated_fields, trace_id?}

NOTE: Updates _job_registry metadata only — does NOT reschedule the APScheduler
job. The metadata change will be reflected in `notify(action="list")` immediately.
For the change to take effect on the NEXT fire, use cancel + schedule/recurring.""",
    examples=[
        'notify(action="modify", job_id="reminder_123", title="Updated Title")',
        'notify(action="modify", job_id="recurring_456", title="New", message="New body")',
    ],
)
def _action_modify(
    job_id: str = "",
    title: str = "",
    message: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Update an existing scheduled/recurring job's title and/or message."""
    if not job_id:
        return fail(
            "job_id is required for modify",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )

    if job_id not in state._job_registry:
        return fail(
            f"Job '{job_id}' not found in registry. Use notify(action='list') to see valid job_ids.",
            trace_id=trace_id,
            error_code="NOT_FOUND",
        )

    if not title and not message:
        return fail(
            "At least one of title or message must be provided for modify.",
            trace_id=trace_id,
            error_code="MISSING_PARAM",
        )

    updated_fields = []

    # Only update fields that are non-empty — this allows partial updates
    # (e.g. update just the title while keeping the existing message).
    if title:
        state._job_registry[job_id]["title"] = title
        updated_fields.append("title")
    if message:
        state._job_registry[job_id]["message"] = message
        updated_fields.append("message")

    state._save_jobs()

    return ok(
        {
            "action_status": "modified",  # semantic status preserved
            "action": "modify",
            "job_id": job_id,
            "updated_fields": updated_fields,
            "title": state._job_registry[job_id].get("title", ""),
            "message": state._job_registry[job_id].get("message", ""),
            "trace_id": trace_id,
        },
        trace_id=trace_id,
    )
