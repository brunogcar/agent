# 🧠 LLM Client Architecture & Provider Abstraction

The LLM client is the unified interface for all model interactions in the agent stack. Following the Phase 1 decomposition, the monolithic `core/llm.py` has been reduced to a thin backward-compatible facade. The core execution engine, provider abstractions, circuit breakers, and dynamic routing now live in the `core/llm_backend/` namespace.

## 🏗️ Architecture Overview

### Design Goals
- **Single Call Site:** Nothing else in the codebase calls `requests` or `httpx` directly for LLM interactions.
- **Provider Abstraction:** Adding new backends requires only a new `Provider` class.
- **Frictionless Routing:** A single `_MODEL` variable in `.env` dictates the provider, base URL, and default model automatically.
- **Role-Based Dispatch:** Callers say `"executor"` or `"consultor"`, not raw model strings.
- **Explicit Advisory:** Cloud APIs are accessed via an explicit `consult` tool, not silent fallbacks.
- **Full Trace Integration:** Every call logged with `trace_id`.

### Component Hierarchy
```text
core/llm.py (Thin Facade / Re-exports)
   ↓
core/llm_backend/
   ├── factory.py          # Composition root & dynamic provider registration
   ├── client.py           # LLMClient (singleton, role dispatch, retries)
   ├── config.py           # RoleConfig builder
   ├── budget.py           # Rate limiting & sliding window protection
   ├── circuit_breaker.py  # State machine (CLOSED → OPEN → HALF_OPEN)
   ├── response.py         # LLMResponse dataclass
   └── providers/
       ├── base.py         # BaseProvider ABC
       ├── lmstudio.py     # Local OpenAI-compatible provider
       └── openai_compat.py# Cloud provider (OpenAI, DeepSeek, Mistral, Qwen, Kimi)
```

---

## 🌐 Frictionless Provider Routing (Phase 3)

The configuration layer eliminates hardcoded provider lists. You no longer need to specify a `PROVIDER` variable for every role. 

### How it Works
- **Exact Match (Cloud):** If you set a role to an exact provider name (e.g., `PLANNER_MODEL=openai`), the config automatically resolves the provider, pulls the `OPENAI_BASE_URL`, and defaults to the `OPENAI_BASE_MODEL`.
- **Prefix/Local Match (Local):** If you set it to a local model name (e.g., `EXECUTOR_MODEL=qwen-3b`), it automatically routes to your local `lmstudio` provider.
- **Opt-Out (Blank):** If you leave it blank (e.g., `CONSULTOR_MODEL=`), the role is safely disabled and skipped in the registry.

### Dynamic Factory Registration
`core/llm_backend/factory.py` scans `cfg` at startup. If a cloud provider's `API_KEY` is present in `.env`, it automatically instantiates and registers an `OpenAICompatibleProvider` for that service. No code changes are required to add new cloud vendors.

---

## 🧠 Advisory Swarm & Explicit Consult Tool (Phase 4)

To maintain a local-first philosophy while allowing strategic cloud escalation, cloud APIs are accessed via an explicit MCP tool rather than silent system fallbacks.

### The `consult` Tool (`tools/consult.py`)
Provides a dedicated, controllable channel for the local Planner to request high-level advice, break deadlocks, or review architecture.

**Guardrails:**
1. **The Kill Switch:** If `CONSULTOR_MODEL` is blank in `.env`, the tool instantly returns `{"status": "disabled"}`. No network calls, no errors.
2. **Mechanical Context Truncation:** The `context` string is strictly capped at 4000 characters. If the local LLM attempts to dump a massive codebase, it is silently truncated and a `warning` is returned.
3. **Rate Limiting:** Backed by an in-memory sliding window in `core/llm_backend/budget.py`. If the agent enters a loop and exceeds the RPM limit, the tool returns `{"status": "rate_limited"}` instead of burning API credits or getting the key banned.

**Tool Signature:**
```python
@tool
def consult(question: str, context: str = "") -> dict:
```

---

## 🔌 Provider Abstraction

### BaseProvider (Abstract)
All LLM backends must implement this interface:
```python
class BaseProvider(ABC):
    name: str = "base"
    
    @abstractmethod
    def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: int,
        json_mode: bool,
        **kwargs: Any,
    ) -> dict: ...
```

### LMStudioProvider (Default Local)
OpenAI-compatible provider for LM Studio (local). Also works with Ollama, vLLM, or any OpenAI-compatible endpoint. Uses a thread-safe singleton `httpx.Client`.

### OpenAICompatibleProvider (Cloud)
Generic adapter for OpenAI, DeepSeek, Mistral, Qwen, and Kimi. Injects the `Authorization: Bearer <API_KEY>` header and routes to the configured `BASE_URL`.

### ProviderRegistry
Manages multiple provider instances. The `factory.py` composition root automatically populates this based on `.env` API keys.
```python
class ProviderRegistry:
    def register(self, name: str, provider: BaseProvider) -> None: ...
    def get(self, name: str) -> BaseProvider: ...
    def available(self) -> list[str]: ...
```

---

## 🎭 Role-Based Dispatch

### RoleConfig
Each role has independent settings, dynamically built from `.env` via the frictionless resolver:
```python
@dataclass
class RoleConfig:
    model: str           # Resolved model name
    provider: str = "lmstudio" # Resolved provider (e.g., "openai", "lmstudio")
    timeout: int = 60
    temperature: float = 0.2
    max_tokens: int = 1024
```

