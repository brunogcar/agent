# 🏗️ Workflow Base

The `workflows/base.py` module provides the **shared foundation** for all agent workflows. It defines the common `WorkflowState` TypedDict, node helper utilities, and the `run_workflow()` dispatcher that routes execution to the correct workflow graph.

**Key characteristics:**
- **Shared state schema** — `WorkflowState` is the common denominator across `research`, `data`, `autocode`, `deep_research`, and `understand` (22 fields)
- **LangGraph immutability** — All helpers return partial update `dict`s, never mutate state in-place
- **Checkpoint resumption** — `run_workflow(resume=True)` restores from the latest checkpoint journal
- **Trace lifecycle** — Automatic trace creation, step logging, error tracking, and completion marking
- **Workflow-agnostic** — No workflow-specific logic; pure infrastructure

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Run a research workflow
result = run_workflow(
    workflow_type="research",
    goal="What are the best practices for ChromaDB in production?",
    trace_id="abc123",
)

# Resume from checkpoint
result = run_workflow(
    workflow_type="autocode",
    goal="Fix the timeout handling in web search",
    trace_id="abc123",
    resume=True,
)

print(result["status"])  # "success" | "failed"
print(result["result"])  # Final result summary
```

---

## ⚙️ Configuration

```ini
# .env — no base-specific env vars
# Uses shared config:
# All timeouts from core/config.py
```

```python
# core/config.py
# No base-specific config. Uses:
# cfg.* — various timeout and limit settings
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Run a workflow | `run_workflow()` | Standard entry point, trace management, checkpoint support |
| Log a node step | `node_step()` | Consistent trace logging across all workflows |
| Mark node failure | `node_error()` | Standardized error handling + checkpoint save |
| Mark node success | `node_done()` | Standardized completion + trace finish |
| Evict large state fields | `trim_state()` | Prevents checkpoint bloat |
| Direct workflow access | Import graph builder | Bypass dispatcher for testing or custom invocation |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](base/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](base/API.md) | WorkflowState schema, utility signatures, dispatcher routing, output format |
| [Changelog](base/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](base/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |
