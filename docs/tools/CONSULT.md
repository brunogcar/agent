# 🔍 Consult Tool

The `consult()` tool provides **optional cloud LLM advisory** for high-stakes tasks requiring stronger reasoning, domain expertise, or external validation. It is strictly **opt-in** and controlled via a `.env` kill-switch.

**Key characteristics:**
- **`@meta_tool` facade** — 3 actions (`advise` / `review` / `explain`) auto-discovered from `consult_ops/actions/` via the `DISPATCH` registry. Adding a new action = drop a file; the `action: Literal[...]` annotation and docstring update themselves.
- **8-file `consult_ops/` subpackage** — `_registry.py` (DISPATCH + `register_action`), `__init__.py` (auto-discovery), `helpers.py` (6 shared utilities), `prompts.py` (3 base prompts + format/context-type modifiers), `actions/{__init__,advise,review,explain}.py`.
- **Same LLM, different prompts** — all 3 actions route to one configured `consultor` role. Only the system prompt differs (base + format suffix + context-type modifier).
- **Cloud LLM dispatch** — Routes to a dedicated consultor model configured separately from local planner/executor/router chains.
- **Kill-switch ready** — Returns `{"status": "disabled"}` if `CONSULTOR_MODEL` is empty; no crashes, no silent fallbacks.
- **Rate-limit guard** — Pre-flight `check_rate_limit()` prevents accidental API quota burn.
- **Token-aware truncation** — Context pruned via `tiktoken` (cl100k_base) before dispatch to prevent overflow.
- **Observability built in** — `trace_id` threaded through every return path; `duration_ms` always present.
- **Cost-conscious** — Not in `PARALLEL_SAFE`, excluded from aggressive routing, intended for targeted use.

---

## 🚀 Quick Start

```python
# Advise — architectural advisory (default pre-v1.0 behavior preserved)
consult(action="advise", question="What are the trade-offs between async and sync database drivers in Python?")

# Review — structured code review with severity-tagged findings
consult(
    action="review",
    question="Focus on the auth flow and token rotation logic",
    context="<full source of auth.py>",
)

# Explain — educational concept explanation with analogies
consult(action="explain", question="How does RAG differ from fine-tuning?")

# With new v1.0 params: trace_id (observability), format, context_type
consult(
    action="review",
    question="Any race conditions in this cache invalidation code?",
    context="<source>",
    format="json",                # markdown (default) | json | bullet_points
    context_type="code",          # "" (default) | code | logs | architecture
    trace_id="wf-1234",
)

# Disabled by default — returns clear status if unconfigured
consult(action="advise", question="Should I use pydantic v1 or v2?")
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
| `action` empty / whitespace | `error` | `action is required (advise \| explain \| review)` |
| `action` not in DISPATCH | `error` | `Unknown action '<x>'. Use: advise \| explain \| review` |
| `CONSULTOR_MODEL` empty / unset | `disabled` | `Consultor is disabled. Set CONSULTOR_MODEL in .env to enable.` |
| `question` empty or whitespace | `error` | `The question parameter cannot be empty.` |
| Provider unavailable (`llm.is_available`) | `disabled` | `Provider for consultor role ('{provider}') is not available...` |
| Rate limit exceeded | `rate_limited` | `Rate limit exceeded for {provider}. Please wait before consulting again.` |
| Handler raises exception | `error` | `Consult action failed: <exc>` |

> **Note:** `consultor` is added to `cfg.model_registry` **only** if `CONSULTOR_MODEL` resolves to a non-empty model. Unlike other roles, there is no fallback chain — if unset, the role simply does not exist in the registry. The router's `_RE_DIRECT_CONSULT` heuristic already routes "ask another model" intents directly here; no router changes were needed for v1.0.

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Local code execution | `python` | Fast, free, sandboxed |
| Local web search | `web` / `tavily` | Self-hosted or API-optimized |
| Cloud advisory / architecture review | `consult(action="advise")` | Stronger reasoning, external validation |
| Cloud code review with severity tags | `consult(action="review")` | 5-dimension structured findings (correctness/security/perf/maintainability/best-practices) |
| Cloud concept explanation | `consult(action="explain")` | Educator persona with analogies + step-by-step breakdowns |
| Local architecture review | `agent` (review role) | Free, local, but weaker model |
| Complex debugging | `consult(action="review")` | Deep trace analysis, higher accuracy |
| Strategic planning | `consult(action="advise")` | Trade-off analysis, industry context |
| Multi-model consensus | `swarm` | Cross-provider consultation; `consult` is single-model only |
| Routine code generation | `python` or `agent` (code role) | Faster, cheaper, no cloud quota |
| Simple factual lookup | `web` | No LLM cost, direct source |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](consult/ARCHITECTURE.md) | Source code reference (8-file subpackage), module tree, dispatch flow, `_call_consultor` indirection, 3-action pattern, design decisions, test coverage |
| [API.md](consult/API.md) | Full `@meta_tool` signature, 3 action sections (advise/review/explain), new params (`trace_id`/`format`/`context_type`), error handling table, security |
| [CHANGELOG.md](consult/CHANGELOG.md) | v1.0 entry, breaking changes, completed table, in-progress + roadmap (10 suggested items), deferred |
| [INSTRUCTIONS.md](consult/INSTRUCTIONS.md) | AI editing rules — NEVER DO (reversed #1), ALWAYS DO (11 rules), anti-patterns from the `_call_consultor` discovery |

---

*Last updated: 2026-07-15 (v1.0). See subfiles for detailed documentation.*
