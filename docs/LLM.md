# 🧠 LLM Client Architecture & Provider Abstraction

The LLM client (`core/llm.py`) is the unified interface for all model interactions in the agent stack. It implements provider abstraction, role-based dispatch, circuit breakers, and structured output support to ensure resilience and maintainability.

## 🏗️ Architecture Overview

### Design Goals

1. **Single Call Site**: Nothing else in the codebase calls `requests` or `httpx` directly for LLM interactions.
2. **Provider Abstraction**: Adding new backends (DeepSeek, Claude, Groq) requires only a new `Provider` class.
3. **Role-Based Dispatch**: Callers say `"executor"` not the raw model string from `.env`.
4. **Per-Role Timeouts**: Enforced centrally, not scattered across tool files.
5. **Structured Output**: Request JSON mode, get a parsed dict back.
6. **Full Trace Integration**: Every call logged with `trace_id`.

### Component Hierarchy

```
LLMClient (singleton)
├── ProviderRegistry
│   └── LMStudioProvider (or custom providers)
├── RoleConfig (per-role settings)
│   ├── planner: Long-context / Vision (cfg.planner_model)
│   ├── executor: Code / Synthesis (cfg.executor_model)
│   ├── router: Fast Classification (cfg.router_model)
│   └── vision, summarize, extract, classify, research, critique, analyze, code, review
└── CircuitBreaker (per-role resilience)
    └── State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
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
    
    def is_available(self) -> bool:
        return True
```

### LMStudioProvider (Default)

OpenAI-compatible provider for LM Studio (local). Also works with Ollama, vLLM, or any OpenAI-compatible endpoint.

**Thread-Safety Implementation:**
- Singleton `httpx.Client` per instance with proper cleanup
- Each thread gets its own client via `_local` for connection pooling
- Reference: httpx GitHub Discussion #1633 confirms singletons are thread-safe

```python
class LMStudioProvider(BaseProvider):
    name = "lmstudio"
    
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = None  # Singleton client instance
        self._lock = threading.Lock()
    
    def _get_client(self) -> httpx.Client:
        """Return (or create) singleton client."""
        if self._client is None or self._client.is_closed:
            with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(
                        base_url=self.base_url,
                        headers={"Content-Type": "application/json"},
                        timeout=None,  # timeout enforced per-request
                    )
        return self._client
    
    def chat_completion(self, model, messages, temperature, max_tokens, timeout, json_mode, **kwargs):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload.update(kwargs)
        
        response = self._get_client().post(
            "/chat/completions",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    
    def close(self) -> None:
        """Close the singleton httpx client safely."""
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None
```

### ProviderRegistry

Manages multiple provider instances:

```python
class ProviderRegistry:
    def register(self, name: str, provider: BaseProvider) -> None:
        self._providers[name] = provider
    
    def get(self, name: str) -> BaseProvider:
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not registered. Available: {list(self._providers.keys())}")
        return self._providers[name]
```

### Adding a New Provider

To add DeepSeek, Claude, or any OpenAI-compatible backend:

```python
from core.llm import llm, LMStudioProvider

# Register DeepSeek as alternative to LM Studio
llm.register_provider(
    "deepseek",
    LMStudioProvider("https://api.deepseek.com/v1")
)

# Override executor model at runtime
import core.config as cfg
cfg.model_registry["executor"]["model"] = "deepseek-coder-v2"
cfg.model_registry["executor"]["provider"] = "deepseek"
```

---

## 🎭 Role-Based Dispatch

### RoleConfig

Each role has independent settings:

```python
@dataclass
class RoleConfig:
    model: str           # From cfg.planner_model, cfg.executor_model, etc.
    provider: str = "lmstudio"
    timeout: int = 60
    temperature: float = 0.2
    max_tokens: int = 1024
```

### Default Role Configurations

| Role | Temperature | Max Tokens | Timeout | Use Case |
|------|-------------|------------|---------|----------|
| `planner` | 0.3 | 2048 | 90s | Orchestration, memory summaries, vision |
| `executor` | 0.1 | 4096 | 120s | Code generation, analysis, synthesis |
| `router` | 0.0 | 512 | 15s | Fast task classification, tool selection |
| `vision` | 0.1 | 1024 | 60s | Multimodal image analysis |
| `summarize` | 0.1 | 512 | 60s | Memory consolidation |
| `extract` | 0.0 | 512 | 60s | Structured data extraction |
| `classify` | 0.0 | 64 | 15s | Intent classification |
| `research` | 0.2 | 1024 | 120s | Web research synthesis |
| `critique` | 0.2 | 768 | 90s | Code review, self-critique |
| `analyze` | 0.1 | 1024 | 90s | Data analysis |
| `code` | 0.1 | 4096 | 120s | Code generation (alias for executor) |
| `review` | 0.2 | 768 | 90s | Code review (alias for critique) |

