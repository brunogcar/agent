<- Back to [Standalone Overview](../STANDALONE.md)

# 📝 API Reference

## 🔧 Module Overview

These are library modules — no `@tool` facade, no `DISPATCH`. Each exports a focused API consumed directly by tools, workflows, and the gateway.

---

## ⚡ Module Reference

### `core/utils.py`

```python
from core.utils import truncate_output, compress_result
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `truncate_output()` | `(text: str, max_chars: int = 4000) -> str` | Truncate large text with `[... N chars truncated ...]` notice |
| `compress_result()` | `(result: dict, max_chars: int = 4000) -> dict` | Recursively compress large string values in dicts/lists |
| `_compress_value()` | `(value: Any, max_chars: int = 4000) -> Any` | Internal recursive helper |

**Default:** `_MAX_OUTPUT_CHARS = 4000`

---

### `core/br_validator.py`

```python
from core.br_validator import parse_brl, parse_br_date, validate_ticker, B3Dividend
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_brl()` | `(value: str \| float \| int) -> float` | Converts `'R$ 1.000,50'` → `1000.50` |
| `parse_br_date()` | `(value: str, fmt: str = "%Y-%m-%d") -> datetime` | Parses `DD/MM/YYYY` or `YYYY-MM-DD` |
| `validate_ticker()` | `(symbol: str) -> str` | Standardizes BOVESPA tickers (`PETR4`, `TAEE11`) |

**Pydantic model:**
```python
class B3Dividend(BaseModel):
    ticker: str
    isin: str | None = None
    value_brl: float
    date_approved: datetime | None = None
    date_ex: datetime | None = None
    date_payment: datetime | None = None
```

---

### `core/citations.py`

```python
from core.citations import citations  # singleton CitationTracker
```

| Method | Signature | Description |
|----------|-----------|-------------|
| `add()` | `(trace_id, url, title="", snippet="") -> int` | Register source, return citation number |
| `cite()` | `(trace_id, url) -> str` | Return inline marker `"[1]"` |
| `get_sources()` | `(trace_id) -> list[dict]` | All sources sorted by citation number |
| `get_numbered()` | `(trace_id) -> list[dict]` | Alias for `get_sources()` |
| `has_sources()` | `(trace_id) -> bool` | Check if trace has any citations |
| `clear()` | `(trace_id) -> None` | Remove trace from store |
| `count()` | `(trace_id) -> int` | Number of unique sources for trace |

**Limits:** `MAX_TRACES = 100` (LRU eviction of oldest)

---

### `core/contracts.py`

```python
from core.contracts import ok, fail, validate_tool_call, ToolCall, ToolResult
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `ok()` | `(data, trace_id="", status="success", **meta) -> dict` | Standardized success response |
| `fail()` | `(error, trace_id="", status="error", error_code="", **meta) -> dict` | Standardized error response with `error_code` (v1.2) |
| `validate_tool_call()` | `(payload: dict) -> ToolCall` | Validate LLM tool call against schema |

**Pydantic models:**
```python
class ToolCall(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    tool: str
    action: str
    args: dict = {}

class ToolResult(TypedDict):
    status: Literal["success", "error", "routed", "needs_clarification", "sent", "scheduled"]
    data: Optional[Any]
    error: Optional[str]
    trace_id: Optional[str]
    error_code: Optional[str]   # v1.2
    model: Optional[str]
    elapsed: Optional[float]
    usage: Optional[dict]
```

**Standard error codes:** `TIMEOUT`, `CONNECT_ERROR`, `RATE_LIMITED`, `SERVER_ERROR`, `CLIENT_ERROR`, `AUTH_FAILED`, `QUOTA_EXHAUSTED`, `INVALID_ACTION`, `INTERNAL_ERROR`, `UNKNOWN`

---

### `core/metrics.py`

