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

[v1.3 P1-2] `_call_planner` now retries the subagent call up to 3×
(1 initial + 2 retries) with exponential backoff (2s, 4s). Was: single
attempt → any transient subagent failure (network blip, rate limit) halted
the iteration. The retry uses string-matching on the exception type so we
don't need a hard dependency on langgraph.errors.GraphRecursionError.

[v1.3 P1-5] `node_propose` caps `current_content` at
`cfg.autocode_max_file_chars` (default 6000) before sending to the LLM.
Was: a 50KB target_file would burn ~12K tokens per iteration just for
context, blowing the context window on long files.

On subagent failure (after all retries), `_call_planner` raises
`RuntimeError`; `node_propose` catches it and returns `status="failed"`.
There is NO `_call()` fallback — a subagent failure halts the current
iteration (v1.2.2 doc fix: earlier docs incorrectly claimed a fallback
existed).

[v1.6] When `parallel_count > 1`, `node_propose` dispatches N parallel
`_call_planner` calls via ThreadPoolExecutor(max_workers=N) — each with the
SAME prompt (the LLM is expected to produce different proposals due to
sampling temperature). Per-call failures (after the v1.3 P1-2 retry logic)
are recorded as failed-proposal placeholders so the batch isn't aborted by
one bad call. The N parsed proposals are stored in `current_experiments`
(plural); the first is mirrored to `current_experiment` (singular) for
v1.5 backward compat. When `parallel_count == 1`, the v1.5 single-call
path runs unchanged.

[v1.8 N6] `_call_planner` now returns a `(response, usage)` tuple instead
of just the response string. `usage` is the dict returned by the subagent
dispatch (has `total` / `prompt` / `completion` token counts). The total
token count is captured on the proposal as `proposal["tokens"]` (both
single and parallel paths) and persisted in `experiment_history` entries
by `node_log._build_history_entry`. Operators can sum `tokens` across
history entries to estimate LLM cost per run. When `usage` is missing or
malformed (older subagent versions, mocked tests), `tokens` defaults to 0.

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


def _call_planner(system: str, user: str, tid: str = "") -> tuple[str, dict]:
    """Call the planner LLM via subagent dispatch.

    [v1.2] Hardening: added json_schema enforcement. Removed context param
    (was duplicating history_str already in user — Kimi B2 finding).

    [v1.3 P1-2] Added 3× retry with exponential backoff (2s, 4s).
    Transient subagent failures (network blips, rate limits, provider 5xx)
    used to halt the iteration immediately. Now we retry up to 2 times
    before giving up and raising RuntimeError. Raises only after all 3
    attempts fail.

    [v1.8 N6] Returns a `(response, usage)` tuple instead of just the
    response string. `usage` is the dict returned by the subagent dispatch
    (has `total` / `prompt` / `completion` token counts). Callers capture
    `usage.get("total", 0)` on the proposal as `proposal["tokens"]` for
    cost tracking. When `usage` is missing or malformed (older subagent
    versions, mocked tests), an empty dict is returned — callers default
    `tokens` to 0 via `usage.get("total", 0)`.

    Returns:
        `(response_text, usage_dict)` — the LLM response string + the usage
        dict from the subagent dispatch. `usage_dict` is `{}` when the
        subagent didn't report usage (older versions / mocks).

    Raises:
        RuntimeError: after all 3 attempts fail.
    """
    import json as _json
    from tools.agent import agent

    last_error = None
    for attempt in range(3):  # 1 initial + 2 retries
        try:
            result = agent(
                action="subagent",
                role="planner",
                task=user,
                system=system,
                json_schema=_json.dumps(_PROPOSE_JSON_SCHEMA),
                trace_id=tid,
            )
            if result.get("status") == "success":
                # [v1.8 N6] Capture usage dict for token tracking. Older
                # subagent versions / mocked tests may not include `usage` —
                # default to {} so callers' `usage.get("total", 0)` yields 0.
                usage = result.get("usage", {}) or {}
                return result.get("response", ""), usage
            last_error = result.get("error", "unknown")
        except Exception as e:
            last_error = str(e)
        # Brief backoff before retry (2s, 4s) — only between attempts, not after the last.
        if attempt < 2:
            import time as _time
            _time.sleep(2 ** (attempt + 1))

    raise RuntimeError(f"Subagent planner failed after 3 attempts: {last_error}")


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


