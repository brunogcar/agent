# 🧭 Router

The Task Router (`core/router.py`) is the **ultra-fast classification layer** that sits between the user's goal and the workflow execution engine. It uses the dedicated Router role (`cfg.router_model`) to classify intent, determine complexity, and select the correct workflow or direct tool, all within a strict 15-second timeout.

**Key characteristics:**
- **Speed-first** — 15s hard timeout, falls back to heuristics if model is slow or unavailable
- **Dual-mode routing** — Model-based (primary) + keyword heuristics (fallback)
- **Confidence-aware** — Low-confidence decisions include clarifying questions to prevent wasted VRAM
- **Robust JSON extraction** — 3-layer pipeline handles markdown fences, nested objects, and escaped quotes. **[Pre-v1.1]** The pipeline now lives in `core/json_extract.extract_first_json()` — `_extract_first_json()` in `core/router.py` is a one-line delegation. The same `core/json_extract.py` module also backs `helpers._parse_json` in autocode (single source of truth for LLM JSON parsing). Internal refactor; no behavior change.
- **Zero hardcoding** — All model references use `cfg.router_model`

---

## 🚀 Quick Start

```python
from core.router import router

# Classify a task
decision = router.route(goal="Fix the timeout bug in tools/web.py")

# Quick complexity score
score = router.classify_complexity("Research ChromaDB best practices")
```

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `ROUTER_MODEL` | Falls back to planner | Fast, small model for classification |
| `ROUTER_TIMEOUT` | `15` | Hard timeout in seconds |

**Current configuration:**

```ini
ROUTER_MODEL=gemma-2-2b-it
ROUTER_TIMEOUT=15
```

---

## 🔄 When to Use vs. Alternatives

| Scenario | Tool | Why |
|----------|------|-----|
| Classify a new task | `router.route(goal)` | Determines which workflow/tool to use |
| Score task complexity | `router.classify_complexity(goal)` | Used by workflows for timeout adjustment |
| Skip routing (known task) | Call workflow/tool directly | When you already know which tool to use |
| Gateway dispatch | `dispatcher.dispatch()` | Uses router internally for `workflow: "auto"` |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](router/ARCHITECTURE.md) | Module tree, routing flow, design goals, heuristic priority, complexity scale, known concerns, testing |
| [API.md](router/API.md) | `route()`, `classify_complexity()`, `RoutingDecision`, routing targets, confidence guard, two-tier strategy, regex patterns |
| [CHANGELOG.md](router/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](router/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-11 (Pre-v1.1 — `Robust JSON extraction` bullet updated to note the 3-layer pipeline now lives in `core/json_extract.extract_first_json()`; `_extract_first_json()` in `core/router.py` is a one-line delegation. See subfiles for detailed documentation.*
