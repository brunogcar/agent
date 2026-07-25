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
    "price_source": "brapi",
    "unit_ticker": false,
    "total_shares": 12888732761,
    "lucro_liquido": 120000000000.0,
    "patrimonio_liquido": 400000000000.0,
    "ebit": 200000000000.0,
    "fco": 180000000000.0,
    "caixa": 34000000000.0,
    "divida_bruta": 371000000000.0,
    "annual_dividends": 60000000000.0,
    "market_cap": 496216309098.5,
    "market_cap_source": "brapi",
    "eps": 9.31,
    "p_l": 4.13,
    "p_l_source": "computed",
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

**Provenance fields (v1.0.9+):**

| Field | Values | Description |
|-------|--------|-------------|
| `unit_ticker` | `true`/`false` | True for UNIT tickers (suffix 11: KLBN11, TAEE11). Triggers market-cap-based ratio computation. |
| `market_cap_source` | `"brapi"`/`"investsite"`/`"computed"`/`"none"` | Where market cap came from. "computed" = price×shares (wrong for units). "brapi"/"investsite" = authoritative. |
| `p_l_source` | `"computed"`/`"investsite"` | Where P/L came from. "investsite" = investsite's pre-computed P/L (fallback for units when market_cap is "computed"). |

For UNIT tickers when brapi fails: `market_cap_source` = "investsite" (if investsite provides it) or "computed" (wrong, fallback to investsite's P/L via `p_l_source` = "investsite").

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
