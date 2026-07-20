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

    # -- Per-iteration state --
    # Each entry: {iteration, description, metric, status, commit, content_hash}
    # [v1.4] content_hash added for dedup (N8) — md5 of new_content.
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
