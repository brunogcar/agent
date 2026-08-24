<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🗺️ Changelog — options skill

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-18 | **Initial implementation.** Single `dashboard` mode (3 tabs: Cadeia de Opções / Put/Call Ratio / Volume por Strike). Modular `_registry.py` + `modes/` + `report.py` pattern (delegates to `skills/_base/`). Reads from `data_sources.b3.cotahist_derivatives` query engine — `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike`. `REQUIRED_SOURCES=["cotahist"]` (derivatives share the same `cotahist.db`). Underlying normalization (`"PETR4"` → `"PETR"`). Option ticker legend (Call months A-L, Put months M-X, strike half-point convention). Accent colors: Calls=green, Puts=red, P/C reference line=grey dashed. Graceful degradation via `_safe_query()` wrapper (missing DB / missing table → error section, dashboard stays `status=ok`). Range selector (`price_range_selector`) wired on all charts. Helpers: `format_value`, `format_brl`, `format_int` (PT-BR). No `engines.py` — all aggregation in SQL (mirrors bcb/macro). |
| v1.1 | 2026-08-22 | **Exercicios tab.** Added 4th tab "Exercicios" (group: Opções) — daily exercise of stock options (BDI 38=call exercise, 42=put exercise). Dual-axis bar chart (call exercise volume green + put exercise volume red) + collapsible table of latest 15 observations. Uses `exercise_summary()` from derivatives_query. `_build_exercise_tab()` follows the same graceful-degradation pattern as the other tabs. |
| v1.2 | 2026-09-04 | **Volatilidade Implícita (Black-Scholes) tab.** Added 5th tab "Volatilidade Implícita" (group: Análise) — IV smile chart + IV table + IV Term Structure heatmap. NEW `engines.py` (pure-Python Black-Scholes — no scipy/numpy): `bs_price()`, `bs_vega()`, `implied_vol()` (Newton-Raphson + bisection fallback, clamp [0.01, 5.0], None for invalid). Risk-free rate = Selic from BCB SGS series 432 ("Meta Selic Copom", % a.a.) — converted to continuous compounding via `r_cont = ln(1 + r_simple)`. Spot price = latest PETR4 close from cotahist equities table. `REQUIRED_SOURCES` grows to `["cotahist", "sgs"]`. NEW `helpers.format_pct(v, decimals=2)`. NEW `report.build_heatmap_section()`. NEW `test_engines.py` (7 BS tests: parity, IV round-trip call/put, invalid inputs, below-intrinsic, intrinsic at T=0, vega > 0). conftest.py grows synthetic sgs.db (series 432=14.25) + PETR4 equities row (close=38.20). Dashboard bumps 4 tabs → 5 tabs. |
| v1.3 | 2026-09-08 | **Posições em Aberto tab + Cadeia de Opções OI enrichment.** Added 6th tab "Posições em Aberto" (group: Posições) — uses the B3 API CSV bulk download (`derivatives.db` 17 cols + `instruments.db` 52 cols joined on TckrSymb in Python — SQLite can't JOIN across DBs without ATTACH). 4 sections: (a) KPI summary table [Total OI / Call-Put OI Ratio / Cobertura % / Descoberta %]; (b) Bar chart of Open Interest by Strike (CALL green vs PUT red side-by-side — the options "wall" chart showing support/resistance concentrations); (c) Summary table matching the Google Sheet R2:U7 layout [Coberta | Travada | Descoberta | Total | Titulares | Lançadores] for CALL vs PUT; (d) Per-option detail table [Ticker | Tipo | Strike | Vencimento | Dias | OI | Var OI | Coberta | Descoberta | Total | Titulares | Lançadores | Forward]. NEW `open_positions(underlying)` + `lookup_option_positions(ticker)` in `data_sources/b3/api/query_engine.py` with graceful degradation (if instruments.db missing → degraded join with strike=None / days_to_expiration=None; if derivatives.db missing → not_synced). Filters: only EQUITY CALL/PUT SgmtNm; skip rows with OpnIntrst=0 AND TtlPos=0. NEW b3-api modes in `data_sources/b3/api/__init__.py` MANIFEST + route() (`open_positions`, `lookup_option_positions`). Cadeia de Opções tab enriched with 3 new columns (OI / Coberta / Descoberta) from `open_positions()` — uses a single call + a ticker→positions map (no N+1 queries). `REQUIRED_SOURCES` grows to `["cotahist", "sgs", "b3-api-derivatives", "b3-api-instruments"]`. NEW sync_map entries in `skills/_base/sync_guard.py` for `b3-api-derivatives` + `b3-api-instruments` (lambda: `table=derivatives/instruments, force=True`). conftest.py grows synthetic `b3/derivatives.db` (10 rows: 8 PETR options + 1 zero-position + 1 FORWARD) + `b3/instruments.db` (9 rows) — monkeypatches `data_sources.b3.api.catalog.db_path` + `connect`. NEW `test_api_open_positions.py` (13 tests: basic, summary, by_strike, detail join, zero-position filter, FORWARD filter, not_found, not_synced, lookup basic/not_found/no_ticker/case-insensitive). Dashboard bumps 5 tabs → 6 tabs. |

---

## ⚠️ Breaking Changes

*(None in v1.0 — first release.)*

*(v1.2 adds `REQUIRED_SOURCES=["cotahist","sgs"]` — callers who skip sync must now also have sgs.db present, or the IV tab degrades gracefully.)*

*(v1.3 adds `b3-api-derivatives` + `b3-api-instruments` to `REQUIRED_SOURCES` — callers who skip sync must also have b3/derivatives.db + b3/instruments.db present, or the Posições em Aberto tab + the Cadeia de Opções OI columns degrade gracefully.)*

---

## 🔄 In Progress / Next Up

- **Futures/forward skill** — BDI 26 (TERM) is already in the
  `cotahist_derivatives` table. A dedicated futures skill is deferred.

---

## 🚫 Deferred / Out of Scope

- **Futures/forward skill** — BDI code 26 (TERM) is already in the
  `cotahist_derivatives` table (the DB is prepared), but a dedicated
  futures skill is deferred to a separate future effort.
- **"Opções" tab in the price dashboard** — cross-skill integration:
  the price dashboard could embed a 4th tab that calls the options
  dashboard. Tracked in the price skill ROADMAP (P3) — see
  [../price/ROADMAP.md](../price/ROADMAP.md).

---

*Last updated: 2026-09-08 (v1.3).*
