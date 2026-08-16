<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🗺️ Changelog — options skill

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-18 | **Initial implementation.** Single `dashboard` mode (3 tabs: Cadeia de Opções / Put/Call Ratio / Volume por Strike). Modular `_registry.py` + `modes/` + `report.py` pattern (delegates to `skills/_base.py`). Reads from `data_sources.b3.cotahist_derivatives` query engine — `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike`. `REQUIRED_SOURCES=["cotahist"]` (derivatives share the same `cotahist.db`). Underlying normalization (`"PETR4"` → `"PETR"`). Option ticker legend (Call months A-L, Put months M-X, strike half-point convention). Accent colors: Calls=green, Puts=red, P/C reference line=grey dashed. Graceful degradation via `_safe_query()` wrapper (missing DB / missing table → error section, dashboard stays `status=ok`). Range selector (`price_range_selector`) wired on all charts. Helpers: `format_value`, `format_brl`, `format_int` (PT-BR). No `engines.py` — all aggregation in SQL (mirrors bcb/macro). |

---

## ⚠️ Breaking Changes

*(None in v1.0 — first release.)*

---

## 🔄 In Progress / Next Up

- **Open interest (DerivativesOpenPosition API)** — current `cotahist_derivatives`
  table has trade volume but NOT open interest. The B3 `DerivativesOpenPosition`
  API was the planned source, but the API changed and needs investigation.
  See [ROADMAP.md](ROADMAP.md).
- **Implied Volatility (Black-Scholes)** — compute IV per option using a
  Black-Scholes engine + the Selic rate from BCB SGS as the risk-free rate.
  See [ROADMAP.md](ROADMAP.md).
- **IV Smile heatmap** — strike (y) vs maturity (x), colored by IV.
  Blocked on the IV computation above.

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

*Last updated: 2026-08-18 (v1.0).*