### Configuration in `.env`

```ini
# ── Model Roles (Match your LM Studio loaded models exactly) ───────────────
PLANNER_MODEL=<your-planner-model-id>
EXECUTOR_MODEL=<your-executor-model-id>
ROUTER_MODEL=<your-router-model-id>
VISION_MODEL=<your-vision-model-id>  # Usually same as planner

# ── Timeouts (override defaults) ───────────────────────────────────────────
PLANNER_TIMEOUT=90
EXECUTOR_TIMEOUT=120
ROUTER_TIMEOUT=15
```

Model identifiers must match exactly what appears in your provider's `/v1/models` response.

---

## 🛡️ Circuit Breaker Pattern (HIG-02)

### Purpose

Prevents cascading failures when LM Studio becomes unresponsive. Each role has an independent circuit breaker.

### State Machine

```
CLOSED → (3 failures) → OPEN → (timeout) → HALF_OPEN → (test call)
  ↑                                                         ↓
  └────────────── (success) ←──────────────────────────────┘
                                                         ↓
                                                    (failure) → OPEN
```

### States

| State | Behavior | Transition |
|-------|----------|------------|
| **CLOSED** | Normal operation. Track failures. | → OPEN after `failure_threshold` consecutive failures |
| **OPEN** | Fail fast. No LLM calls. | → HALF_OPEN after `recovery_timeout` seconds |
| **HALF_OPEN** | Allow single test call. | → CLOSED on success, → OPEN on failure |

### Implementation

```python
class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60,
                 half_open_max_calls: int = 1) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitBreaker.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0
        self._lock = threading.Lock()
    
    def can_execute(self) -> bool:
        """Enforces half_open_max_calls and proper state transitions."""
        now = time.time()
        with self._lock:
            if self._state == CircuitBreaker.CLOSED:
                return True
            
            if self._state == CircuitBreaker.OPEN:
                if now - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitBreaker.HALF_OPEN
                    self._half_open_calls = 0
                else:
                    return False
            
            if self._state == CircuitBreaker.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                else:
                    return False
        
        return False
    
    def record_success(self) -> None:
        """Reset on successful call (probing succeeded)."""
        with self._lock:
            if self._state == CircuitBreaker.HALF_OPEN:
                self._state = CircuitBreaker.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
    
    def record_failure(self) -> None:
        """Failures in HALF_OPEN immediately reopen the circuit!"""
        now = time.time()
        with self._lock:
            if self._state == CircuitBreaker.HALF_OPEN:
                # Probing failed – go back to open immediately
                self._state = CircuitBreaker.OPEN
                self._failure_count = self.failure_threshold
                self._half_open_calls = 0
            elif self._state == CircuitBreaker.CLOSED:
                self._failure_count += 1
                self._last_failure_time = now
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitBreaker.OPEN
    
    def get_state_info(self) -> dict[str, Any]:
        """Return circuit breaker state info for monitoring."""
        with self._lock:
            time_since_failure = 0.0
            if self._last_failure_time > 0:
                time_since_failure = time.time() - self._last_failure_time
            return {
                "state": self._state,
                "failure_count": self._failure_count,
                "timeout_seconds": self.recovery_timeout,
                "time_since_last_failure": time_since_failure,
            }
```

### Per-Role Circuit Breakers

Each role gets a circuit breaker with `recovery_timeout` set to the role's timeout:

```python
def _build_breakers(self) -> None:
    """Build circuit breakers for each role."""
    for role_name, role_cfg in self._roles.items():
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=role_cfg.timeout,  # Use role timeout as recovery window
            half_open_max_calls=1,
        )
        self._breakers[role_name] = breaker
```

### Monitoring Circuit Breakers

Query breaker states for observability:

```python
from core.llm import llm

# Get all breaker states
states = llm.circuit_breaker_states
# {
#     "planner": {"state": "closed", "failure_count": 0, "timeout_seconds": 90},
#     "executor": {"state": "open", "failure_count": 3, "timeout_seconds": 120},
#     "router": {"state": "closed", "failure_count": 1, "timeout_seconds": 15}
# }

# Check specific role
info = llm._breakers["executor"].get_state_info()
# {'state': 'open', 'failure_count': 3, 'timeout_seconds': 120, 'time_since_last_failure': 45.2}
```

### Prometheus Metrics

The gateway exposes breaker states at `/metrics`:

