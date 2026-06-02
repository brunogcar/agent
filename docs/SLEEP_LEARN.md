# Sleep & Learn Meta-Learning Daemon

## Overview
The Sleep & Learn daemon is a standalone, background meta-cognition subsystem (`core/sleep_learn/`) that allows the agent to observe its own execution traces, distill procedural rules from successes and failures, and dynamically inject those rules into the Planner's context to improve future decision-making.

## Architecture
Following the AI panel's consensus, the daemon is implemented as a **standalone subsystem** that imports `memory_backend` and `llm_backend` as dependencies. It never tightly couples to them, and `memory_backend` never imports `sleep_learn`.

### Core Components
- **`daemon.py`**: The main orchestrator. Checks idle state, sweeps observations, runs distillation, executes the feedback loop, and triggers the janitor.
- **`sweeper.py`**: Gathers high-signal events (errors, retries, corrections) from recent traces.
- **`distiller.py`**: Uses the public `llm.complete()` API to extract actionable procedural rules from observations.
- **`filters.py`**: Quality and safety gates that reject generic, overly short, or dangerous rules before they reach storage.
- **`storage.py`**: Writes validated rules to a physically isolated ChromaDB collection (`procedural_meta`).
- **`injector.py`**: Queries the isolated collection and injects the top-K relevant rules into the Planner's system prompt.
- **`feedback.py`**: Parses agent logs to update rule confidence scores (boost on success, penalize on failure, auto-purge below 0.3).
- **`janitor.py`**: Purges expired or low-confidence rules from the isolated collection.

## Phased Implementation
- **Phase 1 (Passive Observation)**: Zero LLM calls. Sweeps traces and logs candidates to `logs/sleep_learn/`.
- **Phase 2 (Active Distillation)**: Uses local LLM to distill rules. Writes to isolated `procedural_meta` collection.
- **Phase 3 (Dynamic Injection)**: Injects top-3 relevant rules into the Planner's context. Includes a kill switch (`SLEEP_LEARN_INJECT_ENABLED`).
- **Phase 4 (Janitor Integration)**: Unified memory compaction. Archives old episodic memories and purges stale rules during idle cycles.
- **Phase 5 (Feedback Loop)**: Dynamic confidence scoring. Rules that lead to successful traces are boosted; failed traces are penalized.

## Hard Guardrails
1. **Public API Only**: The daemon strictly uses `llm.complete()`. It never bypasses rate limiters, token budgets, or circuit breakers.
2. **Physical Isolation**: Learned rules are stored in a separate ChromaDB instance (`memory_root/sleep_learn_db`) to prevent polluting the main `episodic`/`semantic` collections.
3. **Ouroboros Prevention**: The daemon is forbidden from reading its own `procedural_meta` output collection.
4. **Zero Coupling**: The feedback loop reads JSONL logs directly. It never imports the tracer or workflow engines.
5. **Lazy Loading**: All ChromaDB imports in the daemon are lazy (inside functions) to prevent slowing down the agent's startup time.
