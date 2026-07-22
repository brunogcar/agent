"""State definition for the autoresearch workflow.

[v1.0] AutoresearchState holds the experiment loop state: the goal (metric to
optimize), the target file under modification, the experiment ledger, and the
proposed/current/evaluated experiment for the active iteration.

Unlike autocode (convergent: one task, one branch), autoresearch is
evolutionary: many experiments, one branch, results.tsv ledger. The loop runs
indefinitely until a human interrupts the process.

The TypedDict extends WorkflowState (total=False) so that shared dispatcher
fields (workflow, trace_id, status, error, result, artifacts) are available,
then adds autoresearch-specific fields.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from core.config import cfg
from workflows.base import WorkflowState


class AutoresearchState(WorkflowState, total=False):
    """State for the autoresearch workflow.

    All fields are optional (total=False) because LangGraph nodes return
    PARTIAL dicts — only the keys they actually modify.

    Field groups:
      Identity / inputs:
        goal, trace_id, project_root, target_file, metric_name,
        metric_direction, time_budget, branch, results_path

      Loop bookkeeping:
        experiment_count, baseline_metric, current_best

      Per-iteration state:
        experiment_history, current_experiment, experiment_output,
        current_metric

      LangGraph plumbing:
        messages, status, error, result
    """

    # -- Inputs --
    goal: str                  # what to optimize, e.g. "minimize val_bpb"
    trace_id: str              # tracer ID for this run
    project_root: str          # git repo root where experiments run
    target_file: str           # the file to modify, e.g. "train.py"
    metric_name: str           # e.g. "val_bpb"
    metric_direction: str      # "lower" or "higher"
    time_budget: int           # seconds per experiment run (default 300)
    branch: str                # git branch name for experiments
    results_path: str          # path to results.tsv ledger

    # -- Loop bookkeeping --
    experiment_count: int      # number of experiments completed
    baseline_metric: float     # metric from the unmodified target_file
    current_best: float        # best metric seen so far

    # -- [v1.4] Loop control --
    max_iterations: int         # [v1.4] 0=unlimited; stop after N experiments
    convergence_window: int     # [v1.4] stop after N consecutive non-improvements
    convergence_epsilon: float  # [v1.4] metric plateau threshold

    # -- [v1.5 N1] Reflect node --
    reflect_notes: str          # LLM reflection on strategy (updated every N iterations)
    reflect_interval: int       # [v1.11 A8] reflect every N iterations (0=use cfg default; state-overridable)

    # -- [v1.6] Parallel experiments (batch mode) --
    # parallel_count=N runs N proposals + N subprocesses per iteration.
    # parallel_count=1 (default) preserves v1.5 single-experiment behavior —
    # nodes branch on this and use the singular fields below.
    parallel_count: int          # [v1.6] N parallel experiments per iteration (default 1)
    current_experiments: list[dict]  # [v1.6] N proposals being evaluated
    experiment_outputs: list[str]    # [v1.6] N outputs from N subprocesses
    current_metrics: list[float]     # [v1.6] N metrics from N evaluations

    # -- [v1.7 N3] Resume support --
    resume: bool                # True = skip baseline + branch, reload history from ledger

    # -- [v1.11 A5] Baseline-established flag --
    # Replaces the v1.7 `current_best > 0.0` sentinel for resume detection.
    # Set to True by node_setup after the baseline runs successfully (fresh
    # start) OR when a resume skips the baseline (prior run already established
    # it). The float sentinel broke for metrics that can legitimately be ≤ 0
    # at baseline (log-likelihood, correlation, RMSE-perfect, etc.) — a
    # resumed run with a negative current_best would re-run the baseline,
    # resetting experiment_count=0 + losing experiment_history.
    baseline_established: bool

    # -- [v1.8 N10] Pre-extracted metric (truncation safety) --
    # Set by node_run_experiment (single path) to the metric extracted from the
    # FULL output BEFORE truncation to 50KB. node_evaluate reads this first and
    # skips re-extracting from the (possibly truncated) experiment_output. This
    # prevents false negatives when the metric was printed early and the script
    # produced lots of output after (pushing the metric out of the 50KB tail).
    # None when no metric was found in the full output (evaluate falls back to
    # re-extracting from the truncated output, which will also yield None).
    # Parallel mode does NOT populate this field — the parallel evaluate path
    # extracts per-output metrics from experiment_outputs directly.
    pre_extracted_metric: Optional[float]

    # -- [v1.9-V2 / mistral #10] Pre-extracted metrics in parallel mode --
    # List of metrics extracted from the FULL parallel outputs BEFORE
    # truncation to 50KB. Mirrors `pre_extracted_metric` (singular) for the
    # parallel path — same truncation-safety guarantee (a verbose parallel
    # experiment > 50KB can lose its metric in the truncation tail, just like
    # single mode). `node_evaluate` (parallel path) checks
    # `pre_extracted_metrics[i]` FIRST for each output `i`; when set (not None),
    # it trusts it + skips re-extracting from the (possibly truncated)
    # `experiment_outputs[i]`. Empty list when no metrics were found OR when
    # not in parallel mode (the single path still uses `pre_extracted_metric`
    # singular). Each entry is `None` when no metric was found in that
    # experiment's full output (evaluate falls back to re-extracting from the
    # truncated output, which will also yield None).
    pre_extracted_metrics: list[float]

    # -- [v1.9] Cross-run dedup + reflect-on-iteration parity --
    # iteration_count: incremented by 1 PER ITERATION in node_log (NOT by N —
    #   it counts iterations, not experiments). node_reflect fires on
    #   iteration_count % interval == 0 (was experiment_count). With
    #   parallel_count=4 and interval=5, experiment_count jumps 4→8→12→16→20
    #   and never hits a multiple of 5, so reflect NEVER fired pre-v1.9.
    #   iteration_count fixes this — it advances by 1 per iteration regardless
    #   of parallel_count.
    iteration_count: int

    # seen_hashes: list of md5 content_hash strings (deduped, capped at 1000).
    #   Used by node_modify to detect duplicates that were evicted from the
    #   100-entry experiment_history cap (qwen P2-1). The ledger TSV stores
    #   content_hash as the 6th column (v1.9 A2) — node_setup populates
    #   seen_hashes from the reloaded history on resume. node_log appends each
    #   new hash here too.
    seen_hashes: list[str]

    # consecutive_discards: count of trailing experiment_history entries with
    #   status="discard". Recomputed on resume by scanning the reloaded history
    #   tail (qwen P1-2). Was: reset to 0 on resume — convergence detector
    #   wouldn't fire until N MORE discards happened (4+10=14 total instead of 10).
    consecutive_discards: int

    # consecutive_no_improvement: count of trailing history entries whose
    #   metric is NOT strictly better than current_best (per direction).
    #   Recomputed on resume alongside consecutive_discards.
    consecutive_no_improvement: int

    # -- Per-iteration state --
    # Each entry: {iteration, description, metric, status, commit, content_hash, tokens}
    # [v1.4] content_hash added for dedup (N8) — md5 of new_content.
    # [v1.8 N6] tokens added — total LLM tokens used by the planner call.
    experiment_history: list[dict]
    current_experiment: dict   # the proposed experiment being run
    experiment_output: str     # stdout/stderr from the last experiment run
    current_metric: float      # metric extracted from the last run

    # -- LangGraph plumbing --
    messages: Annotated[list[AnyMessage], add_messages]
    status: str                # "running" | "success" | "failed"
    error: str
    result: str


def _default_state(
    goal: str = "",
    trace_id: str = "",
    project_root: str = "",
    target_file: str = "",
    metric_name: str = "",
    metric_direction: str = "lower",
    time_budget: Optional[int] = None,
    branch: str = "",
    results_path: str = "",
    max_iterations: int = 0,
    convergence_window: int = 10,
    convergence_epsilon: float = 0.001,
    parallel_count: int = 1,
    reflect_interval: int = 0,
) -> dict:
    """Create a default state dictionary for the autoresearch workflow.

    Pulls sane defaults from cfg (autoresearch_time_budget, autoresearch_target_file,
    autoresearch_metric_name, autoresearch_metric_direction) so callers don't
    have to repeat themselves.

    Args:
        goal: What to optimize, e.g. "minimize val_bpb".
        trace_id: Trace ID (created by run_workflow if empty).
        project_root: Git repo root. Defaults to cfg.workspace_root.
        target_file: File to modify. Defaults to cfg.autoresearch_target_file.
        metric_name: Metric to extract from experiment output.
        metric_direction: "lower" or "higher" (which is better).
        time_budget: Per-experiment wall-clock budget in seconds.
        branch: Git branch for experiment commits.
        results_path: Path to results.tsv ledger.
        max_iterations: [v1.4] Stop after N experiments. 0=unlimited (legacy).
        convergence_window: [v1.4] Stop after N consecutive non-improvements.
        convergence_epsilon: [v1.4] Metric plateau threshold (stuck detector).
        parallel_count: [v1.6] Run N proposals + N subprocesses per iteration.
            1 (default) preserves v1.5 single-experiment behavior.
        reflect_interval: [v1.11 A8] Reflect every N iterations. 0 = use
            `cfg.autoresearch_reflect_interval` (env: AUTORESEARCH_REFLECT_INTERVAL,
            default 5). Allows per-invocation override of the reflect cadence
            (was: only configurable via global env var).

    Returns:
        A dict suitable as LangGraph initial state.
    """
    if not target_file:
        target_file = cfg.autoresearch_target_file
    if not metric_name:
        metric_name = cfg.autoresearch_metric_name
    if not metric_direction:
        metric_direction = cfg.autoresearch_metric_direction
    if time_budget is None:
        time_budget = cfg.autoresearch_time_budget
    if not project_root:
        project_root = str(getattr(cfg, "workspace_root", ""))

    # [v1.4] Pull loop-control defaults from cfg (env-overridable).
    if max_iterations == 0:
        max_iterations = int(getattr(cfg, "autoresearch_max_iterations", 0))
    if convergence_window == 10:
        convergence_window = int(getattr(cfg, "autoresearch_convergence_window", 10))
    if convergence_epsilon == 0.001:
        convergence_epsilon = float(getattr(cfg, "autoresearch_convergence_epsilon", 0.001))

    # [v1.6] Pull parallel_count from cfg (env-overridable via
    # AUTORESEARCH_PARALLEL_COUNT). The caller's explicit value wins when > 1;
    # default 1 falls through to the cfg default (also 1 unless overridden).
    if parallel_count == 1:
        parallel_count = int(getattr(cfg, "autoresearch_parallel_count", 1))

    # [v1.11 A8] Pull reflect_interval from cfg when caller didn't override.
    # 0 = "use cfg default" (env AUTORESEARCH_REFLECT_INTERVAL, default 5).
    # Non-zero caller value wins (per-invocation override).
    if reflect_interval == 0:
        reflect_interval = int(getattr(cfg, "autoresearch_reflect_interval", 5))

    return {
        "workflow": "autoresearch",
        "goal": goal,
        "trace_id": trace_id,
        "project_root": project_root,
        "target_file": target_file,
        "metric_name": metric_name,
        "metric_direction": metric_direction,
        "time_budget": time_budget,
        "branch": branch,
        "results_path": results_path,
        "experiment_count": 0,
        "baseline_metric": 0.0,
        "current_best": 0.0,
        "max_iterations": max_iterations,
        "convergence_window": convergence_window,
        "convergence_epsilon": convergence_epsilon,
        "reflect_notes": "",
        "reflect_interval": reflect_interval,  # [v1.11 A8] state-overridable
        "parallel_count": parallel_count,
        "current_experiments": [],
        "experiment_outputs": [],
        "current_metrics": [],
        "resume": False,  # [v1.7 N3] default False — only True on checkpoint resume
        "baseline_established": False,  # [v1.11 A5] replaces current_best>0 sentinel
        "pre_extracted_metric": None,  # [v1.8 N10] single-path; cleared in parallel
        "pre_extracted_metrics": [],  # [v1.9-V2 / mistral #10] parallel-path; empty in single mode
        "iteration_count": 0,  # [v1.9] incremented by 1 per iteration (not by N)
        "seen_hashes": [],  # [v1.9] dedup across history cap (qwen P2-1)
        "consecutive_discards": 0,  # [v1.9] recomputed on resume (qwen P1-2)
        "consecutive_no_improvement": 0,  # [v1.9] recomputed on resume
        "experiment_history": [],
        "current_experiment": {},
        "experiment_output": "",
        "current_metric": 0.0,
        "messages": [],
        "status": "running",
        "error": "",
        "result": "",
        "artifacts": [],
    }
