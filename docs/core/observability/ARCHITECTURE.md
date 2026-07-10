<- Back to [Observability Overview](OBSERVABILITY.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `core/observability/__init__.py` | Empty package init — no side effects |
| `core/observability/tracer_engine.py` | `Tracer` singleton, `_FileWriter`, `_TraceStore`, `generate_trace_id()` — the actual tracer implementation (moved from `core/tracer.py` in v1.3) |
| `core/observability/reader.py` | `read_trace()`, `list_recent_traces()` — memory + disk retrieval (moved from `core/tracer_reader.py`) |
| `core/observability/metrics.py` | Prometheus metrics registry — node duration, task status, TDD iterations, LLM tokens (moved from `core/metrics.py`) |
| `core/observability/checkpoint.py` | `save_checkpoint()`, `get_latest()`, `mark_complete()`, `scan_incomplete()`, `quarantine()`, `sanitize_state()` — workflow resumability journal (moved from `workflows/helpers/checkpoint.py`) |
| `core/tracer.py` | Thin facade — re-exports `tracer`, `Tracer`, `_TraceStore`, `generate_trace_id`, `_writer`, and other module-level names from `tracer_engine.py`. Exists so 71+ callers don't need to change import paths. |
| `core/config.py` | `log_path`, `autocode_debug`, `workspace_root` configuration |
| `core/gateway_backend/routes/traces.py` | HTTP endpoints: `GET /traces`, `GET /traces/{id}` — imports `read_trace`/`list_recent_traces` from `core.observability.reader` |
| `core/gateway_backend/routes/metrics.py` | HTTP endpoint: `GET /metrics` — imports `generate_metrics`/`get_content_type` from `core.observability.metrics` |
| `workflows/base.py` | Workflow dispatcher — imports `save_checkpoint`/`get_latest`/`mark_complete` from `core.observability.checkpoint` |
| `server.py` | MCP entrypoint — imports `scan_incomplete` from `core.observability.checkpoint` for boot-time crash recovery |

---

## 🌳 Module Tree

```text
core/observability/
├── __init__.py            # Empty package init
├── tracer_engine.py       # Tracer singleton, _FileWriter, _TraceStore, generate_trace_id
├── reader.py              # Trace retrieval (memory fast-path, disk slow-path)
├── metrics.py             # Prometheus metrics (complementary)
└── checkpoint.py          # Workflow resumability journal (append-only JSONL per trace)

core/tracer.py             # Thin facade → re-exports from observability/tracer_engine.py
```

### Component Hierarchy

```text
core.tracer (facade)
└── core.observability.tracer_engine
    ├── Trace ID Generator (uuid4 hex, 12 chars)
    ├── structlog Config (stderr only, JSON renderer)
    │   └── Graceful Fallback (standard logging if structlog missing)
    ├── _FileWriter (Thread-safe JSONL, daily rotation, atexit close)
    ├── _TraceStore (In-memory, bounded to 200 traces, FIFO eviction)
    └── tracer = Tracer()  # Module-level singleton

core.observability.reader
├── Fast Path (In-memory lookup via _TraceStore)
└── Slow Path (Disk scan of last 14 days of JSONL logs)

core.observability.metrics
├── registry (CollectorRegistry — singleton if prometheus_client available)
├── NODE_DURATION (Histogram, label=node_name)
├── TASK_STATUS (Counter, label=status)
├── TDD_ITERATIONS (Histogram)
├── LLM_TOKENS (Counter, label=role)
└── track_node(), track_task_status(), track_tdd_iterations(), track_llm_tokens(),
    generate_metrics(), get_content_type()

core.observability.checkpoint
├── CHECKPOINT_DIR = {workspace_root}/checkpoints
├── QUARANTINE_DIR = {workspace_root}/checkpoints/quarantine
├── sanitize_state() — recursive JSON-safe primitive extraction
├── save_checkpoint() — append entry, fsync, zombie-loop counting
├── get_latest() — read last entry, zombie quarantine, version validation
├── mark_complete() — delete journal on success
├── quarantine() — move to QUARANTINE_DIR
└── scan_incomplete() — find workflows modified in last 48h still non-terminal
```

---

## 🔀 Data Flow

```mermaid
graph TD
    A["Workflow / Tool / LLM call"] --> B["tracer.step(trace_id, node, message)<br/>(via core.tracer facade)"]
    B --> C["structlog stderr<br/>JSON with timestamps + context"]
    B --> D["_FileWriter<br/>JSONL to logs/agent_YYYYMMDD.jsonl"]
    B --> E["_TraceStore<br/>In-memory dict, bounded to 200"]
    E --> F["GET /traces<br/>Fast path: memory lookup"]
    D --> G["GET /traces/{id}<br/>Slow path: JSONL disk scan"]
    C --> H["Terminal / MCP host debug console"]

    I["Workflow node boundary"] --> J["save_checkpoint(trace_id, node, state)"]
    J --> K["Append to checkpoints/{trace_id}.jsonl<br/>with fsync + zombie-loop count"]
    K --> L["get_latest(trace_id) on resume"]
    L --> M{"Zombie check"}
    M -->|resume_count >= 5 OR consecutive same-node failures| N["quarantine() — move to quarantine/"]
    M -->|OK| O["Restore state, set status='running'"]
    P["Workflow success"] --> Q["mark_complete(trace_id) — delete journal"]
    R["Server boot"] --> S["scan_incomplete() — find crashed workflows<br/>modified in last 48h"]
```

---

## 💡 Key Design Decisions

### Tracer & Reader
- **Thin facade pattern** — `core/tracer.py` is a thin re-export facade. The actual `Tracer` implementation, `_FileWriter`, `_TraceStore`, and `generate_trace_id` live in `core/observability/tracer_engine.py`. The facade exists to maintain the stable `from core.tracer import tracer` import pattern used by 71+ files across the codebase, so the v1.3 extraction didn't require touching every consumer. The same pattern is used by `core/llm.py` (facade) → `core/llm_backend/` (impl) and `core/memory_engine.py` (facade) → `core/memory_backend/` (impl).
- **MCP stdio safety** — NEVER writes to `sys.stdout`. All output goes to `sys.stderr` and JSONL files. Any `print()` without `file=sys.stderr` will crash the MCP connection.
- **Dual output** — Structured stderr (console) + JSONL files (persistent, queryable). Provides both real-time visibility and post-mortem analysis.
- **Trace ID propagation** — Every operation tagged with 12-char hex ID from `uuid4`. Enables end-to-end correlation across workflows, tools, and LLM calls.
- **Bounded memory** — In-memory `_TraceStore` capped at 200 traces with FIFO eviction. Prevents unbounded memory growth in long-running agents.
- **Thread-safe** — All writes guarded by `threading.Lock()`. Concurrent workflow executions are safe.
- **Graceful degradation** — Falls back to standard `logging` if `structlog` is missing. Core observability never breaks from a missing optional dependency.
- **Daily rotation** — JSONL files rotate daily (`agent_YYYYMMDD.jsonl`). `_FileWriter` checks the date on every write.
- **Silent I/O errors** — `_FileWriter` intentionally ignores non-fatal disk errors. A logging failure should never crash the agent. KeyboardInterrupt/SystemExit are always re-raised.
- **Auto-flush + atexit close** — `f.flush()` after every write, plus `atexit.register(_writer.close)` for clean shutdown.
- **Reader dual-path** — `read_trace()` first checks in-memory store (fast path), then falls back to disk scan of last 14 days of JSONL logs (slow path). The 14-day limit prevents I/O explosion on huge log dirs.

### Metrics
- **Prometheus optional** — All metrics helpers are no-ops if `prometheus_client` is not installed. Caller code can call `track_node(...)` from anywhere without guarding imports.
- **Singleton registry** — One `CollectorRegistry()` shared by all metric instruments. Tracked: `autocode_node_duration_seconds` (histogram), `autocode_task_status_total` (counter), `autocode_tdd_iterations` (histogram), `autocode_llm_tokens_total` (counter).
- **Trace-Metrics separation** — `tracer.step()` provides qualitative data (what happened, when, with what context). `metrics.py` provides quantitative data (how long, how many, what status). Both are needed for full observability.

### Checkpoint Journal
- **Append-only JSONL** — One file per trace (`checkpoints/{trace_id}.jsonl`). Each entry is a single JSON line with `ts`, `node`, `status`, `state`, `resume_count`, `version`. Append-only means partial writes never corrupt earlier entries.
- **fsync on every write** — `f.flush()` + `os.fsync(f.fileno())` after every append. Crash-safe — the OS is forced to flush to disk before the file is closed.
- **Zombie detection** — Two heuristics: (1) `resume_count >= MAX_RESUMES (5)` — a workflow that's been resumed 5+ times is stuck in a loop. (2) Consecutive same-node failures (`prev.status == failed && entry.status == failed && prev.node == entry.node`) — pathological retry loop. Either triggers `quarantine()` (move to `quarantine/` subdir) and returns `None` so the caller starts fresh.
- **Version validation** — Each entry has a `version: 1` field. `get_latest()` injects `_checkpoint_version` into the restored state so consumers (e.g., `workflows/base.py run_workflow`) can reject incompatible checkpoints.
- **sanitize_state()** — Recursively extracts JSON-safe primitives (str, int, float, bool, None, datetime, Decimal, UUID, Path-like). Drops non-serializable objects (httpx clients, locks, CircuitBreakers) by returning `None`. Prevents `json.dumps()` from crashing on unserializable workflow state.
- **MAX_RESUMES = 5** — Hard cap on resume attempts. Tunable via the module-level constant (no env var yet).
- **scan_incomplete() cutoff** — Only scans journals modified in the last 48 hours. Prevents the boot-time scan from re-trying ancient crashed workflows that the user has likely forgotten about.

---

## 🧪 Testing

```bash
# Run all observability tests
python -m pytest tests/core/tracer/ -v
```

**Test layout:**
```text
tests/core/tracer/
├── test_tracer.py    # Tracer + _TraceStore + generate_trace_id (patches core.tracer._writer)
└── test_reader.py    # read_trace (memory + disk), list_recent_traces
```

**Mock strategy:**
- Mock `_FileWriter` for unit tests (avoid disk I/O) — `patch("core.tracer._writer")` for tracer tests, `patch("core.observability.reader.tracer")` for reader tests
- Use real `_TraceStore` for concurrency tests
- Test structlog fallback by mocking `import structlog` to raise `ImportError`
- For reader disk-scan tests, mock `cfg.log_path` to a tmp_path and write dummy JSONL files

> ⚠️ The checkpoint module currently has no dedicated test file — it's tested indirectly via `tests/workflows/base/test_dispatcher.py` (resume + crash scenarios) and `tests/workflows/base/test_node_helpers.py` (save_checkpoint + mark_complete mocking).

---

## ⚠️ Known Concerns

- **`patch("core.tracer._writer")` semantics** — The v1.3 facade re-exports `_writer` from `tracer_engine`, but `Tracer` method bodies reference `_writer` via `tracer_engine`'s module globals. So `patch("core.tracer._writer")` replaces the name in the facade's namespace but does NOT intercept writes from `Tracer` methods. Tests that need to intercept writes should patch `core.observability.tracer_engine._writer` instead. (The existing test in `test_tracer.py` may need its patch path updated in a follow-up.)
- **`tracer.step()` 2-arg signature usage** — Some callers use `tracer.step("health", "Health check")` with only 2 positional arguments. The signature is `step(trace_id, node, message="")`, so this sets `trace_id="health"` and `node="Health check"`. This produces trace records with a non-unique identifier that could collide with other health check calls. For non-trace-scoped logging, use `tracer.warning()` or a dedicated logging call.
- **JSONL file growth** — JSONL files are created daily and never compressed. Over time, a busy agent can produce hundreds of megabytes of logs. No automatic compression or archival. The 14-day scan limit in `reader.py` prevents performance issues, but disk usage grows unbounded.
- **No trace sampling** — Every operation is traced — no filtering or sampling. High-frequency operations (router calls, memory recalls) produce many low-value trace entries.

---

*Last updated: 2026-07-10. See [API.md](API.md) for function signatures, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
