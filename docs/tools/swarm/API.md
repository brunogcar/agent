<- Back to [Swarm Overview](../SWARM.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(DISPATCH["swarm"], doc_sections=[...])
def swarm(
    action: str,
    question: str = "",
    context: str = "",
    providers: str = "",
    max_tokens: int = 1024,
    timeout: int = 60,
    trace_id: str = "",
) -> dict:
    """Multi-model swarm meta-tool — consult multiple cloud LLMs in parallel."""
```

> **Note:** Unlike `git()` / `file()` / `web()`, the swarm facade declares `action: str` and performs manual dispatch via `DISPATCH["swarm"][action]`, returning a `fail()` result listing valid actions for direct-Python callers that bypass schema validation. **However**, `@meta_tool` still applies the `Literal[...]` enum to the `action` parameter (just like other meta-tools — there is no skip logic in `@meta_tool`), so the LLM-facing FastMCP schema gets the enum and rejects hallucinated action names at the schema layer. Both layers coexist: schema validation for LLM calls, manual dispatch + friendly `fail()` for internal Python callers (e.g. autocode's `_swarm_debug_consensus`).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `str` | — | **Required.** One of: `consensus` \| `race` \| `vote` \| `compare` \| `list_providers`. Lowercased + stripped before dispatch |
| `question` | `str` | `""` | The question to ask every provider. **Required for `consensus`, `race`, `vote`, `compare`.** Ignored by `list_providers` |
| `context` | `str` | `""` | Optional shared background. Prepended as a `user`/`assistant` turn (`Background: ...` / `Understood.`) before the question |
| `providers` | `str` | `""` | Optional comma-separated provider filter, e.g. `"openai,claude"`. Empty = all configured cloud providers. Case-insensitive, trimmed. `lmstudio` always excluded |
| `max_tokens` | `int` | `1024` | Max response tokens per provider. Passed through to `provider.chat_completion(max_tokens=...)` |
| `timeout` | `int` | `60` | Per-provider call timeout (seconds). `ThreadPoolExecutor` waits up to `timeout + 10s` for futures |
| `trace_id` | `str` | `""` | Trace identifier for observability. Auto-injected into the result dict |

**Dispatch behavior:**
1. `action` is lowercased + stripped; empty → `fail("action is required")`.
2. `DISPATCH["swarm"][action]` lookup; unknown → `fail("Unknown action '...'. Use: consensus | race | vote | compare | list_providers")`.
3. All kwargs forwarded to the handler (`**kwargs` absorbs unused params per handler).
4. Handler exceptions caught and returned as `fail(f"Swarm action failed: {e}")`.
5. `max_tokens` must be in `[1, 8192]`; `timeout` must be in `[1, 300]` seconds — out-of-bounds returns `fail(..., error_code="INVALID_ACTION")` (v1.0.1).
6. `duration_ms` (total wall time) appended to every successful result.

---

## ⚡ Actions

### Summary Table

| Action | Required Params | Optional Params | Purpose |
|--------|-----------------|-----------------|---------|
| `consensus` | `question` | `context`, `providers`, `max_tokens`, `timeout` | All providers answer → planner synthesizes best response |
| `race` | `question` | `context`, `providers`, `max_tokens`, `timeout` | All providers answer in parallel → first valid response wins, rest cancelled |
| `vote` | `question` | `context`, `providers`, `max_tokens`, `timeout` | All providers answer → agreement analysis (unanimous/majority/split/disagreement) |
| `compare` | `question` | `context`, `providers`, `max_tokens`, `timeout` | All providers answer → responses returned side-by-side (no synthesis) |
| `list_providers` | — | — (ignores all other params) | Lists all configured cloud providers + their models |

---

### `consensus` — Synthesized Multi-Model Answer

**Purpose:** Ask every configured cloud provider the same question, then have the planner role synthesize a single best answer that combines the strongest points from each response and notes any disagreements.

**Required params:** `question`

**Optional params:** `context`, `providers`, `max_tokens`, `timeout`

**Example:**
```python
swarm(action="consensus", question="How to handle concurrent writes in SQLite?")
swarm(action="consensus", question="Best architecture for a chat app?", providers="openai,claude")
swarm(action="consensus", question="Async or sync drivers?", context="Project uses FastAPI + Postgres.")
```

**Return format:**
```json
{
  "status": "success",
  "responses": [
    {"provider": "claude", "model": "claude-3-5-sonnet-20241022", "text": "...", "latency": 2.31, "tokens": 412, "error": ""},
    {"provider": "openai", "model": "gpt-4o-mini", "text": "...", "latency": 1.84, "tokens": 388, "error": ""}
  ],
  "synthesis": "Combined answer combining the strongest points from each response...",
  "provider_count": 4,
  "successful_count": 3,
  "trace_id": "abc123",
  "duration_ms": 5421
}
```

**Notes:**
- The synthesis step uses `llm.complete(role="planner", ...)` — this is the **only** place swarm routes through `llm.complete()` rather than calling `provider.chat_completion()` directly.
- If all providers fail, returns `fail("All providers failed to respond.", responses=results)` — the `responses` array is still attached so callers can inspect the per-provider errors.
- `provider_count` = number of providers *attempted* (after filter + env checks); `successful_count` = those that returned non-empty text with no error.

---

### `race` — First Valid Response Wins

**Purpose:** Fire the question to all providers in parallel; return as soon as the first provider returns a valid (non-empty, error-free) response. Remaining futures are cancelled (best effort).

**Required params:** `question`

**Optional params:** `context`, `providers`, `max_tokens`, `timeout`

**Example:**
```python
swarm(action="race", question="What is the capital of France?")
swarm(action="race", question="Quick fact: who invented Python?", providers="openai,deepseek")
```

**Return format:**
```json
{
  "status": "success",
  "winner": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "text": "Paris.",
    "latency": 0.82,
    "tokens": 5,
    "error": ""
  },
  "responses": [
    {"provider": "deepseek", "model": "deepseek-chat", "text": "Paris.", "latency": 0.82, "tokens": 5, "error": ""}
  ],
  "provider_count": 4,
  "trace_id": "abc123",
  "duration_ms": 940
}
```

**Notes:**
- `responses` may include only the winner plus any providers that completed *before* the winner (e.g. failed fast). Late providers are cancelled.
- If all providers fail, returns `fail("All providers failed to respond.", responses=results)`.
- **v1.0.1:** race now returns as soon as the first valid response lands (previously blocked on `ThreadPoolExecutor.__exit__` → `shutdown(wait=True)` until all in-flight calls finished). Cancellation is best-effort — `shutdown(cancel_futures=True)` cancels PENDING futures; running futures complete in the background with results discarded (`wait=False`).

---

### `vote` — Agreement Analysis

**Purpose:** Ask all providers, then group responses by normalized text (lowercased, truncated to 200 chars) to classify agreement: `unanimous`, `majority`, `split`, or `disagreement`.

**Required params:** `question`

**Optional params:** `context`, `providers`, `max_tokens`, `timeout`

**Example:**
```python
swarm(action="vote", question="Is this code safe to deploy? Answer YES or NO.")
swarm(action="vote", question="Classify this email as spam or not spam: ...", providers="openai,claude,gemini")
```

**Return format:**
```json
{
  "status": "success",
  "responses": [ /* same shape as consensus */ ],
  "agreement": "majority",
  "groups": [
    {"providers": ["openai", "claude", "gemini"], "count": 3, "preview": "yes"},
    {"providers": ["deepseek"], "count": 1, "preview": "yes, with caveats"}
  ],
  "provider_count": 5,
  "successful_count": 4,
  "trace_id": "abc123",
  "duration_ms": 3120
}
```

**Agreement classification rules (v1.0.1):**
| Condition | Agreement |
|-----------|-----------|
| Only 1 provider succeeded | `single_response` |
| All successful responses (≥2) normalize to the same text | `unanimous` |
| Exactly 2 distinct normalized texts AND largest group > 50% of successful | `majority` |
| Exactly 2 distinct normalized texts AND no group > 50% (incl. 2v2 tie) | `split` |
| 3+ distinct normalized texts | `disagreement` |

**v1.0.1 changes:**
- `single_response` is a new label (v1.0 misclassified this as `unanimous`). A single voter cannot express agreement; downstream consumers (e.g. autocode `vcs_ops.confidence_map`) should map `single_response` to `LOW` confidence, not `HIGH`.
- `split` now correctly covers the 2-successful-2-distinct case (v1.0 misclassified it as `disagreement` due to a `len(successful) > 2` guard).

**Normalization:** `text.strip().lower()[:200]` — leading/trailing whitespace removed, case-folded, truncated to 200 chars. This is a *coarse* comparison suited to short answers (YES/NO, class labels). For long-form prose, `disagreement` is the expected outcome.

**Notes:**
- `groups` is sorted by `count` descending (largest group first).
- Each group's `preview` is the first 100 chars of its normalized key.
- If all providers fail, returns `fail("All providers failed to respond.", responses=results)`.

---

### `compare` — Side-by-Side, No Synthesis

**Purpose:** Ask all providers and return every response unmodified. No planner synthesis, no agreement analysis — the caller inspects each response directly.

**Required params:** `question`

**Optional params:** `context`, `providers`, `max_tokens`, `timeout`

**Example:**
```python
swarm(action="compare", question="Explain RAFT consensus in 3 sentences.")
swarm(action="compare", question="Best practices for error handling in Python?", providers="openai,claude")
```

**Return format:**
```json
{
  "status": "success",
  "responses": [
    {"provider": "claude", "model": "claude-3-5-sonnet-20241022", "text": "...", "latency": 2.41, "tokens": 156, "error": ""},
    {"provider": "deepseek", "model": "deepseek-chat", "text": "...", "latency": 1.92, "tokens": 142, "error": ""},
    {"provider": "openai", "model": "gpt-4o-mini", "text": "...", "latency": 1.78, "tokens": 138, "error": ""}
  ],
  "provider_count": 3,
  "successful_count": 3,
  "trace_id": "abc123",
  "duration_ms": 2456
}
```

**Notes:**
- `responses` is sorted by provider name (deterministic output) — same as `consensus` and `vote`.
- If all providers fail, returns `fail("All providers failed to respond.", responses=results)`.

---

### `list_providers` — Introspection

**Purpose:** List all cloud providers currently configured for swarm use. Performs **no LLM calls** — pure env introspection. Useful as a pre-flight check before calling `consensus` / `race` / `vote` / `compare`.

**Required params:** none (all other params ignored)

**Example:**
```python
swarm(action="list_providers")
```

**Return format:**
```json
{
  "status": "success",
  "providers": [
    {"name": "claude", "model": "claude-3-5-sonnet-20241022", "available": true},
    {"name": "deepseek", "model": "deepseek-chat", "available": true},
    {"name": "openai", "model": "gpt-4o-mini", "available": true}
  ],
  "count": 3,
  "trace_id": "abc123",
  "duration_ms": 4
}
```

**Notes:**
- `lmstudio` is never listed (always skipped — swarm is cloud-only).
- Providers without `<NAME>_BASE_MODEL` env var are silently excluded — they won't appear here.
- `available` is always `true` in v1.0 (the field exists for future health-check gating).

---

## ❗ Error Handling

All errors return a standardized `fail()` dict:

```json
{
  "status": "error",
  "error": "Descriptive message",
  "trace_id": "abc123"
}
```

| Error | Trigger | Includes |
|-------|---------|----------|
| `action is required` | Empty `action` param | — |
| `Unknown action '<x>'. Use: consensus \| race \| ...` | Action not in DISPATCH | — |
| `question is required for <action>` | Empty `question` on `consensus` / `race` / `vote` / `compare` | — |
| `max_tokens must be between 1 and 8192, got <n>` | `max_tokens` out of bounds (v1.0.1) | `INVALID_ACTION` |
| `timeout must be between 1 and 300 seconds, got <n>` | `timeout` out of bounds (v1.0.1) | `INVALID_ACTION` |
| `No cloud providers configured. Set *_API_KEY and *_BASE_MODEL in .env to enable.` | `_get_available_providers()` returns empty | — |
| `All providers failed to respond.` | Every provider returned an error or empty text | `responses: [...]` (per-provider errors visible) |
| `Swarm action failed: <exception>` | Unhandled exception in handler | — |

**Per-provider errors** are NOT fatal — a provider that raises (network error, auth error, timeout, etc.) is captured into its result dict with `text=""` and `error="<message>"`, and the remaining providers still contribute to the result. The action only fails if *every* provider fails.

**Timeout behavior:** `ThreadPoolExecutor` uses `as_completed(futures, timeout=timeout+10)` (in `_call_all_providers`) and `wait(futures, timeout=remaining, return_when=FIRST_COMPLETED)` (in `_call_providers_race`). A provider that exceeds the per-call `timeout` inside `chat_completion()` is captured by the provider's own timeout handling; a future that exceeds `timeout+10` at the executor level is recorded as a `timeout` error for that provider. **v1.0.1:** `_call_provider()` now sanitizes exception messages via `_sanitize_error()` before storing them — this strips API keys that Gemini puts in the URL query string (`?key=...`) from `httpx.HTTPStatusError` messages, preventing key leakage into logs + LLM context.

---

## 🔒 Security

**No filesystem operations, no path_guard needed.** Swarm does not read from or write to the filesystem. It only:

1. Reads environment variables (`*_API_KEY`, `*_BASE_MODEL`) — already trusted config.
2. Calls `provider.chat_completion()` over HTTPS to cloud LLM APIs — same surface area as `consult()` and `agent()`.
3. Returns text payloads from those APIs to the caller — no automatic file writes, no subprocess execution, no shell.

**No SSRF surface.** All outbound calls go to the cloud LLM provider endpoints already trusted by `core/llm/`. No user-supplied URLs are passed to swarm.

**API key handling.** API keys are read from env by the provider instances at registration time — swarm never touches them directly. Swarm's `_get_available_providers()` only checks *whether* `<NAME>_BASE_MODEL` is set, never reads `<NAME>_API_KEY`.

**Provider text is untrusted.** Text returned from cloud providers is treated as untrusted model output and returned to the caller as-is. Callers (e.g. `agent()`, `parallel()`, or the LLM orchestrator) are responsible for any downstream rendering safety. Swarm itself does not `eval()`, `exec()`, or `subprocess.run()` provider text.

**Cost / rate-limit awareness.** Swarm bypasses `llm.complete()`'s role routing, circuit breakers, and rate limiting (by design — see ARCHITECTURE.md). Callers should be aware that a `consensus` call to N providers burns N API calls per invocation. Per-provider rate limiting is a roadmap item (see CHANGELOG.md).

---

*Last updated: 2026-07-13 (v1.0.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