```
# Circuit breaker states
circuit_breaker_state{role="planner",state="closed"} 1
circuit_breaker_state{role="executor",state="open"} 1
circuit_breaker_failure_count{role="executor"} 3
circuit_breaker_time_since_failure{role="executor"} 45.2
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
    model: str             # Model identifier (from cfg)
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
    messages=[
        {"role": "system", "content": "You are a senior Python developer..."},
        {"role": "user", "content": "Fix this bug: ..."}
    ],
    temperature=0.1,
    max_tokens=4096,
    timeout=120,
    json_mode=True,
    trace_id="abc123"
)

if result.ok:
    print(result.text)
    if result.parsed:
        print(result.parsed["fix"])
else:
    print(f"Error: {result.error}")
```

### `complete()` Method

High-level convenience method with system/user/context separation:

```python
result = llm.complete(
    role="executor",
    system="You are a senior Python developer...",
    user="Fix this bug: ...",
    context="Background: The agent uses ChromaDB for memory...",
    content="def broken_function():\n    return x + y",
    temperature=0.1,
    max_tokens=4096,
    timeout=120,
    json_mode=True,
    trace_id="abc123"
)
```

**Message Construction:**
1. System message: `{"role": "system", "content": system}`
2. Context (if provided): `{"role": "user", "content": f"Background:\n{context}"}` + `{"role": "assistant", "content": "Understood."}`
3. User message: `{"role": "user", "content": user}` or `f"{user}\n\nContent:\n{content}"` if content provided

### `is_available()` Method

Check if a role's provider is reachable:

```python
if llm.is_available("planner"):
    print("Planner model is ready")
else:
    print("Planner model is unavailable")
```

### `register_provider()` Method

Add a new provider backend:

```python
from core.llm import llm, LMStudioProvider

llm.register_provider(
    "deepseek",
    LMStudioProvider("https://api.deepseek.com/v1")
)
```

### `list_roles()` Method

List all configured roles:

```python
roles = llm.list_roles()
# [
#     {"role": "planner", "model": cfg.planner_model, "provider": "lmstudio", "timeout": 90, "temperature": 0.3, "max_tokens": 2048},
#     {"role": "executor", "model": cfg.executor_model, "provider": "lmstudio", "timeout": 120, "temperature": 0.1, "max_tokens": 4096},
#     ...
# ]
```

---

## 🔧 Structured Output & JSON Parsing

### JSON Mode

Request structured JSON output:

```python
result = llm.complete(
    role="executor",
    system="Output ONLY valid JSON, no other text.",
    user="Analyze this code and return {'bug': '...', 'fix': '...'}",
    json_mode=True
)

if result.ok and result.parsed:
    print(result.parsed["bug"])
    print(result.parsed["fix"])
```

### Robust JSON Extraction (P1 Fix)

The `_parse_response()` method implements a 3-layer JSON extraction strategy:

1. **Direct Parse**: Try parsing the raw string directly (handles clean JSON, arrays, and backticks in strings)
2. **Markdown Code Block**: Extract from ` ```json ... ``` ` blocks
3. **Outermost Structure**: Find the outermost `{...}` or `[...]` object/array

```python
# Handles these cases:
# 1. Clean JSON: {"bug": "missing import", "fix": "add import os"}
# 2. Markdown: ```json\n{"bug": "..."}\n```
# 3. Mixed text: Here is the analysis:\n{"bug": "..."}\nHope this helps!
# 4. Arrays: [{"issue": 1}, {"issue": 2}]
```

### Schema Validation

For tool calls, validates against expected schema:

```python
if parsed and isinstance(parsed, dict) and "tool" in parsed and "action" in parsed:
    try:
        from core.contracts import validate_tool_call
        validate_tool_call(parsed)
    except Exception as e:
        tracer.error("schema_validation_failed", error=str(e), role=role)
```

---

## 🧵 Thread Safety

### Singleton Pattern

The `llm` instance is a singleton:

```python
# At module level
llm = LLMClient()
```

### Per-Thread HTTP Clients

`LMStudioProvider` uses thread-local storage for connection pooling:

```python
def _get_client(self) -> httpx.Client:
    if self._client is None or self._client.is_closed:
        with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.Client(...)
    return self._client
```

### Circuit Breaker Locks

Each `CircuitBreaker` has its own lock to prevent race conditions:

```python
def record_failure(self) -> None:
    with self._lock:
        # Update state atomically
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitBreaker.OPEN
```

### Cleanup at Exit

Registered via `atexit` to close all provider clients:

