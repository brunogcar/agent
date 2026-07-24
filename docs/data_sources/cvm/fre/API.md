<- Back to [FRE Overview](../FRE.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download CVM FRE ZIPs and populate fre.db.

| Param | Type | Default | Description |
|---|---|---|---|
| `years` | `list[int]` | `[current_year]` | Specific years to sync |
| `full_history` | `bool` | `false` | Sync all years 2010-present |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="status"`
Show fre.db statistics (no params).

### `mode="shareholders"`
Query shareholder composition (who owns the company).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker, name fragment, or CNPJ |
| `limit` | `int` | `50` | Max shareholders |

### `mode="free_float"`
Query free float / shareholder distribution.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker, name, or CNPJ |

### `mode="compensation"`
Query executive/board compensation.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker, name, or CNPJ |

### `mode="capital"`
Query stock capital + share counts.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker, name, or CNPJ |

### `mode="search"`
Search companies by name fragment.

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | (required) | Name fragment |
| `limit` | `int` | `10` | Max results |

## Tool Invocation

```python
data_source(domain="cvm", sub_domain="fre", mode="sync")
data_source(domain="cvm", sub_domain="fre", mode="shareholders", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="fre", mode="free_float", params='{"company":"VALE3"}')
data_source(domain="cvm", sub_domain="fre", mode="compensation", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="fre", mode="capital", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="fre", mode="search", params='{"query":"PETROBRAS"}')
```

---

*Last updated: 2026-07-23 (v1.0).*