### Default Role Configurations
| Role | Temperature | Max Tokens | Timeout | Use Case |
|---|---|---|---|---|
| planner | 0.3 | 2048 | 180s | Orchestration, task decomposition |
| executor | 0.1 | 4096 | 120s | Code generation, analysis, synthesis |
| router | 0.0 | 512 | 15s | Fast task classification, tool selection |
| consultor | 0.2 | 1024 | 60s | Cloud advisory, architectural review |
| vision | 0.1 | 1024 | 60s | Multimodal image analysis |
| code | 0.1 | 4096 | 120s | Code generation (alias for executor) |
| review | 0.2 | 768 | 90s | Code review (alias for critique) |

---

## 🛡️ Circuit Breaker Pattern (HIG-02)

Prevents cascading failures when a provider becomes unresponsive. Each role has an independent circuit breaker.

### State Machine
```text
CLOSED → (3 failures) → OPEN → (timeout) → HALF_OPEN → (test call)
  ↑                                                         ↓
  └────────────── (success) ←──────────────────────────────┘
                                                         ↓
                                                    (failure) → OPEN
```

### Implementation
```python
class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"
    
    def can_execute(self) -> bool: ...
    def record_success(self) -> None: ...
    def record_failure(self) -> None: ...
    def get_state_info(self) -> dict[str, Any]: ...
```

---

## 📡 API Reference

### LLMResponse
Unified response object returned by all LLM calls:
```python
@dataclass
class LLMResponse:
    text: str              # Raw text output
    role: str              # Role that was called
    model: str             # Model identifier
    provider: str          # Provider used (e.g., "lmstudio", "openai")
    usage: dict[str, int]  # {"prompt": N, "completion": M, "total": T}
    elapsed: float         # Seconds taken
    parsed: Optional[Any]  # Parsed JSON if json_mode=True
    error: str = ""        # Error message if ok=False
    ok: bool = True        # Success flag
```

### `call()` Method
Low-level call with full control:
```python
result = llm.call(
    role="executor",
    messages=[{"role": "user", "content": "Fix this bug..."}],
    temperature=0.1,
    max_tokens=4096,
    timeout=120,
    json_mode=True,
    trace_id="abc123"
)
```

### `complete()` Method
High-level convenience method with system/user/context separation:
```python
result = llm.complete(
    role="executor",
    system="You are a senior Python developer...",
    user="Fix this bug...",
    context="Background: The agent uses ChromaDB...",
    json_mode=True,
    trace_id="abc123"
)
```

---

## 🔧 Structured Output & JSON Parsing

### Robust JSON Extraction (P1 Fix)
The `_parse_response()` method implements a 3-layer JSON extraction strategy to handle LLM hallucinations and markdown wrapping:
1. **Direct Parse:** Try parsing the raw string directly.
2. **Markdown Code Block:** Extract from ` ```json ... ``` ` blocks.
3. **Outermost Structure:** Find the outermost `{...}` or `[...]` object/array using regex.

---

## 🧵 Thread Safety

- **Singleton Pattern:** The `llm` instance is a singleton.
- **Per-Thread HTTP Clients:** `LMStudioProvider` uses thread-local storage / double-checked locking for connection pooling.
- **Circuit Breaker Locks:** Each `CircuitBreaker` has its own `threading.Lock` to prevent race conditions.
- **Cleanup at Exit:** Registered via `atexit` to close all provider clients safely.

---

## ⚠️ AI Agent Instructions for LLM Operations

If you are an AI assistant modifying the LLM stack:
1. **Never Bypass Circuit Breakers:** Always check `breaker.can_execute()` before making LLM calls.
2. **Thread Safety:** Never remove the `_lock` from `CircuitBreaker` or `LMStudioProvider`.
3. **Provider Agnosticism:** Never hardcode provider names (like `"openai"`) in business logic. Always use the `provider` field from `RoleConfig`.
4. **Consult Tool Guardrails:** Never remove the 4000-character truncation or the rate limit check in `tools/consult.py`.
5. **No Silent Fallbacks:** Cloud APIs must only be accessed via the explicit `consult` tool. Do not implement silent circuit-breaker overrides to cloud providers.
6. **Trace Integration:** Every call must log via `tracer.step()` with `trace_id`.

---

## 📊 Configuration (`.env`)

```env
# ── Local Runtime Provider ──────────────────────────────────────────────
LM_STUDIO_BASE_URL=http://localhost:1234/v1

# ── Cloud Advisory Providers (Comment out API key to disable) ───────────
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_BASE_MODEL=gpt-4o-mini

# DEEPSEEK_API_KEY=sk-...
# DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
# DEEPSEEK_BASE_MODEL=deepseek-chat

# ── Model Roles (Frictionless Routing) ──────────────────────────────────
# Set to exact provider name (e.g., "openai") to route to cloud.
# Set to local model name (e.g., "qwen-3b") to route to LM Studio.
# Leave blank to disable the role.
PLANNER_MODEL=qwen-qwen3.5-9b
EXECUTOR_MODEL=granite-4.0-h-tiny@q2_k
ROUTER_MODEL=granite-4.0-350m
CONSULTOR_MODEL=openai
CONSULTOR_TIMEOUT=60
```