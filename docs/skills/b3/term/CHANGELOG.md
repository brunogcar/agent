<- Back to [TERM](../TERM.md)

# Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-08-16 | **Initial implementation.** 3-tab dashboard: Contratos Ativos (term chain table) + Spread Termo vs Spot (dual-axis chart: term price vs spot price + spread) + Volume Histórico (bar chart). Queries `data_sources.b3.cotahist.derivatives_query` (merged into cotahist — no separate data source). BDI 26/74. |

## 🔄 In Progress / Next Up

- Forward skill (BDI 46/48) — same architecture, separate skill.
- Index options skill (BDI 83/84) — same architecture, separate skill.

## 🚫 Deferred / Out of Scope

- Open interest — needs DerivativesOpenPosition API (broken, investigate later).
- Implied volatility — needs Black-Scholes engine.
