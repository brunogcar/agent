# 🧩 STANDALONE

Standalone utility modules in `core/` — shared helpers, contracts, guards, and trackers used across tools, workflows, and the gateway. These files have no subpackage structure; each is a self-contained module imported directly by consumers.

**Key characteristics:**
- **Zero dependencies on each other** — Each module is independent (except `path_guard` → `contracts` for `fail()`)
- **Cross-cutting concerns** — Used by tools, workflows, gateway, and skills alike
- **No `@tool` facade** — These are library code, not MCP tools
- **No individual test suites** — Tested indirectly via consumer test suites
- **Thread-safe where applicable** — `citations` and `metrics` use locks / CollectorRegistry

---

## 🚀 Quick Start

```python
from core.contracts import ok, fail, validate_tool_call          # All tools use this
from core.path_guard import resolve_path, check_protected_file   # File + git tools use this
from core.utils import compress_result, truncate_output          # Facades use this
from core.citations import citations                             # Research workflows use this
from core.metrics import track_node, generate_metrics           # Gateway uses this
from core.br_validator import parse_brl, validate_ticker         # Skills use this
```

---

## 🔄 When to Use vs Alternatives

| Need | File | Why |
|------|------|-----|
| Standardized tool responses | `core/contracts.py` | Every tool returns `ok()` / `fail()` dicts with `trace_id` + `error_code` |
| Path validation / SSRF guard | `core/path_guard.py` | Centralized `resolve_path()`, `check_protected_file()`, `check_git_operation()` |
| Output compression | `core/utils.py` | `compress_result()` truncates large string fields recursively |
| Citation tracking | `core/citations.py` | Per-trace source numbering for research workflows |
| Prometheus metrics | `core/metrics.py` | Node duration, task status, TDD iterations, LLM tokens |
| BRL / BR date / ticker parsing | `core/br_validator.py` | Brazilian financial data validation for `skills/b3` |

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

*Last updated: 2026-07-04. See subfiles for detailed documentation.*
