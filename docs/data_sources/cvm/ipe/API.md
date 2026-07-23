<- Back to [CVM Overview](../CVM.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download CVM IPE ZIPs and populate ipe.db.

| Param | Type | Default | Description |
|---|---|---|---|
| `years` | `list[int]` | `[current_year]` | Specific years to sync |
| `full_history` | `bool` | `false` | Sync all years 2003-present |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="status"`
Show ipe.db statistics (no params).

### `mode="query"`
Query IPE events with filters.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | `""` | Company name, CNPJ, or B3 ticker |
| `categoria` | `str` | `""` | Filter by category |
| `tipo` | `str` | `""` | Filter by type |
| `keyword` | `str` | `""` | Filter by keyword in assunto (subject) |
| `data_from` | `str` | `""` | Start date YYYY-MM-DD |
| `data_to` | `str` | `""` | End date YYYY-MM-DD |
| `limit` | `int` | `20` | Max results |

### `mode="search"`
Search companies by name.

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | (required) | Name fragment |
| `limit` | `int` | `10` | Max results |

## Tool Invocation

```python
data_source(domain="cvm", sub_domain="ipe", mode="sync")
data_source(domain="cvm", sub_domain="ipe", mode="query", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="ipe", mode="query", params='{"keyword":"dividendo","data_from":"2024-01-01"}')
data_source(domain="cvm", sub_domain="ipe", mode="search", params='{"query":"PETROBRAS"}')
```

---

*Last updated: 2026-07-23 (v1.0).*
