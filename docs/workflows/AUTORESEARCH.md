<- Back to [Workflows Overview](WORKFLOWS.md)

# 🔬 Autoresearch Workflow

The `autoresearch` workflow runs an **autonomous experiment-driven optimization loop**. It repeatedly modifies a target file (e.g. `train.py`), runs it as a time-boxed subprocess, extracts a metric from the output, and either commits the change (if the metric improved) or rolls it back. The loop runs indefinitely until a human interrupts it (or LangGraph's `recursion_limit` is hit, which the dispatcher catches as `success`).

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — point it at a training script, come back in the morning, and (hopefully) the metric has improved. Unlike `autocode` (convergent: one task, iterate until tests pass), autoresearch is **evolutionary**: many experiments, one git branch, `results.tsv` ledger of outcomes. Every experiment — keep *or* discard — is logged; improvements are committed, failures are `git reset --hard HEAD` + `git clean -fd` so the next iteration starts from a clean baseline.

**[v1.4] Loop control:** The loop runs indefinitely by default (legacy v1.3 behavior). Callers can opt in to auto-stop via `max_iterations=N` (hard cap) or env vars (`AUTORESEARCH_MAX_ITERATIONS`, `AUTORESEARCH_CONVERGENCE_WINDOW`, `AUTORESEARCH_CONVERGENCE_EPSILON`). The `route_after_log` router checks 3 stopping conditions after each `node_log`: max-iterations, convergence (last N all discarded), stuck (last N within ε of best). All default OFF. Experiments are also deduplicated by md5 hash of `new_content` (N8) — duplicate proposals skip the write and return `status="failed"`.

**[v1.5] Reflect + cross-run learning:** A new `node_reflect` sits between `log` and `route_after_log`. It is a no-op most iterations but every `autoresearch_reflect_interval` iterations (default 5; `0=disabled` via `AUTORESEARCH_REFLECT_INTERVAL`) it calls the planner LLM with the full experiment history and stores the strategy summary in `state["reflect_notes"]` — surfaced to the next `node_propose` so the LLM has strategic context, not just raw history. `node_decide` records a procedural memory via `memory.store_procedural()` on every discard (cross-run learning, N4); `node_propose` recalls procedural memories before proposing so the LLM avoids re-proposing known-bad strategies. All memory calls are non-fatal (chromadb may be unavailable — try/except wraps them).

**[v1.6] Parallel experiments (batch mode):** When `parallel_count > 1` (env: `AUTORESEARCH_PARALLEL_COUNT`, default 1), each iteration runs N experiments in parallel: `node_propose` dispatches N `_call_planner` calls via ThreadPoolExecutor (each with the SAME prompt — the LLM produces different proposals via sampling temperature); `node_modify` writes each proposal to its own temp dir under `{project_root}/.autoresearch/parallel/{i}/{target_file}` (the real `target_file` is only touched by `node_decide`); `node_run_experiment` runs N subprocesses concurrently; `node_evaluate` extracts N metrics; `node_decide` picks the best, copies the winner's content to the real `target_file`, git commits it, discards the rest, and cleans up the temp dir; `node_log` writes N ledger rows + N history entries (experiment_count increments by N). When `parallel_count == 1` (default), all nodes behave exactly as v1.5 (single-experiment, singular state fields only). The graph topology is UNCHANGED — parallelism is node-internal, coordinated via the `parallel_count` state field.

**[v1.7] Resume + checkpoint:** `run_workflow(resume=True)` triggers checkpoint restore for autoresearch. `node_decide` now calls `save_checkpoint(tid, "keep", state)` after every successful `_git_commit` (both single-experiment AND parallel paths) — discards do NOT checkpoint (they reset the working tree to the prior HEAD; no recoverable state worth resuming from). On resume, the dispatcher's autoresearch branch calls `get_latest(trace_id)` AFTER building a fresh `_ar_default(...)` state; if a checkpoint exists, it merges in only the autoresearch-specific fields (`experiment_count`, `current_best`, `baseline_metric`, `experiment_history`, `branch`, `results_path`, `reflect_notes`) — caller params (`goal`, `target_file`, etc.) are preserved as-is — and sets `ar_state["resume"] = True`. `node_setup` reads this flag: when `resume=True` AND `state["branch"]` is non-empty, branch creation is skipped (the prior run's branch is reused); when `state["current_best"] > 0.0`, the baseline run is ALSO skipped, and `experiment_history` is reloaded from `results.tsv` via the new `_load_history_from_ledger` helper. `experiment_count` is set to `len(history)`. When `resume=False` (default), behavior is exactly v1.6. Checkpoint write failures are non-fatal (try/except) so the experiment loop is never blocked.

