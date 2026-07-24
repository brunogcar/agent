<- Back to [BRIDGE Overview](../BRIDGE.md)

# 📖 API Reference

## data_source(domain="cvm", sub_domain="bridge", ...)

### mode="sync"

Bridge one or more tickers: ensure dividends data (fetches from API if needed),
join with CAD for CNPJ + names, and upsert into bridge.db.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| ticker | str | one of ticker/tickers | Single ticker e.g. `"PETR4"`. Ignored if `tickers` given. |
| tickers | list[str] | one of ticker/tickers | Multiple tickers. Takes precedence over `ticker`. |
| force | bool | no | Re-fetch dividends + re-join CAD even if already bridged. Default: `false`. |

**Single ticker** returns the per-ticker result:
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "cd_cvm": "9512",
  "cnpj": "33000167000101",
  "denom_social": "PETROLEO BRASILEIRO S.A. PETROBRAS",
  "trading_name": "PETROBRAS",
  "sit": "ATIVO"
}
```

**Multiple tickers** returns an aggregate:
```json
{
  "status": "ok",
  "total": 3,
  "linked": 2,
  "skipped": 1,
  "errors": 0,
  "results": {
    "PETR4": {"status": "ok", "cd_cvm": "9512", "cnpj": "33000167000101"},
    "VALE3": {"status": "ok", "cd_cvm": "4170", "cnpj": "33592510000154"},
    "ITUB4": {"status": "skipped", "reason": "already in bridge"}
  }
}
```

**Action values** (in sync_log): `linked` (full success), `no_cvm` (dividends
ok but no codeCVM), `no_cad` (cd_cvm not in cad.db — partial entry stored),
`error`.

**Examples:**
```
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"tickers":["PETR4","VALE3","ITUB4"]}')
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4","force":true}')
```

---

### mode="status"

Show bridge.db stats. No params.

```json
{
  "status": "ok",
  "path": "/path/to/bridge.db",
  "db_size_kb": 12.5,
  "total_tickers": 5,
  "with_cnpj": 4,
  "with_cd_cvm": 5,
  "cnpj_coverage_pct": 80.0,
  "log": {"linked": 4, "no_cad": 1},
  "last_sync": {"synced_at": "2026-07-23T...", "ticker": "VALE3", "action": "linked"}
}
```

---

### mode="lookup"

Resolve a ticker, CNPJ, or CD_CVM to the full bridge identity record.

| Param | Type | Description |
|-------|------|-------------|
| ticker | str | B3 ticker e.g. `"PETR4"` |
| cnpj | str | 14-digit CNPJ (formatted or numeric) |
| cd_cvm | str | CVM code e.g. `"9512"` |

Provide exactly one. Returns the full `ticker_map` row:

```json
{
  "status": "ok",
  "ticker": "PETR4",
  "issuing": "PETR",
  "cd_cvm": "9512",
  "trading_name": "PETROBRAS",
  "cnpj": "33000167000101",
  "denom_social": "PETROLEO BRASILEIRO S.A. PETROBRAS",
  "denom_comerc": "PETROBRAS",
  "sit": "ATIVO",
  "setor_ativ": "Petróleo",
  "tp_merc": "Bolsa",
  "synced_at": "2026-07-23T..."
}
```

---

### mode="resolve"

Fuzzy name search across `trading_name`, `denom_social`, `denom_comerc`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| query | str | — | Name fragment (≥ 2 chars) |
| limit | int | 10 | Max results |

```json
{
  "status": "ok",
  "query": "petro",
  "count": 1,
  "matches": [{"ticker": "PETR4", "cd_cvm": "9512", "cnpj": "33000167000101", ...}]
}
```

---

## Internal: _bridge.py resolve_company()

The bridge is consumed by `data_sources/cvm/_bridge.py:resolve_company()`,
which all CVM sub-domains use to accept ticker input:

```
resolve_company(conn, "PETR4")
  → _resolve_via_bridge("PETR4") → (cnpj, cd_cvm) from ticker_map
  → 1a. try cnpj → empresas WHERE cnpj=?   (preferred)
  → 1b. fallback cd_cvm → empresas WHERE cd_cvm=?  (if cnpj empty)
  → return (empresa_ids, company_name)
```

This means after bridging a ticker, you can query DFP/ITR/FRE/IPE directly
with the ticker:

```
data_source(domain="cvm", sub_domain="dfp", mode="query", params='{"company":"PETR4"}')
```

---

*Last updated: 2026-07-23 (v1.0).*