def _generate_single_proposal(system: str, user: str, tid: str, iteration: int) -> dict:
    """[v1.6] Call the planner once, parse, and return a proposal dict.

    Extracted from `node_propose` so the parallel path can call it N times
    via ThreadPoolExecutor. Both paths share the same prompt-building +
    parsing logic — only the dispatch differs (1 call vs N parallel calls).

    Raises:
        RuntimeError: if `_call_planner` fails after all retries (v1.3 P1-2).
            The parallel caller catches this and records a failed-proposal
            placeholder so the batch isn't aborted by one bad call.

    Args:
        system: System prompt (the _PROPOSE_SYSTEM constant).
        user: User prompt (built once, reused for all N parallel calls —
            the LLM is expected to produce different proposals due to
            sampling temperature).
        tid: Trace ID for observability.
        iteration: The iteration number to stamp on the returned proposal.

    Returns:
        Parsed proposal dict with `iteration` and `tokens` set. `tokens`
        is the total LLM token count from the subagent's `usage` dict
        (v1.8 N6) — 0 when usage is unavailable.
    """
    raw, usage = _call_planner(system, user, tid)
    proposal = _parse_proposal(raw)
    proposal["iteration"] = iteration
    proposal["tokens"] = usage.get("total", 0)  # [v1.8 N6] total tokens used
    return proposal


