<- Back to [CVM Overview](../../CVM.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2.1 | 2026-07-23 | **P1 hotfix: CNPJ format mismatch.** DFP/ITR sync stored CNPJ raw (formatted "33.000.167/0001-01") but bridge/resolver use normalized ("33000167000101") — caused every ticker query to return `not_found` from DFP/ITR. Fix: (1) `_bridge.py` resolver now uses `REPLACE(REPLACE(REPLACE(cnpj,'.',''),'/',''),'-','')` in all 4 CNPJ queries to normalize on-the-fly (works with both formats, no re-sync needed). (2) DFP sync_engine + ITR sync_engine now import + use `cnpj_digits()` to normalize CNPJ at ingest time (future re-syncs will be clean). FRE/IPE already used `cnpj_digits()` — unaffected. 2 new tests (formatted CNPJ in dfp.db + direct CNPJ query). 34 total tests. |
| v1.2 | 2026-07-23 | **ISIN fallback + auto-sync-on-demand.** (1) Added `isin_fetcher.py` — downloads B3 ISIN ZIP (confirmed alive: 300k ISIN→CNPJ entries), caches in `memory_db/b3/isin_index.db` (24h TTL). When dividends returns no codeCVM, sync_engine falls back: dividends.db ISIN → ISIN ZIP → CNPJ → CAD by cnpj. New sync_log action `linked_isin`. (2) `_bridge.py` resolver now auto-syncs the bridge when a ticker isn't in bridge.db (`auto_sync=True` default) — first query for any ticker populates it transparently. 5 new tests (3 ISIN fallback + 2 auto-sync). 32 total tests. |
| v1.0 | 2026-07-23 | **Initial implementation.** Replaces legacy `skills/b3/b3_cvm/` (4-source join: instruments.db + B3 ISIN ZIP + CVM CSV + dfp_itr.db). New approach: 2-source chain via dividends per-ticker API (ticker → codeCVM) + CAD (cd_cvm → CNPJ + names). No bulk downloads, no ISIN ZIP, no instruments.db dependency, no mkt_cap. 4 modes: sync (per-ticker or list), status, lookup (ticker/cnpj/cd_cvm), resolve (fuzzy name). `ticker_map` table (11 columns) + `sync_log`. Resolver (`_bridge.py`) updated: `_resolve_via_bridge` returns (cnpj, cd_cvm) with cd_cvm fallback for DFP/ITR empresas. 27 tests (10 sync + 12 query + 5 resolver). |

---

*Last updated: 2026-07-23 (v1.2).*
