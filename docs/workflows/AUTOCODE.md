# 🤖 Autocode Workflow

The `autocode` workflow handles **autonomous code generation and modification** tasks. It takes a natural language goal, optionally some initial files, and produces working code with tests, verification, and a structured report.

**Key characteristics:**

- **30-node LangGraph state machine** — 26 active + 3 backward-compat wrappers + 1 `node_hitl_gate` (v3.4). See [ARCHITECTURE.md](autocode/ARCHITECTURE.md).
- **Mode-driven** — `feature`, `fix`, `fix_error`, `refactor`, `improve`, `edit`, `create_skill`, `audit`.
- **TDD-first** — Generates tests before implementation (when applicable).
- **Iterative debug loop** — 4-phase prompt (investigation → pattern → hypothesis → fix) with retry until tests pass or max retries exceeded.
- **Four debug paths** (mutually exclusive): single-LLM (default), swarm (`AUTOCODE_SWARM_DEBUG=1`), parallel subagent (`AUTOCODE_PARALLEL_SUBAGENT_DEBUG=1`, v3.5 F1), single subagent (`AUTOCODE_SUBAGENT_DEBUG=1`).
- **Impact analysis** — Blast radius analysis before execution.
- **Git + GitHub integration** — Branches, commits, optional push/PR/auto-merge (all default OFF).
- **HiTL approval gate** (v3.4) — Opt-in async-checkpoint-resume pause before commit via `AUTOCODE_HITL_ENABLED=1`.
- **Cancellation-aware subprocess** (v3.6) — `node_run_pytest` / `node_run_lint` / `node_run_tests` wrap `subprocess.run(...)` with pre-check + deadline-aware timeout + post-check (bounds zombie linger to ≤1s past graph deadline).
- **Lazy Dev / YAGNI Ladder** — `CODER_SYSTEM` includes the 7-rung minimization ladder; `ponytail:` comment convention for deliberate simplifications.
- **v3.0 Sub-state architecture** — All state fields live in 8 typed sub-states. Accessors are the only read path. See [SUBSTATE.md](autocode/SUBSTATE.md).
- **[v3.7] Full audit mode** — `task_type="audit"` routes to a dedicated read-only pipeline (`node_audit_scan` → `node_audit_report` → END) that scans the whole repo for dead code, missing type hints, and complexity hotspots. Bypasses TDD entirely.
- **Memory integration** — Stores procedural knowledge for future recall.
- **Report generation** — Generates a structured report with the final result.

See [CHANGELOG.md](autocode/CHANGELOG.md) for the full version history.

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Fix an error
result = run_workflow(
    workflow_type="autocode",
    goal="Fix the timeout handling in web search",
    mode="fix_error",
    error_msg="TimeoutError: Request timed out after 30 seconds",
    files={"web.py": "..."},
    trace_id="autocode_001",
)

# Add a feature
result = run_workflow(
    workflow_type="autocode",
    goal="Add retry logic to the web search tool",
    mode="feature",
    feature_desc="Add exponential backoff retry with jitter",
    files={"web.py": "..."},
    trace_id="autocode_002",
)

# Improve code
result = run_workflow(
    workflow_type="autocode",
    goal="Refactor the web search tool for better error handling",
    mode="improve",
    files={"web.py": "..."},
    trace_id="autocode_003",
)

print(result["status"])  # "success" | "failed"
print(result["result"])  # "Code changes applied successfully..."
```

---

## ⚙️ Configuration

```ini
# .env
AUTOCODE_GRAPH_TIMEOUT=300          # Workflow timeout (seconds)
AUTOCODE_MAX_RETRIES=3              # Max debug retries
AUTOCODE_MAX_FILE_CHARS=128000      # Max file content chars

