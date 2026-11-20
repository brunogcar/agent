<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Roadmap

> What's built, what's next, and what's deferred for the Brazilian Financial Data WebUI.

---

## ✅ Built (v1 → v1.5)

### Architecture
- [x] Single-command entry point (`python webui.py`)
- [x] One process, one port (extends existing FastAPI gateway)
- [x] SQLite WAL mode for concurrent read/write
- [x] Service layer between routes and calculation engines
- [x] Direct engine imports (bypasses MCP dispatcher)
- [x] SSE for sync progress (not WebSocket) — working end-to-end since v1.5
- [x] CSS variables 3-layer theme system (JSON theme files)
- [x] JSON i18n (not gettext)
- [x] Vendored JS (HTMX + Alpine + Chart.js, no CDN)
- [x] [v1.5] Ticker regex validation at every company route (422 on garbage)
- [x] [v1.5] TrustedHostMiddleware loopback-only (LAN = `WEBUI_ALLOW_LAN=1`)
- [x] [v1.5] Threadpool route handlers (plain `def` — event loop never blocks)
- [x] [v1.5] Shared Jinja env (`webui/templating.py`, `__file__`-relative)

### Pages
- [x] Dashboard (`/webui/`) — market overview, quick links, sync ribbon (HTML since v1.5)
- [x] Company (`/webui/company/{ticker}`) — header + 4 tabs
- [x] Macro (`/webui/macro`) — placeholder
- [x] Sync (`/webui/sync`) — freshness table + Sincronizar buttons + live SSE log
- [x] Settings (`/webui/settings`) — theme + language dropdowns

### Company Tabs
- [x] Visão Geral — company header (identity card) + registration tables + activity description + candlestick chart (7 range options, Ctrl+wheel zoom)
- [x] Preço — 5 lazy subtabs: Cotação (tables + Histograma + Início vs Fim), Indicadores (RSI/MACD/Stochastic/OBV/ADX/CCI/Williams %R), Volatilidade (Bollinger Bands + rolling vol), Volume (volume bars + trade count + contracts), Fibonacci (global dropdowns + COMPRA/VENDA + dividend adjustments)
- [x] Financeiro — Visão Geral (TTM + Trajetória + WACC/DuPont/Altman + Red Flags) + Demonstrações (all 5 statements, one fetch, per-statement charts)
- [x] Valuation — Visão Geral / Múltiplos (nested subtabs + 5Y histories) / Valor Intrínseco / Fundamentos (nested subtabs) / Todas as métricas
- [ ] Dividends — DPA history + dividend events (buttons hidden until shipped)
- [ ] Historical — 5Y price + ratio charts (buttons hidden until shipped)

### Features
- [x] Ticker search (HTMX debounced keyup, wildcard-escaped, relevance-ranked since v1.5)
- [x] Company header (identity card — persistent across all tabs)
- [x] Candlestick chart (OHLCV + MM20/50/100/200, Ctrl+wheel zoom, Shift+drag pan, 7 ranges)
- [x] Theme toggle (dark/light, cookie is the single source of truth)
- [x] Language switcher (pt-BR/en-US — shell only; content is pt-BR)
- [x] Sidebar collapse (persists in localStorage since v1.5) + current-page highlight
- [x] Favicon (SVG bar-chart icon)
- [x] Sync status (freshness table with badges, auto-refresh)
- [x] SSE sync stream (live progress events — native EventSource since v1.5)
- [x] Per-source "Sincronizar" buttons (dedupe: one running job per source)
- [x] Cache-busting (?v=37 on static URLs, ?_t= on API fetch)
- [x] Price service (ohlcv_with_mas, price_data, indicators, volatility, volume, fibonacci)
- [x] Chart.js zoom plugin + Hammer.js (vendored locally)
- [x] [v1.5] Chart lifecycle: destroy on HTMX cleanup + before re-renders (no leaks)
- [x] [v1.5] Lazy subtabs everywhere (Preço/Financeiro/Valuation — active subtab only)
- [x] [v1.5] Shared 60s-TTL OHLCV cache (4 Preço subtabs = 1 DB scan)
- [x] [v1.5] pt-BR number formatting (Intl.NumberFormat, thousands separators)

---

## 🔄 Next Up (v1.6)

### Company Tabs (finish the set)
- [ ] **Dividends tab** — DPA history table, annual bar chart, yield history line chart, payout trend. Reuse `data_sources/b3/dividends/` + `skills/cvm/calculations/engines/dividends.py`.
- [ ] **Historical tab** — 5Y price chart with overlays (P/L bands, Graham Number, moving averages), metric time series (revenue, earnings, margins). Reuse `skills/cvm/historical/` engines.

### Macro Page
- [ ] **BCB SGS indicators** — Selic, IPCA, CDI, PIB, exchange rates. Time series charts.
- [ ] **Focus Bulletin** — market expectations (median, high, low) for IPCA, PIB, Selic, exchange rate. Table + chart.
- [ ] **Macro dashboard** — ribbon of key indicators on the dashboard page.

### Polish
- [ ] **i18n honesty pass** — externalize app.js strings via a `window.I18N` dump OR document pt-BR as the content language and keep en-US for the shell.
- [ ] **Accessibility** — `role=tab`/`aria-selected` on tab buttons, aria-labels on charts, keyboard nav on the search dropdown (blur/Escape dismissal).
- [ ] **Mobile** — sidebar hamburger, `overflow-x` on wide tables, touch pan on charts.

---

## 🔮 Planned (v2)

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
