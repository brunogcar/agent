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
| `dividends`  | `memory_db/ddm/dividends.db`             | DDM dividends agenda — single flat table of upcoming + historical dividend events (ticker \| tipo \| value \| record_date \| ex_date \| payment_date). Mirrors the juros/poupanca single-page sync pattern. |

### Per-subdomain differences

| Aspect                | `inflation`                         | `juros`                                       | `poupanca`                                            | `acoes`                                                | `focus`                                                  | `fluxo`                                                  | `dividends`                                          |
| --------------------- | ----------------------------------- | --------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------- | -------------------------------------------------------- | ---------------------------------------------------- |
| Tables per page       | 2 (matrix + historical)             | 1 (matrix only)                               | 1 (matrix only)                                       | 1 (flat stocks list)                                   | 4 (one per target year)                                  | 1 (daily flow by investor type)                          | 1 (dividend agenda)                                  |
| "Ano" column          | Yes (year acumulado)                | No (daily rates, not cumulative)              | No (monthly yield, not cumulative)                    | N/A (no matrix)                                        | N/A (years are separate tables, not columns)             | N/A (daily series, not cumulative)                       | N/A (event list, not cumulative)                     |
| Historical series     | Parsed directly from HTML table 2   | DERIVED from matrix (AVERAGE)                 | DERIVED from matrix (SUM)                             | None (single snapshot, no history)                     | None (single snapshot per ref_date; history via PK)      | None (full daily series is the only table)               | None (events are the series itself)                  |
| Numeric fields        | `month_value`, `year_acumulado`, `acumulado_12m` | `month_value`, `media_no_ano`, `media_12m`     | `month_value`, `acumulado_no_ano`, `acumulado_12m`    | `negocios`, `last_price`, `variation`                  | `four_weeks_ago`, `one_week_ago`, `today` (TEXT)         | `estrangeiro`, `institucional`, `pessoa_fisica`, `inst_fin`, `outros` | `value`, `record_date`, `ex_date`, `payment_date`    |
| Unit                  | `%` (monthly variation)             | `% a.a.` (annualized daily rate)              | `%` (monthly yield)                                   | `R$` (price) + `%` (variation)                         | Mixed: `%` + `R$` + int (preserved as strings)           | `R$ mi` (millions of R$, parsed to REAL float)           | `R$` + `%` (per share / yield)                        |
| Indices               | IGP-M, IPCA, INPC                   | Selic, Meta Selic, CDI                        | Poupanca                                              | (no catalog — flat list of ~380 stocks)                | 12 indicators (IPCA, PIB Total, Cambio, ...)             | 5 investor-type columns                                  | (no catalog — one row per event per ticker)          |
| Catalog category      | `Inflacao`                          | `Juros`                                       | `Renda Fixa`                                          | (no catalog)                                           | (no catalog — 4 year-tables)                             | (no catalog — single daily table)                        | (no catalog — single event table)                    |
| Pre-sort              | None (matrix is year × month)       | None                                          | None                                                  | Negócios DESC (DDM pre-sorts the page)                 | Indicator order (DDM-controlled)                         | Date ASC                                                 | None (rows in DDM page order)                        |
| Primary key           | `(slug, ref_date)`                  | `(slug, ref_date)`                            | `(slug, ref_date)`                                    | `ticker` (single row per stock)                        | `(year, indicator, ref_date)` (history-aware)            | `data` (single row per trading day)                      | `(ticker, record_date, tipo)`                        |
| DB file location      | `memory_db/ddm/inflation/inflation.db` | `memory_db/ddm/juros.db`                   | `memory_db/ddm/poupanca.db`                           | `memory_db/ddm/acoes.db`                               | `memory_db/ddm/focus.db`                                 | `memory_db/ddm/fluxo.db`                                 | `memory_db/ddm/dividends.db`                         |

All 7 DB files live under `memory_db/ddm/` (the inflation DB is in a
sub-folder; juros, poupanca, acoes, focus, fluxo, and dividends sit directly
in the `ddm/` folder side-by-side).

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
  - `sub_domain="dividends"` → route directly to the dividends sub-domain.

Auto-discovery is filesystem-driven — dropping a new sub-domain directory
(`funds/`) into `data_sources/ddm/` is enough to make it available via
`data_source(domain="ddm", sub_domain="...", ...)`. Directories prefixed
with `_` (e.g. `_base/`, `_parsers.py`) are auto-skipped by the discovery
loop — they provide shared infrastructure, not sub-domains.

### Shared infrastructure (`_base/` package — Phase 3 C1)

The 7 DDM sub-domains share ~80% of their catalog / fetcher / sync_engine /
status_reporter / route code (HTTP cache, concurrency, DELETE+INSERT idempotency,
DB-connect scaffold, route dispatcher). As of Phase 3 Commit 1, this shared
code lives in `data_sources/ddm/_base/` (6 modules). Each sub-domain now
subclasses `BaseDDMCatalog`, `BaseDDMFetcher`, `BaseDDMSyncEngine`,
`BaseDDMStatusReporter` (and the domain hub subclasses `BaseDDMRoute`) instead
of duplicating the scaffold. Per-source code is now thin: source-specific
constants (URL, schema, catalog) + thin re-exports of the base class.

See [`ddm/_base/ARCHITECTURE.md`](ddm/_base/ARCHITECTURE.md) for the canonical
map of the shared package.

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

- [`ddm/_base/ARCHITECTURE.md`](ddm/_base/ARCHITECTURE.md) — Phase 3 C1 shared
  infrastructure package (6 modules: catalog_base, fetcher_base, sync_base,
  status_base, route_base, `__init__`).
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
- [`ddm/dividends/API.md`](ddm/dividends/API.md) — dividends API.
- [`ddm/dividends/ARCHITECTURE.md`](ddm/dividends/ARCHITECTURE.md) —
  dividends file map and DB schema (single dividend-event table).
