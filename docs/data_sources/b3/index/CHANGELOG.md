<- Back to [INDEX Overview](../INDEX.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-05 | **Initial implementation.** 8 modes: sync_index, sync_all, index, search, summary, history, ticker, status. 3-table schema (indices, constituents, history). 5 active indices (IBOV, SMLL, BDRX, IFIX, IDIV) + 26 catalogued. Sync guard integration via `required_sources=["index"]`. Weights normalized to 0.0–1.0. DELETE + INSERT per index (idempotent). |

---

## 🔄 In Progress / Next Up

- **Historical constituent changes** — Track additions/removals over time (quarterly rebalance). Would need a `constituents_history` table keyed on (index_symbol, ticker, refdate_from, refdate_to).
- **Sector classification per constituent** — Join with B3 API instruments + CVM FCA to break down each index by sector (e.g., IBOV: 30% financials, 25% commodities).
- **Index returns vs benchmark** — Compute relative performance (e.g., SMLL vs IBOV over 1Y/5Y) as a precomputed column in `indices`.

---

## 🚫 Deferred / Out of Scope

- **Real-time index values** — Only end-of-day history is synced. Intraday quotes would require a different API (B3 streaming / WebSocket).
- **Custom index construction** — Building user-defined baskets (e.g., "IBOV ex-PETR4") belongs in the skills/ layer (`skills/b3/index`), not in the data source.
- **Full 26-index sync by default** — `sync_all()` is intentionally limited to `ACTIVE_INDICES` (5). Adding all 26 would 5× the sync time for marginal value.

---

*Last updated: 2026-08-05 (v1.0).*
