<- Back to [ITR Overview](../ITR.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download CVM ITR ZIPs and populate itr.db.

| Param | Type | Default | Description |
|---|---|---|---|
| `years` | `list[int]` | `[current_year]` | Specific years to sync |
| `full_history` | `bool` | `false` | Sync all years 2015-present |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="status"`
Show itr.db statistics (no params).

### `mode="query"`
Full quarterly statements for a company (all account codes, cumulative).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker, name fragment, or CNPJ |
| `grupo` | `str` | `""` | Filter: BPA, BPP, DRE, DFC_MI, DFC_MD, DVA, DMPL |
| `codigo` | `str` | `""` | Account code prefix filter |
| `anos` | `list[int]` | last 3 | Specific years |
| `consolidado` | `int` | `1` | 1=consolidated, 0=individual |

**Note:** Values are CUMULATIVE (Jan→period end), NOT standalone quarters.

### `mode="resumo"`
Summary quarterly metrics (key accounts, cumulative).

### `mode="search"`
Search companies by name fragment in the ITR database.

## Tool Invocation

```python
data_source(domain="cvm", sub_domain="itr", mode="sync")
data_source(domain="cvm", sub_domain="itr", mode="query", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="itr", mode="status")
```

---

*Last updated: 2026-07-23 (v1.0).*
