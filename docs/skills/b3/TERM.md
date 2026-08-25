<- Back to [B3 Skills](../B3.md)

# Term Skill

B3 term (a termo) contracts dashboard. Queries the `cotahist_derivatives` table
(same DB as equities + options) for term contract data (BDI 26/74), and falls
back to the **EQUITY FORWARD** snapshot from the new b3.api
(`derivatives.db` + `instruments.db`) when COTAHIST has no term data for a
stock (which is always — B3 routes stock term to the BTC, Balcão Organizado).

## Quick Start

```
skill(domain="b3", sub_domain="term", mode="dashboard", params='{"ticker":"PETR4"}')
```

## Configuration

- Required sources: `["cotahist", "b3-api-derivatives", "b3-api-instruments"]`
  - `cotahist` — populates `cotahist_derivatives` (BDI 26/74) during the
    standard COTAHIST sync. Used for index term (IBOV futures, BDI 74).
  - `b3-api-derivatives` — DerivativesOpenPosition CSV bulk download
    (EQUITY FORWARD snapshot for stock term fallback).
  - `b3-api-instruments` — InstrumentsConsolidated CSV (company name, ISIN,
    security category join for the forward snapshot).

## Forward-data fallback (v2)

When COTAHIST has no term data for a stock (BDI 26 = 0 rows — always, since
B3 routes stock term to the BTC), the dashboard queries
`data_sources.b3.api.query_engine.forward_positions(ticker)`:

1. Constructs the forward ticker: `{TICKER}T` (e.g. `PETR4` → `PETR4T`).
2. Queries `derivatives.db` `WHERE TckrSymb = 'PETR4T' AND SgmtNm = 'EQUITY FORWARD'`.
3. Joins `instruments.db` on `TckrSymb` for company name (`CrpnNm`), ISIN,
   security category (`SctyCtgyNm`), specification (`SpcfctnCd`).
4. Computes `forward_price_per_share = FwdPric / CurQty`.

The dashboard then shows, per tab:

- **Contratos Ativos**: forward contract snapshot KPI table + spot price
  snapshot (last 5 closes) + forward-vs-spot spread row.
- **Spread Termo vs Spot**: 1-row comparison table (forward vs spot +
  spread) + spot price chart (90 days, as reference).
- **Volume Histórico**: open position details table (OI, total quantity,
  forward price) + info text explaining this is a daily snapshot (the BTC
  doesn't publish daily term volume).

If `derivatives.db` is not synced, the dashboard falls back to the legacy
spot-price-only display with a note explaining how to enable the forward
fallback (`data_source(domain="b3", sub_domain="api", mode="sync", ...)`).

## Subfile Directory

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](term/ARCHITECTURE.md) | File map, data flow, query inventory |
| [API.md](term/API.md) | Dashboard mode signature, response shape |
| [CHANGELOG.md](term/CHANGELOG.md) | Version history |
| [INSTRUCTIONS.md](term/INSTRUCTIONS.md) | AI editing rules |
| [ROADMAP.md](term/ROADMAP.md) | Backlog + future features |
