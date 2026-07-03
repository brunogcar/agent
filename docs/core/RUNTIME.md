# 🔧 RUNTIME

The runtime subsystem (`core/runtime/`) is the **process governance layer** of the MCP Agent Stack. It handles activity tracking, process health monitoring, LLM server watchdog, background task execution, and async cancellation guards. It has zero dependencies on HTTP, gateway, or transport — it operates purely at the process level.

**Key characteristics:**
- **Activity tracking** — Global idle detection for background daemons and inference slot management
- **Process watchdog** — HTTP health probe + auto-restart with cooldown for LLM servers
- **Provider abstraction** — LM Studio, Ollama, vLLM support without code changes
- **Background task execution** — `ThreadPoolExecutor` with timeout monitoring
- **Async cancellation** — Prevents ghost mutations when workflows are cancelled
- **Health checks** — Comprehensive subsystem status for monitoring

---

## 🚀 Quick Start

```python
from core.runtime.activity_tracker import tracker
from core.runtime.cancellation import ensure_not_cancelled
from core.runtime.health import get_health
from core.runtime.providers import get_provider
from core.runtime.task_runner import run_background_task
```

*(Fill this section with relevant info from edits and refactors. Add quick-start examples as they are learned.)*

---

## 🔄 When to Use vs Alternatives

| Need | Use | Why |
|------|-----|-----|
| Idle detection / inference slots | `core/runtime/activity_tracker.py` | Thread-safe, RLock, background slot support |
| Ghost mutation prevention | `core/runtime/cancellation.py` | Async cancellation guard before writes |
| Subsystem health | `core/runtime/health.py` | Comprehensive checks: dirs, LM Studio, models, ChromaDB |
| LLM server monitoring | `core/runtime/watchdog.py` | Auto-restart with cooldown, lock files, provider-agnostic |
| Background tasks | `core/runtime/task_runner.py` | ThreadPoolExecutor + timeout monitor daemon |
| LLM provider abstraction | `core/runtime/providers.py` | LM Studio, Ollama, vLLM without code changes |

> **Note:** Runtime is internal infrastructure. It is consumed by `gateway_backend`, `llm_backend`, `memory_backend`, and `workflows`. It is never called directly by tools or end users.

---

## ⚙️ Configuration

```ini
MAX_CONCURRENT_INFERENCES=2              # Max parallel LLM calls
RUNTIME_PROVIDER=lmstudio                # LLM server provider
LM_STUDIO_BASE_URL=http://localhost:1234/v1  # LLM server endpoint
LM_STUDIO_RESTART_CMD=                   # Custom restart command (optional)
ENV=development                          # Environment mode
```

### Idle Thresholds

| Daemon | `min_idle_seconds` | Default | Purpose |
|--------|-------------------|---------|---------|
| Meta-learning | `min_idle_seconds` | 7200 (2h) | Only learn when agent is idle |
| Sleep-learn daemon | `SLEEP_MIN_IDLE_SECONDS` | 7200 (2h) | Only process feedback when idle |
| Diversity enforcer | 4 hours | 14400 | Only clean procedural memory when idle |
| Janitor | Inherited from daemon | — | Runs during sleep-learn idle cycles |

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](runtime/ARCHITECTURE.md) | Module tree, integration flow, design decisions, known concerns, test coverage, source code reference |
| [API.md](runtime/API.md) | Module APIs, function signatures, return shapes, health response format, error handling |
| [CHANGELOG.md](runtime/CHANGELOG.md) | Version history, completed milestones, roadmap, deferred items |
| [INSTRUCTIONS.md](runtime/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-04. See subfiles for detailed documentation.*
