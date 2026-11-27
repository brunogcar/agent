<- Back to [WebUI Overview](../WEBUI.md)

# 🔌 WebUI API Reference

> All HTTP routes exposed by the WebUI. Routes are prefixed `/webui` (HTML pages) or `/api/webui` (JSON/SSE). The existing gateway routes (`/chat`, `/task`, `/ws`, `/health`) are also mounted on the same app.

Last updated: 2026-11-26 (v1.27 — the Ferramentas main tab + the Comparação tool routes; v1.22.3 — the whole money roadmap: corporate actions, proventos/YOC, TWR/XIRR vs CDI/IBOV, allocation/alerts/what-if, ledger pagination+undo+backup, engine perf; v1.22.2 — nota de corretagem PDF import + IR/DARF helper; v1.21 — directory route, shorts/bonificações, overview by user; v1.21 carteira/portfolio routes; v1.20 system log + settings; v1.7 adapter dispatch + pre-flight)

---

## HTML Page Routes

Server-rendered Jinja2 pages. These return full HTML documents (extending `base.html`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/webui/` | Dashboard (home — market overview, no ticker required) |
| GET | `/webui/company/{ticker}` | Company overview page (default tab: visao_geral) |
| GET | `/webui/company/{ticker}/{tab}` | Company tab page (tab: visao_geral, preco, financials, valuation, proventos) |
| GET | `/webui/macro` | Macro indicators page |
| GET | `/webui/mercado` | Mercado page (DDM families) |
| GET | `/webui/carteira` | Carteira (portfolio) page — users → accounts → transactions → PM positions [v1.21] |
| GET | `/webui/tools` | Ferramentas page — analysis tools (Comparação + Screener) [v1.27, v1.28] |
| GET | `/webui/sync` | Data sync status page |
| GET | `/webui/settings` | Settings page (schema-driven form [v1.20]) |
| GET | `/` | Redirects to `/webui/` |

### Query Parameters

All HTML routes accept:
- `?theme=<dark|light>` — override theme for this request (sets cookie)
- `?lang=<pt-BR|en-US>` — override language for this request (sets cookie)

---

## JSON API Routes

Return JSON. Used by Chart.js and programmatic clients.

### `GET /api/webui/home`

[v1.19] **The Painel landing payload** — one call, one screen, THREE separate sets (v1.28.3, per the user's review): **(1) the macro KPI cards** (`kpis`: `home.kpis` selects which catalog entries show and in what order; the 23-key catalog [v1.28.3 — the families complete] — the SGS reads (Selic/CDI a.a., Meta Selic, TR), the **Juros "mercado" twins** (Selic/CDI/Meta Selic mercado mês/12m [ddm-juros] — "slightly different" from the SGS reads, exactly why both live in the catalog), the **ano acumulados** (IPCA/IGP-M/INPC — ano [ddm-inflation, `year_acumulado`] + Poupança — ano [ddm-poupanca, `acumulado_no_ano`]), the monthly/12m reads (IPCA/IGP-M mês/12m [sgs], INPC/Poupança mês/12m [ddm]); per-KPI degradation: a down source renders its cards `"-"` but never hides the others; the family engines are read ONLY when one of their KPIs is enabled — and the IPCA/IGP-M (mês)/(12m) cards still ride SGS, only their — ano cards read ddm-inflation) + **(2) the ticker KPI cards** (`ticker_cards`: one per `home.ticker_kpis` entry — ANY share-like instrument: ações, FIIs, ETFs, BDRs; close + signed day % + the 52-week range `high_52`/`low_52` + the 52-week position `pos_52` (0–100) + the day `volume` + **`spark`** — the trailing-52-week close series (≤40 points, `series_52w()`; the chart band's green line, its last point the value's dashed reference line; `null` when the window missed the symbol); the price wears the Ações 22-range palette pill `price: {pill, text, range}` — a symbol the snapshot window missed falls back to `quotes_for()`, a symbol absent everywhere renders degraded with `"—"`/`null`; the card reads in THREE horizontal bands — the header (identity left, price pill + day % right), the full-width 52-week chart with the position bar under it, the stats rows Mín 52 sem (FIRST), Máx 52 sem, Volume (dia) + **(3) the managed ranking cards** (`cards`: `home.cards` selects which boxes show and in what order — Top 10 IBOV/SMLL by weight, quote-enriched; Mais Negócios; Maiores Volumes; Maiores Altas; Maiores Baixas; **Maiores Altas BDR** and **Maiores Quedas BDR** — the *34/35/36 universe under the same 100-trade liquidity gate) + the two catalogs (`kpi_catalog`, 23 keys + `card_catalog`, 8 keys — the ⚙️ Gerenciar Painel box's checkbox lists). **[v1.28.3] The ranking rows are STANDARDIZED — "ticker · info · price · %"**: every row's `value` IS the price and always carries the `price` pill; `extra` carries the card's context (peso on the index cards, negócios, volume on Maiores Volumes) — the NAME rides the tooltip when an extra exists and fills the info slot on the altas/baixas/BDR cards (`extra: null`). Section-scoped degradation: each part fails alone with a PT-BR message naming its sync source. [v1.19] Memoized 60s under a lock (single-flight — concurrent callers coalesce into one `market_snapshot()`, which itself is windowed to the last 10 sessions; the payload only changes on sync — and, [v1.28.3], on a `home.kpis`/`home.ticker_kpis`/`home.cards` save: the memo keys on them).

```json
{
  "status": "ok",
  "kpis": [{"label": "Selic (a.a.)", "value": "13,65%", "tooltip": "…"}],
  "kpi_catalog": [{"key": "selic_aa", "title": "Selic (a.a.)"}, …],
  "ticker_cards": [{"ticker": "BOVA11", "name": "ISHARES BOVA", "kind": "ETF",
                    "value": "R$ 129,35", "variation": "+1,21%",
                    "price": {"pill": "#2563eb", "text": "#fff",
                              "range": "125 ≤ X < 150"},
                    "high_52": "R$ 140,10", "low_52": "R$ 118,30",
                    "pos_52": 51, "spark": [118.30, 121.4, …, 129.35],
                    "volume": "R$ 88,00 mi",
                    "tooltip": "…"}],
  "cards": [
    {"key": "ibov", "title": "IBOV · Top 10", "subtitle": "Maiores pesos — carteira de 05/08/2026",
     "error": null,
     "items": [{"ticker": "VALE3", "name": "VALE", "value": "R$ 34,50",
                "price": {"pill": "#c8e6c9", "text": "#000", "range": "30 ≤ X < 40"},
                "variation": "+1,23%", "extra": {"label": "peso", "text": "10,886%"}}]}
  ],
  "card_catalog": [{"key": "ibov", "title": "IBOV · Top 10"}, …]
}
```
`kpis_note` (optional) carries the SGS degradation message; `variation` is `null` without a previous-session close; `extra` is `null` on the altas/baixas/BDR cards (the client fills the info slot with the NAME); on Maiores Volumes the `value` is the COTAÇÃO (pill'd) and the `extra` carries `{label: "volume", text: "R$ …"}`; `ticker_cards` is `[]` when `home.ticker_kpis` is empty. KPI keys: `selic_aa`/`selic_mercado_mes`/`selic_mercado_12m`/`cdi_aa`/`cdi_mercado_mes`/`cdi_mercado_12m`/`meta_selic`/`meta_selic_mercado_mes`/`meta_selic_mercado_12m`/`tr`/`ipca_mes`/`ipca_ano`/`ipca_12m`/`igpm_mes`/`igpm_ano`/`igpm_12m`/`inpc_mes`/`inpc_ano`/`inpc_12m`/`poupanca_mes`/`poupanca_ano`/`poupanca_12m`/`usd_brl`. Card keys: `ibov`/`smll`/`negocios`/`volumes`/`altas`/`baixas`/`altas_bdr` [v1.28.1]/`baixas_bdr` [v1.28.3]. Rendered by `loadHomeData()` (app.js).

### `GET /api/webui/company/{ticker}/sections/{key}`

[v1.7] **Generic subtab endpoint** — dispatches ANY adapter registered in `webui/adapters/registry.py`. This is the canonical endpoint for new tabs; the per-family endpoints below are stable aliases over the same service methods.

**Parameters:**
- `key`: `"<family>:<sub>"` — one of `valuation:overview|multiples|intrinsic|fundamentals|all`, `proventos:overview|historico|anual`, `preco:cotacao|indicadores|volatilidade|volume|fibonacci`, `financials:overview|demonstracoes`
- `period`: `annual` (default) | `quarterly` — only used by `financials:demonstracoes`
- `periods`: number of periods (default 10 annual / 20 quarterly) — only used by `financials:demonstracoes`

**Response:** a contract payload (`webui/adapters/contract.py`):
```json
{
  "ticker": "PETR4", "status": "ok",
  "kpis": [{"label": "P/L", "value": "6,54", "tooltip": "…"}],
  "sections": [
    {"type": "table", "title": "…", "columns": ["Métrica", "Valor"], "rows": [["…", "…"]]},
    {"type": "chart", "title": "…", "chart_data": {"type": "line", "data": {"labels": […], "datasets": […]}}}
  ]
}
```
Error shape: `{"ticker": "PETR4", "_error": "mensagem PT-BR"}` (HTTP 200 — the client renders the message). Unknown/malformed keys → 404 plain text.

### `GET /api/webui/company/{ticker}/candlestick?range={range}`

Returns OHLCV data + moving averages for the candlestick chart.

**Parameters:**
- `range`: `1M` | `3M` | `6M` | `1A` | `5A` | `10A` | `Tudo` (default: `1A`)

**Response:**
```json
{
  "labels": ["2024-01-02", ...],
  "ohlc": [{"o": 48.0, "h": 49.0, "l": 47.5, "c": 48.5}, ...],
  "body_data": [[47.5, 48.5], ...],
  "ma20": [null, ...],
  "ma50": [null, ...],
  "ma100": [null, ...],
  "ma200": [null, ...],
  "closes": [48.5, ...]
}
```

### `GET /api/webui/company/{ticker}/price-data`

Returns full price data for the Cotação subtab (10Y): snapshot, period returns, annual returns, histogram.

### `GET /api/webui/company/{ticker}/indicators`

Returns technical indicators for the Indicadores subtab (10Y): RSI, MACD, Stochastic, OBV, ADX, CCI, Williams %R.

### `GET /api/webui/company/{ticker}/volatility`

Returns volatility data for the Volatilidade subtab (10Y): Bollinger Bands + rolling vol (20d/60d/252d).

### `GET /api/webui/company/{ticker}/volume`

Returns volume data for the Volume subtab (10Y): volume bars + trade count + contracts + stats.

### `GET /api/webui/company/{ticker}/fibonacci`

Returns Fibonacci data for the Fibonacci subtab (1Y): swing extremes (4w/12w/52w) + levels + trade setups + dividend adjustments.

### `GET /api/webui/company/{ticker}/backtest/meta`

[v1.25; v1.28.1 — the FERRAMENTAS tool's data] The Backtest form catalog — ONE fetch primes the whole interactive form: the 8 strategies (label/description/kind + each one's parametrizable entry/exit conditions as `{key, label, default, min, max, step, scale, suffix}` specs; thresholds in % convert via `scale`), the ticker's available price range (`range.first/last`) and the engine defaults (3A window clamped, capital R$ 10.000, 100% position, 252 dias máx.). The company TAB is gone (the simulator lives in 🧰 Ferramentas → Backtest with its own ticker picker + `?b=` deep link); the endpoints stay per-ticker by design.

### `POST /api/webui/company/{ticker}/backtest/run`

[v1.25] Runs ONE parametrized scenario. Body MUST be `application/json` (the v1.22 CSRF rule — a cross-site text/plain POST must not parse); the engine (cotahist scan + the signal precompute) runs via `run_in_threadpool`. Params: `strategy` (one of the meta catalog), `start_date`/`end_date` (clamped to the ticker's range), `initial_capital`, `position_pct`, `max_holding_days` (0 = ilimitado), `stop_loss_pct`, `take_profit_pct` (both verified on the daily close), `fee_brl` (per operação — buy and sell each pay), `exit_on_signal`, and the strategy's own `thresholds` (`{key: value}` from the meta specs). Validation failures answer `{"_error": "mensagem PT-BR"}` with 400.

**Response (ok):** `performance` (retorno total, CAGR, max drawdown, Sharpe rf=0, win rate, trades, buy&hold, alpha, fator de lucro, retorno médio, tempo médio, capital final), `trades` (entrada/saída/preços/ações/PnL/retorno/dias/motivo — `stop_loss|take_profit|signal|max_holding|end_of_period`), `curves` (labels + equity + buy_hold + drawdown + price + entry/exit markers, downsampled to ≤1200 pts) and `warnings` (missing DFP/ITR series → "sincronize CVM"; no entries → "ajuste os limiares"). The price series is bdi_code=2 (lote padrão), ONE row per session — DIR/REC rights rows never poison the simulation.

### `GET /api/webui/company/{ticker}/governance/practices`

[v1.26] The Práticas subtab — the CGVN practices table for ONE filing plus the filings list for the Exercício select. Params: `data_ref` (a filing's Data_Referencia; default/unknown → latest — a stale select never 404s the pane), `capitulo` (exact chapter), `adotada` (exact adoption: Sim/Parcialmente/Não/Não se Aplica), `q` (busca in prática/explicação/item). **Response (ok):** `data_referencia`, `exercicio` (from the document's Data_Fim_Exercicio_Social — the CGVN ref=exercício+1 convention), `data_entrega`, `link` (the protocolo PDF on CVM), `filings` (every filing: exercício/score/sim/total), `capitulos`, `adotadas`, `filters`, `rows` (id_item/capítulo/princípio/prática/adotada/explicação — the Explicação texts are huge, rows expand client-side).

### `GET /api/webui/company/{ticker}/ipe/events`

[v1.26] The Informações Periódicas tab — its OWN tab since the split (moved from `/governance/events`; CGVN is the self-assessment, IPE is what the company FILED — "different purpose"). ONE faceted page of the ticker's IPE events (Informações Periódicas e Eventuais: AGO/AGE, avisos, fatos relevantes, calendários…). Params: `categoria`/`tipo`/`especie` (EXACT match; the sentinel `__none__` selects the EMPTY value — 14% of real rows carry no tipo), `ano` (ano_origem), `q` (assunto substring), `page` (1-based), `per_page` (1-100, default 25). **Response (ok):** `total`/`page`/`pages`, `events` (data_entrega/data_referencia/categoria/tipo/especie/assunto/versao/protocolo/link_download — versao > 1 = reapresentação, badged not deduped; empty assunto falls back to tipo → categoria client-side), `chips` (the quick presets) and **`facets`** — the four cascading lists (`categorias`/`tipos`/`especies`/`anos`, each `{v, n}`): every facet respects ALL filters EXCEPT its own field (pick Tipo=AGO and the Categoria facet narrows to Assembleia). Facet ordering: `anos` CHRONOLOGICAL (newest first — [v1.26] the user-reported count-ordered Ano select), the rest most-used first. No generic key — the whole tab is this one custom-rendered endpoint (the backtest precedent).

### Lazy subtab endpoints (aliases of `/sections/{key}`)

Each family also has dedicated endpoints over the same service methods — `financials-overview`, `financials-statements`, `valuation-overview|-multiples|-intrinsic|-fundamentals|-all`, `proventos-overview|-historico|-anual`. Same payloads as `/sections/{key}`; kept for the existing client loaders.

### Section families (the registry keys)

[v1.22.1] Every lazy subtab is a `<family>:<sub>` key registered in `webui/adapters/registry.py` behind ONE generic endpoint per scope — `GET /api/webui/company/{ticker}/sections/{key}` (company tabs), `GET /api/webui/macro/sections/{key}` (the Macro page, no ticker segment) and the Mercado families under the mercado endpoints. The full key set (18 families, 74 keys — [v1.26] + the governance family):

| Family | Keys | Loaded by |
|---|---|---|
| `preco` | `cotacao`, `indicadores`, `volatilidade`, `volume`, `fibonacci` | Company · Preço tab (5 subtabs) |
| `financials` | `overview`, `demonstracoes` | Company · Financeiro tab |
| `valuation` | `overview`, `multiples`, `intrinsic`, `fundamentals`, `all` | Company · Valuation tab (5 subtabs) |
| `proventos` | `overview`, `historico`, `anual` | Company · Proventos tab |
| `options` | `overview`, `chain`, `iv`, `activity`, `positions` | Company · Opções tab |
| `shareholders` | `overview`, `holders`, `free_float`, `equity` | Company · Acionistas tab |
| `insiders` | `overview`, `transactions`, `monthly`, `by_role`, `by_tipo` | Company · Insiders tab ([v1.26.1] `by_tipo` = the Por Tipo subtab — the by_role twin on the Tipo_Movimentacao axis; cargo/tipo pills + per-tipo colored charts) |
| `historical` | `overview`, `valuation`, `profitability`, `leverage` | Company · Histórico tab [v1.24] |
| `governance` | `overview` | Company · Governança tab [v1.26] — Visão Geral only; Práticas is the dedicated `/governance/practices` endpoint above. The Informações Periódicas tab [v1.26] has NO registry key — it is the dedicated `/ipe/events` endpoint, one custom renderer |
| `macro` | `overview`, `juros`, `inflacao`, `cambio`, `atividade`, `retorno_real`, `focus`, `curva` | Macro page (8 lazy subtabs) |
| `focus` | `overview`, `juros`, `inflacao`, `cambio`, `atividade`, `fiscal`, `externo` | Mercado · Focus |
| `fluxo` | `overview`, `mensal`, `anual`, `por_investidor` | Mercado · Fluxo |
| `indices` | `overview`, `ibov`, `smll`, `idiv`, `ifix`, `bdrx` | Mercado · Índices |
| `inflacao` | `overview`, `ipca`, `igpm`, `inpc` | Mercado · Inflação |
| `juros` | `overview`, `selic`, `cdi`, `meta_selic` | Mercado · Juros |
| `poupanca` | `overview`, `poupanca` | Mercado · Poupança [v1.23] — the overview reads ddm-inflation (IPCA) + ddm-juros (CDI, compounded to 12m) OPTIONALLY; missing sources degrade to poupança-only and get named |
| `acoes` | `overview`, `evolucao` | Mercado · Ações |
| `dividendos` | `overview`, `empresas`, `calendario`, `bdrs` | Mercado · Proventos |

The company page's 12 tabs: `visao_geral`, `preco`, `financials`, `valuation`, `historical`, `proventos`, `options`, `shareholders`, `insiders`, `governance`, `ipe`, `backtest` — each has a page shell (`/webui/company/{ticker}/{tab}`) and lazy-loads its families' keys on first visit (pointer-intent prefetch ~300ms before the click). [v1.26] `ipe` (Informações Periódicas) is split from `governance`: different purpose — what the company FILED vs how it self-assesses.

---

## Pre-flight Routes

[v1.7] System health checks surfaced in the UI. Cheap (file stats, SQLite pragmas, `MAX(rowid)` probes) — run per request, no side effects (never creates directories).

### `GET /api/webui/preflight/`

Full report — JSON.

**Response:**
```json
{
  "status": "warn",
  "generated_at": "2026-11-21T10:00:00",
  "duration_ms": 137,
  "memory_root": "D:/mcp/agent/memory_db",
  "summary": {"ok": 31, "warn": 4, "fail": 1, "total": 36},
  "groups": [
    {"id": "bancos", "name": "Bancos de Dados", "checks": [
      {"id": "db:dfp", "label": "dfp.db (cvm)", "status": "ok",
       "detail": "1.4 GB · 12,3 mi linhas"}
    ]},
    {"id": "dados", "name": "Sincronizações", "checks": […]},
    {"id": "sistema", "name": "Sistema", "checks": […]},
    {"id": "adapters", "name": "Adapters", "checks": […]},
    {"id": "configuracao", "name": "Configuração", "checks": […]}
  ]
}
```

### `GET /api/webui/preflight/panel`

Grouped checks card — HTML partial (Sync page, `hx-trigger="load"`).

### `GET /api/webui/preflight/banner`

One-line summary with link to `/webui/sync` — HTML partial (Dashboard).

---

## Tools Routes (Ferramentas) [v1.27, v1.28]

The Ferramentas tools — Comparação (2-4 companies side by side, the
online-shop way) and Screener (one ticker × its whole sector's
medians).

### `GET /api/webui/tools/comparison?tickers={tickers}`

The full comparison payload. **Payload-cached** on the composite
DFP+ITR × COTAHIST fingerprint of every compared ticker (the v1.26.1
webui_payloads foundation) — a hit returns in ~1ms with a `cache_note`
provenance line; any new demonstração or cotação of ANY of the companies
rebuilds the set.

**Parameters:**
- `tickers`: comma/space/dot-separated B3 tickers (2-4 after dedupe;
  order matters — it is the column order AND the cache key)

**Response:** the custom-renderer payload —
```json
{
  "status": "ok",
  "tickers": ["PETR4", "VALE3"],
  "companies": [{"ticker", "name", "sector", "color", "price",
                 "price_date", "var_day", "error"}],
  "groups": [{"key": "valuation", "name": "Valuation",
              "rows": [{"label": "P/L", "fmt": "num", "raw": [2.6, 77.17],
                        "values": ["2,60", "77,17"], "best": [0], "tip"}]}],
  "charts": [{"id": "radar", "title", "desc", "cd": {Chart.js config}}],
  "price_hist": {"monthly": {"PETR4": [{"date": "2021-11", "close": 40.1}, …]},
                 "daily": {"PETR4": [{"date": "2026-11-24", "close": 38.5}, …]}},
  "errors": ["VALE3: algumas fontes falharam (indicadores parciais…)"],
  "cache_note": "Pré-calculado em …"
}
```
`price_hist` feeds BOTH client-side charts (the Cotação Histórica
cards and the base-100 line): `monthly` carries the month-end closes
over the whole cotahist history (`date` = `YYYY-MM`), `daily` the last
~13 months (`date` = `YYYY-MM-DD`) — the Tudo/10A/5A pills slice the
first, 1A/6M/3M/1M the second, client-side.
Validation errors (fewer than 2 / more than 4 / bad ticker shape) return
`{"status": "error", "error": "…PT-BR…"}` with HTTP 200 (the client
renders the message).

### `GET /api/webui/tools/comparison/search?q={query}`

JSON ticker search for the comparison picker (the same bridge-DB search
as the top bar's HTMX `/search`, but JSON — the picker renders its own
dropdown). **[v1.28] Both Ferramentas pickers use it** — the screener's
dropdown hits the same endpoint.

**Response:** `{"results": [{"ticker": "PETR4", "name": "PETROBRAS"}, …]}`

### `GET /api/webui/tools/screener?ticker={ticker}` [v1.28]

The Screener tool — ONE ticker screened against its whole SECTOR: the
peer table, the sector medians and the per-metric verdicts. **Payload-
cached** on the composite DFP+ITR × COTAHIST fingerprint of EVERY
sector company PLUS the peer list itself (a bridge resync that changes
the sector membership rebuilds too).

Peer discovery: the bridge DB's `ticker_map.setor_ativ` (one class per
company — the CNPJ-root dedupe keeps the most liquid share, so
PETR3/PETR4 never count twice in the medians; capped at 40 companies
by liquidity). Medians run over the sector INCLUDING the subject, over
available values only, and multiples take positive values only (a
negative P/L is a loss, not a bargain; net debt is the exception —
negative = caixa líquido).

**Parameters:**
- `ticker`: one B3 ticker (the sector is resolved from it)

**Response:** the custom-renderer payload —
```json
{
  "status": "ok",
  "ticker": "PETR4", "name": "PETROBRAS",
  "sector": "Petróleo e Gás", "company_count": 3,
  "price": 40.87, "price_date": "2026-11-24", "var_day": 0.012,
  "kpis": [{"label": "Mediana P/L", "value": "11,87"}, …],
  "table": [{"ticker", "name", "is_subject", "price", "market_cap",
             "p_l", "p_vpa", "ev_ebitda", "roe", "dy", "receita",
             "ebitda", "marg_ebitda", "cresc", "segmento", "partial",
             "price_raw", "mktcap_raw", "p_l_raw", "p_vpa_raw",
             "ev_ebitda_raw", "roe_raw", "dy_raw", "receita_raw",
             "ebitda_raw", "marg_ebitda_raw", "cresc_raw"}],
  "vs_rows": [{"label": "P/L", "tip", "my_fmt": "2,60",
               "med_fmt": "11,87", "delta_fmt": "-78,10%",
               "verdict": "cheap", "direction": "cheap"}],
  "charts": [{"id": "pl_setor|roe_setor|vs_mediana",
              "title", "desc", "cd": {Chart.js config}}],
  "price_hist": {"monthly": {"PETR4": [{"date": "2021-11", "close": 40.1}]},
                 "daily": {"PETR4": [{"date": "2026-11-24", "close": 38.5}]}},
  "errors": ["VALE3: algumas fontes falharam (indicadores parciais…)"],
  "cache_note": "Pré-calculado em …"
}
```
`verdict` per row: `cheap`/`expensive` (multiples and leverage — lower
is better; the client renders barata/cara) or `above`/`below` (quality
metrics — higher is better) or `na` (not comparable). `price_hist`
feeds the subject's Cotação Histórica card (same two-resolution
contract as the comparison tool). Validation errors (missing/bad
ticker), an unresolvable sector and a single-company sector return
`{"status": "error", "error": "…PT-BR…"}` with HTTP 200.

---

## HTMX Partial Routes

Return HTML fragments (no `<html>` wrapper) for HTMX partial swaps.

### `GET /api/webui/search?q={query}`

Ticker search — returns an HTML list of matching tickers.

**Parameters:**
- `q`: Search query (matches ticker prefix or company name substring)

**Response:** HTML fragment:
```html
<ul class="search-list">
  <li><a href="/webui/company/PETR4">
    <span class="ticker">PETR4</span>
    <span class="name">Petrobras</span>
  </a></li>
</ul>
```

### `GET /api/webui/company/{ticker}/header`

Company header — returns the 3-part header HTML fragment (identity card + 4 registration tables + activity description).

### `GET /api/webui/company/{ticker}/tab/{tab}`

Tab content — returns the HTML fragment for a specific company tab.

**Parameters:**
- `tab`: `visao_geral` | `preco` | `financials` | `valuation` | `historical` | `proventos` | `options` | `shareholders` | `insiders` | `governance` | `ipe` | `backtest` — the company page's 12 tabs

---

## Carteira Routes [v1.21]

The portfolio REST surface (`webui/routes/portfolio.py`, all under `/api/webui/portfolio`; the store + PM engine in `webui/services/portfolio.py`). Every number is a pre-formatted PT-BR string; validation is all-or-nothing with per-field PT-BR errors (`400` + `{"_error": …, "errors": {field: message}}`). [v1.22] every mutation additionally passes the CSRF guard (cross-site origins and non-JSON bodies are rejected before the handler runs) and a degraded store (unreadable JSON on disk) refuses writes with a PT-BR `503`.

### Reads

- `GET /state` — users + accounts + watchlist + ticker metadata (the Gerenciar UI + selectors; `store_error` carries the degraded-store banner)
- `GET /directory` — the users → accounts tree with live KPIs (per-USER sums only, never across users)
- `GET /positions?scope=all|user:{id}|account:{id}` — PM positions + KPI cards + totals + recent transactions for a scope (shorts count in the totals; a mixed long+short of one ticker shows PM/Lucro % as "—" with a 🔀 flag)
- `GET /overview` — the Painel widget payload (watched accounts grouped by user + watchlist tickers)

### Users / accounts

- `POST /users` `{name}` — create · `PUT /users/{id}` — rename · `DELETE /users/{id}` — cascade (accounts + txs)
- `POST /accounts` `{user_id, name, broker, watch}` — create · `PUT /accounts/{id}` — update (any field incl. the ⭐ watch toggle) · `DELETE /accounts/{id}` — cascade (txs)

### Transactions

- `POST /txs` `{account_id, ticker, type: buy|sell, quantity, price, fees?, date, note?}` — create (sells are free to short — qty goes negative; buys at R$ 0,00 are bonificações; sells at R$ 0,00 and NaN/±inf values are rejected)
- `PUT /txs/{id}` — update (same-user accounts only — moving a tx to ANOTHER user's account is refused; `warnings` returns when the edit leaves shorts open)
- `DELETE /txs/{id}` — delete (PM/lucro recalculated by the replay; `warnings` when the delete leaves shorts open; nonexistent id → `404`)

Replay semantics [v1.22]: transactions replay in `(date, created_at, seq)` order — `seq` is the monotonic insertion counter (backfilled for pre-v1.22 files), so same-second entries keep their insertion order. A buy that covers a short and flips long splits its fees (covered share → realizado, excess share → the new long's PM).

### Watchlist + ticker metadata

- `POST /watchlist` `{ticker}` — add · `DELETE /watchlist/{ticker}` — remove
- `POST /tickers/{ticker}/refresh` — re-fetch the CVM name/sector in a background thread

---

## System Routes [v1.20]

The system surface: the log drawer's feed + the schema-driven settings store. Lives in `webui/routes/system.py`; the data services in `webui/services/syslog.py` and `webui/services/settings.py`.

### `GET /api/webui/logs`

System-log ring-buffer entries (JSON). The log captures every non-static HTTP request (method, path + query string — [v1.28.1] the meaningful `?…` rides along, the `_t=` cache-buster stripped — status, duration), the sync job lifecycle, startup events, Python WARNING+ records, uvicorn's own INFO banners [v1.28.1] and — [v1.28.1] the TERMINAL TAIL: every `print()` the process emits (the `[ratios] 12/49 roe (0.00s) = 0.5841` progress lines, the `[webui] … partial: …` notes, engine tracebacks) via the stdout/stderr tee, tagged with parsed sources (`ratios`/`webui`/`app`/`stderr`). In memory, per process.

**Parameters:**
- `?after=<id>` — only entries with id greater than this (incremental tail); omit/0 → the last `limit` entries
- `?limit=<n>` — snapshot size (default 300)

Returns `{"entries": [{"id", "ts", "level", "source", "message"}, …]}` (oldest first).

### `GET /api/webui/logs/stream`

SSE stream of the system log (the 📜 drawer's live feed). On connect: one `snapshot` event with the whole current buffer, then `logs` events (~1s batches) plus a keepalive comment every ~15s of silence. Auto-reconnects (`retry: 3000`).

### `GET /api/webui/settings`

The settings schema + current values — the Configurações page renders its form from this. Returns:

```json
{
  "sections": [{"name": "Sincronização", "settings": [
    {"key": "sync.auto_on_startup", "label": "…", "type": "bool",
     "default": false, "value": false, "help": "…"}
  ]}],
  "values": {"sync.auto_on_startup": false, "…": "…"}
}
```

`ui.theme` / `ui.locale` values are seeded from the request cookies (the cookie is the single source of truth for those).

### `PUT /api/webui/settings`

Persist a `{key: value}` patch (JSON body). Validation is all-or-nothing per the SCHEMA (types, min/max, select options) — any invalid key rejects the whole patch with `400` + `{"_error": …, "errors": {key: PT-BR message}}`. On success returns `{"ok": true, "applied": [keys], "values": {…}}`; `ui.theme`/`ui.locale` additionally get a `Set-Cookie` on the response.

Storage: `memory_db/webui_settings.json` (atomic write). Every setting is wired: `sync.auto_on_startup` (sync stale sources at boot), `sync.stale_hours` (staleness threshold everywhere), `sync.schedule_hours` (periodic auto-sync, 0 = off), `home.card_rows`, `home.cache_seconds`, `home.ticker_kpis` [v1.28.3] (the Painel's quote cards, in order — ações, FIIs, ETFs, BDRs; the ⚙️ Gerenciar Painel box is the editor), `home.cards` [v1.28.3] (which ranking boxes show + their order), `logs.level`, `logs.buffer`.

---

## Sync Routes

### `GET /api/webui/sync/status`

Returns freshness status for all data sources — HTML partial (the Sync page table). `/api/webui/sync/status.json` returns the JSON shape:
```json
{
  "dfp": { "last_sync": "2026-09-15T10:30:00", "stale": false, "status": "fresh" },
  "itr": { "last_sync": "", "stale": true, "status": "stale" },
  ...
}
```

### `GET /api/webui/sync/box`

[v1.19] The compact sync status box for the Painel's bottom slot — a collapsed `<details>` whose summary carries the overall count ("14 de 20 atualizadas · 6 desatualizados"), with the same freshness table + a note linking to the Sincronização page inside. Same 30s refresh cadence the old dashboard ribbon used.

### `POST /api/webui/sync/all`

Triggers background syncs for every STALE source (fresh within 24h skipped). One job per source, deduped.

### `POST /api/webui/sync/{source}`

Triggers a background sync for one data source. Returns immediately with a job_id.

**Parameters:**
- `source`: any key from the sync_guard registry — `dfp`, `itr`, `fca`, `fre`, `cad`, `bridge`, `cotahist`, `b3_dividends`, `sgs`, `focus`, `ddm-*`, `b3-api-*`, etc.

**Response:**
```json
{ "job_id": "a1b2c3d4", "source": "dfp", "status": "started" }
```

### `GET /api/webui/sync/stream`

SSE (Server-Sent Events) stream of sync progress events. Auto-reconnects on disconnect.

**Events:**
```
data: {"event": "sync.started", "job_id": "a1b2c3d4", "source": "dfp"}

data: {"event": "sync.completed", "job_id": "a1b2c3d4", "source": "dfp", "status": "completed"}

data: {"event": "sync.failed", "job_id": "a1b2c3d4", "source": "dfp", "error": "..."}
```

**Keepalive:** The server sends `: keepalive` comments every 15 seconds to prevent proxy timeouts.

---

## Carteira (Portfolio) Routes [v1.21]

The user's own money: users → accounts → transactions → PM (preço médio) positions + watchlist. Lives in `webui/routes/portfolio.py`; the store, the position engine and the quote enrichment in `webui/services/portfolio.py` (storage: `memory_db/webui_portfolio.json` — atomic write + mtime-checked in-memory cache). All mutations validate all-or-nothing and return `{"ok": true, …}` or HTTP 400 `{"_error": summary, "errors": {field: PT-BR message}}`. [v1.21] Sells may SHORT (qty goes negative — the sell price becomes the short's PM; buys cover and can flip long) and price `0` is valid (bonificação); only negative prices/quantities and future dates are refused. Numeric strings are PT-BR aware (`"1.234,56"` → 1234.56). CRUD events feed the 📜 system log (source `carteira`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/webui/portfolio/state` | Users + accounts (+ `tx_count`, `user_name`) + watchlist + ticker metadata — the manage UI |
| GET | `/api/webui/portfolio/directory` | — Users → accounts tree with live KPIs (patrimônio/custo/lucro per account AND per user — sums NEVER across users) — the Carteira landing/user pages |
| GET | `/api/webui/portfolio/positions?scope=all\|user:{id}\|account:{id}` | PM positions + KPI cards + totals + the 200 most recent transactions (chronological ASC; `short`/`zero` row flags) for the scope |
| GET | `/api/webui/portfolio/overview` | The Painel widget payload — watched accounts GROUPED BY USER (per-user subtotals) + watchlist tickers [v1.28.3: `sector` (the cadastro's CVM cache) + `low_day`/`high_day` (the quote's own session high/low) before the `low_52`/`high_52` pair, closed by `var_52` (the 52-week series' first-vs-last variation); the band pill rides `price_pill`, the main price only] |
| POST | `/api/webui/portfolio/users` | Create user `{name}` |
| PUT | `/api/webui/portfolio/users/{id}` | Rename |
| DELETE | `/api/webui/portfolio/users/{id}` | Delete (cascades accounts + transactions) |
| POST | `/api/webui/portfolio/accounts` | Create `{user_id, name, broker?, watch?}` |
| PUT | `/api/webui/portfolio/accounts/{id}` | Update any field (incl. the ⭐ watch flag) |
| DELETE | `/api/webui/portfolio/accounts/{id}` | Delete (cascades transactions) |
| POST | `/api/webui/portfolio/txs` | Create `{account_id, ticker, type: buy\|sell\|corp, quantity, price, fees?, date, note?}` — `corp` (v1.22.3) is the corporate action: `{action: split\|group\|bonus, factor}` (qty ×= f, PM ÷= f, custo invariant; replays FIRST within its date; [v1.22.4] the action is REQUIRED — empty → PT-BR field error — and corp rows PERSIST quantity/price/fees = 0, self-describing). Mutation responses carry `undo_token` + `undo_label` (the ↩️ toast) |
| PUT | `/api/webui/portfolio/txs/{id}` | Update (undo token included) |
| DELETE | `/api/webui/portfolio/txs/{id}` | Delete (undo token included; the undo re-inserts with the SAME id/seq) |
| GET | `/api/webui/portfolio/txs?scope=&page=&per_page=&ticker=&type=&date_from=&date_to=&q=` | [v1.22.3] The paginated/filtered ledger: filters narrow BEFORE paging; page 1 = the newest `per_page` (default 50, cap 200) rows, oldest-first inside the page; returns `{rows, total, page, pages}`. [v1.22.4] the `ticker` filter is a case-insensitive PREFIX (1–8 alphanumerics — "KL" matches KLBN4 + KLBN11 while you type; the old exact-match 4–8 rule 400'd on every partial keystroke) |
| POST | `/api/webui/portfolio/undo` | [v1.22.3] `{token}` → one-shot restore of the last tx mutation (create removes / update restores the previous fields / delete re-inserts); expired or unknown tokens → `404` |
| GET | `/api/webui/portfolio/export` | [v1.22.3] The whole store JSON (the Gerenciar download) |
| POST | `/api/webui/portfolio/restore` | [v1.22.3] Replace the whole store from an exported file — validate-everything-then-swap (`_parse_store` incl. the tx reconciliation); anything invalid → `400`, store untouched; the `.bak` of the current file is automatic |
| GET | `/api/webui/portfolio/alerts` | [v1.22.3] Every price alert + its live evaluation against the quote map (`triggered: true\|false\|null`) |
| POST | `/api/webui/portfolio/alerts` | [v1.22.3] Create `{ticker, op: above\|below, price}` — one alert per (ticker, op): the new price replaces the old |
| DELETE | `/api/webui/portfolio/alerts/{id}` | [v1.22.3] Remove an alert |
| POST | `/api/webui/portfolio/watchlist` | Add ticker `{ticker}` |
| DELETE | `/api/webui/portfolio/watchlist/{ticker}` | Remove ticker |
| POST | `/api/webui/portfolio/tickers/{ticker}/refresh` | Re-fetch the CVM name/sector (background thread) |
| POST | `/api/webui/portfolio/import/nota` | [v1.22.2] `{pdf_b64}` → nota PREVIEW (dry-run — nothing written): broker/CNPJ, nº nota, pregão, client, parsed trades with pro-rata fees, `needs_mapping` (modelo B3 specs without ticker + suggestions), IRRF, warnings, and the dedup pre-check (`dedup.imported`). XP / modelo B3 / BTG layouts; à vista + fracionário; pdfplumber (pypdf fallback) |
| POST | `/api/webui/portfolio/import/commit` | [v1.22.2] Parsed nota (mapped by the user) → ALL txs in ONE atomic save: `{account_id, broker, broker_cnpj, nota, pregao, trades: [{ticker, type, quantity, price, fees, date}]}`. Dedup law: the same (CNPJ, nº nota, pregão) is refused `409`; per-row PT-BR validation errors, all-or-nothing; every tx carries the `NC nº · corretora · data` note tag |
| GET | `/api/webui/portfolio/import/notas?account_id=` | [v1.22.2] The imported-notas registry (one account or all): broker, pregão, `alive` count (txs still present), fees, IRRF — the undo UI |
| DELETE | `/api/webui/portfolio/import/nota/{id}` | [v1.22.2] Undo an import: removes the nota's txs + its registry row (PM/lucro recalculated; short warnings like any delete) |
| GET | `/api/webui/portfolio/ir?scope=all\|user:{id}\|account:{id}` | [v1.22.2] IR mês a mês per user (CPF level — accounts summed): swing × day-trade split (day carve-out: matched same-day pairs never touch the PM), R$ 20k exemption, separate swing/day loss carry pools, IRRF estimates (0,005% swing / 1% day per account), 15%/20%, DARF 6015/6120 with due dates (último dia útil do mês seguinte)
| GET | `/api/webui/portfolio/proventos?scope=` | [v1.22.3] Proventos per position / yield-on-cost: the txs × dividends.db join with the DATA COM entitlement rule (buys that day receive, sells don't; corp actions re-base first) — per-ticker received/pending/YOC + the full events table + notes (JCP bruto, short pays the dividend). [v1.22.4] events merge TWO sources (B3 provents + the DDM agenda, deduped; each row carries `source`), and a ⚠️ note lists OPEN positions with zero events (sync hint)
| GET | `/api/webui/portfolio/position-detail?scope=&ticker=` | [v1.22.3] One ticker's full story in the scope: per-account PM LADDER (every tx with the running qty/PM and Δ realizado), the merged position, the live quote, and the proventos it paid — the 🔍 drawer
| GET | `/api/webui/portfolio/performance?scope=` | [v1.22.3] TWR/XIRR vs CDI/IBOV + the patrimônio evolution curve (month-end grid): TWR chained between cashflow dates (the flow executes at the close), XIRR by bisection, CDI from the sgs daily series 12 (juros.db monthly fallback), IBOV proxied by BOVA11 — same window, same day-count annualization. [v1.22.4] IVVB11 joins as the S&P 500 (BRL) proxy (`ivvb_total`/`ivvb_annual` + `curve.ivvb`); a sign-flipped TWR chain (shorts / buy far above the close) reports `twr_total: null` + a note instead of crashing; the four report GETs answer `{"ok": false, "_error": …}` JSON on ANY internal failure (never a plain-text 500)
| GET | `/api/webui/portfolio/allocation?scope=` | [v1.22.3] Per-setor/per-ticker weights over the LONG book + HHI (×10.000) + maior posição/top-3 + the short exposure line + the doughnut chart data
| POST | `/api/webui/portfolio/simulate` | [v1.22.3] The what-if simulator: `{scope, trades: [{ticker, type: sell\|buy, quantity, price}]}` → before/after KPIs (patrimônio, custo, lucro não realizado, lucro realizado) + per-ticker deltas — NOTHING is written |

### `GET /api/webui/portfolio/positions?scope=all` (sample)

```json
{
  "status": "ok", "empty": null,
  "scope_label": "Geral — todos os usuários e contas",
  "session_date": "20/11/2026", "quotes_ok": true,
  "kpis": [{"label": "Patrimônio", "value": "R$ 10.860,00", "tooltip": "…"},
            {"label": "Custo (PM)", "value": "R$ 7.319,60", "tooltip": "…"},
            {"label": "Lucro não realizado", "value": "+R$ 3.540,40", "tooltip": "…"},
            {"label": "Lucro %", "value": "+48,37%", "tooltip": "…"},
            {"label": "Lucro realizado", "value": "+R$ 176,07", "tooltip": "…"}],
  "positions": [{"ticker": "POMO4", "name": "MARCOPOLO S.A.",
                 "sector": "Material Rodoviário",
                 "pm": "2,44", "price": "3,62", "qty": "3.000",
                 "cost": "R$ 7.319,60", "value": "R$ 10.860,00",
                 "profit": "+R$ 3.540,40", "profit_pct": "+48,37%",
                 "accounts": ["Bruno · XP Clear"]}],
  "totals": {"cost": "R$ 7.319,60", "value": "R$ 10.860,00",
             "profit": "+R$ 3.540,40", "profit_pct": "+48,37%"},
  "txs": [{"id": "…", "date": "01/04/2026", "date_iso": "2026-04-01",
            "ticker": "POMO4", "account": "Bruno · XP Clear",
            "account_id": "…", "type": "sell", "qty": "500",
            "quantity": 500, "price": "2,80", "raw_price": 2.8,
            "fees": "—", "raw_fees": 0.0, "total": "R$ 1.400,00", "note": ""}]
}
```

Every number is a PRE-FORMATTED PT-BR string (the house rule — the client only colorizes by the leading sign). Degradation: cotahist down → `quotes_ok: false` + `quotes_note` naming the source; a held ticker simply absent from the synced history → per-ticker "—" + `quotes_note` listing the stragglers (totals require every quote). Empty states: `"empty": "no_users" | "no_accounts" | "no_txs"` (the client renders the setup guides).

---

## Existing Gateway Routes (Mounted on Same App)

The WebUI app also mounts the existing gateway routes, so the agent's MCP-to-HTTP bridge is available on the same port:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Synchronous chat (submit + wait) |
| POST | `/task` | Async task submission |
| GET | `/result/{trace_id}` | Poll for task result |
| GET | `/ws` | WebSocket for live task progress |
| GET | `/health` | Health check |
| GET | `/health/models` | LLM model health |
| GET | `/tools` | List available MCP tools |
| GET | `/metrics` | Telemetry metrics |
| GET | `/traces` | List traces |
| GET | `/traces/{trace_id}` | Get trace detail |
| GET | `/api/reports` | List generated reports |
| GET | `/reports/{trace_id}` | Serve a generated HTML report |
| GET | `/docs` | FastAPI Swagger docs |
| GET | `/openapi.json` | OpenAPI schema |

---

## Service Layer Contract

Routes never import skill engines directly. All data access goes through `webui/services/`. Since v1.7 the service singletons are owned by `webui/adapters/registry.service()` (memoized factory shared by routes and the adapter dispatch path).

### `CompanyService`

```python
class CompanyService:
    def header(self, ticker: str) -> dict
    def search(self, query: str, limit: int = 10) -> list[dict]
    def ratios(self, ticker: str) -> dict
    def price_series(self, ticker: str, years: int = 5) -> list[dict]
```

### `SyncService`

```python
class SyncService:
    def freshness(self) -> dict[str, dict]
    def subscribe(self) -> asyncio.Queue
    def unsubscribe(self, q: asyncio.Queue) -> None
    def trigger_sync(self, source: str) -> dict  # job dict (deduped)
    def trigger_sync_all(self, stale_only: bool = True) -> dict
    def job_status(self, job_id: str) -> dict | None
    def all_jobs(self) -> list[dict]
```

### `PreflightService` (v1.7)

```python
class PreflightService:
    def run(self) -> dict  # {status, summary, groups: [{id, name, checks: [...]}]}
```

---

## Authentication

The existing gateway routes use Bearer token auth (`GATEWAY_SECRET` in `.env`). The WebUI routes (`/webui/*`, `/api/webui/*`) do NOT require auth by default — they're designed for localhost access.

To expose the WebUI on a network, bind to `0.0.0.0` and add auth middleware to the WebUI routes.

---

## Error Handling

- HTML routes return FastAPI's default error pages (500, 404)
- JSON API routes return JSON error responses
- HTMX partial routes return HTML error fragments (so HTMX can swap them in)
- SSE stream handles disconnects gracefully (unsubscribes on `request.is_disconnected()`)
