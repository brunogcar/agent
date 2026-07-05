# 🔄 Workflow Tool

The `workflow()` tool launches **multi-step autonomous LangGraph workflows** for complex tasks: research, data analysis, autocode, deep research, and codebase understanding. It acts as the primary entry point for long-running operations that require planning, execution, and iteration.

**Key characteristics:**
- **Workflow dispatch** — Routes to `research`, `data`, `autocode`, `deep_research`, `understand`, or `auto` (router-classified)
- **Strict type validation** — `VALID_WORKFLOWS` frozenset prevents LLM hallucination of non-existent workflow types
- **Fail-fast parameter guards** — Autocode validates `target_file`, `error_msg`, `feature_desc` BEFORE taking git snapshots or invoking the Planner
- **Auto-routing** — `type="auto"` (or omitted) lazily imports the Router model to classify the goal and select the correct workflow
- **Guaranteed observability** — Every return dict (success or error) contains `trace_id`. Auto-generated if not provided by MCP host
- **Resume support** — `resume=True` continues interrupted workflows from checkpoint

---

## 🚀 Quick Start

```python
# Research workflow
workflow(type="research", goal="Find the best Python async database drivers")

# Data analysis workflow
workflow(type="data", goal="Analyse sales_data.csv for Q3 trends", code="import pandas as pd")

# Autocode — fix a bug
workflow(type="autocode", goal="Fix the null pointer", target_file="src/main.py", mode="fix_error", error_msg="NullPointerException at line 42")

# Autocode — add a feature
workflow(type="autocode", goal="Add user authentication", target_file="src/auth.py", mode="add_feature", feature_desc="JWT-based auth with refresh tokens")

# Auto-routing (let the router decide)
workflow(type="auto", goal="Generate a report on our Q3 performance")

# Understand codebase
workflow(type="understand", goal="Map the auth module", project_root="D:\mcp\agent\src")
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `VALID_WORKFLOWS` | `tools/workflow.py` | `{"research", "data", "autocode", "deep_research", "understand", "auto"}` | Strict allowlist of workflow types |
| `trace_id` | Caller / auto-generated | — | Execution trace identifier. Auto-generated if not provided. |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Quick web search | `web` | Single call, no planning overhead |
| Single file edit | `file` | Direct, no workflow orchestration |
| Git operation | `git` | Atomic, immediate |
| Multi-step research | `workflow(type="research")` | Planning, web search, synthesis, citation |
| Data analysis pipeline | `workflow(type="data")` | Pandas, numpy, chart generation |
| Code fix / feature | `workflow(type="autocode")` | TDD, git snapshots, safety checks |
| Iterative deep research | `workflow(type="deep_research")` | ReAct loop, budget tracking, convergence detection |
| Report/dashboard generation | `report` tool | HTML/PDF dashboards — call `report(action="...")` directly, not via workflow |
| Codebase mapping | `workflow(type="understand")` | Knowledge graph, dependency analysis |
| Unclear task | `workflow(type="auto")` | Router classifies and selects workflow |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](workflow/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](workflow/API.md) | Full tool signature, workflow types, parameter validation, output format |
| [CHANGELOG.md](workflow/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](workflow/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-05. See subfiles for detailed documentation.*
