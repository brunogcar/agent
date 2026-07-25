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
    "annual_dividends": 60000000000.0
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

Adds `data_availability` field:
```json
{
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

*Last updated: 2026-07-25 (v1.0.14).*
