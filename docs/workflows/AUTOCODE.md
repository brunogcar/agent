# 🤖 Autocode Workflow

The `autocode` workflow handles **autonomous code generation and modification** tasks. It takes a natural language goal, optionally some initial files, and produces working code with tests, verification, and git commit.

**Key characteristics:**
- **18-node LangGraph state machine** ([v1.3] was 17 in v1.2 — added `node_publish`)
- **Mode-driven** — Supports `fix_error`, `improve`, `add_feature`, `create_skill`, and `unclear` modes
- **TDD-first** — Generates tests before implementation (when applicable)
- **Iterative refinement** — Debug loop with retry until tests pass or max retries exceeded
- **Impact analysis** — Analyzes blast radius of changes before execution
- **Git integration** — Creates branches, commits changes, and generates commit messages
- **[v1.3] GitHub integration** — Optional push + PR + auto-merge via `node_publish` (all gated on config flags + `is_configured()`, all default OFF)
- **[v1.3] Swarm debug** — Optional 2-run multi-model debug (consensus → vote, confidence HIGH/MEDIUM/LOW) via `AUTOCODE_SWARM_DEBUG=1`
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

# [v1.3] GitHub + Swarm integration flags (ALL default OFF — autocode behaves
# identically to v1.2 unless explicitly opted in)
AUTOCODE_PULL_BEFORE_BRANCH=0       # Pull recent commits before branching
AUTOCODE_PUSH_ON_COMMIT=0           # Push branch to origin after commit
AUTOCODE_OPEN_PR=0                  # Open a PR after push
AUTOCODE_AUTO_MERGE=0               # DANGEROUS — auto-merge the PR (squash)
AUTOCODE_DEBUG_COMMENT_PR=0         # Post LOW-confidence swarm verdict as PR comment
AUTOCODE_SWARM_DEBUG=0              # Use swarm (consensus → vote) for debug
```

```python
# core/config.py
cfg.autocode_graph_timeout = 300         # Workflow timeout (seconds)
cfg.autocode_max_retries = 3             # Max debug retries
cfg.autocode_max_file_chars = 128000     # Max file content chars

# [v1.3] GitHub + Swarm integration flags
cfg.autocode_pull_before_branch = False  # Pull recent commits before branching
cfg.autocode_push_on_commit = False      # Push branch to origin after commit
cfg.autocode_open_pr = False             # Open a PR after push
cfg.autocode_auto_merge = False          # DANGEROUS — auto-merge the PR (squash)
cfg.autocode_debug_comment_pr = False    # Post LOW-confidence swarm verdict as PR comment
cfg.autocode_swarm_debug = False         # Use swarm (consensus → vote) for debug
```

> **[v1.3] Note on stale timeout env vars:** Earlier versions of this doc listed
> `AUTOCODE_PLANNER_TIMEOUT`, `AUTOCODE_EXECUTOR_TIMEOUT`, and
> `AUTOCODE_ROUTER_TIMEOUT`. **These env vars DO NOT EXIST.** Per-role LLM
> timeouts come from `cfg.model_registry[role]["timeout"]` (see `core/config.py`
> `model_registry` block) — there are no separate autocode-specific timeout
> env vars. `AUTOCODE_GRAPH_TIMEOUT` is the only autocode timeout; it must be
> ≥ the max per-role timeout (validated at config load time).
>
> `# TODO(2.0):` Audit all docs and remove any remaining stale references to the
> three non-existent timeout env vars. See CHANGELOG.md § 2.0 Review Notes →
> Documentation → "Stale env vars in AUTOCODE.md".

> **[v1.3] GitHub prerequisite:** `node_publish` and `_github_pull()` call
> `tools.github` which requires `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` in
> `.env`. If any of the three is missing, `is_configured()` returns `False` and
> every `github_ops.py` helper graceful-skips (logs a `tracer.step`, returns
> `False`/`None`, workflow continues). See `tools/github_ops/client.py`.

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
| Generate report | `report` workflow | Structured report generation |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](autocode/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](autocode/API.md) | Node reference, output format, error handling, security |
| [Changelog](autocode/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](autocode/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-10 (v1.3 — added `node_publish` + GitHub/Swarm integration + 6 new config flags; fixed stale timeout env vars). 18-node LangGraph state machine (was 17 in v1.2).*
