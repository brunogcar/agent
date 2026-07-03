# 🔍 Consult Tool

The `consult()` tool provides **optional cloud LLM advisory** for high-stakes tasks requiring stronger reasoning, domain expertise, or external validation. It is strictly **opt-in** and controlled via a `.env` kill-switch.

**Key characteristics:**
- **Cloud LLM dispatch** — Routes to a dedicated consultor model configured separately from local planner/executor/router chains
- **Kill-switch ready** — Returns `{"status": "disabled"}` if `CONSULTOR_MODEL` is empty; no crashes, no silent fallbacks
- **Rate-limit guard** — Pre-flight `check_rate_limit()` prevents accidental API quota burn
- **Token-aware truncation** — Context pruned via `tiktoken` (cl100k_base) before dispatch to prevent overflow
- **Cost-conscious** — Not in `PARALLEL_SAFE`, excluded from aggressive routing, intended for targeted use

---

## 🚀 Quick Start

```python
# Basic advisory query
consult(question="What are the trade-offs between async and sync database drivers in Python?")

# With supporting context
consult(
    question="Why is this query slow?",
    context="EXPLAIN ANALYZE output: Seq Scan on users..."
)

# Disabled by default — returns clear status if unconfigured
consult(question="Should I use pydantic v1 or v2?")
# → {"status": "disabled", "error": "Consultor is disabled. Set CONSULTOR_MODEL in .env to enable."}
```

---

## ⚙️ Configuration & Kill-Switch

The consult tool is **disabled by default**. It only activates when explicitly configured:

```ini
# .env
CONSULTOR_MODEL=gpt-4o                     # Cloud model name — must match provider /v1/models
CONSULTOR_BASE_URL=https://api.openai.com/v1
CONSULTOR_API_KEY=sk-...
CONSULTOR_TIMEOUT=60                       # HTTP timeout (seconds)
```

**Kill-switch behavior:**

| Condition | Return Status | Message |
|-----------|--------------|---------|
| `CONSULTOR_MODEL` empty / unset | `disabled` | `Consultor is disabled. Set CONSULTOR_MODEL in .env to enable.` |
| `question` empty or whitespace | `error` | `The question parameter cannot be empty.` |
| Provider unavailable (`llm.is_available`) | `disabled` | `Provider for consultor role ('{provider}') is not available...` |
| Rate limit exceeded | `rate_limited` | `Rate limit exceeded for {provider}. Please wait before consulting again.` |

> **Note:** `consultor` is added to `cfg.model_registry` **only** if `CONSULTOR_MODEL` resolves to a non-empty model. Unlike other roles, there is no fallback chain — if unset, the role simply does not exist in the registry.

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Local code execution | `python` | Fast, free, sandboxed |
| Local web search | `web` / `tavily` | Self-hosted or API-optimized |
| Cloud advisory / architecture review | `consult` | Stronger reasoning, external validation |
| Local architecture review | `agent` (review role) | Free, local, but weaker model |
| Complex debugging | `consult` | Deep trace analysis, higher accuracy |
| Strategic planning | `consult` | Trade-off analysis, industry context |
| Routine code generation | `python` or `agent` (code role) | Faster, cheaper, no cloud quota |
| Simple factual lookup | `web` | No LLM cost, direct source |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](consult/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](consult/API.md) | Full tool signature, output format, security |
| [CHANGELOG.md](consult/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](consult/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
