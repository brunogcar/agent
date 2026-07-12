<- Back to [Workflows Overview](WORKFLOWS.md)

# 🔬 Autoresearch Workflow

> **Status:** Planned — not yet implemented. This is a design placeholder.

## Overview

Autoresearch is a planned workflow for **autonomous experiment-driven optimization**. Unlike autocode (convergent: solve one task), autoresearch is **evolutionary**: try many approaches, keep the best.

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — an autonomous ML training optimization loop where an agent modifies training code, runs 5-minute experiments, and keeps or discards based on a metric.

## Core Idea

```
LOOP FOREVER:
  1. Modify target code (e.g., train.py, config, hyperparams)
  2. Run experiment (fixed time budget or fixed steps)
  3. Measure metric (e.g., val_loss, accuracy, val_bpb)
  4. If improved → keep (git commit)
  5. If worse/equal → discard (git reset)
  6. Log result to ledger (TSV)
  7. Repeat
```

The agent runs autonomously overnight — you wake up to a log of experiments and (hopefully) a better model/config.

## Difference from Autocode

| Aspect | Autocode | Autoresearch |
|--------|----------|--------------|
| **Goal** | Solve one task (feature/bug) | Optimize a metric over many experiments |
| **Loop** | Convergent (iterate until correct) | Evolutionary (try many, keep best) |
| **Exit** | Tests pass + verification | Human interrupts (runs indefinitely) |
| **State** | One task, one branch | Many experiments, one branch, ledger of results |
| **Metric** | Tests pass/fail | Numeric metric (lower/higher is better) |

## Prerequisites

1. **Autocode 2.0 complete** — clean infrastructure to reuse
2. **Subagent infrastructure** — `tools/agent_ops/actions/subagent.py` for isolated experiment proposals
3. **Chonkie integration in autocode** — `node_summarize_context` pattern (Phase 4)

## References

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — original inspiration
- Autocode 2.0 CHANGELOG — infrastructure this workflow will reuse

---

*Last updated: 2026-07-11. This is a design placeholder — implementation tracked in the autocode CHANGELOG "Future Tracks" section.*
