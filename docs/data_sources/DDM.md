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

The focus page (Boletim Focus) is FOUR yearly tables (one per target year:
2026, 2027, 2028, 2029), each with 6 columns: Indicador | Há 4 semanas |
1 sem | Hoje | Comp. | Resp. Values are PT-BR strings preserved verbatim
("5,151%", "R$ 5,200"); the Comp. column uses Unicode glyphs (▲/▼/=)
normalized to "up"/"down"/"flat". The endpoint is CloudFront-protected —
the fetcher sends the full Chrome 127 browser header set to bypass the
WAF rules.

The fluxo page (B3 investment flow) is ONE table of daily net inflow /
outflow by investor type (~247 rows = ~1 year of trading days), with 6
columns: Data | Estrangeiro | Institucional | Pessoa física | Inst.
Financeira | Outros. Values use PT-BR formatting with the "mi" suffix
(millions of R$): "-1.582,35 mi" = -1582.35 million R$. Values are
parsed to REAL (floats in millions R$) at the fetcher boundary, dates
are normalized to YYYY-MM-DD. The endpoint is CloudFront-protected —
full Chrome 127 browser headers (same as focus).

## Sub-domains

| Sub-domain   | DB path                                  | Description                                            |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `inflation`  | `memory_db/ddm/inflation/inflation.db`   | Brazilian inflation indices (IGP-M, IPCA, INPC).       |
| `juros`      | `memory_db/ddm/juros.db`                 | Brazilian interest-rate indices (Selic, Meta Selic, CDI). Uses AVERAGE for derived `media_no_ano` + `media_12m`. |
| `poupanca`   | `memory_db/ddm/poupanca.db`              | Brazilian savings-account monthly yield (Poupanca). Uses SUM for derived `acumulado_no_ano` + `acumulado_12m`. |
| `acoes`      | `memory_db/ddm/acoes.db`                 | B3 listed stocks (PETR4, VALE3, ...) — flat snapshot table (Ticker \| Nome \| Negócios \| Última \| Variação). Pre-sorted by Negócios DESC. |
| `focus`      | `memory_db/ddm/focus.db`                 | Boletim Focus (market expectations survey). 4 yearly tables (2026-2029) × 12 indicators. Values stored as PT-BR strings verbatim. CloudFront-protected (full Chrome 127 browser headers). |
| `fluxo`      | `memory_db/ddm/fluxo.db`                 | B3 investment flow (daily net inflow / outflow by investor type). 1 table × ~247 daily rows × 6 columns (Data \| Estrangeiro \| Institucional \| Pessoa física \| Inst. Financeira \| Outros). Values parsed to REAL (millions R$); dates normalized to YYYY-MM-DD. CloudFront-protected (full Chrome 127 browser headers). |

### Per-subdomain differences

| Aspect                | `inflation`                         | `juros`                                       | `poupanca`                                            | `acoes`                                                | `focus`                                                  |
| --------------------- | ----------------------------------- | --------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| Tables per page       | 2 (matrix + historical)             | 1 (matrix only)                               | 1 (matrix only)                                       | 1 (flat stocks list)                                   | 4 (one per target year)                                  |
| "Ano" column          | Yes (year acumulado)                | No (daily rates, not cumulative)              | No (monthly yield, not cumulative)                    | N/A (no matrix)                                        | N/A (years are separate tables, not columns)             |
| Historical series     | Parsed directly from HTML table 2   | DERIVED from matrix (AVERAGE)                 | DERIVED from matrix (SUM)                             | None (single snapshot, no history)                     | None (single snapshot per ref_date; history via PK)      |
| Numeric fields        | `month_value`, `year_acumulado`, `acumulado_12m` | `month_value`, `media_no_ano`, `media_12m`     | `month_value`, `acumulado_no_ano`, `acumulado_12m`    | `negocios`, `last_price`, `variation`                  | `four_weeks_ago`, `one_week_ago`, `today` (TEXT)         |
| Unit                  | `%` (monthly variation)             | `% a.a.` (annualized daily rate)              | `%` (monthly yield)                                   | `R$` (price) + `%` (variation)                         | Mixed: `%` + `R$` + int (preserved as strings)           |
| Indices               | IGP-M, IPCA, INPC                   | Selic, Meta Selic, CDI                        | Poupanca                                              | (no catalog — flat list of ~380 stocks)                | 12 indicators (IPCA, PIB Total, Cambio, ...)             |
| Catalog category      | `Inflacao`                          | `Juros`                                       | `Renda Fixa`                                          | (no catalog)                                           | (no catalog — 4 year-tables)                             |
| Pre-sort              | None (matrix is year × month)       | None                                          | None                                                  | Negócios DESC (DDM pre-sorts the page)                 | Indicator order (DDM-controlled)                         |
| Primary key           | `(slug, ref_date)`                  | `(slug, ref_date)`                            | `(slug, ref_date)`                                    | `ticker` (single row per stock)                        | `(year, indicator, ref_date)` (history-aware)            |
| DB file location      | `memory_db/ddm/inflation/inflation.db` | `memory_db/ddm/juros.db`                   | `memory_db/ddm/poupanca.db`                           | `memory_db/ddm/acoes.db`                               | `memory_db/ddm/focus.db`                                 |

All 6 DB files live under `memory_db/ddm/` (the inflation DB is in a
sub-folder; juros, poupanca, acoes, focus, and fluxo sit directly in
the `ddm/` folder side-by-side).

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
  - `sub_domain="focus"` → route directly to the focus sub-domain.
  - `sub_domain="fluxo"` → route directly to the fluxo sub-domain.

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

# Sync the boletim-focus page (single HTTP call, CloudFront-protected).
ddm(sub_domain="focus", mode="sync_all")

# Sync the fluxo page (single HTTP call, CloudFront-protected, ~247 daily rows).
ddm(sub_domain="fluxo", mode="sync_all")

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

# Get the full Focus snapshot (4 years x 12 indicators).
ddm(sub_domain="focus", mode="focus_data")

# Get all years for a specific indicator.
ddm(sub_domain="focus", mode="indicator", indicator="IPCA")

# Get all fluxo observations (daily series, ASC by date).
ddm(sub_domain="fluxo", mode="fluxo_data")

# Get the latest trading day's flow.
ddm(sub_domain="fluxo", mode="last")

# Monthly cumulative sum for one investor.
ddm(sub_domain="fluxo", mode="fluxo_by_investor", investor="estrangeiro")
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
- [`ddm/focus/API.md`](ddm/focus/API.md) — 8-mode focus API.
- [`ddm/focus/ARCHITECTURE.md`](ddm/focus/ARCHITECTURE.md) —
  focus file map and DB schema (4 yearly tables, CloudFront-protected).
- [`ddm/fluxo/API.md`](ddm/fluxo/API.md) — 8-mode fluxo API.
- [`ddm/fluxo/ARCHITECTURE.md`](ddm/fluxo/ARCHITECTURE.md) —
  fluxo file map and DB schema (1 daily table, CloudFront-protected).
