<- Back to [COTAHIST_DERIVATIVES Overview](../COTAHIST_DERIVATIVES.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-18 | **Initial implementation.** 4 query functions: `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike`. `status_reporter.stats()` for DB summary. `catalog.parse_option_ticker()` — B3 option ticker parser (Call months A-L, Put months M-X, strike half-point rule `215` → 21.5). `DERIVATIVES_SCHEMA_SQL` — `cotahist_derivatives` table with 4 derived columns (`underlying`, `option_type`, `expiration_month`, `strike_parsed`) + 5 indexes. `BDI_LABELS` for codes {78, 82, 83, 84, 26}. Shared DB: `db_path()` delegates to `data_sources/b3/cotahist/catalog.db_path()` (derivatives table in the SAME `cotahist.db` as equities). NO `sync_engine.py` — derivatives are populated by the standard COTAHIST sync (the sync engine writes to BOTH tables in one ZIP parse pass, dispatching per-row by BDI code). Nearest-maturity auto-selection for `options_chain` + `volume_by_strike`. Underlying normalization (strip trailing digits) in every query function. Status codes: `ok` / `error` / `not_synced` / `not_found`. |

---

## ⚠️ Breaking Changes

*(None in v1.0 — first release.)*

---

## 🔄 In Progress / Next Up

- **Open interest column** — the `cotahist_derivatives` table currently has
  trade volume but NOT open interest. The B3 `DerivativesOpenPosition` API
  was the planned source, but the API changed and needs investigation.
  Tracked in the options skill ROADMAP — see
  [../../../skills/b3/options/ROADMAP.md](../../../skills/b3/options/ROADMAP.md).
- **Index options (BDI 83/84) deeper analytics** — currently treated the
  same as stock options. A future enhancement could separate index option
  flows (BOVA, WIN, etc.) into a dedicated view.

---

## 🚫 Deferred / Out of Scope

- **Separate sync_engine.py** — intentionally NOT created. Derivatives
  ride on the standard COTAHIST sync (same ZIP parse writes to both
  tables). A separate sync would require downloading the same ZIP twice
  + parsing the same TXT twice.
- **Futures/forward analytics** — TERM rows (BDI 26) are stored but a
  dedicated futures skill is deferred to a separate future effort. The DB
  is prepared — see the options skill ROADMAP P5.
- **Real-time options quotes** — COTAHIST is end-of-day only. Real-time
  options chains would require a streaming/polling API (brapi or paid B3
  market data feed).

---

*Last updated: 2026-08-18 (v1.0).*
