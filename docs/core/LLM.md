# 🧠 LLM

The LLM backend is the **unified interface for all model interactions** in the agent stack. It handles role-based model selection, context budgeting, circuit breakers, and structured output parsing. Nothing else in the codebase calls the LLM server directly — everything goes through `core.llm`.

**Key characteristics:**
- **Role-based dispatch** — Callers say `"executor"` or `"router"`, not raw model strings
- **Circuit breaker per role** — 3 cumulative failures (no time window) → cooldown equal to that role's own configured timeout, auto-recovery via half-open
- **Cognitive context budgeting** — Priority-based message trimming that preserves the most important content
- **Dual output modes** — Text and JSON, each with their own extraction pipeline
- **Provider abstraction** — LM Studio (local), OpenAI-compatible (OpenAI, DeepSeek, Mistral, Qwen, Kimi, Z.ai, MiMo), native (Claude/Anthropic, Gemini/Google)
- **Thread-safe singleton** — One `llm` instance, imported everywhere via `from core.llm import llm`

---

## 🚀 Quick Start

```python
from core.llm import llm

# Simple prompt + response
result = llm.complete(role="executor", system="You are a senior Python developer.", user="Fix this bug")

# JSON structured output
result = llm.complete(role="executor", system="...", user="...", json_mode=True)

# Raw message control (low-level)
result = llm.call(role="executor", messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}])
```

---

## ⚙️ Configuration

### Environment Variables

| Env Variable | Role | Default | Description |
|--------------|------|---------|-------------|
| `PLANNER_MODEL` | planner | — | Large model for complex reasoning |
| `EXECUTOR_MODEL` | executor | Falls back to planner | Medium model for code/analysis |
| `ROUTER_MODEL` | router | Falls back to planner | Fast model for classification |
| `VISION_MODEL` | vision | Falls back to planner | Multimodal model |
| `SUMMARIZE_MODEL` | summarize | Falls back to executor | Lightweight summarization |
| `EXTRACT_MODEL` | extract | Falls back to executor | Lightweight extraction |
| `RESEARCH_MODEL` | research | Falls back to executor | Web research synthesis |
| `CRITIQUE_MODEL` | critique | Falls back to executor | Quality feedback |
| `ANALYZE_MODEL` | analyze | Falls back to executor | Data analysis |
| `CODE_MODEL` | code | Falls back to executor | Code generation |
| `REVIEW_MODEL` | review | Falls back to executor | Code review |
| `REFACTOR_MODEL` | refactor | Falls back to code | Autonomous code refactoring |
| `TEST_MODEL` | test | Falls back to code | Autonomous test generation |
| `DOCUMENT_MODEL` | document | Falls back to summarize | Autonomous documentation generation |
| `LM_STUDIO_BASE_URL` | — | `http://localhost:1234/v1` | LLM server endpoint |

**Timeout env vars** (all in `core/config.py`, none in `llm_backend/config.py`):
`PLANNER_TIMEOUT`, `EXECUTOR_TIMEOUT`, `ROUTER_TIMEOUT`, `VISION_TIMEOUT`, `CLASSIFY_TIMEOUT`, `ROUTE_TIMEOUT`, `SUMMARIZE_TIMEOUT`, `EXTRACT_TIMEOUT`, `RESEARCH_TIMEOUT`, `CRITIQUE_TIMEOUT`, `ANALYZE_TIMEOUT`, `CODE_TIMEOUT`, `REVIEW_TIMEOUT`, `REFACTOR_TIMEOUT`, `TEST_TIMEOUT`, `DOCUMENT_TIMEOUT`, `CONSULTOR_TIMEOUT`.

---

## 🔄 When to Use

| Scenario | Method | Why |
|----------|--------|-----|
| Simple prompt + response | `llm.complete(role, system, user)` | High-level, handles context budgeting |
| JSON structured output | `llm.complete(..., json_mode=True)` | 3-layer extraction, populates `result.parsed` |
| Raw message control | `llm.call(role, messages)` | Low-level, no budgeting or assembly |
| Quick classification | `llm.complete(role="router", ...)` | 15s timeout, temperature=0.0 |
| Complex planning | `llm.complete(role="planner", ...)` | 180s timeout, temperature=0.2 |
| Lightweight extraction | `llm.complete(role="extract", ...)` | Small fast model, low cost |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](llm/ARCHITECTURE.md) | Module tree, call flow, facade pattern, role hierarchy, thread safety, observability, known concerns |
| [API.md](llm/API.md) | `complete()`, `call()`, `LLMResponse`, role configuration, fallback chain, context budgeting, circuit breaker, provider abstraction, JSON parsing |
| [CHANGELOG.md](llm/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](llm/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-08. See subfiles for detailed documentation.*
