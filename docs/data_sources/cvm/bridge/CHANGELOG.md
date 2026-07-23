<- Back to [CVM Overview](../../CVM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2 | 2026-07-23 | **ISIN fallback + auto-sync-on-demand.** (1) Added `isin_fetcher.py` — downloads B3 ISIN ZIP (confirmed alive: 300k ISIN→CNPJ entries), caches in `memory_db/b3/isin_index.db` (24h TTL). When dividends returns no codeCVM, sync_engine falls back: dividends.db ISIN → ISIN ZIP → CNPJ → CAD by cnpj. New sync_log action `linked_isin`. (2) `_bridge.py` resolver now auto-syncs the bridge when a ticker isn't in bridge.db (`auto_sync=True` default) — first query for any ticker populates it transparently. 5 new tests (3 ISIN fallback + 2 auto-sync). 32 total tests. |
| v1.0 | 2026-07-23 | **Initial implementation.** Replaces legacy `skills/b3/b3_cvm/` (4-source join: instruments.db + B3 ISIN ZIP + CVM CSV + dfp_itr.db). New approach: 2-source chain via dividends per-ticker API (ticker → codeCVM) + CAD (cd_cvm → CNPJ + names). No bulk downloads, no ISIN ZIP, no instruments.db dependency, no mkt_cap. 4 modes: sync (per-ticker or list), status, lookup (ticker/cnpj/cd_cvm), resolve (fuzzy name). `ticker_map` table (11 columns) + `sync_log`. Resolver (`_bridge.py`) updated: `_resolve_via_bridge` returns (cnpj, cd_cvm) with cd_cvm fallback for DFP/ITR empresas. 27 tests (10 sync + 12 query + 5 resolver). |

---

*Last updated: 2026-07-23 (v1.2).*
