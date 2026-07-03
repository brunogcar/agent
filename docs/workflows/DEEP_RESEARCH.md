# 🔬 Deep Research Workflow

The `deep_research` workflow performs **iterative, deep research** on a topic. It uses a cyclic LangGraph workflow to search, synthesize, and evaluate until the research converges or the budget is exhausted.

**Key characteristics:**
- **Iterative search** — Cycles between search, synthesis, and evaluation until convergence
- **Budget management** — Tracks API calls and browser actions to prevent runaway costs
- **Convergence detection** — Uses cosine similarity to detect when new information stops adding value
- **Multi-tool search** — Uses Tavily API, web search, and browser fallback for comprehensive coverage
- **Memory integration** — Recalls past research for context and stores results for future recall
- **Report generation** — Generates a structured report with the final synthesis

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Deep research on a topic
result = run_workflow(
    workflow_type="deep_research",
    goal="What are the latest advancements in quantum computing error correction?",
    trace_id="deep_research_001",
)

print(result["status"])  # "success" | "failed" | "incomplete"
print(result["result"])  # "Quantum computing error correction has seen..."
```

---

## ⚙️ Configuration

```ini
# .env
DEEP_RESEARCH_MAX_API_CALLS=15          # Max Tavily API calls per run
DEEP_RESEARCH_MAX_BROWSER_ACTIONS=10   # Max browser actions per run
DEEP_RESEARCH_CONVERGENCE_THRESHOLD=0.85 # Convergence similarity threshold (0-1)
DEEP_RESEARCH_TIMEOUT_SECONDS=300       # Workflow timeout (seconds)
```

```python
# core/config.py
cfg.deep_research_max_api_calls = 15      # Max Tavily API calls per run
cfg.deep_research_max_browser_actions = 10 # Max browser actions per run
cfg.deep_research_convergence_threshold = 0.85 # Convergence similarity threshold (0-1)
cfg.deep_research_timeout_seconds = 300    # Workflow timeout (seconds)
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Deep research on a topic | `deep_research` workflow | Iterative search with convergence detection |
| Quick research | `research` workflow | Single-pass search + synthesis, faster |
| Analyze data | `data` workflow | Code generation + execution, data analysis |
| Fix code | `autocode` workflow | Targeted code changes with test verification |
| Understand codebase | `understand` workflow | Static analysis, dependency graph |
| Generate report | `report` workflow | Structured report generation |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](deep_research/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](deep_research/API.md) | Node reference, output format, error handling, security |
| [Changelog](deep_research/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](deep_research/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |
