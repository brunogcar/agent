<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.14 | 2026-07-25 | **ROIC + Graham number + TTM valuation + data freshness.** (1) ROIC = NOPAT / Invested Capital (34% tax rate, approximate — flagged via roic_tax_rate). (2) Graham number = sqrt(22.5 × EPS × VPA), only when EPS > 0 and VPA > 0. (3) TTM valuation: _get_financials_ttm() calls financials.quarterly() and uses the TTM summary. Falls back to financials.annual() when TTM key metrics are None (one quarter missing). (4) Data freshness: new skills/cvm/_freshness.py helper returns last-sync timestamps for all CVM/B3 databases. valuation.ratios() now includes data_freshness field. (5) Valuation adapter updated: ROIC + Graham added to indicator table + KPI strip. TTM labels on financial values. |
| v1.0.13 | 2026-07-25 | **Back-calculate market_cap from investsite P/L.** investsite does not expose market cap as a standalone value. Fix: when use_investsite_ratios is True, back-calculate market_cap = investsite_P/L × lucro_liquido. |
| v1.0.12 | 2026-07-25 | **investsite market_cap exact key match + list handling.** |
| v1.0.9 | 2026-07-25 | **UNIT ticker fix.** Market-cap-based ratios (P/L = market_cap / lucro_liquido). |
| v1.0.8 | 2026-07-24 | **Collective LLM review fixes.** Calls financials skill internally. Added PSR, EV/EBITDA, P/FCF, DPA. |

---

## 🔄 In Progress / Next Up

- **Real tax rate for ROIC** — currently uses flat 34% (IRPJ + CSLL). Could derive actual rate from DRE IR+CSLL accounts.
- **CAPEX from DFC** — currently FCI is the proxy for P/FCF. Real CAPEX needs wildcard/description match.
- **COTAHIST historical P/L** — P/L over time (needs COTAHIST historical prices + historical financials).

---

## 🚫 Deferred / Out of Scope

- **TIR (IRR)** — not feasible from CVM data. Requires cash flow timing.
- **Sector benchmarks** — ✅ Done via `screener` skill.
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling.

---

*Last updated: 2026-07-25 (v1.0.14).*
