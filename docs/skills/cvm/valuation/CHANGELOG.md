<- Back to [VALUATION Overview](../VALUATION.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0.13 | 2026-07-25 | **Back-calculate market_cap from investsite P/L.** investsite does not expose market cap as a standalone value (only Preco/Lucro, Preco/VPA, Dividend Yield). v1.0.12 found the P/L correctly but market_cap stayed "computed" (price×shares, wrong for units). Fix: when use_investsite_ratios is True, back-calculate market_cap = investsite_P/L × lucro_liquido. This gives a consistent market cap for EV, P/EBIT, PSR, EV/EBITDA. market_cap_source = "investsite_derived".
| v1.0.12 | 2026-07-25 | **investsite market_cap exact key match + list handling.** v1.0.11 used substring scan ("mercado" in key) which matched ratio keys like "Valor de Mercado / Receita" (PSR ~3.13) instead of market cap. Fix: (1) use EXACT key match against {"valor de mercado","market cap","valor mercado"} — no substring. (2) Handle list values — investsite returns lists when a row has Consolidado + Individual columns; take first element (Consolidado). KLBN11 market cap now correctly resolves to ~R$ 22B instead of 3.13.
| v1.0.11 | 2026-07-25 | **investsite market_cap key fix.** v1.0.10 used hardcoded key names ("Valor de Mercado", "Market Cap") but the actual investsite label varies. Fix: scan ALL keys in precos_relativos case-insensitively for anything containing "mercado", "market", or "cap". Now finds market cap regardless of exact label. Combined with the investsite P/L fallback from v1.0.10, unit tickers (KLBN11) now get correct P/L AND market cap when brapi fails. |
| v1.0.10 | 2026-07-25 | **investsite market_cap fallback.** When brapi fails (free tier doesn't cover all tickers), the unit-ticker fix from v1.0.9 doesn't work — market_cap falls through to price×shares (wrong for units). Fix: (1) extract "Valor de Mercado" from investsite's precos_relativos section and return it as market_cap. (2) Also extract investsite's pre-computed Preco/Lucro + Preco/VPA — for unit tickers when market_cap is still "computed", use investsite's P/L + P/VPA directly (they do market-cap-based math server-side, correct for all types). Added p_l_source field ("computed" or "investsite"). KLBN11 now shows correct P/L regardless of which price source succeeds. |
| v1.0.9 | 2026-07-25 | **UNIT ticker fix.** For UNIT tickers (suffix 11 — KLBN11, TAEE11...), price is per-unit but total_shares is individual shares, so price×shares overstates market cap and P/L is inflated. Fix: (1) use brapi's `market_cap` when available (authoritative for units), fall back to price×shares. (2) Compute P/L, P/VPA, P/EBIT, P/FCO from `market_cap` (not per-share): `P/L = market_cap / lucro_liquido`. This is mathematically identical for regular stocks AND correct for units. (3) Added `unit_ticker` flag + `market_cap_source` field. EPS/VPA/DPA stay per-individual-share (informational). |
| v1.0.8+report | 2026-07-25 | **Report wiring (no skill change).** The `valuation` result can now be rendered as a table or exported to xlsx via the report tool's adapters: `valuation_ratios`, `valuation_summary` (`config["adapter"]`). The `valuation_ratios` adapter builds a KPI strip (Preço, P/L, P/VPA, EV/EBITDA, Div Yield, Market Cap) + a full indicator table. See [CVM Skills — Report Integration](../../CVM.md#-report-integration-v12). |
| v1.0.8 | 2026-07-24 | **Collective LLM review fixes.** (1) Valuation now calls financials skill internally (`_get_financials()`) instead of duplicating DFP code list — gets EBITDA, margins, ROE/ROA for free. (2) Added PSR, EV/EBITDA, P/FCF, DPA, Dívida Líq/EBITDA. (3) Fixed brapi price_date (was "", now uses today). (4) Fixed shares source mislabel (capital_social fallback now correctly labeled). (5) Fixed stale docstring. (6) Negative PL guard for P/VPA (returns None when PL ≤ 0). |
| v1.0 | 2026-07-24 | **Initial implementation.** 2 modes: ratios (P/L, P/VPA, EV, P/EBIT, P/FCO, Dividend Yield, Market Cap) + summary. Price from brapi (primary) or investsite (fallback) or b3 trades.db (last resort). Shares from FRE (primary) or investsite (fallback). Auto-sync bridge for new tickers. |

---

## ✅ Now Available (via report tool, v1.2)

- **Tabular rendering + xlsx export** — `report(action="table"|"export", data=<valuation JSON>, config={"adapter":"valuation_ratios"[,"format":"xlsx"]})`. The adapter builds a KPI strip + indicator table; number formatting (BRL/multiples/%) is handled by `report_ops/formats.py`.

---

## 🔄 In Progress / Next Up

- **ROIC** — NOPAT / Invested Capital = EBIT × (1 - tax_rate) / (PL + Dívida - Caixa). Needs tax rate (derive from DRE IR+CSLL, or use 34% as default). Flag as approximate.
- **CAPEX** — from DFC investing activities. Not a single fixed code — varies by company. Needs wildcard/description match approach like EBIT.
- **TTM ratios** — Currently uses latest annual DFP. TTM (trailing twelve months) would be more current. Combines ITR quarterly + DFP annual. Critical for seasonal businesses.
- **COTAHIST as historical price source** — for P/L over time, backtesting, charts. COTAHIST is official + instant (local). A candlestick chart adapter (COTAHIST OHLCV → `report(chart)`) is on the report tool roadmap (v1.3).
- **Graham number** — sqrt(22.5 × EPS × VPA). Simple value investing formula.

---

## 🚫 Deferred / Out of Scope

- **TIR (IRR)** — not feasible from CVM data. Requires cash flow timing (dates of each cash flow), which annual/quarterly filings don't provide. Would need a separate DCF calculator with user-supplied assumptions.
- **Sector benchmarks** — aggregate financials across companies for median P/L, ROE, etc. Separate skill (e.g., `skills/cvm/screener`).
- **Real-time prices** — 15-min delay (brapi) is the practical ceiling for a local-first agent without paid B3 feeds.

---

*Last updated: 2026-07-25 (v1.0.13).*
