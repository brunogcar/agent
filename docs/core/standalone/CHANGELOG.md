<- Back to [Standalone Overview](../STANDALONE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| **v1.6** | 2026-07-22 | **`core/backoff_retry.py` gains `non_retryable` param** (consumed by **autoresearch v1.11 A4**). New optional param `non_retryable: Optional[tuple] = None` on `retry_with_backoff`. When `fn()` raises an exception matching `isinstance(e, non_retryable)`, the exception is re-raised immediately (no sleep, no retry, no `tracer.error` log). Default `None` = retry every `Exception` (backward-compatible v1.5 behavior). Use case: callers can distinguish transient failures (network blips, rate limits — worth retrying) from real bugs (ImportError, AttributeError — never worth retrying; each retry is a wasted LLM API hit + backoff sleep). **autoresearch** `_call_planner` passes `non_retryable=(_PropagateError,)` so non-transient exceptions propagate immediately. **autocode** `_call` passes no `non_retryable` — behavior unchanged. 2 new unit tests in `tests/core/test_backoff_retry.py`. |
| **v1.5** | 2026-07-25 | **Added `core/atomic_write.py` + `core/backoff_retry.py`** — two new standalone modules extracted from duplicated workflow code (centralize-workflow-utils refactor, Phases A + C). **`atomic_write(path, content, *, encoding="utf-8")`**: tempfile.mkstemp in same dir + os.fdopen + fsync + os.replace; cleans up tempfile on failure; creates parent dirs. Extracted from 4 duplicated implementations (autoresearch `modify.py::_atomic_write`, autocode `patch.py::apply_patch`/`apply_patches`, autocode `write_new_files.py` node, autocode `create_skill.py` node). 7 unit tests in `tests/core/test_atomic_write.py`. **`retry_with_backoff(fn, retries=2, base_delay=2.0, cancellation_check=None, tid="")`**: exponential backoff (base * 2^attempt) with interruptible sleep (polls `cancellation_check` in 0.1s slices when provided, else `time.sleep`). Raises `RuntimeError("cancelled during backoff")` if cancellation fires during sleep. Extracted from autocode `_call()` (manual retry + `threading.Event.wait`) + autoresearch `_call_planner()` (manual retry + `time.sleep`). Return type NOT unified — returns whatever `fn` returns (works for both `str` autocode + `tuple[str, dict]` autoresearch). 6 unit tests in `tests/core/test_backoff_retry.py`. |
| **v1.4** | 2026-07-18 | **Added `core/symbol_offload.py`** — new standalone module: `offload_to_file()`, `drill_down()`, `is_symbol_ref()`, `_auto_summary()`. TencentDB-inspired pattern: offload verbose state fields to per-trace files (`workspace/.symbols/{trace_id}/{field}.json`), replace with compact SymbolRef dicts in state. Complements chonkie (within-field compression) with cross-field context management. Used by autocode (`summarize_context.py` — debug_history), memory (`read_ops.py` — recall > 10 results), sleep_learn (`injector.py` — > 5 injected rules). 16 unit tests in `tests/core/test_symbol_offload.py`. |
| Pre-v1.1 | 2026-07-16 | **Added `core/time_utils.py`** — new standalone module: tz-aware `now()`/`parse_iso()`/`parse_human()`/`parse_duration()`/`cron_next_fire()`/`compute_missed_fires()`/`_build_cron_trigger()`, all reading `cfg.timezone` (`AGENT_TZ` env). Replaces the external `@mcpcentral/mcp-time` MCP dependency for our own tooling. Used by `notify_ops` (v1.1 swap) + `schedule_ops` (v1.0). 44 unit tests in `tests/core/test_time_utils.py`. |
| Pre-v1.1 | 2026-07-05 | `check_protected_file` now fails-closed on unknown operations (Bug #2). Was fail-open, which allowed new write actions to silently bypass protection on protected files. |
| Pre-v1 | — | Initial standalone modules created |

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

### Pre-v1.1 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| `check_protected_file` fails-closed on unknown operations | Unknown action names (not in `READ_OPERATIONS` or `WRITE_OPERATIONS`) now return `(False, error_msg)` instead of `(True, "")`. New tools must explicitly add their actions to the operation sets in `core/path_guard.py`. | Add any new tool actions to `READ_OPERATIONS` or `WRITE_OPERATIONS` in `core/path_guard.py`. The error message names the missing action. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| `core/contracts.py` — `ok()` / `fail()` / `ToolCall` | ✅ Pre-v1 | Standardized responses across all tools |
| `core/contracts.py` — `error_code` field (v1.2) | ✅ Pre-v1 | Programmatic error classification |
| `core/path_guard.py` — `resolve_path()` | ✅ Pre-v1 | Symlink-safe, null-byte defense, cross-platform |
| `core/path_guard.py` — `check_protected_file()` | ✅ Pre-v1 | Read/write operation sets, protected file guard |
| `core/path_guard.py` — `check_git_operation()` | ✅ Pre-v1 | Git scoping with `WORKSPACE_ROOT` restriction |
| `core/path_guard.py` — v1.1 fixes | ✅ Pre-v1 | Added `move_file`, `copy_file`, `create_directory` to `WRITE_OPERATIONS`; added `clone` to `GIT_WORKSPACE_ONLY`; explicit `cwd.exists()` check |
| `core/utils.py` — `compress_result()` / `truncate_output()` | ✅ Pre-v1 | Recursive dict/list compression |
| `core/citations.py` — `CitationTracker` | ✅ Pre-v1 | Thread-safe, per-trace, LRU eviction (MAX_TRACES=100) |
| `core/metrics.py` — Prometheus registry | ✅ Pre-v1 | Graceful degradation if `prometheus_client` missing |
| `core/br_validator.py` — BRL / date / ticker parsing | ✅ Pre-v1 | Pydantic v2 `B3Dividend` model |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Dedicated test suites for standalone modules | Currently tested indirectly via consumer tests | P2 |
| `core/utils.py` expansion | More compression strategies (JSON minification, base64 detection) | P3 |
| `core/br_validator.py` expansion | More Brazilian financial instruments (FII, ETF, BDR) | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Move standalone modules to subpackages** | These are intentionally flat. If a module grows complex enough to need a subpackage, it should be promoted to a full component (like `core/net/`). | Skip |
| 2 | **Add `**kwargs` to `ok()` / `fail()`** | FastMCP schema breaks. Use `**meta` instead. | Skip |
| 3 | **Custom path resolution in tools** | Centralized in `path_guard.py`. Never duplicate. | Skip |

---

*Last updated: 2026-07-22 (v1.6 — backoff_retry non_retryable param).*
