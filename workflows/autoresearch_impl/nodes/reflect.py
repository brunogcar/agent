"""Reflect node — LLM reflects on experiment history every N iterations.

[v1.5 N1] Inspired by karpathy/autoresearch's explicit reflection step.
Every `autoresearch_reflect_interval` iterations (default 5), calls the
planner LLM with the full experiment history and asks it to reflect on
what's working and suggest a strategy for the next few experiments.

The reflection is stored in `state["reflect_notes"]` and included in the
propose node's prompt so the LLM has strategic context, not just raw history.

On non-reflect iterations, this node is a no-op (returns {}).

Module-level import of `_call_planner` from propose creates a
`reflect._call_planner` binding that tests can patch without touching the
real propose module (mirrors the standard `from X import Y` patch idiom).
"""
from __future__ import annotations

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.nodes.propose import _call_planner
from workflows.autoresearch_impl.state import AutoresearchState


REFLECT_SYSTEM = """\
You are a research strategy advisor. Look at the full experiment history and
reflect on what's working and what's not. Then suggest a STRATEGY for the next
few experiments.

Consider:
1. Which types of changes have worked? (e.g., learning rate, architecture, data)
2. Which types have consistently failed?
3. Is there a pattern in the failures? (e.g., all too aggressive, all too conservative)
4. What hasn't been tried yet that might work?
5. Should we switch strategy entirely? (e.g., from hyperparameter tuning to architecture changes)

Return a brief 2-3 paragraph reflection. Be specific — reference actual
experiments by iteration number. End with "NEXT STRATEGY: <one-sentence summary>".
"""


def node_reflect(state: AutoresearchState) -> dict:
    """Reflect on experiment history every N iterations.

    No-op on non-reflect iterations (returns {}).
    On reflect iterations, calls planner LLM with REFLECT_SYSTEM prompt.

    The reflection is stored in `state["reflect_notes"]` (overwriting any prior
    reflection) and surfaced to the next `node_propose` call via a dedicated
    `Strategist reflection` block in the proposal prompt.

    Failures are non-fatal — if the LLM call raises, the node returns `{}`
    so the loop continues with whatever reflection was previously stored
    (or no reflection at all on the first failed attempt).
    """
    tid = state.get("trace_id", "")
    interval = getattr(cfg, "autoresearch_reflect_interval", 5)

    if interval <= 0:
        return {}  # disabled — caller opted out via AUTORESEARCH_REFLECT_INTERVAL=0

    experiment_count = state.get("experiment_count", 0)
    if experiment_count == 0 or experiment_count % interval != 0:
        return {}  # not a reflect iteration (only fires on multiples of `interval`)

    history = state.get("experiment_history", []) or []
    current_best = state.get("current_best", 0.0)
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    goal = state.get("goal", "")

    # Build the reflection prompt from full history (most recent at the end).
    # Cap at 100 entries (matches experiment_history's own cap, v1.3 P2-3) so
    # an overnight run doesn't blow the planner's context window.
    trimmed = history[-100:]
    history_str = "\n".join(
        f"  #{h.get('iteration', '?')} [{h.get('status', '?')}] "
        f"{metric_name}={h.get('metric', '?')} — {h.get('description', '')}"
        for h in trimmed
    )

    user = (
        f"Goal: {goal}\n"
        f"Metric: {metric_name}\n"
        f"Current best: {current_best}\n"
        f"Total experiments: {experiment_count}\n\n"
        f"Full experiment history:\n{history_str}\n\n"
        f"Reflect on what's working and suggest a strategy for the next experiments."
    )

    tracer.step(tid, "reflect", f"reflecting on {experiment_count} experiments (interval={interval})")

    try:
        # Reuse the same _call_planner as propose (subagent dispatch with 3×
        # retry + 2s/4s backoff). Bound at module load so tests can patch
        # `reflect._call_planner` without touching the real propose module.
        # [v1.8 N6] _call_planner now returns (response, usage) tuple — we
        # discard the usage dict here (reflect doesn't track tokens; only
        # node_propose + node_log do, for experiment_history cost tracking).
        reflection, _usage = _call_planner(REFLECT_SYSTEM, user, tid)
        tracer.step(tid, "reflect", f"reflection: {reflection[:200]}")
        return {"reflect_notes": reflection}
    except Exception as e:
        tracer.warning(tid, "reflect", f"reflection failed (non-fatal): {e}")
        return {}  # Non-fatal — continue without updating the prior reflection
