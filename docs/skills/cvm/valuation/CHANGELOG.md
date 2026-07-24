<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-07-24 | **Initial implementation.** 2 modes: ratios (P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap) + summary (ratios + data source status). Combines b3 trades.db (price) + cvm dfp.db (financials) + cvm fre.db (shares) + bridge (ticker→CNPJ). Uses core/br_validator. 16 tests. |

---

## 🔄 In Progress / Next Up

- **EV/EBITDA** — Need EBITDA (currently in financials skill, not directly queryable here). Could import compute_ebitda from financials/metrics.py.
- **EV/EBITDA TTM** — Trailing twelve months EBITDA for the most-watched leverage ratio. Requires TTM computation (on financials roadmap).
- **P/FCF** — Price-to-Free-Cash-Flow. Need FCF = FCO - CAPEX (CAPEX from experimental or DFC).
- **TTM-based ratios** — Currently uses latest annual DFP. TTM would be more current (combines ITR quarters + DFP annual).
- **Historical ratios** — P/L over time (needs historical prices + historical earnings).
- **Sector comparison** — Compare a company's P/L against sector median (needs aggregation across companies).

---

## 🚫 Deferred / Out of Scope

- **Live price from investsite** — Could use investsite skill as a price source if b3 trades.db isn't synced. Deferred — b3 trades is the primary source.
- **Individual (non-consolidated) ratios** — Would need `consolidado=0` param. Deferred.

---

*Last updated: 2026-07-24 (v1.0).*
