<- Back to [Calculations Overview](../CALCULATIONS.md)

# 🗺️ Roadmap

Items remaining after the v1.3 P2 sprint. The P2 sprint added 10 new engines + 15 new metrics (see CHANGELOG.md v1.3). Remaining items are P3 — defer until consumer skills demand them.

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
| 3.06.02 | Despesas Financeiras (gross interest expense) | Would replace the abs(financial_result) approximation in interest_coverage with the true gross interest line |
| DVA 8.1 | Personnel costs (Remuneração de Pessoal) | Completes the DVA distribution-side decomposition (7 = 8.1 + 8.2 + 8.3 + 8.4) |
| DVA 8.4 | Shareholder remuneration (Dividends + net income) | Cross-checks dividends engine (B3) + earnings engine (DRE 3.11) |

### New metrics (deferred)
| Metric | Why deferred |
|--------|-------------|
| PEG Ratio | Needs growth-rate window design decision (1yr? 3yr CAGR?) — not just an engine |
| Payables Turnover | Needs "Purchases" derivation (COGS + ΔInventory) — fragile; payables engine exists but the numerator is non-trivial |
| Debt Service Coverage | Debt amortization schedule not available in CVM DFP/ITR — may not be feasible |
| NWC Turnover | Low urgency, niche |
| Personnel-to-Value-Added Ratio | Needs DVA 8.1 engine (P3 above) — stakeholder-distribution analysis |
| Distribution Decomposition Ratios | 8.1/7, 8.2/7, 8.3/7, 8.4/7 — needs DVA 8.1 + 8.4 engines (P3 above) |

### Hardening (deferred from P2)
- **DFC_MD vs DFC_MI**: D&A and CapEx engines search by description in both methods. Verify the description-search works for direct-method DFC filers (rare in Brazil but they exist).
- **Consolidated vs individual**: All engines filter `consolidado = 1`. Add fallback to individual statements when consolidated is empty (some smaller filers only file individual).
- **Multi-code summing**: Document which engines sum multiple codes (debt sums 2.01.04 + 2.02.01). Create a helper function for future multi-code engines (inventory sub-components).
- **Negative value handling policy**: Decide project-wide: does negative earnings → negative ROA (informative) or None (safe)? Currently inconsistent across metrics.
- **Scale unit edge cases**: Add tests for `parse_escala()` with NULL/unexpected values. Low priority — all engines already use it consistently.
- **Date boundary tests**: Add explicit tests for date exactly at period-end, before first period, after last period. Current implementation handles these correctly via `<= date` filtering, but no explicit tests verify this.
- **Currency inflation adjustment**: Real feature, wrong layer. Belongs as an opt-in post-processing step over already-computed series (wrap any `_history()` output through an IPCA deflator), not inside every engine. Needs BCB IPCA data source integration.
- **Subfolder reorganization**: Wait until 35+ engines. The `category` field provides organizational metadata without breaking import paths. At 30 engines (v1.3), flat is still navigable — but the threshold is approaching. When reorganizing, group by category: `engines/market/`, `engines/dre/`, `engines/bpa/`, `engines/bpp/`, `engines/dfc/`, `engines/dva/`, `engines/shares/`. Update `_registry.py` auto-discovery glob pattern to recurse into subfolders.
- **DVA cross-statement consistency check**: Verify DVA 7 ≈ DVA 8.1 + 8.2 + 8.3 + 8.4 once the 8.1 + 8.4 engines are added. Useful as a data-quality assertion, not a metric per se.

---

*Last updated: 2026-07-28 (v1.3). Items will be promoted to P1/P0 as consumer skills demand them.*
