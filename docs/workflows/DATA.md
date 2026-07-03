# 📊 Data Workflow

The `data` workflow handles **data analysis and visualization** tasks. It takes a natural language goal, optionally some initial Python code, and produces a data analysis result with optional visualization.

**Key characteristics:**
- **Goal-driven** — User describes what they want; LLM generates the analysis code
- **Execution loop** — Generated code is executed in the sandboxed Python environment
- **Critique loop** — If execution fails, the LLM critiques the error and generates a fix
- **Memory integration** — Recalls relevant past analyses for context
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
| Generate report | `report` workflow | Structured report generation |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](data/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](data/API.md) | Node reference, output format, error handling, security |
| [Changelog](data/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](data/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |
