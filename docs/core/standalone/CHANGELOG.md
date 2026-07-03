<- Back to [Standalone Overview](../STANDALONE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| Pre-v1 | — | Initial standalone modules created |

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes recorded yet. Add entries here as they occur.)*

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

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for module details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
