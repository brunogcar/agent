<- Back to [VALUATION Overview](../VALUATION.md)

# 📝 API Reference

## 🔧 Skill Signature

```
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')
```

| Param | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | `str` | **Yes** | Always `"cvm"` |
| `sub_domain` | `str` | **Yes** | Always `"valuation"` |
| `mode` | `str` | **Yes** | `ratios` or `summary` |
| `params` | `str` (JSON) | **Yes** | JSON string: `{"company":"PETR4"}` |

---

## ⚡ Modes

### `mode="ratios"` (default)

Compute all valuation ratios from b3 price + CVM TTM financials + FRE shares.

**v1.0.14 new metrics:**
- **ROIC** = NOPAT / Invested Capital. NOPAT = EBIT × (1 - 0.34). Invested Capital = PL + Dívida Bruta - Caixa. Approximate (flat 34% tax rate). Flagged via `roic_tax_rate` field.
- **Graham Number** = sqrt(22.5 × EPS × VPA). Only computed when EPS > 0 and VPA > 0 (Graham's constraint). Price below Graham = potentially undervalued.
- **TTM financials** — uses trailing twelve months (sum of last 4 standalone quarters) instead of latest annual DFP. Falls back to annual when TTM key metrics are None.
- **Data freshness** — `data_freshness` field shows last-sync timestamp for each database.

**v1.4 new metrics (15 — sourced from calculations metrics via `_safe_call`):**

| Family | Metric keys | Calculations source |
|--------|-------------|---------------------|
| EV multiples | `ev_sales`, `ev_fcf` | `metrics.ev_sales.ev_sales_at`, `metrics.ev_fcf.ev_fcf_at` |
| Liquidity | `cash_ratio`, `quick_ratio` | `metrics.cash_ratio.cash_ratio_at`, `metrics.quick_ratio.quick_ratio_at` |
| Margins | `ocf_margin`, `fcf_margin` | `metrics.ocf_margin.ocf_margin_at`, `metrics.fcf_margin.fcf_margin_at` |
| Capital structure | `working_capital`, `cash_flow_to_debt` | `metrics.working_capital.working_capital_at`, `metrics.cash_flow_to_debt.cash_flow_to_debt_at` |
| Growth | `retention_ratio`, `sustainable_growth` | `metrics.retention_ratio.retention_ratio_at`, `metrics.sustainable_growth.sustainable_growth_at` |
| Coverage | `interest_coverage` | `metrics.interest_coverage.interest_coverage_at` |
| Turnover | `inventory_turnover`, `receivables_turnover`, `fixed_asset_turnover` | `metrics.inventory_turnover.inventory_turnover_at`, `metrics.receivables_turnover.receivables_turnover_at`, `metrics.fixed_asset_turnover.fixed_asset_turnover_at` |
| Price/tangible | `price_to_tangible_book` | `metrics.price_to_tangible_book.price_to_tangible_book_at` |

Each metric is wrapped in `_safe_call(fn, ticker, today)` so a FileNotFoundError (e.g., ITR db missing in test env) returns None without poisoning the rest of the ratios result.

Returns:
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "ratios": {
    "price": 38.50,
    "price_date": "2026-07-25",
    "unit_ticker": false,
    "market_cap": 496216309098.5,
    "market_cap_source": "brapi",
    "p_l": 4.13,
    "p_l_source": "computed",
    "p_vpa": 1.24,
    "ev": 833216309098.5,
    "ev_ebitda": 4.5,
    "psr": 1.2,
    "dividend_yield": 0.121,
    "roic": 0.15,
    "roic_tax_rate": 0.34,
    "graham_number": 36.7,
    "eps": 9.31,
    "vpa": 31.04,
    "dpa": 4.65,
    "lucro_liquido": 120000000000.0,
    "ebitda": 185000000000.0,
    "ebit": 200000000000.0,
    "receita_liquida": 400000000000.0,
    "patrimonio_liquido": 400000000000.0,
    "caixa": 34000000000.0,
    "divida_bruta": 371000000000.0,
    "fco": 180000000000.0,
    "fcf": 150000000000.0,
    "annual_dividends": 60000000000.0,
    "ev_sales": 2.05,
    "ev_fcf": 11.1,
    "cash_ratio": 0.09,
    "quick_ratio": 0.85,
    "ocf_margin": 0.45,
    "fcf_margin": 0.18,
    "working_capital": 15000000000.0,
    "cash_flow_to_debt": 0.48,
    "retention_ratio": 0.50,
    "sustainable_growth": 0.09,
    "interest_coverage": 8.0,
    "inventory_turnover": 5.5,
    "receivables_turnover": 7.2,
    "fixed_asset_turnover": 1.3,
    "price_to_tangible_book": 1.6
  },
  "sources": {
    "price": {"status": "ok", "source": "brapi"},
    "financials": {"status": "ok", "source": "ttm", "period": "2T2025–1T2026"},
    "shares": {"status": "ok", "source": "fre_distribuicao"}
  },
  "data_freshness": {
    "dfp": "2026-07-23T14:26:04",
    "itr": "2026-07-23T14:39:21",
    "fre": "2026-07-23T14:41:08",
    "cad": "2026-07-24T13:07:26",
    "bridge": "",
    "b3_dividends": "2026-07-24T22:51:18",
    "cotahist": "2026-07-23"
  }
}
```

### `mode="summary"`

Ratios + data source availability.

[v1.4] Adds a `headline_v13_metrics` block at the top level — the 10 most important v1.4 metrics (EV/Sales, EV/FCF, Quick Ratio, Cash Ratio, OCF Margin, FCF Margin, Interest Coverage, Cash Flow to Debt, Sustainable Growth, P/Tangible Book) surfaced for quick scanning without drilling into `ratios`.

Adds `data_availability` field:
```json
{
  "headline_v13_metrics": {
    "ev_sales": 2.05,
    "ev_fcf": 11.1,
    "quick_ratio": 0.85,
    "cash_ratio": 0.09,
    "ocf_margin": 0.45,
    "fcf_margin": 0.18,
    "interest_coverage": 8.0,
    "cash_flow_to_debt": 0.48,
    "sustainable_growth": 0.09,
    "price_to_tangible_book": 1.6
  },
  "data_availability": {
    "price": "ok",
    "price_source": "brapi",
    "dfp_ttm": "ok",
    "fre_shares": "ok"
  }
}
```

---

## 🔢 Metric Formulas

| Metric | Formula | Notes |
|--------|---------|-------|
| P/L | market_cap / lucro_liquido | Market-cap-based (v1.0.9). Correct for UNIT tickers. |
| P/VPA | market_cap / patrimonio_liquido | None when PL ≤ 0 |
| EV | market_cap + divida_bruta - caixa | |
| EV/EBITDA | ev / ebitda | |
| PSR | market_cap / receita_liquida | |
| ROIC | (ebit × (1 - 0.34)) / (pl + divida_bruta - caixa) | **v1.0.14**. Approximate — 34% flat tax rate. |
| Graham Number | sqrt(22.5 × eps × vpa) | **v1.0.14**. Only when EPS > 0 and VPA > 0. |
| Dividend Yield | (annual_dividends / shares) / price | |

---

## 🔌 Report Adapters

| Adapter | What it tables |
|---------|----------------|
| `valuation_ratios` | KPI strip (Preço, P/L, P/VPA, EV/EBITDA, ROIC, Graham, Div Yield, Market Cap) + full indicator table |
| `valuation_summary` | Ratios table + data-source availability table |

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; modes + params + return shapes unchanged). See [ARCHITECTURE.md](ARCHITECTURE.md) for the updated source code reference.*
