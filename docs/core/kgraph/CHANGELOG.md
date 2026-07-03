<- Back to [Knowledge Graph Overview](../KGRAPH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-04 | Initial implementation. AST-based dependency extraction, SQLite graph storage, test targeting, project isolation. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| AST-based dependency extraction | ✅ Pre-v1 | Deterministic `ast` module import parsing |
| SQLite graph storage | ✅ Pre-v1 | WAL mode, thread-safe, indexed |
| Test targeting | ✅ Pre-v1 | Source → test file mapping via AST analysis |
| Hybrid validation | ✅ Pre-v1 | mtime + size (fast) then MD5 (slow) cache invalidation |
| Project isolation | ✅ Pre-v1 | Per-project `.understand/` directories |
| Critical path detection | ✅ Pre-v1 | Full suite trigger for global infrastructure files |
| Project-specific ChromaDB collections | ✅ Pre-v1 | Physical isolation from main memory |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Class/function-level nodes | Beyond file-level granularity | P2 |
| Cross-language support | JavaScript, TypeScript AST parsing | P3 |
| Call graph analysis | Function-level dependency tracking | P2 |
| Incremental indexing | Only re-parse changed files (delta updates) | P1 |
| Visualization | Mermaid/SVG export of dependency graphs | P3 |
| Test coverage integration | Map coverage data to graph nodes | P3 |
| Fix `yaml` import in `test_mapper.py` | Add `import yaml` with `ImportError` guard, or document PyYAML as optional dependency | P1 |
| GraphStore cleanup on shutdown | Add `close_all()` class method, register via `atexit` | P1 |
| Relative path in AST cache key | Use relative path instead of absolute path for cache key | P2 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for component details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
