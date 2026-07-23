<- Back to [CVM Overview](../CVM.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download CVM DFP ZIPs and populate dfp.db.

| Param | Type | Default | Description |
|---|---|---|---|
| `years` | `list[int]` | `[current_year]` | Specific years to sync |
| `full_history` | `bool` | `false` | Sync all years 2010-present |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="status"`
Show dfp.db statistics (no params).

### `mode="query"`
Full annual statements for a company (all account codes, all groups).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker, name fragment, or CNPJ |
| `grupo` | `str` | `""` | Filter: BPA, BPP, DRE, DFC_MI, DFC_MD, DVA, DMPL |
| `codigo` | `str` | `""` | Account code prefix filter (e.g., "1.01") |
| `anos` | `list[int]` | last 5 | Specific years |
| `consolidado` | `int` | `1` | 1=consolidated, 0=individual |

### `mode="resumo"`
Summary annual metrics (key accounts only).

### `mode="search"`
Search companies by name fragment.

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | (required) | Name fragment |
| `limit` | `int` | `10` | Max results |

## Tool Invocation

```python
data_source(domain="cvm", sub_domain="dfp", mode="sync")
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="dfp", mode="resumo", params='{"company":"PETR4","anos":[2023,2024]}')
data_source(domain="cvm", sub_domain="dfp", mode="search", params='{"query":"PETROBRAS"}')
```

## Return Shapes

- `sync`: `{status, form, years_synced, years_skipped, errors, total_rows}`
- `status`: `{status, form, path, db_size_mb, empresas, contas, year_range, synced_years, grupos, meses_distribution}`
- `query`: `{status, company, cnpj, consolidado, form, periods: {year: {grupo: [{codigo, descricao, valor, ...}]}}}`
- `resumo`: `{status, company, cnpj, consolidado, form, metrics: {label: {year: value}}}`
- `search`: `{status, query, companies: [{cnpj, nome, cd_cvm, anos, num_anos}]}`

---

*Last updated: 2026-07-23 (v1.0).*
