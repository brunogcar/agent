# 🔍 Research Workflow

The `research` workflow handles **web research and synthesis** tasks. It takes a natural language goal, searches the web for relevant information, scrapes the results, and synthesizes a comprehensive answer.

**v1.1:** Wired `trim_state_node` between synthesize and report. After synthesize produces `result`, oversized `search_results` (up to 40KB) is evicted to episodic memory (chonkie-aware — keeps preview, evicts chunks individually). Falls back to whole-string eviction if chonkie is missing. See [Changelog](research/CHANGELOG.md).

**v1.0:** Split monolithic `workflows/research.py` (513 lines) into `workflows/research_impl/` subpackage with per-node modules. Fixed 8 bugs (agent missing action, as_completed timeout, 800-char truncation, zombie futures, etc.). Added `WORKFLOW_METADATA` for MCP client introspection. See [Architecture](research/ARCHITECTURE.md).

**Key characteristics:**
- **Web search first** — Searches the web for relevant sources (uses `cfg.web_max_search_results`, default 10)
- **Parallel scraping** — Scrapes multiple sources concurrently with `ThreadPoolExecutor` (v1.0: global timeout via `wait()`, cancels zombie futures)
- **Synthesis** — LLM synthesizes the scraped content into a coherent answer
- **Trim node (v1.1)** — Evicts oversized `search_results` to episodic memory after synthesize produces `result`
- **Memory integration** — Stores the full research result in semantic memory (v1.0: was truncated to 800 chars) + episodic summary
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
