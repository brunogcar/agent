<- Back to [CVM Skills](../../)

# 🏗️ Architecture — shareholders skill

## Purpose

Combines two CVM data sources into a single shareholder/equity view:

| Source | What it provides |
|--------|-----------------|
| FRE `posicao_acionaria` | Named shareholders + ownership % (ON/PN/total), controlling status |
| FRE `distribuicao_capital` | Free float %, shareholder counts (PF/PJ/inst) |
| DFP BPP 2.03.* | Equity structure in BRL (capital, reservas, minority) over N periods |

## Why a skill (not just data_source)?

The legacy `cvm_shareholders` skill only had aggregate equity amounts (BPP). The
real value is **named shareholders with ownership %** — which lives in FRE, not
DFP. This skill combines both into one queryable view.

## Data Flow

```
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')
  │
  ▼  shareholders mode → FRE.query_engine.shareholders(company="PETR4")
  │    → resolve_company("PETR4") → bridge → CNPJ → FRE posicao_acionaria
  │
  ▼  equity_structure mode → DFP.connect_dfp + resolve_company + BPP 2.03.* query
  │    → resolve_company("PETR4") → bridge → empresa_ids → contas WHERE codigo LIKE '2.03.%'
  │
  ▼  summary mode → calls shareholders + free_float + equity_structure
```

## Modes

| Mode | Source | Returns |
|------|--------|---------|
| `shareholders` | FRE | Named shareholders + ownership % (ON/PN/total) |
| `free_float` | FRE | Free float %, shareholder counts |
| `equity_structure` | DFP | Equity breakdown in BRL over N periods |
| `summary` | FRE + DFP | Top shareholders + free float + latest equity total |

## Resolution

All modes accept `company` (B3 ticker, name fragment, or CNPJ). The underlying
data_source query engines call `resolve_company()` with `auto_sync=True`, so
the first query for a new ticker auto-syncs the bridge transparently.

## No Sync

This skill is read-only. It assumes `fre.db` + `dfp.db` are already synced.
If they're not, queries return `not_synced` / `not_found`.

## File Layout

```
skills/cvm/shareholders/
├── __init__.py        # Manifest + route (4 modes)
└── shareholders.py    # Logic: delegates to FRE + DFP query engines
```

---

*Last updated: 2026-07-23 (v1.0).*
