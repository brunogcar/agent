<- Back to [WebUI Overview](../WEBUI.md)

# 🔌 WebUI API Reference

> All HTTP routes exposed by the WebUI. Routes are prefixed `/webui` (HTML pages) or `/api/webui` (JSON/SSE). The existing gateway routes (`/chat`, `/task`, `/ws`, `/health`) are also mounted on the same app.

Last updated: 2026-09-16 (v1)

---

## HTML Page Routes

Server-rendered Jinja2 pages. These return full HTML documents (extending `base.html`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/webui/` | Dashboard (home — market overview, no ticker required) |
| GET | `/webui/company/{ticker}` | Company overview page (default tab: visao_geral) |
| GET | `/webui/company/{ticker}/{tab}` | Company tab page (tab: visao_geral, valuation, financials, dividends, historical) |
| GET | `/webui/macro` | Macro indicators page |
| GET | `/webui/sync` | Data sync status page |
| GET | `/webui/settings` | Settings page (theme, language) |
| GET | `/` | Redirects to `/webui/` |

### Query Parameters

All HTML routes accept:
- `?theme=<dark|light>` — override theme for this request (sets cookie)
- `?lang=<pt-BR|en-US>` — override language for this request (sets cookie)

---

## JSON API Routes

Return JSON. Used by Chart.js and programmatic clients.

### `GET /api/webui/company/{ticker}/ratios`

Returns all 79 valuation ratios for a ticker.

**Response:**
```json
{
  "p_l": 16.54,
  "p_vpa": 1.45,
  "ev_ebitda": 2.80,
  "roe": 0.3119,
  "roic": 0.1680,
  "dividend_yield": 0.1075,
  ...
}
```

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
- `tab`: `visao_geral` | `valuation` | `financials` | `dividends` | `historical`

---

## Sync Routes

### `GET /api/webui/sync/status`

Returns freshness status for all data sources.

**Response:**
```json
{
  "dfp": { "last_sync": "2026-09-15T10:30:00", "stale": false, "status": "fresh" },
  "itr": { "last_sync": "", "stale": true, "status": "stale" },
  ...
}
```

### `POST /api/webui/sync/{source}`

Triggers a background sync for one data source. Returns immediately with a job_id.

**Parameters:**
- `source`: One of `dfp`, `itr`, `fca`, `fre`, `cad`, `cotahist`, `brapi`, `sgs`, etc.

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

Routes never import skill engines directly. All data access goes through `webui/services/`.

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
    def trigger_sync(self, source: str) -> str  # returns job_id
    def job_status(self, job_id: str) -> dict | None
    def all_jobs(self) -> list[dict]
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
