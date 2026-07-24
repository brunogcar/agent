<- Back to [VALUATION Overview](../VALUATION.md)

# 📖 API Reference

## skill(domain="cvm", sub_domain="valuation", ...)

### mode="ratios" (default)

Compute all valuation ratios from b3 price + CVM financials + FRE shares.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | B3 ticker (PETR4) |

Returns:
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "ratios": {
    "price": 38.50,
    "price_date": "2026-07-24",
    "total_shares": 12888732761,
    "lucro_liquido": 120000000000.0,
    "patrimonio_liquido": 400000000000.0,
    "ebit": 200000000000.0,
    "fco": 180000000000.0,
    "caixa": 34000000000.0,
    "divida_bruta": 371000000000.0,
    "annual_dividends": 60000000000.0,
    "market_cap": 496216309098.5,
    "eps": 9.31,
    "p_l": 4.13,
    "vpa": 31.04,
    "p_vpa": 1.24,
    "ev": 833216309098.5,
    "p_ebit": 2.48,
    "p_fco": 2.76,
    "dividend_yield": 0.121,
    "div_per_share": 4.65
  },
  "sources": {
    "price": {"status": "ok", "date": "2026-07-24"},
    "financials": {"status": "ok", "ano": 2023},
    "shares": {"status": "ok", "total_shares": 12888732761}
  }
}
```

### mode="summary"

Ratios + data source availability.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | B3 ticker |

Adds `data_availability` field showing which DBs are synced.

---

## Examples

```
skill(domain="cvm", sub_domain="valuation", mode="ratios", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="valuation", mode="summary", params='{"company":"VALE3"}')
```

---

*Last updated: 2026-07-24 (v1.0).*
