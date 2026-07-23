<- Back to [CVM Overview](../CVM.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download cad_cia_aberta.csv and populate cad.db. Full replace (~1.5MB, ~2s).

| Param | Type | Default | Description |
|---|---|---|---|
| `force` | `bool` | `false` | Re-download even if already synced today |

### `mode="status"`
Show cad.db statistics (no params).

### `mode="lookup"`
Look up a single company by CNPJ, CD_CVM, or name. Returns best match.

| Param | Type | Default | Description |
|---|---|---|---|
| `cnpj` | `str` | `""` | Company CNPJ (formatted or numeric) |
| `cd_cvm` | `str` | `""` | CVM internal code (e.g., "9512") |
| `name` | `str` | `""` | Company name or fragment |
| `full` | `bool` | `false` | Return all 46 columns |

### `mode="search"`
Search companies with multiple filters.

| Param | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | `""` | Name fragment |
| `setor` | `str` | `""` | Sector fragment |
| `sit` | `str` | `""` | Registration status (ATIVO, CANCELADA) |
| `controle` | `str` | `""` | Control type (PRIVADO, ESTATAL) |
| `uf` | `str` | `""` | State code (SP, RJ, MG) |
| `active_only` | `bool` | `true` | Filter to SIT='ATIVO' |
| `limit` | `int` | `20` | Max results |

### `mode="sectors"`
List all distinct sectors with company counts (no params).

## Tool Invocation

```python
data_source(domain="cvm", sub_domain="cad", mode="sync")
data_source(domain="cvm", sub_domain="cad", mode="lookup", params='{"cnpj":"33000167000101"}')
data_source(domain="cvm", sub_domain="cad", mode="lookup", params='{"cd_cvm":"9512"}')
data_source(domain="cvm", sub_domain="cad", mode="search", params='{"setor":"Energia"}')
data_source(domain="cvm", sub_domain="cad", mode="sectors")
```

## Return Shapes

- `sync`: `{status, rows, size_kb, synced_at}` (or `{status: "skipped"}`)
- `status`: `{status, form, path, db_size_mb, total_companies, active, cancelled, last_sync, top_sectors, market_types}`
- `lookup`: `{status: "ok", company: {...}}` or `{status: "multiple", matches: [...]}`
- `search`: `{status, total_matches, returned, companies: [...]}`
- `sectors`: `{status, sectors: [{setor, count}], total}`

---

*Last updated: 2026-07-23 (v1.0).*
