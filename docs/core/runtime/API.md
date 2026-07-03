<- Back to [RUNTIME Overview](../RUNTIME.md)

# 📝 API Reference

## 🔧 Module Overview

`core/runtime/` is not a single `@tool` facade. It is a collection of 6 modules consumed by `gateway_backend`, `llm_backend`, `memory_backend`, and `workflows`. Each module exports a focused API.

---

## ⚡ Module Reference

### `core/runtime/activity_tracker.py`

**Singleton:**
```python
from core.runtime.activity_tracker import tracker
```

**State:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `last_user_activity` | `float` | `time.time()` | Timestamp of last user interaction |
| `active_inferences` | `int` | `0` | Number of concurrent LLM calls |
| `background_active` | `bool` | `False` | Whether background work is running |
| `max_concurrent_inferences` | `int` | `2` (from `cfg`) | Max parallel LLM calls |

**Thread Safety:** Uses `threading.RLock()` — the `R` (reentrant) is critical because `touch()` is called inside `inference_slot()`, which already holds the lock. A regular `Lock()` would deadlock.

**API:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `touch()` | `() -> None` | Update `last_user_activity` timestamp |
| `inference_start()` | `() -> None` | Increment `active_inferences` + touch |
| `inference_end()` | `() -> None` | Decrement `active_inferences` |
| `inference_slot()` | `(timeout=30) -> ContextManager` | Acquire/release inference slot |
| `try_acquire_background_slot()` | `(min_idle_seconds=7200) -> bool` | Atomically check idle + reserve slot |
| `release_background_slot()` | `() -> None` | Release background reservation |

**Usage:**
```python
with tracker.inference_slot(timeout=30.0):
    # LLM call here — guaranteed slot
    result = llm.complete(...)
# Slot auto-released even on exception

if tracker.try_acquire_background_slot(min_idle_seconds=7200):
    try:
        # Safe to run background work
        process_feedback()
    finally:
        tracker.release_background_slot()
```

**Who uses it:**

| Consumer | Method | Purpose |
|----------|--------|---------|
| `gateway/dependencies.py` | `tracker.touch()` | Update idle detection on every HTTP request |
| `llm_backend/client.py` | `inference_slot()` | Limit concurrent LLM calls |
| `meta_learning.py` | `try_acquire_background_slot()` | Only learn when agent is idle |
| `sleep_learn/daemon.py` | `try_acquire_background_slot()` | Only process feedback when idle |
| `memory_backend/janitor.py` | `try_acquire_background_slot()` | Only run maintenance when idle |

---

### `core/runtime/cancellation.py`

**API:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `ensure_not_cancelled()` | `(trace_id="") -> None` | Raises `CancelledError` if async task is cancelling |

**The Problem:** Without cancellation guards:
1. User submits a long workflow via `/task`
2. User cancels (or it times out)
3. The workflow thread is still running
4. It writes to ChromaDB, creates files, or commits to git
5. These mutations are now orphaned — the workflow is "cancelled" but side effects remain

**The Solution:** `ensure_not_cancelled(trace_id)` checks `asyncio.current_task().cancelling()` before every mutation. If the task is cancelling, raises `CancelledError` to abort the side effect. Safely ignores the check in synchronous contexts (no event loop) — `RuntimeError` is caught.

**Who uses it:**
- `memory_backend/write_ops.py` — Before every ChromaDB mutation
- `memory_backend/maintenance.py` — Before deduplication and vacuum operations
- Workflow nodes — Before file writes, git operations

---

### `core/runtime/health.py`

