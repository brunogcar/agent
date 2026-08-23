<- Back to [Backtest Overview](../BACKTEST.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. Never query CVM/B3 directly — use calculations engines/metrics for signals.
2. Never modify BUILTIN_STRATEGIES at runtime in production code.
3. Never create `.bak` files.
4. Never print to stdout — MCP stdio corruption.

## ✅ ALWAYS DO

1. Always use calculations metric `*_at()` functions for signal generation.
2. Always wrap signal calls in try/except — missing data is non-fatal.
3. Always track equity curve for every bar.
4. Always compute buy & hold comparison for alpha.
5. Always close open positions at end of backtest period.

---

### Anti-patterns & Lessons Learned

- **v2.0 lesson:** _registry.py + __init__.py now delegate to `skills/_base/` (shared ModeSpec + make_registry + make_route + auto_discover_modes). The duplicated ~97-line _registry.py + ~88-line __init__.py boilerplate is gone — each skill's _registry.py is now ~16 lines, __init__.py is ~50 lines. Adding a new mode = drop a file in `modes/` + `@register_mode(...)` (unchanged). Adding a new skill = 3 files (_registry.py + __init__.py + modes/) following the pattern in [SKILLS.md → How to Create a New Skill](../../SKILLS.md). Bug fixes to the dispatch infrastructure now only need to be made in ONE place.

---

*Last updated: 2026-07-30 (v2.0).*
