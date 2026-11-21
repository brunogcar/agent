<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Roadmap

> What's built, what's next, and what's deferred for the Brazilian Financial Data WebUI.

---

## ✅ Built (v1 → v1.7)

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
- [x] **[v1.7] Adapter contract + registry** — `webui/adapters/` formalizes the section-payload pattern (Valuation v1.4 / Proventos v1.6): every lazy subtab is registered under a `"<family>:<sub>"` key and served by ONE generic endpoint (`GET /api/webui/company/{ticker}/sections/{key}`). Contract validation at dispatch time (violations logged + `_contract_violations` attached). Memoized service singletons shared by routes and dispatch (one PriceService = one OHLCV cache). All 15 existing subtabs registered; per-family endpoints remain as aliases.
- [x] **[v1.7] Pre-flight checks** — `PreflightService` + `/api/webui/preflight` (JSON) + `/panel` (Sync page card: Diagnóstico do Sistema, with "Verificar novamente") + `/banner` (Dashboard one-liner). Per-DB existence/size/expected-schema/WAL/`MAX(rowid)` row sanity (26 DBs across cvm/b3/bcb/ddm), sync coverage, vendor assets, Python/disk/write access, adapter registry integrity, launch config. Side-effect free (resolves the memory root without mkdir).

### Pages
- [x] Dashboard (`/webui/`) — market overview, quick links, sync ribbon (HTML since v1.5)
- [x] Company (`/webui/company/{ticker}`) — header + 4 tabs
- [x] Macro (`/webui/macro`) — placeholder
- [x] Sync (`/webui/sync`) — freshness table + pre-flight panel (v1.7) + Sincronizar buttons + live SSE log
- [x] Settings (`/webui/settings`) — theme + language dropdowns

### Company Tabs
- [x] Visão Geral — company header (identity card) + registration tables + activity description + candlestick chart (7 range options, Ctrl+wheel zoom)
- [x] Preço — 5 lazy subtabs: Cotação (tables + Histograma + Início vs Fim), Indicadores (RSI/MACD/Stochastic/OBV/ADX/CCI/Williams %R), Volatilidade (Bollinger Bands + rolling vol), Volume (volume bars + trade count + contracts), Fibonacci (global dropdowns + COMPRA/VENDA + dividend adjustments)
- [x] Financeiro — Visão Geral (TTM + Trajetória + WACC/DuPont/Altman + Red Flags) + Demonstrações (all 5 statements, one fetch, per-statement charts)
- [x] Valuation — Visão Geral / Múltiplos (nested subtabs + 5Y histories) / Valor Intrínseco / Fundamentos (nested subtabs) / Todas as métricas
- [x] **[v1.6] Proventos** — complete corporate-actions view: Histórico (every cash_dividends row, type pills + year filter + sortable columns + yield at ex-date + upcoming-payments + corporate actions + subscriptions), Visão Geral (6 KPIs + stacked annual + monthly seasonality + yield TTM history), Anual (per-ex-year aggregation + DVA declarado). ISIN dedupe across share classes. Renamed from "Dividends" (covers dividendos, JCP, rendimentos, bonificações, desdobramentos, grupamentos, subscrições).
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
- [x] Cache-busting (?v=40 on static URLs, ?_t= on API fetch)
- [x] Price service (ohlcv_with_mas, price_data, indicators, volatility, volume, fibonacci)
- [x] Chart.js zoom plugin + Hammer.js (vendored locally)
- [x] [v1.5] Chart lifecycle: destroy on HTMX cleanup + before re-renders (no leaks)
- [x] [v1.5] Lazy subtabs everywhere (Preço/Financeiro/Valuation — active subtab only)
- [x] [v1.5] Shared 60s-TTL OHLCV cache (4 Preço subtabs = 1 DB scan)
- [x] [v1.5] pt-BR number formatting (Intl.NumberFormat, thousands separators)
- [x] [v1.7] Valuation + Proventos loaders fetch through the generic `/sections/{key}` endpoint (adapter dispatch path)

---

## 🔄 Next Up

### v1.7.1 — Data fix
- [ ] **Quarterly balanços (trimestral)** — Demonstrações > `Período: trimestral` shows all 4 quarters of each year with the same balance-sheet values. Root cause: BPA/BPP ITR rows are snapshots (`DT_INI_EXERC` empty) so `compute_meses` stamps them all `meses=12` — quarter-end balances collide in one bucket and `_snap()` carries the year-end value forward. Fix in the CVM layer (query/migration re-key on `data_fim_exerc`) + audit every snapshot consumer (bpa/bpp engines' `meses IN (3,6,9)` ITR lookups, TTM balances, Altman Z, red flags, Valuation > Fundamentos).

### v1.7.2 — Valuation gap fill
- [ ] **Preço / EBIT-EBITDA / Menos Comuns subtabs** — add the missing charts/tables vs the static dashboard reference.

### v1.8 — Feature wave (built on the v1.7 adapter registry)

#### Company Tabs
- [ ] **Options tab**
- [ ] **Insider tab**
- [ ] **Shareholders tab**
- [ ] **Historical tab** — 5Y price chart with overlays (P/L bands, Graham Number, moving averages), metric time series (revenue, earnings, margins). Reuse `skills/cvm/historical/` engines.

#### Screener
- [ ] **Sector screener** — select sector → see all companies with key metrics (P/L, DY, ROE, market cap).
- [ ] **Filter + sort** — filter by P/L range, DY range, market cap range. Sort by any column.
- [ ] **Peer comparison** — side-by-side comparison of 2-5 tickers.

#### Macro Page
- [ ] **BCB SGS indicators** — Selic, IPCA, CDI, PIB, exchange rates. Time series charts.
- [ ] **Focus Bulletin** — market expectations (median, high, low) for IPCA, PIB, Selic, exchange rate. Table + chart.
- [ ] **Macro dashboard** — ribbon of key indicators on the dashboard page.

### Polish
- [ ] **i18n honesty pass** — externalize app.js strings via a `window.I18N` dump OR document pt-BR as the content language and keep en-US for the shell.
- [ ] **Accessibility** — `role=tab`/`aria-selected` on tab buttons, aria-labels on charts, keyboard nav on the search dropdown (blur/Escape dismissal).
- [ ] **Mobile** — sidebar hamburger, `overflow-x` on wide tables, touch pan on charts.

---

## 🔮 Planned (v2)

### Macro Page
- [ ] **BCB SGS indicators** — Selic, IPCA, CDI, PIB, exchange rates. Time series charts.
- [ ] **Focus Bulletin** — market expectations (median, high, low) for IPCA, PIB, Selic, exchange rate. Table + chart.
- [ ] **Macro dashboard** — ribbon of key indicators on the dashboard page.
- [ ] **acoes dashboard**
- [ ] **dividends dashboard**
- [ ] **fluxo dashboard**
- [ ] **index dashboard**
- [ ] **inflation dashboard**
- [ ] **juros dashboard**
- [ ] **poupanca dashboard**
- [ ] **PETR4_index (indices ibov) dashboard**

## 🔮 Planned (v3)

### Settings (auto-generated)
- [ ] **Settings as data** — SDNext-style schema-driven settings page. Define settings as a dict (key, label, type, default, section), auto-render the form. Adding a setting = one dict entry.
- [ ] **Theme accent color** — user-selectable accent (teal, blue, violet, orange) via CSS variable override.
- [ ] **Sync preferences** — auto-sync on startup (on/off), stale threshold (hours), sync schedule.

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
