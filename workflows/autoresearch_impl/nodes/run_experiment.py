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

[v1.8 N5 / v1.9-V2 correction #1] Full output logging — BEFORE truncation,
the full stdout+stderr is written to `{project_root}/.autoresearch/logs/
{iteration}.log` (single mode) or `{project_root}/.autoresearch/logs/
{iteration}_{i}.log` (parallel mode, one per experiment). Operators can
inspect the full output for debugging when the truncated state copy doesn't
have enough context. Non-fatal — disk errors don't halt the loop.

[v1.9-V2 correction #1] Log dir relocated from `logs/autoresearch/` (which
lived at the project root level) to `{project_root}/.autoresearch/logs/` —
mirrors the `.understand` project-scoped pattern (`.autoresearch/` already
holds the `parallel/` subdir; `logs/` lives alongside it).

[v1.8 N10 / v1.9-V2 mistral #10] Pre-extract metric BEFORE truncation — the
single-mode path extracts the metric from the FULL output before truncating
to 50KB and stores it in `pre_extracted_metric`. The parallel-mode path
extracts each per-output metric into `pre_extracted_metrics` (plural list).
`node_evaluate` reads these FIRST and skips re-extracting from the (possibly
truncated) `experiment_output` / `experiment_outputs`. Prevents false
negatives when the metric was printed early and the script produced lots of
output after, pushing the metric out of the 50KB tail. Single path clears
`pre_extracted_metrics=[]`; parallel path clears `pre_extracted_metric=None`
(backward compat — singular field not used in parallel).
"""
from __future__ import annotations

import subprocess
import sys

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState
from workflows.autoresearch_impl.helpers import run_target_subprocess as _run_subprocess
from workflows.autoresearch_impl.helpers import extract_metric as _extract_metric


def _is_cancelled(tid: str) -> bool:
    """[v1.10 / Phase B] Lazy + safe cancellation check.

    Wraps `workflows.base.is_workflow_cancelled` in a try/except so a broken
    import doesn't crash the node. Returns False on any failure — fail-open
    so a broken cancellation system doesn't halt the experiment loop.
    """
    if not tid:
        return False
    try:
        from workflows.base import is_workflow_cancelled
        return is_workflow_cancelled(tid)
    except Exception:
        return False

# v1.3 (P2-1): _run_subprocess now imported from helpers.py (was a local copy).
# v1.8 (N10): _extract_metric imported here too — used to pre-extract the
# metric from the FULL output before truncation (single-mode path only).
# v1.9-V2 (mistral #10): parallel-mode path now also pre-extracts per-output
# metrics into the new `pre_extracted_metrics` list field.


def _write_full_output_log(
    results_path: str,
    iteration: int,
    output: str,
    slot: int = -1,
    project_root: str = "",
) -> None:
    """[v1.8 N5 / v1.9 D2 / v1.9-V2 correction #1] Write the FULL output to a
    per-iteration log file.

    [v1.9-V2 correction #1] Log dir relocated to
    `{project_root}/.autoresearch/logs/` — mirrors the `.understand` project-
    scoped pattern (`.autoresearch/` already holds the `parallel/` subdir;
    `logs/` lives alongside it). The previous v1.9 location
    `Path(results_path).parent / "logs" / "autoresearch"` added a `logs/`
    subfolder at the project root level; V2 corrects this to keep all
    autoresearch artifacts under one `.autoresearch/` folder. Falls back to
    `Path(results_path).parent / ".autoresearch" / "logs"` when `project_root`
    is empty (safety).

    [v1.9 D2] Log rotation cap — before writing, check the total size of the
    log dir. If it exceeds `cfg.autoresearch_log_dir_max_mb` (default 1024 =
    1GB), SKIP the write + trace a warning. We don't delete old logs
    (operators may want them); we just stop adding new ones. The walk is
    capped at 2000 files via `itertools.islice` so the size check itself
    doesn't become slow on dirs with 10k+ files. (minimax Risk #1)

    Filenames: `{iteration}.log` (single mode, slot=-1) or
    `{iteration}_{slot}.log` (parallel mode, slot=i).

    Non-fatal — disk errors are swallowed so the experiment loop is never
    blocked by a log-write failure. Operators can inspect the full output
    for debugging when the truncated state copy doesn't have enough context.

    Args:
        results_path: Path to the results.tsv ledger. Used as the FALLBACK
            locator for the log dir when `project_root` is empty
            (`{parent}/.autoresearch/logs/`).
        iteration: The 1-indexed iteration number (experiment_count + 1).
        output: The full stdout+stderr captured from the subprocess (BEFORE
            any truncation).
        slot: For parallel mode, the per-experiment slot index (0-based).
            -1 (default) means single mode — the filename is just
            `{iteration}.log`.
        project_root: [v1.9-V2] Project root path. The log dir is
            `{project_root}/.autoresearch/logs/` when non-empty (preferred —
            mirrors `.understand` pattern). Falls back to
            `{results_path}.parent / ".autoresearch" / "logs"` when empty.
    """
    if not results_path and not project_root:
        return
    try:
        import itertools
        from pathlib import Path
        from core.config import cfg
        # [v1.9-V2 correction #1] Log dir under .autoresearch/ (project-scoped,
        # mirrors .understand pattern). Falls back to results_path parent when
        # project_root is empty.
        if project_root:
            log_dir = Path(project_root) / ".autoresearch" / "logs"
        else:
            log_dir = Path(results_path).parent / ".autoresearch" / "logs"

        # [v1.9 D2] Check total dir size — skip write if over the cap.
        max_mb = int(getattr(cfg, "autoresearch_log_dir_max_mb", 1024))
        if max_mb > 0 and log_dir.exists():
            total_bytes = 0
            # Cap the walk at 2000 files so the size check itself doesn't
            # become slow on dirs with 10k+ files.
            for entry in itertools.islice(log_dir.iterdir(), 2000):
                try:
                    if entry.is_file():
                        total_bytes += entry.stat().st_size
                except OSError:
                    continue
            if total_bytes >= max_mb * 1024 * 1024:
                from core.tracer import tracer
                tracer.warning(
                    "", "run_experiment",
                    f".autoresearch/logs/ size {total_bytes // (1024*1024)}MB "
                    f"exceeds cap {max_mb}MB (AUTORESEARCH_LOG_DIR_MAX_MB) — "
                    f"skipping log write for iteration {iteration}",
                )
                return

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

    [v1.8 N5 / v1.9-V2 correction #1] In BOTH single and parallel paths,
    writes the FULL output to `{project_root}/.autoresearch/logs/{iteration}.log`
    (or `{iteration}_{i}.log` in parallel mode) BEFORE truncation — operators
    can inspect the full output for debugging. Non-fatal.

    [v1.8 N10 / v1.9-V2 mistral #10] In BOTH single AND parallel paths,
    extracts the metric from the FULL output BEFORE truncation and stores
    it. Single path stores it in `pre_extracted_metric` (singular); parallel
    path stores per-output metrics in `pre_extracted_metrics` (plural list).
    `node_evaluate` reads these FIRST (skipping re-extraction from the
    truncated output), preventing false negatives when the metric was
    printed early and the script produced lots of output after.
    """
    tid = state.get("trace_id", "")
    # [v1.10 / Phase B] Cancellation check — before each subprocess (single
    # + parallel). If cancelled, return status="failed" so the loop exits
    # cleanly without spawning subprocesses that would outlive the workflow.
    if _is_cancelled(tid):
        tracer.step(tid, "run_experiment", "workflow cancelled — skipping subprocess")
        return {
            "status": "failed",
            "errors": ["Workflow cancelled"],
            "error": "Workflow cancelled",
        }
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

        # [v1.8 N5 / v1.9-V2 correction #1] Write each output to its own
        # per-iteration log file BEFORE truncation. One log per experiment:
        # `{iteration}_{i}.log`. Iteration is computed from experiment_count
        # + 1 (matches the singular path). Non-fatal — disk errors don't halt
        # the loop.
        results_path = state.get("results_path", "")
        iteration = state.get("experiment_count", 0) + 1
        for i, output in enumerate(results):
            if output:
                _write_full_output_log(
                    results_path, iteration, output, slot=i,
                    project_root=project_root,
                )

        # [v1.9-V2 / mistral #10] Pre-extract each output's metric from the
        # FULL output BEFORE truncation — mirrors the single-path pre-extract
        # (v1.8 N10). A verbose parallel experiment >50KB can lose its metric
        # in the truncation tail, just like single mode. node_evaluate
        # (parallel path) checks `pre_extracted_metrics[i]` FIRST and skips
        # re-extracting from the (possibly truncated) `experiment_outputs[i]`.
        metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
        pre_metrics: list = []
        for i, output in enumerate(results):
            m = _extract_metric(output, metric_name) if output else None
            pre_metrics.append(m)
            if m is not None:
                tracer.step(
                    tid, "run_experiment",
                    f"parallel experiment {i}: pre-extracted {metric_name}={m} "
                    f"from full output ({len(output)} chars before truncation)",
                )

        # Truncate very large outputs to prevent state bloat. 50KB each is
        # enough for evaluate to find the metric (usually printed at the end)
        # while keeping the trace log + state dict manageable. Truncation
        # happens AFTER pre-extraction so the pre_extracted_metrics list holds
        # the metrics from the FULL outputs.
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
            # [v1.9-V2 / mistral #10] Pre-extracted per-output metrics from
            # the FULL outputs (before truncation). node_evaluate (parallel
            # path) reads these FIRST and skips re-extracting from the
            # (possibly truncated) experiment_outputs. Entries are None when
            # no metric was found in that output's full text.
            "pre_extracted_metrics": pre_metrics,
            # [v1.8 N10] Parallel mode does NOT populate the SINGULAR
            # pre_extracted_metric — explicitly clear it so a stale value
            # from a prior single-mode iteration doesn't leak in. Parallel
            # evaluate reads the plural list above; single evaluate reads
            # this singular field.
            "pre_extracted_metric": None,
        }

    # ── v1.5 single-subprocess path (unchanged) ────────────────────────────
    # If modify failed, skip the run — decide will discard.
    if state.get("status") == "failed":
        tracer.step(tid, "run_experiment", "skipping run — prior node failed")
        # [v1.8 N10] Clear pre_extracted_metric on the skip path too — a stale
        # value from a prior iteration would mislead evaluate.
        # [v1.9-V2] Also clear pre_extracted_metrics (plural) for the same
        # reason — a stale list from a prior parallel iteration could mislead
        # parallel evaluate.
        return {
            "experiment_output": state.get("experiment_output", ""),
            "pre_extracted_metric": None,
            "pre_extracted_metrics": [],
        }

    tracer.step(
        tid, "run_experiment",
        f"running {target_file} (budget={time_budget}s) @ {project_root or 'cwd'}",
    )
    output = _run_subprocess(target_file, project_root, time_budget)

    # [v1.8 N5 / v1.9-V2 correction #1] Write the FULL output to a per-
    # iteration log file BEFORE any truncation. Operators can inspect the
    # full output for debugging when the truncated state copy doesn't have
    # enough context. Non-fatal.
    results_path = state.get("results_path", "")
    iteration = state.get("experiment_count", 0) + 1
    _write_full_output_log(results_path, iteration, output, project_root=project_root)

    # [v1.8 N10 / v1.9-V2] Extract metric BEFORE truncation — prevents false
    # negatives when the metric is printed early and the script produces lots
    # of output after (pushing the metric out of the 50KB tail). node_evaluate
    # reads this first and skips re-extracting from the (possibly truncated)
    # output. Single path uses pre_extracted_metric (singular); parallel path
    # uses pre_extracted_metrics (plural list).
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
        "pre_extracted_metrics": [],  # [v1.9-V2] single mode — plural list unused
        "status": "running",
        "error": "",
    }
