"""Node: propose — LLM proposes the next experiment.

[v1.1+] Dispatches the planner LLM via `agent(action="subagent", role="planner")`
for isolated curated-context dispatch (was: `autocode_impl.helpers._call()` in
v1.0). The subagent gets a fresh LLM call with NO session history — only:
  - the optimization goal (e.g. "minimize val_bpb")
  - the metric name and direction
  - the current best metric
  - the experiment history (descriptions + metrics + outcomes)
  - the current target_file content

The subagent returns a JSON object describing the proposed change:
  {
    "description": "Increase learning rate from 1e-4 to 3e-4",
    "rationale":   "Current LR is conservative; larger LR may converge faster.",
    "new_content": "<the FULL new content of the target file after your change>"
  }

[v1.2] Hardening: `_PROPOSE_JSON_SCHEMA` enforcement added (was prompt-only).
Removed duplicate `history_str` from `context` param (was in both `user` and
`context` — wasted tokens).

On subagent failure, `_call_planner` raises `RuntimeError`; `node_propose`
catches it and returns `status="failed"`. There is NO `_call()` fallback —
a subagent failure halts the current iteration (v1.2.2 doc fix: earlier docs
incorrectly claimed a fallback existed).

The propose node only produces the proposal — modify.py applies it. This
separation lets us retry modify without re-querying the LLM if the patch
fails to apply.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


_PROPOSE_SYSTEM = """\
You are an autonomous research engineer. Your job is to propose the NEXT
single experiment that has the highest chance of improving the target metric.

You will be given:
- The optimization goal (e.g., "minimize val_bpb")
- The metric name and direction (lower is better / higher is better)
- The current best metric value
- A history of past experiments (description + metric + outcome)
- The current content of the target file you may modify

Think carefully about what change is most likely to help. Consider:
1. Past experiments — what worked, what didn't, and WHY.
2. Common ML/engineering heuristics that haven't been tried yet.
3. Small, surgical changes are easier to reason about than large rewrites.

Return STRICT JSON with these keys:
{
  "description": "<one-sentence description of the change>",
  "rationale":   "<1-2 sentences explaining why this might help>",
  "new_content": "<the FULL new content of the target file after your change>"
}

Do NOT include any text outside the JSON object.
"""


def _format_history(history: list[dict], metric_name: str, limit: int = 20) -> str:
    """Format experiment_history for the LLM prompt.

    Shows the most recent `limit` experiments (most-recent first) with their
    descriptions, metrics, and outcomes (keep/discard/baseline).
    """
    if not history:
        return "(no prior experiments — this is the first proposed change)"
    # Most recent first, capped at `limit` entries
    recent = list(reversed(history[-limit:]))
    lines = []
    for h in recent:
        it = h.get("iteration", "?")
        desc = h.get("description", "(no description)")
        metric = h.get("metric", "")
        status = h.get("status", "")
        lines.append(f"  #{it} [{status}] {metric_name}={metric} — {desc}")
    return "\n".join(lines)


def _read_target_file(target_file: str, project_root: str) -> str:
    """Read the current content of the target file.

    Returns an empty string on read failure (the LLM can still propose a
    full rewrite based on the description).
    """
    try:
        path = Path(project_root) / target_file if project_root else Path(target_file)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


_PROPOSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "rationale": {"type": "string"},
        "new_content": {"type": "string"},
    },
    "required": ["description", "rationale", "new_content"],
    "additionalProperties": False,
}


def _call_planner(system: str, user: str, tid: str = "") -> str:
    """Call the planner LLM via subagent dispatch.

    [v1.2] Hardening: added json_schema enforcement. Removed context param
    (was duplicating history_str already in user — Kimi B2 finding).
    """
    import json as _json
    from tools.agent import agent
    result = agent(
        action="subagent",
        role="planner",
        task=user,
        system=system,
        json_schema=_json.dumps(_PROPOSE_JSON_SCHEMA),  # [Hardening] enforce schema
        trace_id=tid,
    )
    if result.get("status") == "success":
        return result.get("response", "")
    raise RuntimeError(f"Subagent planner failed: {result.get('error', 'unknown')}")


def _parse_proposal(raw: str) -> dict:
    """Parse the LLM's JSON response into a proposal dict.

    Falls back to {"description": raw, "new_content": ""} on parse failure
    so the workflow can still record the attempt in the ledger.
    """
    from core.json_extract import extract_json
    data = extract_json(raw)
    if not isinstance(data, dict):
        return {
            "description": "(unparseable proposal)",
            "rationale": raw[:500],
            "new_content": "",
        }
    return {
        "description": str(data.get("description", "")).strip(),
        "rationale": str(data.get("rationale", "")).strip(),
        "new_content": str(data.get("new_content", "")).strip(),
    }


def node_propose(state: AutoresearchState) -> dict:
    """Propose the next experiment via the planner LLM.

    Returns a partial state dict with `current_experiment` set to the
    proposal dict {iteration, description, rationale, new_content}.
    """
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    metric_direction = state.get("metric_direction", "") or cfg.autoresearch_metric_direction
    current_best = state.get("current_best", 0.0)
    history = state.get("experiment_history", []) or []
    target_file = state.get("target_file", "") or cfg.autoresearch_target_file
    project_root = state.get("project_root", "")

    iteration = state.get("experiment_count", 0) + 1
    tracer.step(tid, "propose", f"iteration {iteration}: querying planner")

    current_content = _read_target_file(target_file, project_root)
    history_str = _format_history(history, metric_name)

    user = (
        f"Goal: {goal}\n"
        f"Metric: {metric_name} ({metric_direction} is better)\n"
        f"Current best: {current_best}\n"
        f"Target file: {target_file}\n\n"
        f"Past experiments (most recent first):\n{history_str}\n\n"
        f"Current target file content:\n```\n{current_content}\n```\n\n"
        f"Propose the next experiment. Return STRICT JSON with keys: "
        f"description, rationale, new_content."
    )

    try:
        raw = _call_planner(_PROPOSE_SYSTEM, user, tid)
    except Exception as e:
        tracer.error(tid, "propose", f"planner LLM call failed: {e}")
        return {
            "current_experiment": {
                "iteration": iteration,
                "description": f"(LLM call failed: {e})",
                "rationale": "",
                "new_content": "",
            },
            "status": "failed",
            "error": f"planner LLM call failed: {e}",
        }

    proposal = _parse_proposal(raw)
    proposal["iteration"] = iteration
    tracer.step(tid, "propose", f"proposed: {proposal.get('description', '')[:80]}")

    return {
        "current_experiment": proposal,
        "status": "running",
        "error": "",
    }