**API:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_health()` | `() -> Dict[str, Any]` | Full health check dictionary |
| `health_check_endpoint()` | `() -> str` | JSON string for HTTP response |

**Checks:**

| Check | What | How | Healthy |
|-------|------|-----|---------|
| **Directories** | 7 critical paths exist | `path.exists()` | All exist |
| **LM Studio** | LLM server reachable | `httpx.get(base_url, timeout=5)` | Status < 500 |
| **Models** | Required models configured | `cfg.planner_model`, etc. not empty | All non-empty |
| **ChromaDB** | Memory system operational | `memory.recall("warmup", top_k=0)` | No exception |

**Response Format:**
```json
{
  "status": "healthy",
  "timestamp": 1718820000,
  "env": "development",
  "version": "1.0.0",
  "checks": {
    "dir_agent_root": {"status": "ok", "path": "D:/mcp/agent"},
    "dir_workspace_root": {"status": "ok", "path": "D:/mcp/agent/workspace"},
    "dir_memory_root": {"status": "ok", "path": "D:/mcp/agent/memory_db"},
    "lm_studio": {"status": "ok", "url": "http://localhost:1234/v1", "response_code": 200},
    "models": {
      "planner": {"status": "ok", "model": "gemma-4-e2b-it@q5_k_s"},
      "executor": {"status": "ok", "model": "gemma-2-2b-it"},
      "router": {"status": "ok", "model": "gemma-2-2b-it"}
    },
    "chromadb": {"status": "ok", "client": "initialized"}
  }
}
```

**Gateway Integration:**

| Endpoint | Auth | Deep Check | Description |
|----------|------|------------|-------------|
| `GET /health` | No | Always | Full subsystem check |
| `GET /health/autocode` | Bearer | Optional `?deep=true` | LM Studio + ChromaDB |
| `GET /health/circuit-breakers` | Bearer | N/A | LLM circuit breaker states |
| `GET /health/models` | Bearer | Always | Checks if models are loaded in LM Studio |

---

### `core/runtime/providers.py`

**API:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_provider()` | `(name: str) -> RuntimeProvider` | Factory for provider instances |

**Provider Interface:**
```python
class RuntimeProvider(ABC):
    name: str                    # "lmstudio", "ollama", "vllm"
    health_url: str              # URL to probe for readiness
    default_restart_cmd: str     # CLI command to restart

    def is_ready(json_data) -> bool  # Verify models are loaded
```

**Available Providers:**

| Provider | `name` | Health URL | Restart Command | Ready Check |
|----------|--------|-----------|-----------------|-------------|
| `LMStudioProvider` | `lmstudio` | `{base_url}/models` | `lms server start` | `data` key present + non-empty |
| `OllamaProvider` | `ollama` | `http://localhost:11434/api/tags` | `ollama serve` | `models` key present + non-empty |
| `VLLMProvider` | `vllm` | `http://localhost:8000/v1/models` | `vllm serve` | `data` key present + non-empty |

**Configuration:**
```ini
RUNTIME_PROVIDER=lmstudio
```

---

### `core/runtime/task_runner.py`

**API:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `init_executor()` | `() -> ThreadPoolExecutor` | Initialize global executor |
| `shutdown_executor()` | `() -> None` | Gracefully drain and shutdown |
| `get_executor()` | `() -> ThreadPoolExecutor` | Get or lazily init executor |
| `run_background_task()` | `(trace_id, execute_fn, timeout=300, on_timeout_fn=None) -> None` | Submit + monitor |

**Lifecycle:**

| Function | When | Description |
|----------|------|-------------|
| `init_executor()` | App startup (lifespan) | Creates `ThreadPoolExecutor(max_workers=10)` |
| `run_background_task()` | Each `/task` request | Submits work + spawns timeout monitor thread |
| `shutdown_executor()` | App shutdown (lifespan) | `shutdown(wait=True, cancel_futures=True)` |
| `get_executor()` | Lazy init | Auto-initializes if lifespan hasn't run (tests) |

**Key Design:**

| Property | Value | Rationale |
|----------|-------|-----------|
| Max workers | 10 | Balances concurrency with resource usage |
| Default timeout | 300s | Matches `AUTOCODE_GRAPH_TIMEOUT` |
| Monitor thread | Daemon | Won't prevent process exit |
| Cancellation | Best-effort | `future.cancel()` — can't interrupt running code |

