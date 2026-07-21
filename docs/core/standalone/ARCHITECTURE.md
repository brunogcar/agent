<- Back to [Standalone Overview](../STANDALONE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose | Consumers |
|------|---------|-----------|
| `core/utils.py` | `truncate_output()`, `compress_result()` — recursive output compression | `tools/agent.py`, `tools/file.py`, `tools/git.py`, `tools/memory.py`, `workflows/dispatch.py` |
| `core/br_validator.py` | `parse_brl()`, `parse_br_date()`, `validate_ticker()`, `B3Dividend` pydantic model | `skills/b3/` (data, export, paths), `tests/core/test_br_validator.py` |
| `core/citations.py` | `CitationTracker` — per-trace source numbering, thread-safe | `workflows/research.py`, `workflows/deep_research_impl/nodes/search.py`, `tools/browser/actions/citations.py` |
| `core/contracts.py` | `ok()`, `fail()`, `validate_tool_call()`, `ToolCall` pydantic model | **All tool facades**, **all action files**, **all workflows**, `core/parallel_executor.py`, `core/path_guard.py`, `core/llm_backend/client.py` |
| `core/metrics.py` | `track_node()`, `track_task_status()`, `generate_metrics()` — Prometheus registry | `core/gateway_backend/metrics.py` (endpoint) |
| `core/path_guard.py` | `resolve_path()`, `check_protected_file()`, `check_git_operation()`, `make_path_error()` | `tools/file.py`, `tools/git.py`, `tools/browser/actions/upload.py`, `tools/file_ops/helpers.py`, `tools/git_ops/helpers.py`, `tools/file_ops/actions/*.py`, `skills/b3/data.py`, `skills/b3/export.py`, `skills/b3/paths.py` |
| `core/symbol_offload.py` | `offload_to_file()`, `drill_down()`, `is_symbol_ref()`, `_auto_summary()` — TencentDB-inspired symbol offloading (verbose state → per-trace file + compact SymbolRef) | `workflows/autocode_impl/nodes/summarize_context.py`, `core/memory_backend/read_ops.py`, `core/sleep_learn/injector.py`, `tests/core/test_symbol_offload.py` |
| `core/atomic_write.py` | `atomic_write(path, content, *, encoding)` — tempfile + fsync + os.replace; parent dir creation; tempfile cleanup on failure (v1.5) | `workflows/autoresearch_impl/nodes/modify.py`, `workflows/autoresearch_impl/nodes/decide.py` (parallel winner copy), `workflows/autocode_impl/patch.py` (apply_patch + apply_patches), `workflows/autocode_impl/nodes/write_new_files.py`, `workflows/autocode_impl/nodes/create_skill.py`, `tests/core/test_atomic_write.py` |
| `core/backoff_retry.py` | `retry_with_backoff(fn, retries, base_delay, cancellation_check, tid)` — exponential backoff + interruptible sleep + cancellation integration (v1.5) | `workflows/autocode_impl/helpers.py::_call`, `workflows/autoresearch_impl/nodes/propose.py::_call_planner`, `tests/core/test_backoff_retry.py` |
| `core/time_utils.py` | `now()`, `parse_iso()`, `parse_human()`, `parse_duration()`, `cron_next_fire()`, `compute_missed_fires()`, `_build_cron_trigger()` — tz-aware time + cron helpers, reads `cfg.timezone` | `tools/notify_ops/` (schedule/recurring/state/helpers), `tools/schedule_ops/` (state/actions), `tests/core/test_time_utils.py` |
| `core/config.py` | `cfg.agent_root`, `cfg.workspace_root`, `cfg.is_protected()` | `path_guard.py` (root resolution), all tools (env vars) |
| `core/tracer.py` | `tracer.new_trace()` | `path_guard.py` (error trace_id injection) |

---

## 🌳 Module Tree

```text
core/
├── utils.py              # Output compression / truncation helpers
├── br_validator.py       # Brazilian financial data validation (BRL, dates, tickers)
├── symbol_offload.py     # TencentDB-inspired symbol offloading (verbose state → file + SymbolRef)
├── atomic_write.py       # Atomic file writes (tempfile + fsync + os.replace)  [v1.5]
├── backoff_retry.py          # LLM retry with exponential backoff + cancellation  [v1.5]
├── citations.py          # Per-trace citation tracker (thread-safe singleton)
├── contracts.py          # Standardized ok()/fail() responses + ToolCall validation
├── metrics.py            # Prometheus metrics registry (graceful degradation)
├── path_guard.py         # Centralized path validation + protected file guards + git scoping
└── time_utils.py         # Tz-aware time + cron helpers (v1.0 — replaces @mcpcentral/mcp-time MCP dep)
```

---

## 💡 Key Design Decisions

- **Centralized path validation** — `path_guard.py` is the single source of truth for all filesystem path security. No tool implements custom path resolution. Three-layer defense: facade → helpers → handlers.
- **Standardized responses** — `contracts.py` `ok()` / `fail()` are used by every tool. `error_code` field (v1.2) enables programmatic error classification.
- **Graceful metric degradation** — `metrics.py` becomes a no-op if `prometheus_client` is not installed. Safe to import anywhere.
- **Thread-safe citation tracker** — `citations.py` uses `threading.Lock()` with per-trace stores. MAX_TRACES = 100 with LRU eviction.
- **Recursive output compression** — `utils.py` `compress_result()` walks dicts/lists and truncates oversized strings. Prevents context window bloat.
- **Pydantic v2 models** — `br_validator.py` uses `@field_validator` for B3 dividend data. `contracts.py` `ToolCall` validates LLM tool call structure.
- **Protected file guard** — `path_guard.py` `READ_OPERATIONS` / `WRITE_OPERATIONS` frozensets define which actions are allowed on protected files. Unknown operations fail-open with a warning.
- **Git scoping** — `path_guard.py` `GIT_WORKSPACE_ONLY` frozenset restricts `init` and `clone` to `WORKSPACE_ROOT`. All other git ops allowed within `AGENT_ROOT`.
- **Symlink safety** — `path_guard.py` `resolve_path()` uses `Path.resolve()` before `_is_within()` check. Catches symlink escapes.
- **Tz-aware time (v1.0)** — `time_utils.py` is the single source of truth for tz-aware datetime + cron. All functions return tz-aware datetimes in `cfg.timezone` (`AGENT_TZ` env, default = system local). Replaces the external `@mcpcentral/mcp-time` MCP dependency for our own tooling. `_build_cron_trigger` remaps DOW to APScheduler day-names, sidestepping `from_crontab`'s 0=Monday trap (standard cron 0=Sunday preserved).
- **Null byte defense** — `path_guard.py` explicitly checks `\x00` (null byte) in paths before any `Path` parsing. Defense in depth.

---

## 🧪 Testing

*(No dedicated test suites for these standalone modules. They are tested indirectly via consumer test suites.)*

```powershell
# Indirect coverage via consumer tests
D:\mcp\agent\venv\Scripts\pytest.exe tests/ -W error --tb=short -v
```

> **Note:** `core/contracts.py` is exercised by every tool test. `core/path_guard.py` is exercised by `tests/tools/file/` and `tests/tools/git/`. `core/utils.py` is exercised by `tests/tools/git/test_git_compression.py`.

---

*Last updated: 2026-07-25 (v1.5 — added atomic_write.py + backoff_retry.py).*
