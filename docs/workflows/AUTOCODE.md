# 🤖 Autocode Workflow

The `autocode` workflow handles **autonomous code generation and modification** tasks. It takes a natural language goal, optionally some initial files, and produces working code with tests, verification, and a structured report.

**Key characteristics:**
- **28-node LangGraph state machine** ([v2.0] — 25 active nodes + 3 backward-compat wrappers + 1 `node_summarize_context` for debug-loop compression)
- **Mode-driven** — Supports `fix_error`, `improve`, `add_feature`, `create_skill`, and `unclear` modes
- **TDD-first** — Generates tests before implementation (when applicable)
- **Iterative refinement** — 4-phase debug loop (investigation → pattern → hypothesis → fix) with retry until tests pass or max retries exceeded
- **Impact analysis** — Analyzes blast radius of changes before execution
- **Git integration** — Creates branches, commits changes, generates commit messages (branch names include `trace_id` suffix for uniqueness)
- **GitHub integration** — Optional push + PR + auto-merge (all gated on config flags + `is_configured()`, all default OFF)
- **Swarm debug** — Optional 2-run multi-model debug (consensus → vote, confidence HIGH/MEDIUM/LOW) via `AUTOCODE_SWARM_DEBUG=1`
- **Subagent debug** — Optional third debug path: single isolated subagent dispatch with curated context (no session state) via `AUTOCODE_SUBAGENT_DEBUG=1` (v2.0.2)
- **Lazy Dev / YAGNI Ladder** — `CODER_SYSTEM` includes the 7-rung minimization ladder (YAGNI → reuse → stdlib → native → installed dep → one line → minimum code); `ponytail:` comment convention for deliberate simplifications
- **v3.0 Sub-state architecture** — All state fields live in 8 typed sub-states (plan, tdd, files, impact, debug, verify, vcs, memory). Legacy flat-field mirrors removed. Accessors are the only read path.
- **Memory integration** — Stores procedural knowledge for future recall
- **Report generation** — Generates a structured report with the final result

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
    mode="add_feature",
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
| [Nodes](autocode/NODES.md) | Per-node reference for all 28 nodes (25 active + 3 backward-compat wrappers), in graph-execution order |
| [Substate](autocode/SUBSTATE.md) | Single source of truth for the v3.0 sub-state architecture — 8 sub-states, accessor signatures, RMW pattern, migration history |
| [Changelog](autocode/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](autocode/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-14 (v3.0 — flat-field removal, Track M1 ✅ COMPLETE, sub-states are now the PRIMARY + ONLY storage; v2.0.5 — Phase 4g review: split-brain sub-state fix + state schema gaps + v2.x→v3.0 migration roadmap; v2.0.4 subagent debug path; v2.0.1 hardening pass; v2.0 GA all 7 phases ✅ COMPLETE). See git history for per-phase details.*