**Usage (in gateway):**
```python
def _execute_and_update():
    try:
        store._update_task(trace_id, "running")
        result = dispatcher.dispatch(trace_id, payload)
        store._update_task(trace_id, "success", result=result)
    except Exception as e:
        store._update_task(trace_id, "failed", error=str(e))

def _on_timeout(tid):
    store._update_task(tid, "failed", error="Task exceeds 300s timeout")

runner.run_background_task(trace_id, _execute_and_update, 300, _on_timeout)
```

---

### `core/runtime/watchdog.py`

**API:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `run_forever()` | `() -> None` | Main watchdog loop (blocks) |
| `_check_health()` | `() -> bool` | Single health probe |
| `_attempt_restart()` | `() -> None` | Execute restart with safety checks |
| `_wait_for_recovery()` | `() -> bool` | Poll provider for 180s |

**Configuration:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `CHECK_INTERVAL` | 30 seconds | Health probe frequency |
| `FAILURE_THRESHOLD` | 3 | Consecutive failures before restart |
| `COOLDOWN_SECONDS` | 900 (15 min) | Max restart window |
| `MAX_RESTARTS` | 3 | Max restarts within cooldown |
| Grace period | 60 seconds | Transient failures ignored after successful recovery |
| Recovery timeout | 180 seconds | Max wait after restart command |

**Safety Features:**

| Feature | Description |
|---------|-------------|
| **Lock file** | `.watchdog_restart.lock` prevents concurrent restarts |
| **Stale lock detection** | Lock files older than 5 minutes are automatically removed |
| **Cooldown** | Max 3 restarts per 15-minute window |
| **Grace period** | 60 seconds after successful recovery — transient failures ignored |
| **Windows support** | `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` + hidden window |
| **Provider-agnostic** | Uses `RuntimeProvider` abstraction — works with LM Studio, Ollama, vLLM |

**Windows-Specific:**
On Windows, the restart subprocess uses:
- `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` — Detaches from parent process
- `STARTUPINFO` with `SW_HIDE` — Prevents console window from flashing
- `stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL` — No I/O inheritance

---

## 🔒 Security

### 🛡️ Cancellation Guards

`ensure_not_cancelled()` prevents ghost mutations by checking `asyncio.current_task().cancelling()` before every write operation. This is a security measure against orphaned side effects from cancelled workflows.

### 🛡️ Watchdog Safety

The watchdog uses multiple safety layers to prevent runaway restarts:
- Lock file prevents concurrent restarts from multiple processes
- Stale lock detection handles process crashes
- Cooldown prevents restart loops
- Grace period ignores transient failures
- Provider abstraction prevents hardcoded commands

---

## 📤 Output & Return Shapes

All modules return standard Python types or `ok()`/`fail()` dicts from `core/contracts.py`.

**Health response dict:**
```json
{
  "status": "healthy",
  "timestamp": 1718820000,
  "env": "development",
  "version": "1.0.0",
  "checks": {
    "dir_agent_root": {"status": "ok", "path": "D:/mcp/agent"},
    "dir_workspace_root": {"status": "ok", "path": "D:/mcp/agent/workspace"},
    "dir_memory_root": {"status": "ok", "path": "D:/mcp/agent/memory_db"},
    "lm_studio": {"status": "ok", "url": "http://localhost:1234/v1", "response_code": 200},
    "models": {
      "planner": {"status": "ok", "model": "gemma-4-e2b-it@q5_k_s"},
      "executor": {"status": "ok", "model": "gemma-2-2b-it"},
      "router": {"status": "ok", "model": "gemma-2-2b-it"}
    },
    "chromadb": {"status": "ok", "client": "initialized"}
  }
}
```

**Provider ready check:**
```python
# LM Studio / vLLM: checks "data" key present and non-empty
# Ollama: checks "models" key present and non-empty
```

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
