# 🔍 Research Workflow

The `research` workflow handles **web research and synthesis** tasks. It takes a natural language goal, searches the web for relevant information, scrapes the results, and synthesizes a comprehensive answer.

**Key characteristics:**
- **Web search first** — Searches the web for relevant sources
- **Parallel scraping** — Scrapes multiple sources concurrently for speed
- **Synthesis** — LLM synthesizes the scraped content into a coherent answer
- **Memory integration** — Stores the research result in memory for future recall
- **Citation tracking** — Tracks sources for attribution
- **Notification** — Reports completion to the user

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

# Basic research
result = run_workflow(
    workflow_type="research",
    goal="What are the best practices for ChromaDB in production?",
    trace_id="research_001",
)

print(result["status"])  # "success" | "failed"
print(result["result"])  # "ChromaDB best practices include..."
```

---

## ⚙️ Configuration

```ini
# .env — no research-specific env vars
# Uses shared config:
# cfg.web_max_search_results — default 10 (hardcoded to 3 in code)
# cfg.worker_timeout — default 60s
# cfg.research_timeout — for agent(role="research")
```

```python
# core/config.py
# No research-specific config. Uses:
# cfg.web_max_search_results — web search max results
# cfg.worker_timeout — worker thread timeout
# cfg.research_timeout — LLM research timeout
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Research a topic | `research` workflow | Web search + synthesis, comprehensive answer |
| Analyze data | `data` workflow | Code generation + execution, data analysis |
| Fix code | `autocode` workflow | Targeted code changes with test verification |
| Deep research | `deep_research` workflow | Iterative search with convergence detection |
| Understand codebase | `understand` workflow | Codebase analysis and dependency mapping |
| Generate report | `report` workflow | Structured report generation |

---

## 📂 Subfile Directory

| Subfile | Description |
|---------|-------------|
| [Architecture](research/ARCHITECTURE.md) | File maps, module trees, mermaid diagrams, design decisions, testing layout |
| [API](research/API.md) | Node reference, output format, error handling, security |
| [Changelog](research/CHANGELOG.md) | Version history, breaking changes, roadmap, completed features, deferred items |
| [Instructions](research/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |
