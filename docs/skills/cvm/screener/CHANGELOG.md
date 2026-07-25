<- Back to [SCREENER Overview](../SCREENER.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-07-25 | **Financials enrichment.** screener.sector now calls financials.annual(periods=2) per peer to add Receita, EBITDA, Lucro Liquido, Marg. EBITDA, Marg. Liquida, Payout, and Cresc. Receita (YoY). Best-effort — financials failures don't skip the peer. Adapter enriched with 7 new columns.
| v1.0 | 2026-07-25 | **Initial implementation.** 2 modes: sector (list peers + medians), compare (is ticker cheap/expensive vs sector). Orchestrates CAD + bridge + valuation. Best-effort — skips companies without ticker or failed valuation. Peers sorted by P/L cheapest-first. 1 report adapter (screener_sector). 15 skill tests. |

---

## 🔄 In Progress / Next Up

- **Sector screener with financials** — currently uses valuation.ratios() for P/L, ROE, EV/EBITDA. Could also pull financials.annual() for revenue, EBITDA growth, margins to enrich the peers table.
- **Custom metric selection** — let the LLM specify which metrics to include (e.g. only P/L + ROE).
- **Historical comparison** — compare a ticker's current P/L vs its own historical P/L range (needs COTAHIST + historical financials).

---

## 🚫 Deferred / Out of Scope

- **Real-time price** — uses 15-min delayed brapi. Real-time needs paid B3 feeds.
- **Cross-sector comparison** — comparing a ticker against multiple sectors. Each sector has different economics; cross-sector comparison is usually misleading.

---

*Last updated: 2026-07-25 (v1.1).*
