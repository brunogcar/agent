# 🤖 Autocode Workflow

The `autocode` workflow handles **autonomous code generation and modification** tasks. It takes a natural language goal, optionally some initial files, and produces working code with tests, verification, and git commit.

**Key characteristics:**
- **Mode-driven** — Supports `fix_error`, `improve`, `add_feature`, `create_skill`, and `unclear` modes
- **TDD-first** — Generates tests before implementation (when applicable)
- **Iterative refinement** — Debug loop with retry until tests pass or max retries exceeded
- **Impact analysis** — Analyzes blast radius of changes before execution
- **Git integration** — Creates branches, commits changes, and generates commit messages
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
AUTOCODE_PLANNER_TIMEOUT=120        # Planner LLM timeout (seconds)
AUTOCODE_EXECUTOR_TIMEOUT=90        # Executor LLM timeout (seconds)
AUTOCODE_ROUTER_TIMEOUT=30          # Router LLM timeout (seconds)
```

```python
# core/config.py
cfg.autocode_graph_timeout = 300    # Workflow timeout (seconds)
cfg.autocode_max_retries = 3         # Max debug retries
cfg.autocode_max_file_chars = 128000 # Max file content chars
cfg.autocode_planner_timeout = 120    # Planner LLM timeout (seconds)
cfg.autocode_executor_timeout = 90     # Executor LLM timeout (seconds)
cfg.autocode_router_timeout = 30      # Router LLM timeout (seconds)
```

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
