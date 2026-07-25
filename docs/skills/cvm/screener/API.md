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
    "medians": {"p_l": 8.5, "p_vpa": 4.1, "ev_ebitda": 13.0, "roe": 0.18, ...},
    "peers": [{"ticker":"SUZB3","name":"SUZANO","p_l":4.0,...}, ...],
    "errors": [],
}
```

### `mode="compare"`

Compare a ticker against its sector medians.

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
    "medians": {...},
    "my_data": {"ticker":"SUZB3","p_l":4.0,...},
    "comparison": {
        "p_l": {"my_value":4.0, "sector_median":8.5, "delta_pct":-0.53, "vs_sector":"cheap"},
        "roe": {"my_value":0.295, "sector_median":0.207, "delta_pct":0.43, "vs_sector":"above"},
        ...
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

*Last updated: 2026-07-25 (v1.0).*