```python
from core.metrics import track_node, track_task_status, track_tdd_iterations, track_llm_tokens, generate_metrics
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `track_node()` | `(node_name: str, duration: float) -> None` | Record node execution duration |
| `track_task_status()` | `(status: str) -> None` | Increment task status counter |
| `track_tdd_iterations()` | `(count: int) -> None` | Record TDD iteration count |
| `track_llm_tokens()` | `(role: str, prompt: int, completion: int) -> None` | Record LLM token consumption |
| `generate_metrics()` | `() -> str` | Prometheus text format output |
| `get_content_type()` | `() -> str` | `CONTENT_TYPE_LATEST` or `"text/plain"` |

**Graceful degradation:** If `prometheus_client` is not installed, all functions become no-ops.

---

### `core/path_guard.py`

```python
from core.path_guard import (
    resolve_path, check_protected_file, check_git_operation,
    make_path_error, READ_OPERATIONS, WRITE_OPERATIONS, GIT_WORKSPACE_ONLY
)
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `resolve_path()` | `(path, default_root="agent", require_exists=False) -> (Path \| None, str)` | Resolve against `AGENT_ROOT` or `WORKSPACE_ROOT`. Returns `(resolved, error_msg)`. |
| `check_protected_file()` | `(path, operation) -> (bool, str)` | Block writes on protected files. Reads always allowed. |
| `check_git_operation()` | `(operation, cwd=None, target=None) -> (bool, str, Path \| None)` | Validate git op scoping. `init`/`clone` restricted to `WORKSPACE_ROOT`. |
| `make_path_error()` | `(path, operation, reason, trace_id="", suggestion="") -> dict` | Standardized error dict with tracer injection |

**Operation sets:**
```python
READ_OPERATIONS = frozenset({"read", "list", "search", "read_pdf", ...})
WRITE_OPERATIONS = frozenset({"write", "edit", "delete", "backup", "patch", "append", ...})
GIT_WORKSPACE_ONLY = frozenset({"clone", "init"})
```

**Security properties:**
- Null bytes blocked before `Path` parsing
- Symlinks resolved via `Path.resolve()` — escapes caught by `_is_within()`
- Absolute paths allowed only if within `AGENT_ROOT`
- Relative paths resolved from `default_root` (`agent` or `workspace`)

---

### `core/time_utils.py`

