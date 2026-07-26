<- Back to [CGVN Overview](../CGVN.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download + parse CGVN data from CVM into cgvn.db.

| Param | Type | Default | Description |
|---|---|---|---|
| `year` | `int` | current year | Single year to sync |
| `force` | `bool` | `false` | Re-download even if already synced today |
| `full_history` | `bool` | `false` | Sync all years from 2018 to current |

### `mode="query"`
Query governance practices by company (CNPJ/ticker/name).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name fragment, or CNPJ |

### `mode="status"`
Show cgvn.db stats (no params).

## Tool Invocation

```python
data_source(domain="cvm", sub_domain="cgvn", mode="sync", params='{"year":2025}')
data_source(domain="cvm", sub_domain="cgvn", mode="sync", params='{"full_history":true}')
data_source(domain="cvm", sub_domain="cgvn", mode="query", params='{"company":"PETR4"}')
data_source(domain="cvm", sub_domain="cgvn", mode="status")
```

## Sync Commands

```powershell
# Sync single year
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cgvn.sync_engine import sync; print(sync(year=2025))"

# Sync full history
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.cvm.cgvn.sync_engine import sync; print(sync(full_history=True))"
```

---

*Last updated: 2026-07-25 (v1.0).*