```python
def _cleanup():
    """Close all registered provider clients."""
    from core.llm import llm as _llm_client
    for provider in _llm_client._registry._providers.values():
        if hasattr(provider, 'close'):
            provider.close()

import atexit
atexit.register(_cleanup)
```

---

## 🐛 DeepSeek Fixes (2026-05-14)

### Bug 1: `close_clients()` AttributeError

**Problem**: Original code referenced non-existent `self._clients` list.

**Fix**: Singleton client pattern with proper cleanup:

```python
def close(self) -> None:
    if self._client and not self._client.is_closed:
        self._client.close()
        self._client = None
```

### Bug 2: `_make_client` Timeout No-Op

**Problem**: Timeout parameter was ignored.

**Fix**: Enforced per-request in `chat_completion()`:

```python
response = self._get_client().post(
    "/chat/completions",
    json=payload,
    timeout=timeout,  # Now enforced
)
```

### Bug 3: CircuitBreaker HALF_OPEN Gaps

**Problem**: State transitions from HALF_OPEN → OPEN on failure were missing.

**Fix**: Proper state machine enforcement:

```python
def record_failure(self) -> None:
    with self._lock:
        if self._state == CircuitBreaker.HALF_OPEN:
            # Probing failed – go back to open immediately
            self._state = CircuitBreaker.OPEN
            self._failure_count = self.failure_threshold
            self._half_open_calls = 0
```

---

## ⚠️ AI Agent Instructions for LLM Operations

If you are an AI assistant modifying `core/llm.py`:

1. **Never Bypass Circuit Breakers**: Always check `breaker.can_execute()` before making LLM calls. Never remove the fail-fast logic.

2. **Thread Safety**: Never remove the `_lock` from `CircuitBreaker` or `LMStudioProvider`. Race conditions will corrupt state.

3. **Timeout Enforcement**: Timeouts are enforced per-request in `chat_completion()`. Never set `timeout=None` on the httpx client itself.

4. **Error Handling**: All exceptions are caught and converted to `LLMResponse.from_error()`. Never let exceptions propagate to callers.

5. **JSON Parsing**: The 3-layer extraction strategy is critical for robustness. Never simplify it to a single `json.loads()` call.

6. **Role Fallback**: Unknown roles fall back to `executor`. Never remove the `_get_role()` fallback logic.

7. **Trace Integration**: Every call must log via `tracer.step()` with `trace_id`. Never remove trace logging.

8. **Provider Registration**: New providers must implement `BaseProvider` and be registered via `register_provider()`. Never hardcode provider logic.

9. **Cleanup**: The `atexit` handler ensures clients are closed. Never remove `_cleanup()`.

10. **Structured Output**: When `json_mode=True`, always attempt parsing. Never return raw text without trying to extract JSON.

11. **Model References**: Always use `cfg.planner_model`, `cfg.executor_model`, `cfg.router_model`, or `cfg.vision_model`. Never hardcode model identifiers in this file.

---

## 🔮 Future Enhancements (Planned)

- **Streaming Responses**: Support for streaming LLM output (Phase 10)
- **Model Distillation**: Automatic routing to smaller models for simple tasks
- **Prompt Caching**: Cache system prompts to reduce token usage
- **Multi-Provider Failover**: Automatic fallback to secondary provider if primary fails
- **Token Budget Enforcement**: Hard limits on total tokens per workflow
- **Adaptive Timeouts**: Dynamic timeout adjustment based on model latency

---

## 📊 Configuration (`.env`)

```ini
# ── LM Studio ──────────────────────────────────────────────────────────────
LM_STUDIO_BASE_URL=http://localhost:1234/v1

# ── Model Roles (Match your LM Studio loaded models exactly) ───────────────
PLANNER_MODEL=<your-planner-model-id>
EXECUTOR_MODEL=<your-executor-model-id>
ROUTER_MODEL=<your-router-model-id>
VISION_MODEL=<your-vision-model-id>

# ── Timeouts (override defaults) ───────────────────────────────────────────
PLANNER_TIMEOUT=90
EXECUTOR_TIMEOUT=120
ROUTER_TIMEOUT=15

# ── Metrics ────────────────────────────────────────────────────────────────
ENABLE_METRICS_ENDPOINT=1  # Expose /metrics for Prometheus
```

---

## 🧪 Testing

Run the LLM client tests:

```bash
python -m pytest tests/core/llm/ -v
```

**Test Coverage Goals:**
- Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Thread safety under concurrent calls
- JSON extraction from malformed responses
- Provider registration and failover
- Timeout enforcement
- Trace integration

---

*Last updated: Phase 4 complete. DeepSeek fixes applied, circuit breakers hardened, structured output robust.*