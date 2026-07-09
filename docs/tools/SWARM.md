# 🐝 Swarm Tool

The `swarm()` tool is a **multi-model meta-tool** that calls multiple cloud LLM providers in parallel and applies a coordination strategy (consensus, race, vote, compare, or list_providers). It uses the same `@meta_tool` + `swarm_ops/` pattern as `git`, `file`, `web`, etc.

Where `consult()` consults a *single* cloud model and `agent()` routes to a *single* role, `swarm()` fans a single question out to **all configured cloud providers at once** and combines the responses — synthesized, raced, voted, or laid out side-by-side.

**Key characteristics:**
- **Multi-model by design** — Same question sent to every configured cloud provider (OpenAI, DeepSeek, Claude, Gemini, Qwen, Kimi, Mistral, Z.ai, MiMo — whatever is configured)
- **Parallel fan-out** — `ThreadPoolExecutor` (capped at 5 workers) calls providers concurrently; `_call_all_providers()` waits for all, `_call_providers_race()` returns on the first valid response
- **5 coordination actions** — `consensus`, `race`, `vote`, `compare`, `list_providers`
- **Direct provider calls** — Calls `provider.chat_completion()` directly (NOT through `llm.complete()`), bypassing role routing, circuit breakers, and rate limiting. Swarm handles resilience at its own layer
- **Cloud-only** — Skips `lmstudio` (local). Swarm is for cloud providers only
- **Env-driven** — Requires `*_API_KEY` + `*_BASE_MODEL` for each participating provider
- **Deterministic output** — Results sorted by provider name
- **NOT parallel-safe** — Uses `ThreadPoolExecutor` internally; nested parallelism (e.g. calling `swarm()` from inside `parallel()`) risks thread exhaustion. Excluded from `PARALLEL_SAFE`
- **Auto-discovered** — `@tool` + `@meta_tool` + `@register_action` = zero manual wiring in `server.py`

---

## 🚀 Quick Start

```python
# Synthesize best answer from all configured cloud providers
swarm(action="consensus", question="How to handle concurrent writes in SQLite?")

# Race — first valid response wins (others cancelled)
swarm(action="race", question="What is the capital of France?")

# Vote — classify or gate decisions by model agreement
swarm(action="vote", question="Is this code safe to deploy? Answer YES or NO.")

# Compare — side-by-side, no synthesis
swarm(action="compare", question="Explain RAFT consensus in 3 sentences.")

# Restrict to a subset of providers (comma-separated, lowercase)
swarm(action="consensus", question="Best architecture for a chat app?", providers="openai,claude")

# Provide shared background context (prepended as a user/assistant turn)
swarm(action="consensus", question="Should we use async or sync drivers?", context="Project uses FastAPI + Postgres.")

# See what providers are wired up before asking anything
swarm(action="list_providers")
```

---

## ⚙️ Configuration

Swarm relies on the cloud providers configured in `.env` for the LLM core. Each participating provider needs **both** an API key and a base model env var:

```ini
# Per-provider: must have BOTH <NAME>_API_KEY and <NAME>_BASE_MODEL to participate
OPENAI_API_KEY=sk-...
OPENAI_BASE_MODEL=gpt-4o-mini

CLAUDE_API_KEY=sk-ant-...
CLAUDE_BASE_MODEL=claude-3-5-sonnet-20241022

GEMINI_API_KEY=...
GEMINI_BASE_MODEL=gemini-1.5-pro

DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_MODEL=deepseek-chat

# ... (QWEN, KIMI, MISTRAL, ZAI, MIMO — same pattern)
```

**Rules:**
- `lmstudio` is **always skipped** (local — swarm is cloud-only).
- A provider without `<NAME>_BASE_MODEL` set is silently skipped (no crash, just excluded).
- Use `swarm(action="list_providers")` to verify which providers are currently active.
- Use the `providers="openai,claude"` filter to restrict a single call to a subset.

**No dedicated swarm `.env` variables.** Per-call `timeout` (default 60s) and `max_tokens` (default 1024) are passed as tool arguments.

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Synthesized answer combining multiple models | `swarm(consensus)` | All models answer, planner synthesizes best response |
| Fastest valid answer (cancel the rest) | `swarm(race)` | First valid response wins, remaining futures cancelled |
| Majority/unanimous vote for classification | `swarm(vote)` | All models answer, agreement analysis (unanimous/majority/split/disagreement) |
| Raw side-by-side model comparison | `swarm(compare)` | All responses returned without synthesis — inspect each directly |
| Discover what cloud providers are configured | `swarm(list_providers)` | No LLM calls, just env introspection |
| Single strong cloud answer (one model) | `consult(question)` | One designated cloud model via separate provider chain — cheaper, no fan-out |
| Route to a specialist sub-agent role | `agent(role, task)` | Role-based dispatch (code, review, plan, etc.), single model per role |
| Local, free, private answer | `llm.complete(role=...)` via `agent(role=...)` | Routes to LM Studio (local), no API spend |
| Parallelize *different* tool calls | `parallel(tools=[...])` | Concurrent non-LLLM tool execution; do NOT nest `swarm()` inside `parallel()` |

**Key distinction — `swarm` vs `consult`:**
- `consult()` is opt-in, single-model, kill-switched, rate-limited — for high-stakes advisory calls to ONE strong cloud model.
- `swarm()` is multi-model, parallel, always-on (when providers configured) — for cross-model consensus, racing, and agreement analysis.

**Key distinction — `swarm` vs `agent`:**
- `agent()` routes by **role** (code, review, plan, etc.) to a single specialist model. Each role has its own context budget, cache, and model routing.
- `swarm()` routes by **provider** (openai, claude, gemini, etc.) — same question to every provider, no role semantics.

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [API.md](swarm/API.md) | Full tool signature, all 5 actions, parameter tables, error handling, security |
| [ARCHITECTURE.md](swarm/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, source code reference, testing |
| [CHANGELOG.md](swarm/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](swarm/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-09. See subfiles for detailed documentation.*
