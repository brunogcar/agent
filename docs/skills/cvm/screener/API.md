<- Back to [SCREENER Overview](../SCREENER.md)

# 📝 API Reference

## 🔧 Skill Signature

```
skill(domain="cvm", sub_domain="screener", mode="...", params='{...}')
```

---

## ⚡ Modes

### `mode="sector"`

List all active companies in a sector with valuation ratios + sector medians.

[v1.2] The peer dict + medians dict now include 3 calculations-sourced metrics: `roa`, `margem_liquida`, `divida_pl`. These come from `valuation.ratios()` which delegates to calculations metrics (`roa_at`, `net_margin_at`, `debt_equity_at`). All v1.1 peer keys (price, market_cap, p_l, p_vpa, ev_ebitda, roe, dividend_yield, receita_liquida, ebitda, lucro_liquido, marg_ebitda, marg_liquida, payout, receita_growth, segmento) and v1.1 medians keys (p_l, p_vpa, ev_ebitda, roe, dividend_yield, market_cap) are preserved unchanged.

```python
params = '{"setor":"Papel e Celulose","limit":20}'
```

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `setor` | `str` | **Yes** | — | Sector name fragment (case-insensitive partial match) |
| `limit` | `int` | No | `20` | Max companies to fetch + compute ratios for |

**Returns:**
```python
{
    "status": "ok",
    "setor": "Papel e Celulose",
    "peer_count": 2,
    "medians": {
        # v1.0 keys
        "p_l": 8.5, "p_vpa": 4.1, "ev_ebitda": 13.0,
        "roe": 0.18, "dividend_yield": 0.13, "market_cap": 37_500_000_000,
        # v1.2 keys (new — from calculations via valuation.ratios)
        "roa": 0.07, "margem_liquida": 0.18, "divida_pl": 1.18,
    },
    "peers": [{"ticker":"SUZB3","name":"SUZANO","p_l":4.0,
               "roa":0.10,"margem_liquida":0.25,"divida_pl":0.85, ...},
              ...],
    "errors": [],
}
```

### `mode="compare"`

Compare a ticker against its sector medians.

[v1.2] The `comparison` dict now includes 3 new metric entries (roa, margem_liquida, divida_pl) alongside the v1.0 entries (p_l, p_vpa, ev_ebitda, roe, dividend_yield). `vs_sector` classification:
- "cheap"/"expensive" — p_l, p_vpa, ev_ebitda, **divida_pl** (lower = cheaper / less leveraged)
- "above"/"below" — roe, **roa**, **margem_liquida**, dividend_yield (higher = better)

```python
params = '{"company":"SUZB3"}'
```

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `company` | `str` | **Yes** | — | B3 ticker |
| `limit` | `int` | No | `20` | Max peers for median computation |

**Returns:**
```python
{
    "status": "ok",
    "ticker": "SUZB3",
    "name": "SUZANO",
    "setor": "Papel e Celulose",
    "peer_count": 2,
    "medians": {...},  # includes v1.2 roa/margem_liquida/divida_pl
    "my_data": {"ticker":"SUZB3","p_l":4.0,
                "roa":0.10,"margem_liquida":0.25,"divida_pl":0.85, ...},
    "comparison": {
        "p_l":         {"my_value":4.0,  "sector_median":8.5,   "delta_pct":-0.53, "vs_sector":"cheap"},
        "p_vpa":       {"my_value":...,  "sector_median":...,   "delta_pct":...,    "vs_sector":"..."},
        "ev_ebitda":   {"my_value":...,  "sector_median":...,   "delta_pct":...,    "vs_sector":"..."},
        "divida_pl":   {"my_value":0.85, "sector_median":1.18,  "delta_pct":-0.28, "vs_sector":"cheap"},
        "roe":         {"my_value":0.30, "sector_median":0.21,  "delta_pct": 0.43, "vs_sector":"above"},
        "roa":         {"my_value":0.10, "sector_median":0.07,  "delta_pct": 0.43, "vs_sector":"above"},
        "margem_liquida": {"my_value":0.25, "sector_median":0.18, "delta_pct":0.39, "vs_sector":"above"},
        "dividend_yield": {"my_value":...,  "sector_median":..., "delta_pct":..., "vs_sector":"..."},
    },
    "peers": [...],
    "errors": [],
}
```

---

## 🔌 Report Adapters

| Adapter | Source mode | What it tables |
|---------|-------------|----------------|
| `screener_sector` | sector | Peers table (sorted by P/L) + KPI strip (sector medians) |

---

*Last updated: 2026-07-27 (v1.2).*
