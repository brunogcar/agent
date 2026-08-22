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

Each indicator page exposes one or two HTML tables:

1. **Monthly matrix** (`id="index-values"`) — year rows × Jan–Dez columns
   (and possibly an "Ano" acumulado column for inflation pages only).
   Cells carry the canonical numeric value in a `data-value` attribute
   (`<td data-value="0.41">0,41%</td>`); missing months render as `--`.
2. **Historical monthly** (class `normal-table`, inflation pages only) —
   DESC rows with the columns: `Mês/Ano` | `Índice do mês (%)` |
   `Acumulado no ano (%)` | `Acumulado 12 meses (%)`. The date column
   uses Portuguese month abbreviations (`Jul/2026`); the numeric columns
   use Brazilian comma decimals (`-1,16`).

Juros + poupanca pages ship ONLY the matrix table (no historical table, no
"Ano" column). The historical series is DERIVED from the matrix at parse
time. Inflation pages ship BOTH tables (matrix + historical).

The acoes page is a SINGLE flat table of stock snapshots (no per-index
slugs, no historical series, no matrix) — different shape, same domain.

## Sub-domains

| Sub-domain   | DB path                                  | Description                                            |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `inflation`  | `memory_db/ddm/inflation/inflation.db`   | Brazilian inflation indices (IGP-M, IPCA, INPC).       |
| `juros`      | `memory_db/ddm/juros.db`                 | Brazilian interest-rate indices (Selic, Meta Selic, CDI). Uses AVERAGE for derived `media_no_ano` + `media_12m`. |
| `poupanca`   | `memory_db/ddm/poupanca.db`              | Brazilian savings-account monthly yield (Poupanca). Uses SUM for derived `acumulado_no_ano` + `acumulado_12m`. |
| `acoes`      | `memory_db/ddm/acoes.db`                 | B3 listed stocks (PETR4, VALE3, ...) — flat snapshot table (Ticker \| Nome \| Negócios \| Última \| Variação). Pre-sorted by Negócios DESC. |

### Per-subdomain differences

| Aspect                | `inflation`                         | `juros`                                       | `poupanca`                                            | `acoes`                                                |
| --------------------- | ----------------------------------- | --------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| Tables per page       | 2 (matrix + historical)             | 1 (matrix only)                               | 1 (matrix only)                                       | 1 (flat stocks list)                                   |
| "Ano" column          | Yes (year acumulado)                | No (daily rates, not cumulative)              | No (monthly yield, not cumulative)                    | N/A (no matrix)                                        |
| Historical series     | Parsed directly from HTML table 2   | DERIVED from matrix (AVERAGE)                 | DERIVED from matrix (SUM)                             | None (single snapshot, no history)                     |
| Numeric fields        | `month_value`, `year_acumulado`, `acumulado_12m` | `month_value`, `media_no_ano`, `media_12m`     | `month_value`, `acumulado_no_ano`, `acumulado_12m`    | `negocios`, `last_price`, `variation`                  |
| Unit                  | `%` (monthly variation)             | `% a.a.` (annualized daily rate)              | `%` (monthly yield)                                   | `R$` (price) + `%` (variation)                         |
| Indices               | IGP-M, IPCA, INPC                   | Selic, Meta Selic, CDI                        | Poupanca                                              | (no catalog — flat list of ~380 stocks)                |
| Catalog category      | `Inflacao`                          | `Juros`                                       | `Renda Fixa`                                          | (no catalog)                                           |
| Pre-sort              | None (matrix is year × month)       | None                                          | None                                                  | Negócios DESC (DDM pre-sorts the page)                 |
| Primary key           | `(slug, ref_date)`                  | `(slug, ref_date)`                            | `(slug, ref_date)`                                    | `ticker` (single row per stock)                        |
| DB file location      | `memory_db/ddm/inflation/inflation.db` | `memory_db/ddm/juros.db`                   | `memory_db/ddm/poupanca.db`                           | `memory_db/ddm/acoes.db`                               |

All 4 DB files live under `memory_db/ddm/` (the inflation DB is in a
sub-folder; juros, poupanca, and acoes sit directly in the `ddm/` folder
side-by-side).

### Planned (not yet built)

| Sub-domain | DB path                                | Description                                                  |
| ---------- | -------------------------------------- | ------------------------------------------------------------ |
| `funds`    | `memory_db/ddm/funds.db`               | Investment fund quotes / portfolios.                         |

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
  - `sub_domain="juros"` → route directly to the juros sub-domain.
  - `sub_domain="poupanca"` → route directly to the poupanca sub-domain.
  - `sub_domain="acoes"` → route directly to the acoes sub-domain.

Auto-discovery is filesystem-driven — dropping a new sub-domain directory
(`funds/`) into `data_sources/ddm/` is enough to make it available via
`data_source(domain="ddm", sub_domain="...", ...)`.

## Usage

```python
from data_sources.ddm import route as ddm

# Sync every inflation index (concurrent, 3 workers).
ddm(sub_domain="inflation", mode="sync_all")

# Sync every juros index (concurrent, 3 workers).
ddm(sub_domain="juros", mode="sync_all")

# Sync the poupanca index (single HTTP call).
ddm(sub_domain="poupanca", mode="sync_all")

# Sync the acoes page (single HTTP call, ~380 stocks).
ddm(sub_domain="acoes", mode="sync_all")

# Query the latest IPCA observation.
ddm(sub_domain="inflation", mode="last", slug="ipca")

# Get the monthly matrix for IGP-M.
ddm(sub_domain="inflation", mode="matrix", slug="igp-m")

# Get the latest poupanca yield.
ddm(sub_domain="poupanca", mode="last", slug="poupanca")

# List all B3 stocks sorted by variation DESC.
ddm(sub_domain="acoes", mode="stocks", order_by="variation", direction="desc")

# Get the snapshot for a specific ticker.
ddm(sub_domain="acoes", mode="ticker", ticker="PETR4")
```

## See also

- [`ddm/inflation/API.md`](ddm/inflation/API.md) — 8-mode inflation API.
- [`ddm/inflation/ARCHITECTURE.md`](ddm/inflation/ARCHITECTURE.md) —
  inflation file map and DB schema.
- [`ddm/juros/API.md`](ddm/juros/API.md) — 8-mode juros API.
- [`ddm/juros/ARCHITECTURE.md`](ddm/juros/ARCHITECTURE.md) —
  juros file map and DB schema (AVERAGE-derived).
- [`ddm/poupanca/API.md`](ddm/poupanca/API.md) — 8-mode poupanca API.
- [`ddm/poupanca/ARCHITECTURE.md`](ddm/poupanca/ARCHITECTURE.md) —
  poupanca file map and DB schema (SUM-derived).
- [`ddm/acoes/API.md`](ddm/acoes/API.md) — 8-mode acoes API.
- [`ddm/acoes/ARCHITECTURE.md`](ddm/acoes/ARCHITECTURE.md) —
  acoes file map and DB schema (flat stocks table).