## 🚀 Quick Start

```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="autoresearch",
    goal="minimize val_bpb",
    target_file="train.py",
    project_root="/path/to/repo",
    trace_id="autoresearch_001",
)
```

The loop runs until you interrupt the process (Ctrl-C) or LangGraph's `recursion_limit` is hit (dispatcher sets `recursion_limit=1000` by default — enough for ~160 experiments overnight). Inspect the results with `tail -f results.tsv` while the loop runs; `git log --oneline autoresearch/{YYYYMMDD-HHMMSS}` shows the kept commits in order.

## ⚙️ Configuration

| Knob | Default | Purpose |
|------|---------|---------|
| `autoresearch_time_budget` | `300` | Per-experiment wall-clock seconds |
| `autoresearch_target_file` | `"train.py"` | File to modify (relative to `project_root`) |
| `autoresearch_metric_name` | `"val_bpb"` | Metric name to extract from output |
| `autoresearch_metric_direction` | `"lower"` | `"lower"` (lower is better) \| `"higher"` |
| `autoresearch_max_iterations` | `0` | **[v1.4]** Hard cap on experiments (0=unlimited) |
| `autoresearch_convergence_window` | `10` | **[v1.4]** Stop after N consecutive non-improvements |
| `autoresearch_convergence_epsilon` | `0.001` | **[v1.4]** Metric plateau threshold (stuck detector) |
| `autoresearch_reflect_interval` | `5` | **[v1.5 N1]** Reflect every N iterations (0=disabled) |
| `autoresearch_parallel_count` | `1` | **[v1.6]** N parallel experiments per iteration (1 = v1.5 single-experiment mode) |

All knobs have sane defaults; override any per-invocation by passing through `run_workflow()` (forwarded via the type handler — v1.3 P2-2 + v1.4 max_iterations + v1.6 parallel_count). **Metric extraction:** `evaluate` greps the LAST occurrence of `{metric_name}: <float>` (or `=` separator) — training scripts that print the metric per epoch just work. **Git prerequisite:** `project_root` must be a git repo (decide runs raw `git` via `subprocess.run`; setup creates branch `autoresearch/{YYYYMMDD-HHMMSS}` via the `git` tool). **[v1.4] Loop control:** All 3 stopping conditions (max_iterations / convergence / stuck) default OFF → v1.3 "loop forever" behavior preserved unless caller opts in. **[v1.5] Reflect + cross-run learning:** `autoresearch_reflect_interval=0` disables reflection entirely. Cross-run learning (N4) is best-effort — if chromadb is unavailable, `node_decide` silently skips the procedural-memory store and `node_propose` silently skips the recall. **[v1.6] Parallel experiments:** `parallel_count=1` (default) preserves v1.5 single-experiment behavior exactly. `parallel_count>1` activates batch mode — effective experiment throughput scales N× (subject to LLM + subprocess parallelism limits). Each iteration produces N ledger rows in `results.tsv`; one git commit per iteration (the winner). **[v1.7] Resume + checkpoint:** Pass `resume=True` to `run_workflow()` to restore from the last-known-good checkpoint (`save_checkpoint` is called after every successful `_git_commit` in `node_decide`). On resume, `node_setup` skips branch creation (when `branch` is non-empty) AND the baseline run (when `current_best > 0.0`), and reloads `experiment_history` from `results.tsv`. Checkpoint failures are non-fatal.

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Optimize a numeric metric via many experiments | `autoresearch` | Evolutionary loop with keep/discard |
| Hyperparameter sweep / iterate on training script | `autoresearch` | Modify config or code → run → measure → keep best |
| Fix a specific bug | `autocode` | Convergent: iterate until tests pass |
| Research a topic | `research` / `deep_research` | No code modification, just synthesis |
| Analyze a dataset once | `data` | Single code execution, no loop |

**Don't use autoresearch if:** you have a correctness target (tests pass/fail — use `autocode`); you don't have a numeric metric to optimize; or your experiment takes hours (the loop runs one experiment at a time).

## 📂 Subdocs

| Subdoc | Content |
|--------|---------|
| [Architecture](autoresearch/ARCHITECTURE.md) | Module tree, dispatch flow (mermaid), design decisions, state TypedDict |
| [API](autoresearch/API.md) | Facade signature, config table, per-node reference, state fields |
| [Changelog](autoresearch/CHANGELOG.md) | Version history + roadmap |
| [Instructions](autoresearch/INSTRUCTIONS.md) | NEVER DO / ALWAYS DO rules + anti-patterns for AI editors |

---

*Last updated: 2026-07-22 (v1.7). See [CHANGELOG.md](autoresearch/CHANGELOG.md) for version history.*
