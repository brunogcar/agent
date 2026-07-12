<- Back to [Workflows Overview](WORKFLOWS.md)

# 🔬 Autoresearch Workflow

The `autoresearch` workflow runs an **autonomous experiment-driven optimization loop**. It repeatedly modifies a target file (e.g. `train.py`), runs it as a time-boxed subprocess, extracts a metric from the output, and either commits the change (if the metric improved) or rolls it back (if it didn't). The loop runs indefinitely until a human interrupts it.

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — you point it at a training script, come back in the morning, and (hopefully) the metric has improved.

**Key characteristics:**
- **Evolutionary, not convergent** — Unlike `autocode` (one task, one convergent debug loop), autoresearch tries many approaches and keeps only the winners.
- **Indefinite loop** — `decide → propose` is an unconditional back-edge; the loop exits only when a human stops the process (or LangGraph's `recursion_limit` is hit).
- **Metric-driven** — Every iteration is judged by a single numeric metric extracted from the experiment output (e.g. `val_bpb`, `accuracy`, `loss`).
- **7-node LangGraph StateGraph** — `setup → propose → modify → run_experiment → evaluate → log → decide → propose (loop)`
- **Git-based keep/discard** — Improvements are committed; failures are `git reset --hard HEAD` + `git clean -fd` so the next iteration starts from a clean baseline.
- **Results ledger** — Every experiment (keep *or* discard) is appended to `results.tsv` so operators can `tail -f` while the loop runs.
- **Atomic writes** — `modify` uses `tempfile.mkstemp` + `os.fsync` + `os.replace`; the target file is never in a half-written state if the process is killed mid-write.
- **Time-boxed experiments** — Each run is killed via `subprocess.run(timeout=...)` after `autoresearch_time_budget` seconds.
- **Reuses autocode infrastructure** — Calls `autocode_impl.helpers._call()` for LLM retries + cancellation; uses `core.json_extract.extract_json()` for proposal parsing.

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Optimize val_bpb on train.py overnight (lower is better)
result = run_workflow(
    workflow_type="autoresearch",
    goal="minimize val_bpb",
    target_file="train.py",
    project_root="/path/to/repo",
    trace_id="autoresearch_001",
)

# Or via the workflow() meta-tool
# workflow(type="autoresearch", goal="minimize val_bpb", target_file="train.py")
```

The loop runs until you interrupt the process (Ctrl-C) or LangGraph's recursion limit is hit (the dispatcher sets `recursion_limit=1000` by default — enough for ~160 experiments overnight; invoke the graph directly with a higher limit for longer runs).

When you return, inspect the results:

```bash
$ tail -n 20 results.tsv
# iteration  commit  metric  status  description
1  a1b2c3d  0.421  keep   Increase learning rate from 1e-4 to 3e-4
2  -        0.430  discard Decrease batch size from 64 to 32
3  e4f5g6h  0.418  keep   Add gradient clipping at 1.0
...
```

`git log --oneline autoresearch/20260712-...` shows the kept commits in order.

---

## ⚙️ Configuration

```ini
# .env
AUTORESEARCH_TIME_BUDGET=300          # Per-experiment wall-clock budget (seconds)
AUTORESEARCH_TARGET_FILE=train.py     # File to modify (relative to project_root)
AUTORESEARCH_METRIC_NAME=val_bpb      # Metric name to extract from output
AUTORESEARCH_METRIC_DIRECTION=lower   # "lower" (lower is better) | "higher"
```

```python
# core/config.py
cfg.autoresearch_time_budget = 300            # Per-experiment wall-clock budget (seconds)
cfg.autoresearch_target_file = "train.py"     # File to modify
cfg.autoresearch_metric_name = "val_bpb"      # Metric name to extract
cfg.autoresearch_metric_direction = "lower"   # "lower" | "higher"
```

All four knobs have sane defaults; you can override any of them per-invocation by passing them through `run_workflow()` (they're forwarded into the autoresearch state).

> **Metric extraction:** The `evaluate` node greps the experiment output for the LAST occurrence of `{metric_name}: <float>` (or `=` / whitespace separator). Training scripts that print the metric per epoch just work — the final value wins. If your script prints the metric in a different format, either reformat it or fork the `evaluate` node.

> **Git prerequisite:** `decide` runs `git add` / `git commit` / `git reset --hard HEAD` via `subprocess.run` directly (not the `git` tool — bypasses tracing noise during the tight loop). `project_root` must be a git repo. The `setup` node creates branch `autoresearch/{YYYYMMDD-HHMMSS}` (or reuses an existing one) via the `git` tool.

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Optimize a numeric metric via many experiments | `autoresearch` workflow | Evolutionary loop with keep/discard |
| Hyperparameter sweep | `autoresearch` workflow | Modify config file → run → measure → keep best |
| Iterate on training script | `autoresearch` workflow | Modify train code → run → measure → keep best |
| Fix a specific bug | `autocode` workflow | Convergent: iterate until tests pass |
| Research a topic | `research` / `deep_research` workflow | No code modification, just synthesis |
| Analyze a dataset once | `data` workflow | Single code execution, no loop |

**Don't use autoresearch if:**
- You have a *correctness* target (tests pass/fail) — use `autocode` instead.
- You don't have a numeric metric to optimize — there's nothing for `evaluate` to extract.
- Your experiment takes hours (the loop runs one experiment at a time; a long time_budget starves the LLM of iterations).

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](autoresearch/ARCHITECTURE.md) | File maps, module trees, mermaid diagram, design decisions, testing layout |
| [API](autoresearch/API.md) | Facade, state fields, per-node reference (7 nodes), routes |
| [Changelog](autoresearch/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](autoresearch/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-12 (v1.0 — initial implementation). See [AR1 worklog](../../../../worklog.md) for implementation details.*
