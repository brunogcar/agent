"""Node: run_experiment — Execute the target_file as a time-boxed subprocess.

[v1.0] Runs the (now-modified) target_file as a subprocess, captures stdout
+ stderr, and stores the combined output in state.experiment_output.

The subprocess is time-boxed via state.time_budget (default 300s). If the
budget is exceeded, the subprocess is killed and a sentinel message is
appended to the output so the evaluate node can detect the timeout.

Returns a PARTIAL state dict with `experiment_output` and a status flag.

[v1.3 P2-1] `_run_subprocess` removed — replaced with the shared
`workflows.autoresearch_impl.helpers.run_target_subprocess`. The two
originals (in setup.py + run_experiment.py) had drifted in subtle ways
(one caught FileNotFoundError, the other didn't); consolidating eliminates
that drift.

[v1.6] When `parallel_count > 1`, runs each of the N temp files in
`{project_root}/.autoresearch/parallel/{i}/{target_file}` concurrently via
ThreadPoolExecutor(max_workers=N). Each subprocess runs in its OWN temp
dir as cwd so relative paths still resolve correctly. Experiments whose
temp file is missing (because `node_modify` marked them failed) get a
"skipped" sentinel output — `node_evaluate` will extract no metric and
`node_decide` will discard them. The N outputs are stored in
`experiment_outputs` (plural); the first is mirrored to
`experiment_output` (singular) for v1.5 backward compat. When
`parallel_count == 1`, the v1.5 single-subprocess path runs unchanged.

[v1.8 N5] Full output logging — BEFORE truncation, the full stdout+stderr
is written to `{results_path}.d/{iteration}.log` (single mode) or
`{results_path}.d/{iteration}_{i}.log` (parallel mode, one per experiment).
Operators can inspect the full output for debugging when the truncated
state copy doesn't have enough context. Non-fatal — disk errors don't
halt the loop.

[v1.8 N10] Pre-extract metric BEFORE truncation — the single-mode path now
extracts the metric from the FULL output before truncating to 50KB, and
stores it in `pre_extracted_metric`. `node_evaluate` reads this first and
skips re-extracting from the (possibly truncated) `experiment_output`.
Prevents false negatives when the metric was printed early and the script
produced lots of output after, pushing the metric out of the 50KB tail.
Parallel mode does NOT pre-extract (its evaluate path handles N outputs
individually — pre-extraction would need a list; deferred until needed).
"""
from __future__ import annotations

import subprocess
import sys

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState
from workflows.autoresearch_impl.helpers import run_target_subprocess as _run_subprocess
from workflows.autoresearch_impl.helpers import extract_metric as _extract_metric

# v1.3 (P2-1): _run_subprocess now imported from helpers.py (was a local copy).
# v1.8 (N10): _extract_metric imported here too — used to pre-extract the
# metric from the FULL output before truncation (single-mode path only).


def _write_full_output_log(
    results_path: str,
    iteration: int,
    output: str,
    slot: int = -1,
) -> None:
    """[v1.8 N5] Write the FULL output to a per-iteration log file.

    Writes to `{results_path}.d/{iteration}.log` (single mode, slot=-1) or
    `{results_path}.d/{iteration}_{slot}.log` (parallel mode, slot=i).

    Non-fatal — disk errors are swallowed so the experiment loop is never
    blocked by a log-write failure. Operators can inspect the full output
    for debugging when the truncated state copy doesn't have enough context.

    Args:
        results_path: Path to the results.tsv ledger. The log dir is its
            sibling: `{results_path}.d/`.
        iteration: The 1-indexed iteration number (experiment_count + 1).
        output: The full stdout+stderr captured from the subprocess (BEFORE
            any truncation).
        slot: For parallel mode, the per-experiment slot index (0-based).
            -1 (default) means single mode — the filename is just
            `{iteration}.log`.
    """
    if not results_path:
        return
    try:
        from pathlib import Path
        log_dir = Path(f"{results_path}.d")
        log_dir.mkdir(parents=True, exist_ok=True)
        if slot >= 0:
            log_file = log_dir / f"{iteration}_{slot}.log"
        else:
            log_file = log_dir / f"{iteration}.log"
        log_file.write_text(output, encoding="utf-8")
    except Exception:
        pass  # Non-fatal — log-write failure must NOT block the loop