def node_propose(state: AutoresearchState) -> dict:
    """Propose the next experiment via the planner LLM.

    Returns a partial state dict with `current_experiment` set to the
    proposal dict {iteration, description, rationale, new_content}.

    [v1.6] When `parallel_count > 1`, generates N proposals in parallel
    via ThreadPoolExecutor(max_workers=N). Each call uses the SAME prompt
    — the LLM is expected to produce different proposals due to sampling
    temperature. Stores all N in `current_experiments` (plural) AND mirrors
    the first to `current_experiment` (singular) for v1.5 backward compat.
    When `parallel_count == 1`, behaves exactly as v1.5 (single call,
    single result in `current_experiment`).
    """
    tid = state.get("trace_id", "")
    goal = state.get("goal", "")
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    metric_direction = state.get("metric_direction", "") or cfg.autoresearch_metric_direction
    current_best = state.get("current_best", 0.0)
    history = state.get("experiment_history", []) or []
    target_file = state.get("target_file", "") or cfg.autoresearch_target_file
    project_root = state.get("project_root", "")
    experiment_count = state.get("experiment_count", 0)
    # [v1.6] parallel_count=1 (default) preserves v1.5 single-experiment
    # behavior. > 1 activates the parallel proposal path.
    parallel_count = int(state.get("parallel_count", 1) or 1)

    iteration = experiment_count + 1
    tracer.step(tid, "propose", f"iteration {iteration}: querying planner")

    current_content = _read_target_file(target_file, project_root)
    # [v1.3 P1-5] Cap target file content to prevent context window overflow.
    # Was: a 50KB target_file would burn ~12K tokens per iteration just for
    # context, blowing the context window on long files. Cap to first/last
    # half of cfg.autocode_max_file_chars (default 6000) so the LLM sees
    # both the imports/structure (top) and the recent changes (bottom).
    max_chars = getattr(cfg, "autocode_max_file_chars", 6000)
    if len(current_content) > max_chars:
        half = max_chars // 2
        original_len = len(current_content)
        current_content = (
            current_content[:half]
            + f"\n... [TRUNCATED — file is {original_len} chars, showing first {half} + last {half}] ...\n"
            + current_content[-half:]
        )
        tracer.warning(
            tid, "propose",
            f"target file truncated from {original_len} to {max_chars} chars "
            f"(autocode_max_file_chars)",
        )

    history_str = _format_history(history, metric_name)

    # [v1.5 N1] Include reflection notes in the prompt (if available).
    # The reflect node (runs every N iterations, default 5) writes a strategy
    # summary to state["reflect_notes"]. When present, we surface it so the
    # LLM has strategic context, not just raw experiment history.
    reflect_notes = state.get("reflect_notes", "")
    reflect_block = ""
    if reflect_notes:
        reflect_block = (
            f"\n\nStrategist reflection (from iteration {experiment_count}):\n"
            f"{reflect_notes}\n"
        )

    # [v1.5 N4] Recall procedural memories (cross-run learning).
    # When a proposal type has repeatedly failed in this or prior runs, a
    # procedural memory is stored via memory.store_procedural(). Recall
    # those memories here so the LLM doesn't re-propose known-bad strategies.
    # Failures are non-fatal — memory may not be available (e.g. tests).
    memory_block = ""
    try:
        from core.memory_engine import memory
        memories = memory.recall(
            query=f"autoresearch {goal} {metric_name}",
            collections=["procedural"],
            top_k=3,
            min_score=0.3,
            trace_id=tid,
        )
        if memories:
            memory_lines = [f"  - {m.get('text', '')[:200]}" for m in memories]
            memory_block = (
                "\n\nPast learned rules (from previous runs):\n"
                + "\n".join(memory_lines) + "\n"
            )
    except Exception:
        pass  # Non-fatal — memory may not be available

    user = (
        f"Goal: {goal}\n"
        f"Metric: {metric_name} ({metric_direction} is better)\n"
        f"Current best: {current_best}\n"
        f"Target file: {target_file}\n\n"
        f"Past experiments (most recent first):\n{history_str}\n\n"
        f"Current target file content:\n```\n{current_content}\n```\n"
        f"{reflect_block}{memory_block}\n"
        f"Propose the next experiment. Return STRICT JSON with keys: "
        f"description, rationale, new_content."
    )

    # ── [v1.6] Parallel path: N proposals via ThreadPoolExecutor ───────────
    # Each call uses the SAME prompt — the LLM is expected to produce
    # different proposals due to sampling temperature. Per-call failures
    # (after the v1.3 P1-2 retry logic) are recorded as failed-proposal
    # placeholders so the batch isn't aborted by one bad call.
    if parallel_count > 1:
        import concurrent.futures

        tracer.step(
            tid, "propose",
            f"parallel mode: generating {parallel_count} proposals concurrently",
        )

        proposals: list[dict] = []
        fail_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as pool:
            future_to_iter = {}
            for i in range(parallel_count):
                it = experiment_count + 1 + i
                fut = pool.submit(_generate_single_proposal, _PROPOSE_SYSTEM, user, tid, it)
                future_to_iter[fut] = it

            for future in concurrent.futures.as_completed(future_to_iter):
                it = future_to_iter[future]
                try:
                    proposal = future.result()
                    proposals.append(proposal)
                    tracer.step(
                        tid, "propose",
                        f"parallel proposal iter {it}: {proposal.get('description', '')[:80]}",
                    )
                except Exception as e:
                    fail_count += 1
                    tracer.warning(
                        tid, "propose",
                        f"parallel proposal iter {it} failed: {e}",
                    )
                    proposals.append({
                        "iteration": it,
                        "description": f"(LLM call failed: {e})",
                        "rationale": "",
                        "new_content": "",
                        "status": "failed",  # signals modify/run to skip
                    })

        # Sort by iteration so the order matches the batch indices downstream.
        proposals.sort(key=lambda p: p.get("iteration", 0))

        # If ALL N calls failed, propagate status="failed" (mirrors v1.5
        # single-call failure behavior). Otherwise status="running" —
        # individual failed proposals are handled per-experiment downstream.
        if fail_count == parallel_count:
            return {
                "current_experiments": proposals,
                "current_experiment": proposals[0] if proposals else {},
                "status": "failed",
                "error": f"all {parallel_count} parallel planner calls failed",
            }

        return {
            "current_experiments": proposals,
            # Mirror the first proposal for v1.5 backward compat (singular
            # field is still used by node_modify / node_run_experiment /
            # node_evaluate / node_decide / node_log when parallel_count==1;
            # the parallel path reads the plural fields).
            "current_experiment": proposals[0] if proposals else {},
            "status": "running",
            "error": "",
        }

    # ── v1.5 single-proposal path (unchanged) ──────────────────────────────
    try:
        # [v1.8 N6] _call_planner now returns (response, usage) tuple.
        # usage is the dict from the subagent dispatch (has total/prompt/
        # completion token counts). Capture total on the proposal for
        # cost tracking — node_log persists it in experiment_history entries.
        raw, usage = _call_planner(_PROPOSE_SYSTEM, user, tid)
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
    proposal["tokens"] = usage.get("total", 0)  # [v1.8 N6] total tokens used
    tracer.step(tid, "propose", f"proposed: {proposal.get('description', '')[:80]}")

    return {
        "current_experiment": proposal,
        "status": "running",
        "error": "",
    }
