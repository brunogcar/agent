<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-07-23 | **Initial implementation.** 4 modes: quarterly (default, 8Q), annual (5Y), complete (by grupo + key codes), summary. Standalone quarter derivation from ITR cumulative + DFP annual. EBITDA = EBIT + D&A (DFC 6.01.01.02). Ratios: margins, ROA/ROE (annualized for quarterly), debt ratios, payout. 23 tests. Read-only — calls DFP/ITR query engines directly. |

---

## 🔄 In Progress / Next Up

- **TTM-based ratios** — Currently ROA/ROE are annualized (×4) for quarterly. Rapina uses TTM (trailing twelve months) for some ratios. Implement TTM EBITDA for `Dív.Líq./EBITDA TTM` ratio.
- **xlsx export** — Export to .xlsx format (like rapina's JHSF example) with multiple sheets (completo anual/trim, resumo anual/trim). Likely a `report` tool action or a skill feature.
- **Charts/graphs** — Visual charts for trends (revenue, margins, debt evolution). Belongs in `report` tool.
- **Individual (non-consolidated)** — Already supported via `consolidado=0` but needs testing with real data.

---

## 🚫 Deferred / Out of Scope

- **All 497 account codes** — `complete` mode returns key codes only (~30 codes across 5 grupos). Full hierarchy export deferred (too noisy for LLM context).
- **Historical restatements** — Currently keeps only the latest version (VERSAO dedup). Showing restated vs original is deferred.
- **Cross-company comparison** — Comparing multiple companies side-by-side is a separate skill (e.g., `skills/cvm/comparison`).

---

*Last updated: 2026-07-23 (v1.0).*
