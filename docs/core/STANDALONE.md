# 🧩 STANDALONE

Standalone utility modules in `core/` — shared helpers, contracts, guards, and trackers used across tools, workflows, and the gateway. These files have no subpackage structure; each is a self-contained module imported directly by consumers.

> **v1.3 moves:** `tracer.py` is now a thin facade → `core/observability/tracer_engine.py` (see [OBSERVABILITY.md](observability/OBSERVABILITY.md)). `tracer_reader.py` and `metrics.py` moved into `core/observability/` as `reader.py` and `metrics.py`. They are no longer standalone modules.

**Key characteristics:**
- **Zero dependencies on each other** — Each module is independent (except `path_guard` → `contracts` for `fail()`)
- **Cross-cutting concerns** — Used by tools, workflows, gateway, and skills alike
- **No `@tool` facade** — These are library code, not MCP tools
- **Individual test suites** — `core/atomic_write.py` + `core/backoff_retry.py` have dedicated tests (v1.5); others are tested indirectly via consumer test suites
- **Thread-safe where applicable** — `citations` uses locks; Prometheus `CollectorRegistry` now lives in `core/observability/metrics.py` (moved out of standalone in v1.3)

> **🔮 Future direction (v1.5 signal):** `core/atomic_write.py` + `core/backoff_retry.py` are the first modules extracted from duplicated workflow code (centralize-workflow-utils refactor). As more shared workflow patterns are identified, these may be consolidated into a `core/workflow_utils/` subpackage. `tools/git_ops/workflow_helpers.py` (the git operation wrappers extracted in the same refactor) is a candidate to join them as `core/workflow_utils/vcs.py`. This is a direction signal, not a commitment — the modules work fine as standalone files until the count grows enough to justify a subpackage.

---

## 🚀 Quick Start

```python
from core.contracts import ok, fail, validate_tool_call          # All tools use this
from core.path_guard import resolve_path, check_protected_file   # File + git tools use this
from core.utils import compress_result, truncate_output          # Facades use this
from core.citations import citations                             # Research workflows use this
from core.br_validator import parse_brl, validate_ticker         # Skills use this
from core.symbol_offload import offload_to_file, drill_down       # Workflows + memory use this
from core.atomic_write import atomic_write                        # Workflows use this (v1.5)
from core.backoff_retry import retry_with_backoff                     # Workflows use this (v1.5)

# v1.3 moves — these now live under core/observability/:
# from core.tracer import tracer                                  # facade → core/observability/tracer_engine.py
# from core.observability.reader import read_trace                # was core/tracer_reader.py
# from core.observability.metrics import track_node               # was core/metrics.py
```

---

## 🔄 When to Use vs Alternatives

| Need | File | Why |
|------|------|-----|
| Standardized tool responses | `core/contracts.py` | Every tool returns `ok()` / `fail()` dicts with `trace_id` + `error_code` |
| Path validation / SSRF guard | `core/path_guard.py` | Centralized `resolve_path()`, `check_protected_file()`, `check_git_operation()` |
| Output compression | `core/utils.py` | `compress_result()` truncates large string fields recursively |
| Citation tracking | `core/citations.py` | Per-trace source numbering for research workflows |
| BRL / BR date / ticker parsing | `core/br_validator.py` | Brazilian financial data validation for `skills/b3` |
| Symbol offloading (TencentDB pattern) | `core/symbol_offload.py` | Offload verbose state fields to per-trace files, replace with compact SymbolRef dicts. Used by autocode (debug_history), memory (recall > 10 results), sleep_learn (> 5 injected rules). |
| Atomic file writes (v1.5) | `core/atomic_write.py` | `atomic_write(path, content)` — tempfile + fsync + os.replace. Extracted from 4 duplicated implementations (autoresearch modify.py, autocode patch.py / write_new_files.py / create_skill.py). |
| LLM retry with backoff (v1.5) | `core/backoff_retry.py` | `retry_with_backoff(fn, retries, base_delay, cancellation_check, tid)` — exponential backoff + interruptible sleep. Extracted from autocode `_call` + autoresearch `_call_planner`. |
| Tz-aware time + cron helpers | `core/time_utils.py` | `now()` / `parse_iso()` / `parse_human()` / `parse_duration()` / `cron_next_fire()` / `compute_missed_fires()` / `_build_cron_trigger()` — reads `cfg.timezone` (`AGENT_TZ` env); used by `notify_ops` + `schedule_ops`; replaces the external `@mcpcentral/mcp-time` MCP dependency |

> **v1.3 move:** Prometheus metrics (`track_node`, `generate_metrics`) moved to `core/observability/metrics.py` — see [OBSERVABILITY.md](observability/OBSERVABILITY.md).

---

## ⚙️ Configuration

*(Fill this section with relevant info from edits and refactors. Add configuration details as they are learned.)*

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](standalone/ARCHITECTURE.md) | Source code reference with consumer mapping, module tree, design decisions |
| [API.md](standalone/API.md) | Per-module API reference, signatures, security rules, return shapes |
| [CHANGELOG.md](standalone/CHANGELOG.md) | Version history, completed features, roadmap, deferred items |
| [INSTRUCTIONS.md](standalone/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-25 (v1.5 — added atomic_write.py + backoff_retry.py).*
