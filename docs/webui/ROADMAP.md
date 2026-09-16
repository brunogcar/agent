<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Roadmap

> What's built, what's next, and what's deferred for the Brazilian Financial Data WebUI.

---

## ✅ Built (v1)

### Architecture
- [x] Single-command entry point (`python webui.py`)
- [x] One process, one port (extends existing FastAPI gateway)
- [x] SQLite WAL mode for concurrent read/write
- [x] Service layer between routes and calculation engines
- [x] Direct engine imports (bypasses MCP dispatcher)
- [x] SSE for sync progress (not WebSocket)
- [x] CSS variables 3-layer theme system (JSON theme files)
- [x] JSON i18n (not gettext)
- [x] Vendored JS (HTMX + Alpine + Chart.js, no CDN)

### Pages
- [x] Dashboard (`/webui/`) — market overview, quick links, sync ribbon
- [x] Company (`/webui/company/{ticker}`) — header + 5 tabs
- [x] Macro (`/webui/macro`) — placeholder
- [x] Sync (`/webui/sync`) — freshness table + SSE log
- [x] Settings (`/webui/settings`) — theme + language dropdowns

### Company Tabs
- [x] Visão Geral — company header (identity card) + registration tables + activity description + candlestick chart (7 range options, zoom/pan)
- [x] Preço — 5 subtabs: Cotação (tables + Histograma + Início vs Fim), Indicadores (RSI/MACD/Stochastic/OBV/ADX/CCI/Williams %R), Volatilidade (Bollinger Bands + rolling vol), Volume (volume bars + trade count + contracts), Fibonacci (global dropdowns + COMPRA/VENDA + dividend adjustments)
- [x] Valuation — full 79-metric ratios table (no KPIs)
- [ ] Financials — DRE/BPA/BPP/DFC/DVA statement tables
- [ ] Dividends — DPA history + dividend events
- [ ] Historical — 5Y price + ratio charts

### Features
- [x] Ticker search (HTMX debounced keyup, bridge.db ticker_map)
- [x] Company header (identity card — persistent across all tabs)
- [x] Candlestick chart (OHLCV + MM20/50/100/200, zoom/pan, 7 ranges)
- [x] Theme toggle (dark/light, FOUC prevention, localStorage + cookie)
- [x] Language switcher (pt-BR/en-US, cookie-based)
- [x] Sidebar collapse (◀/▶ button, icons-only mode)
- [x] Favicon (SVG bar-chart icon)
- [x] Sync status (freshness table, auto-refresh)
- [x] SSE sync stream (live progress events)
- [x] Cache-busting (?v=N on static URLs, ?_t= on API fetch)
- [x] Price service (ohlcv_with_mas, price_data, indicators, volatility, volume, fibonacci)
- [x] Chart.js zoom plugin + Hammer.js (vendored locally)

---

## 🔄 Next Up (v1.2)

### Company Tabs (complete the 5-tab set)
- [ ] **Financials tab** — DRE, BPA, BPP, DFC, DVA statement tables. Period toggle (quarterly/annual). Reuse `skills/cvm/financials/` engines. This is the biggest data tab — needs period selector, statement type selector, and wide tables with frozen columns.
- [ ] **Dividends tab** — DPA history table, annual bar chart, yield history line chart, payout trend. Reuse `data_sources/b3/dividends/` + `skills/cvm/calculations/engines/dividends.py`.
- [ ] **Historical tab** — 5Y price chart with overlays (P/L bands, Graham Number, moving averages), metric time series (revenue, earnings, margins). Reuse `skills/cvm/historical/` engines.

### Macro Page
- [ ] **BCB SGS indicators** — Selic, IPCA, CDI, PIB, exchange rates. Time series charts.
- [ ] **Focus Bulletin** — market expectations (median, high, low) for IPCA, PIB, Selic, exchange rate. Table + chart.
- [ ] **Macro dashboard** — ribbon of key indicators on the dashboard page.

### Sync Page
- [ ] **Sync trigger buttons** — per-source "Sync now" button that POSTs to `/api/webui/sync/{source}` and shows progress via SSE.
- [ ] **Sync all stale** — bulk button that syncs all stale sources in parallel.
- [ ] **Sync log** — last 10 sync operations with timestamps + row counts.

---

## 🔮 Planned (v3)

### Settings (auto-generated)
- [ ] **Settings as data** — SDNext-style schema-driven settings page. Define settings as a dict (key, label, type, default, section), auto-render the form. Adding a setting = one dict entry.
- [ ] **Theme accent color** — user-selectable accent (teal, blue, violet, orange) via CSS variable override.
- [ ] **Sync preferences** — auto-sync on startup (on/off), stale threshold (hours), sync schedule.

### Screener
- [ ] **Sector screener** — select sector → see all companies with key metrics (P/L, DY, ROE, market cap).
- [ ] **Filter + sort** — filter by P/L range, DY range, market cap range. Sort by any column.
- [ ] **Peer comparison** — side-by-side comparison of 2-5 tickers.

### Watchlist
- [ ] **Saved tickers** — SQLite-stored watchlist. Add/remove from the company page.
- [ ] **Watchlist view** — table with live KPIs for all watched tickers.

### Export
- [ ] **Download report** — "Download as HTML" button on each company page. Calls the existing `build_dashboard()` and serves the self-contained HTML.
- [ ] **Export to Excel** — export ratios table to .xlsx.

---

## 🔮 Planned (v4)

### Agent Integration
- [ ] **Agent chat tab** — embedded chat interface using the existing `/chat` + `/ws` endpoints. Talk to the LLM from the WebUI.
- [ ] **Task history** — list of recent agent tasks with status + result preview.

### Polish
- [ ] **Multiple themes** — solarized, midnight, high-contrast.
- [ ] **ES (Spanish) locale** — third language.
- [ ] **Mobile responsive** — sidebar collapses to hamburger menu, tables scroll horizontally.
- [ ] **Keyboard shortcuts** — `/` to focus search, `g d` to go to dashboard, etc.
- [ ] **Loading indicators** — HTMX `hx-indicator` spinners on all async requests.
- [ ] **Error toasts** — non-blocking error notifications.

---

## 🚫 Deferred / Out of Scope

- **User authentication / multi-user** — the WebUI is a local single-user tool. The gateway's Bearer token is sufficient. Don't add user registration, sessions, or RBAC.
- **Real-time price streaming** — prices are daily (COTAHIST) or 15-min delayed (brapi). Don't build a real-time price feed — poll on page load.
- **Custom chart builder** — Chart.js with predefined configs is enough. Don't build a drag-and-drop chart builder.
- **Plugin system** — the page registry is a simple list of dicts. Don't build a plugin system until there are 5+ toolset pages.
- **Offline PWA** — the WebUI requires a server connection (SQLite DBs are local, but the Python server must run). Don't build a Progressive Web App.