def node_run_experiment(state: AutoresearchState) -> dict:
    """Run the modified target_file as a subprocess.

    Returns a partial state dict with `experiment_output`.

    [v1.6] When `parallel_count > 1`, runs N subprocesses concurrently via
    ThreadPoolExecutor — one per temp dir under
    `{project_root}/.autoresearch/parallel/{i}/`. Per-experiment failures
    (missing temp file → sentinel output, timeout, crash) are isolated;
    the batch is never aborted by a single bad subprocess.

    [v1.8 N5] In BOTH single and parallel paths, writes the FULL output to
    `{results_path}.d/{iteration}.log` (or `{iteration}_{i}.log` in parallel
    mode) BEFORE truncation — operators can inspect the full output for
    debugging. Non-fatal.

    [v1.8 N10] In the single path, extracts the metric from the FULL output
    BEFORE truncation and stores it in `pre_extracted_metric`. `node_evaluate`
    reads this first (skipping re-extraction from the truncated output),
    preventing false negatives when the metric was printed early and the
    script produced lots of output after.
    """
    tid = state.get("trace_id", "")
    target_file = state.get("target_file", "") or cfg.autoresearch_target_file
    project_root = state.get("project_root", "")
    time_budget = state.get("time_budget", cfg.autoresearch_time_budget)
    parallel_count = int(state.get("parallel_count", 1) or 1)

    # ── [v1.6] Parallel path: N subprocesses via ThreadPoolExecutor ────────
    if parallel_count > 1:
        import concurrent.futures
        from pathlib import Path

        proposals = state.get("current_experiments", []) or []
        base_path = Path(project_root) if project_root else Path(".")
        parallel_dir = base_path / ".autoresearch" / "parallel"

        n = len(proposals)
        tracer.step(
            tid, "run_experiment",
            f"parallel mode: running {n} subprocesses concurrently (budget={time_budget}s)",
        )

        def _run_one(i: int) -> str:
            """Run experiment i in its own temp dir; return captured output."""
            exp_dir = parallel_dir / str(i)
            target_path = exp_dir / target_file
            if not target_path.exists():
                # modify marked this proposal failed (empty content / dedup /
                # path / protected) — never wrote the temp file. Return a
                # sentinel so evaluate extracts no metric and decide discards.
                return f"[autoresearch] experiment {i} skipped — file not found\n"
            return _run_subprocess(str(target_path), str(exp_dir), time_budget)

        results: list[str] = [""] * n
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as pool:
            future_to_idx = {pool.submit(_run_one, i): i for i in range(n)}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    # Isolated failure — don't abort the batch. evaluate will
                    # extract no metric from this sentinel and decide will
                    # discard this experiment.
                    tracer.warning(
                        tid, "run_experiment",
                        f"parallel experiment {idx} crashed: {e}",
                    )
                    results[idx] = (
                        f"[autoresearch] experiment {idx} crashed: "
                        f"{type(e).__name__}: {e}\n"
                    )

        # [v1.8 N5] Write each output to its own per-iteration log file BEFORE
        # truncation. One log per experiment: `{iteration}_{i}.log`. Iteration
        # is computed from experiment_count + 1 (matches the singular path).
        # Non-fatal — disk errors don't halt the loop.
        results_path = state.get("results_path", "")
        iteration = state.get("experiment_count", 0) + 1
        for i, output in enumerate(results):
            if output:
                _write_full_output_log(results_path, iteration, output, slot=i)

        # Truncate very large outputs to prevent state bloat. 50KB each is
        # enough for evaluate to find the metric (usually printed at the end)
        # while keeping the trace log + state dict manageable.
        for i, output in enumerate(results):
            if output and len(output) > 50_000:
                results[i] = output[-50_000:]
                tracer.warning(
                    tid, "run_experiment",
                    f"parallel experiment {i} output truncated to last 50KB",
                )

        return {
            "experiment_outputs": results,
            # Mirror the first output for v1.5 backward compat (singular
            # field is used by node_evaluate when parallel_count==1).
            "experiment_output": results[0] if results else "",
            "status": "running",
            "error": "",
            # [v1.8 N10] Parallel mode does NOT pre-extract — the parallel
            # evaluate path extracts per-output metrics from experiment_outputs
            # directly. Explicitly clear pre_extracted_metric so a stale value
            # from a prior single-mode iteration doesn't leak in.
            "pre_extracted_metric": None,
        }

    # ── v1.5 single-subprocess path (unchanged) ────────────────────────────
    # If modify failed, skip the run — decide will discard.
    if state.get("status") == "failed":
        tracer.step(tid, "run_experiment", "skipping run — prior node failed")
        # [v1.8 N10] Clear pre_extracted_metric on the skip path too — a stale
        # value from a prior iteration would mislead evaluate.
        return {
            "experiment_output": state.get("experiment_output", ""),
            "pre_extracted_metric": None,
        }

    tracer.step(
        tid, "run_experiment",
        f"running {target_file} (budget={time_budget}s) @ {project_root or 'cwd'}",
    )
    output = _run_subprocess(target_file, project_root, time_budget)

    # [v1.8 N5] Write the FULL output to a per-iteration log file BEFORE any
    # truncation. Operators can inspect the full output for debugging when
    # the truncated state copy doesn't have enough context. Non-fatal.
    results_path = state.get("results_path", "")
    iteration = state.get("experiment_count", 0) + 1
    _write_full_output_log(results_path, iteration, output)

    # [v1.8 N10] Extract metric BEFORE truncation — prevents false negatives
    # when the metric is printed early and the script produces lots of output
    # after (pushing the metric out of the 50KB tail). node_evaluate reads
    # this first and skips re-extracting from the (possibly truncated) output.
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    pre_extracted_metric = _extract_metric(output, metric_name)
    if pre_extracted_metric is not None:
        tracer.step(
            tid, "run_experiment",
            f"pre-extracted {metric_name}={pre_extracted_metric} from full output "
            f"({len(output)} chars before truncation)",
        )

    # Truncate very large outputs to prevent state bloat. 50KB is enough for
    # the evaluate node to find the metric (usually printed at the end) while
    # keeping the trace log manageable. Truncation happens AFTER the metric
    # has been pre-extracted above (v1.8 N10).
    if len(output) > 50_000:
        output = output[-50_000:]
        tracer.warning(tid, "run_experiment", f"output truncated to last 50KB (was larger)")

    return {
        "experiment_output": output,
        "pre_extracted_metric": pre_extracted_metric,  # [v1.8 N10]
        "status": "running",
        "error": "",
    }
