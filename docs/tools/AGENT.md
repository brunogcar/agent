# 🤖 Agent Tool

The `agent()` tool is the **meta-cognitive dispatcher** of the MCP Agent Stack. It routes tasks to specialist sub-agents based on a `role` parameter, each with its own system prompt, model, timeout, and output format.

**Key characteristics:**
- **Single entry point** — The LLM sees one tool: `agent(action, role, task, ...)`
- **Role-specialized prompts** — 15 distinct personas, each with tailored instructions
- **Per-role model routing** — Router uses fast 2B models, Executor uses capable 9B models
- **Per-role context budgets** — Router gets 4K tokens, Planner gets 32K tokens
- **Structured output enforcement** — JSON mode for `extract`, prompt-only JSON for `route`, `plan`, `code`, `review`
- **Response caching** — Deterministic roles (`classify`, `route`) cached with 5-min TTL
- **NOT_PARALLEL_SAFE** — Serialized via global LLM client queue; no concurrent agent calls

---

## 🚀 Quick Start

```python
# Fast classification (single word output, cached)
result = agent(role="classify", task="Is this a bug?")

# Task routing (structured JSON, cached)
result = agent(role="route", task="Summarize this file")

# Generate code patch (returns {analysis, patch, tests})
result = agent(role="code", task="Fix the off-by-one error")

# Review a patch (returns {verdict, issues, corrected_patch})
result = agent(role="review", task="Review this diff", content=diff_text)

# Vision analysis (delegates to tools/vision.py)
result = agent(role="vision", task="Describe this image", context="/path/to/image.png")

---

## ⚙️ Configuration

No dedicated `.env` variables. Uses:
- `cfg.max_context_tokens` — fallback for `_max_context_chars()` (default: 8000 tokens → 32,000 chars)
- Per-role model config in `core/config.py` — `ROUTER_MODEL`, `EXECUTOR_MODEL`, `PLANNER_MODEL`, etc.
- Per-role budgets in `ROLE_CONFIG` — override global default per role

---

## 🔀 When to Use vs. Alternatives

| Need | Tool | Why |
|------|------|-----|
| Fast classification | `agent(dispatch, classify)` | Router, single word output, cached |
| Task routing | `agent(dispatch, route)` | Router, structured JSON, cached |
| Web research synthesis | `agent(dispatch, research)` | Executor, cites sources |
| Summarize long content | `agent(dispatch, summarize)` | Executor, dense output |
| Extract structured data | `agent(dispatch, extract)` | Executor, API json_mode |
| Evaluate quality | `agent(dispatch, critique)` | Executor, APPROVE/REVISE/REJECT |
| Analyze code | `agent(dispatch, analyze)` | Executor, no fixes — analysis only |
| Generate code patch | `agent(dispatch, code)` | Executor, returns `{analysis, patch, tests}` |
| Review code patch | `agent(dispatch, review)` | Executor, returns `{verdict, issues, corrected_patch}` |
| Decompose goal | `agent(dispatch, plan)` | Planner, returns ordered steps JSON |
| Architecture advice | `agent(dispatch, consultor)` | Consultor, best practices |
| Image analysis | `agent(vision_delegate, ...)` | Delegates to `tools/vision.py` |
| Debug metrics | `agent(metrics, ...)` | Returns per-role metrics and parse warnings |
| Clear cache | `agent(clear_cache)` | Clears response cache for deterministic roles |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](agent/ARCHITECTURE.md) | Module tree, design decisions, dispatch flow, test coverage, source code reference |
| [API.md](agent/API.md) | Full tool signature, all actions and roles, context trimming, JSON handling, caching, metrics, error taxonomy, security |
| [CHANGELOG.md](agent/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](agent/INSTRUCTIONS.md) | AI editing rules — NEVER DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