# GitHub + Swarm + Subagent integration flags (ALL default OFF — autocode behaves
# identically to a local-only workflow unless explicitly opted in)
AUTOCODE_PULL_BEFORE_BRANCH=0       # Pull recent commits before branching
AUTOCODE_PUSH_ON_COMMIT=0           # Push branch to origin after commit
AUTOCODE_OPEN_PR=0                  # Open a PR after push
AUTOCODE_AUTO_MERGE=0               # DANGEROUS — auto-merge the PR (squash)
AUTOCODE_DEBUG_COMMENT_PR=0         # Post LOW-confidence swarm verdict as PR comment
AUTOCODE_SWARM_DEBUG=0              # Use swarm (consensus → vote) for debug
AUTOCODE_SUBAGENT_DEBUG=0           # Use single isolated subagent dispatch for debug (v2.0.2)
AUTOCODE_SWARM_DEBUG_FALLBACK=0      # [v3.1] Escalate to swarm consensus when debug retries exhausted (HIGH → one more cycle, LOW → verify)
AUTOCODE_PARALLEL_SUBAGENT_DEBUG=0  # [v3.5 F1] Use parallel subagent debug (N hypotheses → N subagents → aggregate)
AUTOCODE_PARALLEL_SUBAGENT_COUNT=3  # [v3.5 F1] Number of parallel hypotheses (default 3, recommended 2-5)
AUTOCODE_HITL_ENABLED=0             # [v3.4 #38] Human-in-the-Loop approval gate before commit (async-checkpoint-resume)
# Note: AUTOCODE_ADAPTIVE_TIMEOUT=1 enables per-task-type graph timeouts (v3.1.2 #40).
# v3.6 #35 cancellation-aware subprocess is always-on (no flag) — bounds zombie linger to ≤1s past graph deadline.
```

```python
# core/config.py
cfg.autocode_graph_timeout = 300         # Workflow timeout (seconds)
cfg.autocode_max_retries = 3             # Max debug retries
cfg.autocode_max_file_chars = 128000     # Max file content chars

cfg.autocode_pull_before_branch = False  # Pull recent commits before branching
cfg.autocode_push_on_commit = False      # Push branch to origin after commit
cfg.autocode_open_pr = False             # Open a PR after push
cfg.autocode_auto_merge = False          # DANGEROUS — auto-merge the PR (squash)
cfg.autocode_debug_comment_pr = False    # Post LOW-confidence swarm verdict as PR comment
cfg.autocode_swarm_debug = False         # Use swarm (consensus → vote) for debug
cfg.autocode_subagent_debug = False      # Use single isolated subagent dispatch for debug (v2.0.2)
cfg.autocode_swarm_debug_fallback = False  # [v3.1] Escalate to swarm consensus when debug retries exhausted
cfg.autocode_parallel_subagent_debug = False  # [v3.5 F1] Use parallel subagent debug
cfg.autocode_parallel_subagent_count = 3      # [v3.5 F1] Number of parallel hypotheses
```

> **Note on stale timeout env vars:** Earlier versions of this doc listed `AUTOCODE_PLANNER_TIMEOUT`, `AUTOCODE_EXECUTOR_TIMEOUT`, and `AUTOCODE_ROUTER_TIMEOUT`. **These env vars DO NOT EXIST.** Per-role LLM timeouts come from `cfg.model_registry[role]["timeout"]` (see `core/config.py`). `AUTOCODE_GRAPH_TIMEOUT` is the only autocode timeout; it must be ≥ the max per-role timeout (validated at config load time).

> **GitHub prerequisite:** `node_push`, `node_create_pr`, `node_merge_pr`, and `_github_pull()` call `tools.github` which requires `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` in `.env`. If any of the three is missing, `is_configured()` returns `False` and every `vcs_ops.py` helper graceful-skips (logs a `tracer.step`, returns `False`/`None`, workflow continues).

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Fix code errors | `autocode` workflow | Targeted fixes with test verification |
| Add features | `autocode` workflow | TDD-first with test generation |
| Improve code | `autocode` workflow | Refactoring with impact analysis |
| Create skills | `autocode` workflow | Reusable skill generation |
| Research a topic | `research` workflow | Web search + synthesis, no code changes |
| Analyze data | `data` workflow | Code generation + execution, data analysis |
| Deep research | `deep_research` workflow | Iterative search with convergence detection |
| Understand codebase | `understand` workflow | Static analysis, dependency graph |
| Optimize a metric via experiments | `autoresearch` workflow | Evolutionary loop: modify → run → measure → keep/discard |
| Generate a report | `report` tool | Structured report generation (tool, not a workflow) |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](autocode/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](autocode/API.md) | Facade (`run_autocode_agent()`), graph overview, output format, state fields, state accessors |
| [Nodes](autocode/NODES.md) | Per-node reference for all 29 nodes (26 active + 3 backward-compat wrappers), in graph-execution order |
| [Substate](autocode/SUBSTATE.md) | Single source of truth for the v3.0 sub-state architecture — 8 sub-states, accessor signatures, RMW pattern, migration history |
| [Changelog](autocode/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](autocode/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-19 (v3.7). See [autocode/CHANGELOG.md](autocode/CHANGELOG.md) for version history.*