```python
from core.time_utils import (
    now, now_iso, parse_iso, parse_human, parse_duration,
    to_utc, from_utc, format_dt, get_timezone,
    cron_next_fire, compute_missed_fires, _build_cron_trigger,
)
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `now()` | `() -> datetime` | Current time as tz-aware datetime in `cfg.timezone` |
| `now_iso()` | `() -> str` | Current time as ISO 8601 string (tz-aware) |
| `parse_iso()` | `(s: str) -> datetime` | Parse ISO 8601; naive inputs assumed configured tz; trailing `Z` = UTC |
| `parse_human()` | `(s: str, base=None) -> datetime` | Parse human-friendly time: ISO / `"in 30m"` / `"9am"` / `"2026-07-16"` / `"1h30m"` |
| `parse_duration()` | `(s: str) -> timedelta` | Parse duration: `"10m"` / `"2h"` / `"1d"` / `"1h30m"` (compound); raises on empty/garbage |
| `to_utc()` | `(dt) -> datetime` | Convert to UTC; naive inputs assumed configured tz |
| `from_utc()` | `(dt, tz=None) -> datetime` | Convert UTC datetime to given tz (default: configured) |
| `format_dt()` | `(dt, fmt="%Y-%m-%d %H:%M:%S") -> str` | Format datetime; naive inputs assumed configured tz |
| `get_timezone()` | `() -> tzinfo` | Resolve `cfg.timezone` (`AGENT_TZ`) → `ZoneInfo`; falls back to system local → UTC. Never raises. |
| `cron_next_fire()` | `(cron_expr, after=None) -> datetime \| None` | Next fire of 5-field cron after `after` (default now); standard cron 0=Sunday via DOW remap |
| `compute_missed_fires()` | `(cron_expr, last_fired, until=None, max_count=1000) -> list[datetime]` | Missed fires in `(last_fired, until]`; exclusive lower bound; safety cap |
| `_build_cron_trigger()` | `(cron_expr, tz) -> CronTrigger` | Build APScheduler trigger; remaps DOW to day-names (0=Sunday, not APScheduler's 0=Monday) |

**Timezone resolution:** `cfg.timezone` (`AGENT_TZ` env) → `ZoneInfo(name)`. Empty string → system local (`datetime.now().astimezone().tzinfo`). Invalid → falls through to local → UTC. Never raises.

**Cron DOW remap (subtle APScheduler trap):** `CronTrigger.from_crontab()` treats numeric `day_of_week` as 0=Monday (Python convention), NOT standard cron's 0=Sunday. `_build_cron_trigger` parses the crontab DOW field (`*`, `*/N`, `a-b`, `a,b`, names) and remaps each to unambiguous day names (`sun`/`mon`/...), which APScheduler interprets correctly. Standard cron semantics preserved — `"0 9 * * 1"` = Monday 9am, not Tuesday.

**Soft APScheduler dependency:** only `cron_next_fire` / `compute_missed_fires` / `_build_cron_trigger` need APScheduler. Everything else is pure stdlib. Callers that don't need cron logic pay zero import cost.

---

## 🔒 Security

### 🛡️ Path Guard

`core/path_guard.py` is the single security boundary for all filesystem operations:

**Three-layer defense:**
1. **Facade** (`tools/<tool>.py`) → `resolve_path()` + `check_protected_file()`
2. **Helpers** (`tools/<tool>_ops/helpers.py`) → thin wrapper re-exporting path_guard
3. **Handlers** (`tools/<tool>_ops/actions/*.py`) → trust paths are validated; do NOT re-validate

**Anti-pattern:** NEVER implement custom path resolution in helpers or handlers. The old `file_ops` refactor had `_resolve()` and `_safe_resolve()` in `helpers.py` that duplicated path_guard logic. That was a bug. Do not repeat it.

### 🛡️ Protected Files

`cfg.is_protected(resolved_path)` determines if a file is infrastructure-protected. Write operations are blocked; read operations are always allowed. Unknown operations fail-closed with an error (v1.5: was fail-open, which allowed new write actions to silently bypass protection).

### 🛡️ Git Scoping

- All git ops must be within `AGENT_ROOT`
- `init` and `clone` must be within `WORKSPACE_ROOT`
- `clone` target is a remote URL, not validated as a filesystem path

---

## 📤 Output & Return Shapes

**`ok()` / `fail()` dict:**
```json
{"status": "success", "data": ..., "error": null, "trace_id": "..."}
{"status": "error", "data": null, "error": "...", "trace_id": "...", "error_code": "..."}
```

**`resolve_path()` return:**
```python
(resolved_path: Path | None, error_message: str)
# error_message == "" on success
```

**`check_protected_file()` / `check_git_operation()` return:**
```python
(allowed: bool, error_message: str, resolved_cwd: Path | None)  # git only
```

**`CitationTracker` source entry:**
```python
{"url": "...", "title": "...", "snippets": [...], "number": 1, "added_at": 1718820000.0}
```

**Prometheus metrics text format:**
```
autocode_node_duration_seconds_bucket{node_name="node_run_tests",le="0.005"} 0
autocode_task_status_total{status="success"} 42
```

---

## `core/symbol_offload.py` — TencentDB symbol offloading

Offload verbose state fields to per-trace files, replace with compact SymbolRef dicts.

### `offload_to_file(trace_id, field_name, content, summary="") -> dict`

Write content to `workspace/.symbols/{trace_id}/{field_name}.json`, return a SymbolRef dict:
```python
{
    "_symbol_ref": "debug_history",          # field name
    "_symbol_file": "/path/to/file.json",    # absolute path
    "_symbol_summary": "5 entries (3 failed, 2 passed)",  # auto or custom
    "_symbol_size": 4523,                    # original content size in bytes
}
```

### `drill_down(symbol_ref) -> Optional[Any]`

Read the full content from the offloaded file. Returns `None` if file missing.

### `is_symbol_ref(value) -> bool`

Check if a value is a SymbolRef dict (has `_symbol_ref` + `_symbol_file` keys).

### `_auto_summary(content) -> str`

Auto-generate a one-line summary from content:
- list with `tests_passed` keys → `"5 entries (3 passed, 2 failed)"`
- list with `rule` keys → `"5 rules"`
- dict → `"3 keys"`
- str → `"100 chars"`

**Usage:**
```python
from core.symbol_offload import offload_to_file, drill_down, is_symbol_ref

# Offload verbose debug_history
ref = offload_to_file(trace_id, "debug_history", debug_history_list)

# Later, drill down for full content
if is_symbol_ref(ref):
    full_history = drill_down(ref)
```


---

*Last updated: 2026-07-18 (v1.4 — symbol_offload.py).*
