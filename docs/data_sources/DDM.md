# DDM (Dados de Mercado) Data Source

Domain: **`ddm`**
Source site: <https://www.dadosdemercado.com.br>
Auth: **none** (public HTML, no JS, no API tokens)
Pattern: subdomain (mirrors `bcb/sgs` + `bcb/focus`)

## Overview

DDM is a Brazilian financial-data aggregator that publishes market data on
server-rendered HTML pages. There is no JSON API and no auth — every page is
a static HTML document that can be scraped with regex (no BeautifulSoup
dependency, no headless browser).

Each indicator page exposes two HTML tables:

1. **Monthly matrix** (`id="index-values"`) — year rows × Jan–Dez + "Ano"
   columns. Cells carry the canonical numeric value in a `data-value`
   attribute (`<td data-value="0.41">0,41%</td>`); missing months render as
   `--`.
2. **Historical monthly** (class `normal-table`) — DESC rows with the
   columns: `Mês/Ano` | `Índice do mês (%)` | `Acumulado no ano (%)` |
   `Acumulado 12 meses (%)`. The date column uses Portuguese month
   abbreviations (`Jul/2026`); the numeric columns use Brazilian comma
   decimals (`-1,16`).

## Sub-domains

| Sub-domain   | DB path                                  | Description                                            |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `inflation`  | `memory_db/ddm/inflation/inflation.db`   | Brazilian inflation indices (IGP-M, IPCA, INPC).       |

### Planned (not yet built)

| Sub-domain | DB path                                | Description                                                  |
| ---------- | -------------------------------------- | ------------------------------------------------------------ |
| `stocks`   | `memory_db/ddm/stocks/stocks.db`       | Equity snapshots / price history from DDM.                   |
| `funds`    | `memory_db/ddm/funds/funds.db`         | Investment fund quotes / portfolios.                         |

## Domain hub

`data_sources/ddm/__init__.py` mirrors `data_sources/bcb/__init__.py`:

- `_discover_sub_domains()` scans `data_sources/ddm/` for sub-directories
  with `__init__.py` + `MANIFEST` + `route()`.
- `route(sub_domain, mode, **kwargs)` dispatches to the matched sub-domain.
  - `sub_domain=""` → auto-select if only one sub-domain exists, error
    otherwise.
  - `sub_domain="all"` → run `mode` on every sub-domain with
    `include_in_all=True`.
  - `sub_domain="inflation"` → route directly to the inflation sub-domain.

Auto-discovery is filesystem-driven — dropping a new sub-domain directory
(`stocks/`, `funds/`) into `data_sources/ddm/` is enough to make it
available via `data_source(domain="ddm", sub_domain="...", ...)`.

## Usage

```python
from data_sources.ddm import route as ddm

# Sync every inflation index (concurrent, 3 workers).
ddm(sub_domain="inflation", mode="sync_all")

# Query the latest IPCA observation.
ddm(sub_domain="inflation", mode="last", slug="ipca")

# Get the monthly matrix for IGP-M.
ddm(sub_domain="inflation", mode="matrix", slug="igp-m")
```

See [`ddm/inflation/API.md`](ddm/inflation/API.md) for the full 8-mode API
and [`ddm/inflation/ARCHITECTURE.md`](ddm/inflation/ARCHITECTURE.md) for the
file map and DB schema.
