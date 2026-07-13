# 📊 Data Workflow

The `data` workflow handles **data analysis and visualization** tasks. It takes a natural language goal, optionally some initial Python code, and produces a data analysis result.

**v1.1:** Wired `trim_state_node` between critique and store. After critique produces `result`, oversized `output` is evicted to episodic memory (chonkie-aware — keeps preview, evicts chunks individually). Falls back to whole-string eviction if chonkie is missing. See [Changelog](data/CHANGELOG.md).

**v1.0:** Split into the `workflows/data_impl/` subpackage (per-node modules + `WORKFLOW_METADATA`), mirroring `research_impl` / `understand_impl`. See [Architecture](data/ARCHITECTURE.md).

**Key characteristics:**
- **Goal-driven** — User describes what they want; the LLM generates the analysis code (unless code is provided)
- **Sandboxed execution** — Generated/provided code runs via `python(mode="run_data")`
- **Critique layer** — `agent(role="critique")` reviews whether the output answers the goal (runs on success; best-effort, logged on failure)
- **Memory integration** — Recalls relevant past analyses for context; stores episodic (result) + procedural (working code, only when LLM-generated)
- **Non-fatal memory/notify** — Memory and notification failures never crash the workflow or flip a successful analysis to failed
- **Notification** — Reports completion to the user

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Basic analysis
result = run_workflow(
    workflow_type="data",
    goal="Analyze the top 5 most active months from the sales dataset",
    trace_id="data_001",
)

# With initial code
result = run_workflow(
    workflow_type="data",
    goal="Plot a bar chart of monthly revenue",
    code="import pandas as pd; df = pd.read_csv('sales.csv')",
    trace_id="data_002",
)

print(result["status"])  # "success" | "failed"
print(result["result"])  # "Analysis complete: Top 5 months are..."
```

---

## ⚙️ Configuration

```ini
# .env — no data-specific env vars
# Uses shared config:
# cfg.code_timeout — for agent(role="code")
# cfg.critique_timeout — for agent(role="critique")
# cfg.python_timeout — for python(code=...)
```

```python
# core/config.py
# No data-specific config. Uses:
# cfg.code_timeout — LLM code generation timeout
# cfg.critique_timeout — LLM critique timeout
# cfg.python_timeout — Python execution timeout
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Analyze data | `data` workflow | Goal-driven, generates code, executes, reviews |
| Research a topic | `research` workflow | Web search + synthesis, no code execution |
| Fix code | `autocode` workflow | Targeted code changes with test verification |
| Deep research | `deep_research` workflow | Iterative search with convergence detection |
| Understand codebase | `understand` workflow | Codebase analysis and dependency mapping |
| Generate report | `report` tool | 11 atomic report actions — charts, maps, dashboards, export to PDF/PNG |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](data/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](data/API.md) | Node reference, output format, error handling, security |
| [Changelog](data/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](data/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |
