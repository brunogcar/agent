<- Back to [INDEX Overview](../INDEX.md)

# 🗺️ Changelog — index skill

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-05 | **Initial implementation.** 3 modes: dashboard (single-index deep dive, 4-tab), compare (multi-index side-by-side, 3-tab), ticker (reverse-lookup). Modular `_registry.py` + `modes/` pattern (delegates to `skills/_base.py`). Sync guard wired via `required_sources=["index"]` + `make_route()`. 11 tests. Read-only over `data_sources/b3/index`. |

---

## 🔄 In Progress / Next Up

- **Beta calculation** — Per-constituent beta vs the parent index (regression of constituent returns on index returns over a trailing 252-day window). Would extend the dashboard with a "Risk" tab.
- **Sector weight analysis** — Compare sector weights across indices (e.g., IBOV vs SMLL: financials weight differential). Currently surfaced only as a table; could add a stacked bar chart.
- **Historical comparison** — Compare index performance across multiple windows (1M/3M/6M/1Y/5Y/YTD) with rebalance-aware return computation.

---

## 🚫 Deferred / Out of Scope

- **Custom index construction** — Building user-defined baskets ("IBOV ex-PETR4") belongs in a future `custom_index` skill, not here.
- **Intraday quotes** — Only end-of-day history is synced. Intraday would require a streaming API.
- **Real-time alerts** — When a constituent crosses a weight threshold. Requires a push architecture (pub/sub), not the current pull model.

---

*Last updated: 2026-08-05 (v1.0).*
