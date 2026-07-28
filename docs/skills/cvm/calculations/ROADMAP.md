<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🗺️ Roadmap

Items deferred from the v1.2 hardening review. Prioritized by impact and complexity.

## P2 — Next sprint

### New engines
| Code | Name | Consumer | Enables |
|------|------|----------|---------|
| 3.06 | Financial Result (Resultado Financeiro) | valuation | Interest Coverage ratio (needs interest-expense sub-line, not net 3.06 — may need description-search) |
| 1.01.03 | Accounts Receivable (Contas a Receber) | valuation | Quick Ratio, Receivables Turnover |
| 1.01.04 | Inventory (Estoques) | valuation | Inventory Turnover, Days Inventory |
| 3.02 | COGS (Custo dos Bens Vendidos) | financials | Gross margin cross-check (3.01 - 3.02 = 3.03) |
| 1.02.03 | PP&E (Imobilizado) | valuation | Fixed Asset Turnover |
| 1.02.04 | Intangibles (Intangível) | valuation | Price to Tangible Book |
| 2.01.01 | Accounts Payable (Fornecedores) | valuation | Payables Turnover |
| DVA | Value Added Statement engines | historical | Interest paid cross-check, total tax burden, wealth distribution analysis (DVA is optional-filing in CVM — handle None gracefully) |

### New metrics (engines already exist)
| Metric | Formula | Type |
|--------|---------|------|
| EV/Sales | EV / Revenue | 2 |
| EV/FCF | EV / (FCO + FCI) | 2 |
| Cash Ratio | Cash / Current Liabilities | 2 |
| OCF Margin | FCO / Revenue | 2 |
| FCF Margin | (FCO + FCI) / Revenue | 2 |
| Working Capital | Current Assets - Current Liabilities | 2 |
| Cash Flow to Debt | FCO / Total Debt | 2 |
| Retention Ratio | 1 - Payout | 2 |
| Sustainable Growth Rate | ROE × Retention | 2 |

### New metrics (need new engines)
| Metric | Needs | Formula |
|--------|-------|---------|
| Quick Ratio | receivables engine | (Cash + Receivables) / Current Liabilities |
| Interest Coverage | 3.06 engine | EBIT / Interest Expense |
| Inventory Turnover | COGS + inventory engines | COGS / Inventory |
| Receivables Turnover | receivables engine | Revenue / Receivables |
| Fixed Asset Turnover | PP&E engine | Revenue / PP&E |
| Price to Tangible Book | intangibles engine | Price / ((PL - Intangibles) / shares) |

### Hardening
- **DFC_MD vs DFC_MI**: D&A and CapEx engines search by description in both methods. Verify the description-search works for direct-method DFC filers (rare in Brazil but they exist).
- **Consolidated vs individual**: All engines filter `consolidado = 1`. Add fallback to individual statements when consolidated is empty (some smaller filers only file individual).
- **Multi-code summing**: Document which engines sum multiple codes (debt sums 2.01.04 + 2.02.01). Create a helper function for future multi-code engines (inventory sub-components).
- **Negative value handling policy**: Decide project-wide: does negative earnings → negative ROA (informative) or None (safe)? Currently inconsistent across metrics.

## P3 — Defer / roadmap

### New engines
| Code | Name | Notes |
|------|------|-------|
| 1.02 | Non-current Assets | Derivable as total_assets - current_assets — probably don't need a dedicated engine |
| 2.02 | Non-current Liabilities | Derivable as total_liabilities - current_liabilities |
| 1.01.02 | Financial Investments | Cash-like but not cash — broader liquidity analysis |
| 3.04 | Operating Expenses | EBITDA component breakdown |
| 3.09 | Continuing Operations Income | More precise than 3.11 for multi-segment firms |
| 3.10 | Discontinued Operations | Flags restructuring |
| 2.01.05 | Tax Obligations | Balance sheet detail |
| 2.03.01 | Subscribed Capital | Capital structure detail |

### New metrics (deferred)
| Metric | Why deferred |
|--------|-------------|
| PEG Ratio | Needs growth-rate window design decision (1yr? 3yr CAGR?) — not just an engine |
| Payables Turnover | Needs "Purchases" derivation (COGS + ΔInventory) — fragile |
| Debt Service Coverage | Debt amortization schedule not available in CVM DFP/ITR — may not be feasible |
| NWC Turnover | Low urgency, niche |
| Tangible Book | Needs intangibles engine (description-search, fragile) |

### Hardening (deferred)
- **Scale unit edge cases**: Add tests for `parse_escala()` with NULL/unexpected values. Low priority — all engines already use it consistently.
- **Date boundary tests**: Add explicit tests for date exactly at period-end, before first period, after last period. Current implementation handles these correctly via `<= date` filtering, but no explicit tests verify this.
- **Currency inflation adjustment**: Real feature, wrong layer. Belongs as an opt-in post-processing step over already-computed series (wrap any `_history()` output through an IPCA deflator), not inside every engine. Needs BCB IPCA data source integration.
- **Subfolder reorganization**: Wait until 25+ engines. The `category` field provides organizational metadata without breaking import paths. At 21 engines, flat is still navigable.

---

*Last updated: 2026-07-28 (v1.2). Items will be promoted to P1/P0 as consumer skills demand them.*
