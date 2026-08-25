<- Back to [TERM](../TERM.md)

# Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v2.0 | 2026-08-25 | **Forward-data enrichment.** When COTAHIST has no term data for a stock (which is always — B3 routes stock term to BTC), the dashboard queries the new b3.api `derivatives.db` for the EQUITY FORWARD contract snapshot (ticker = `{TICKER}T`, e.g. PETR4T). Shows: (1) Contratos Ativos: forward contract KPI table (ticker, company, ISIN, security category, specification, forward price per share, open interest, total quantity, aggregate value) + spot price snapshot (last 5 closes) + forward-vs-spot spread row; (2) Spread Termo vs Spot: 1-row comparison table (forward vs spot + spread) + spot price chart (90 days); (3) Volume Histórico: open position details table (OI, total quantity, forward price) + info text. Added `forward_positions()` mode to `data_sources/b3/api/query_engine.py` + `forward_positions` route in `b3/api/__init__.py`. Extended `_load_instruments_index()` to also load ISIN, SctyCtgyNm, SpcfctnCd. `REQUIRED_SOURCES` now `["cotahist", "b3-api-derivatives", "b3-api-instruments"]`. Graceful degradation: if `derivatives.db` not synced, falls back to legacy spot-price-only display. |
| v1.0 | 2026-08-16 | **Initial implementation.** 3-tab dashboard: Contratos Ativos (term chain table) + Spread Termo vs Spot (dual-axis chart: term price vs spot price + spread) + Volume Histórico (bar chart). Queries `data_sources.b3.cotahist.derivatives_query` (merged into cotahist — no separate data source). BDI 26/74. |

## 🔄 In Progress / Next Up

- Forward skill (BDI 46/48) — same architecture, separate skill.
- Index options skill (BDI 83/84) — same architecture, separate skill.

## 🚫 Deferred / Out of Scope

- ~~Open interest — needs DerivativesOpenPosition API (broken, investigate later).~~ Done in v2.0 via b3.api derivatives.db CSV bulk download.
- Implied volatility — needs Black-Scholes engine.
