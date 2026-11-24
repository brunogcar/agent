<- Back to [WebUI Overview](../WEBUI.md)

# 🔌 WebUI API Reference

> All HTTP routes exposed by the WebUI. Routes are prefixed `/webui` (HTML pages) or `/api/webui` (JSON/SSE). The existing gateway routes (`/chat`, `/task`, `/ws`, `/health`) are also mounted on the same app.

Last updated: 2026-11-23 (v1.21 fix 1 — directory route, shorts/bonificações, overview by user; v1.21 carteira/portfolio routes; v1.20 system log + settings; v1.7 adapter dispatch + pre-flight)

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

[v1.19] **The Painel landing payload** — one call, one screen. Macro KPI row (BCB SGS: Selic anualizada, IPCA/IGP-M acumulado 12m, USD/BRL ptax) + 5 ranked ticker cards (Top 10 IBOV/SMLL by weight, quote-enriched; Mais Negócios; Maiores Altas; Maiores Baixas — latest cotahist session). Section-scoped degradation: each part fails alone with a PT-BR message naming its sync source. [v1.19 fix 1] Memoized 60s under a lock (single-flight — concurrent callers coalesce into one `market_snapshot()`, which itself is windowed to the last 10 sessions; the payload only changes on sync).

```json
{
  "status": "ok",
  "kpis": [{"label": "Selic (a.a.)", "value": "13,65%", "tooltip": "…"}],
  "cards": [
    {"key": "ibov", "title": "IBOV · Top 10", "subtitle": "Maiores pesos — carteira de 05/08/2026",
     "error": null,
     "items": [{"ticker": "VALE3", "name": "VALE", "value": "R$ 34,50",
                "variation": "+1,23%", "extra": {"label": "peso", "text": "10,886%"}}]}
  ]
}
```
`kpis_note` (optional) carries the SGS degradation message; `variation` is `null` without a previous-session close; `extra` is `null` on the altas/baixas cards. Rendered by `loadHomeData()` (app.js).

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

### Lazy subtab endpoints (aliases of `/sections/{key}`)

Each family also has dedicated endpoints over the same service methods — `financials-overview`, `financials-statements`, `valuation-overview|-multiples|-intrinsic|-fundamentals|-all`, `proventos-overview|-historico|-anual`. Same payloads as `/sections/{key}`; kept for the existing client loaders.

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
- `tab`: `visao_geral` | `preco` | `financials` | `valuation` | `proventos`

---

## System Routes [v1.20]

The system surface: the log drawer's feed + the schema-driven settings store. Lives in `webui/routes/system.py`; the data services in `webui/services/syslog.py` and `webui/services/settings.py`.

### `GET /api/webui/logs`

System-log ring-buffer entries (JSON). The log captures every non-static HTTP request (method, path, status, duration), the sync job lifecycle, startup events and Python WARNING+ records — in memory, per process.

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

Storage: `memory_db/webui_settings.json` (atomic write). Every setting is wired: `sync.auto_on_startup` (sync stale sources at boot), `sync.stale_hours` (staleness threshold everywhere), `sync.schedule_hours` (periodic auto-sync, 0 = off), `home.card_rows`, `home.cache_seconds`, `logs.level`, `logs.buffer`.

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

The user's own money: users → accounts → transactions → PM (preço médio) positions + watchlist. Lives in `webui/routes/portfolio.py`; the store, the position engine and the quote enrichment in `webui/services/portfolio.py` (storage: `memory_db/webui_portfolio.json` — atomic write + mtime-checked in-memory cache). All mutations validate all-or-nothing and return `{"ok": true, …}` or HTTP 400 `{"_error": summary, "errors": {field: PT-BR message}}`. [v1.21 fix 1] Sells may SHORT (qty goes negative — the sell price becomes the short's PM; buys cover and can flip long) and price `0` is valid (bonificação); only negative prices/quantities and future dates are refused. Numeric strings are PT-BR aware (`"1.234,56"` → 1234.56). CRUD events feed the 📜 system log (source `carteira`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/webui/portfolio/state` | Users + accounts (+ `tx_count`, `user_name`) + watchlist + ticker metadata — the manage UI |
| GET | `/api/webui/portfolio/directory` | [fix 1] Users → accounts tree with live KPIs (patrimônio/custo/lucro per account AND per user — sums NEVER across users) — the Carteira landing/user pages |
| GET | `/api/webui/portfolio/positions?scope=all\|user:{id}\|account:{id}` | PM positions + KPI cards + totals + the 200 most recent transactions (chronological ASC; `short`/`zero` row flags) for the scope |
| GET | `/api/webui/portfolio/overview` | The Painel widget payload — watched accounts GROUPED BY USER (per-user subtotals) + watchlist tickers (price, var. dia) |
| POST | `/api/webui/portfolio/users` | Create user `{name}` |
| PUT | `/api/webui/portfolio/users/{id}` | Rename |
| DELETE | `/api/webui/portfolio/users/{id}` | Delete (cascades accounts + transactions) |
| POST | `/api/webui/portfolio/accounts` | Create `{user_id, name, broker?, watch?}` |
| PUT | `/api/webui/portfolio/accounts/{id}` | Update any field (incl. the ⭐ watch flag) |
| DELETE | `/api/webui/portfolio/accounts/{id}` | Delete (cascades transactions) |
| POST | `/api/webui/portfolio/txs` | Create `{account_id, ticker, type: buy\|sell, quantity, price, fees?, date, note?}` |
| PUT | `/api/webui/portfolio/txs/{id}` | Update |
| DELETE | `/api/webui/portfolio/txs/{id}` | Delete |
| POST | `/api/webui/portfolio/watchlist` | Add ticker `{ticker}` |
| DELETE | `/api/webui/portfolio/watchlist/{ticker}` | Remove ticker |
| POST | `/api/webui/portfolio/tickers/{ticker}/refresh` | Re-fetch the CVM name/sector (background thread) |

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
