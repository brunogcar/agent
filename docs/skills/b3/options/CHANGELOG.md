<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🗺️ Changelog — options skill

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-18 | **Initial implementation.** Single `dashboard` mode (3 tabs: Cadeia de Opções / Put/Call Ratio / Volume por Strike). Modular `_registry.py` + `modes/` + `report.py` pattern (delegates to `skills/_base/`). Reads from `data_sources.b3.cotahist_derivatives` query engine — `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike`. `REQUIRED_SOURCES=["cotahist"]` (derivatives share the same `cotahist.db`). Underlying normalization (`"PETR4"` → `"PETR"`). Option ticker legend (Call months A-L, Put months M-X, strike half-point convention). Accent colors: Calls=green, Puts=red, P/C reference line=grey dashed. Graceful degradation via `_safe_query()` wrapper (missing DB / missing table → error section, dashboard stays `status=ok`). Range selector (`price_range_selector`) wired on all charts. Helpers: `format_value`, `format_brl`, `format_int` (PT-BR). No `engines.py` — all aggregation in SQL (mirrors bcb/macro). |
| v1.1 | 2026-08-22 | **Exercicios tab.** Added 4th tab "Exercicios" (group: Opções) — daily exercise of stock options (BDI 38=call exercise, 42=put exercise). Dual-axis bar chart (call exercise volume green + put exercise volume red) + collapsible table of latest 15 observations. Uses `exercise_summary()` from derivatives_query. `_build_exercise_tab()` follows the same graceful-degradation pattern as the other tabs. |
| v1.2 | 2026-09-04 | **Volatilidade Implícita (Black-Scholes) tab.** Added 5th tab "Volatilidade Implícita" (group: Análise) — IV smile chart + IV table + IV Term Structure heatmap. NEW `engines.py` (pure-Python Black-Scholes — no scipy/numpy): `bs_price()`, `bs_vega()`, `implied_vol()` (Newton-Raphson + bisection fallback, clamp [0.01, 5.0], None for invalid). Risk-free rate = Selic from BCB SGS series 432 ("Meta Selic Copom", % a.a.) — converted to continuous compounding via `r_cont = ln(1 + r_simple)`. Spot price = latest PETR4 close from cotahist equities table. `REQUIRED_SOURCES` grows to `["cotahist", "sgs"]`. NEW `helpers.format_pct(v, decimals=2)`. NEW `report.build_heatmap_section()`. NEW `test_engines.py` (7 BS tests: parity, IV round-trip call/put, invalid inputs, below-intrinsic, intrinsic at T=0, vega > 0). conftest.py grows synthetic sgs.db (series 432=14.25) + PETR4 equities row (close=38.20). Dashboard bumps 4 tabs → 5 tabs. |

---

## ⚠️ Breaking Changes

*(None in v1.0 — first release.)*

*(v1.2 adds `REQUIRED_SOURCES=["cotahist","sgs"]` — callers who skip sync must now also have sgs.db present, or the IV tab degrades gracefully.)*

---

## 🔄 In Progress / Next Up

- **Open interest (DerivativesOpenPosition API)** — current `cotahist_derivatives`
  table has trade volume but NOT open interest. The B3 `DerivativesOpenPosition`
  API was the planned source, but the API changed and needs investigation.
  See [ROADMAP.md](ROADMAP.md).

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

*Last updated: 2026-09-05 (v1.2).*
