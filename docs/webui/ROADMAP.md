<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Roadmap

> What's built, what's next, and what's deferred for the Brazilian Financial Data WebUI.
>
> **[v1.20] Pruned** — the completed per-feature essays moved to the
> CHANGELOG's version table (one topic summary each); this file now carries
> only the shape of what exists and what's still open.
>
> **[v1.21]** — Carteira shipped; the v2 Watchlist items landed inside it
> (watched accounts + watchlist tickers on the Painel).

---

## ✅ Built (v1 → v1.22)

### The app today

- **Painel** (`/webui`) — the Brazil one-screen landing: SGS KPI row (Selic · TR · IPCA mês · IPCA 12m · IGP-M mês · IGP-M 12m · USD/BRL) + 6 ranked ticker cards (Top 10 IBOV/SMLL, Mais Negócios, **Maiores Volumes (R$)**, Altas, Baixas), every row a company-page link; **⭐ Tickers Observados** (own box) + **💼 Minhas Carteiras** (contas grouped by user, [v1.21 fix 1]); compact sync box + pre-flight banner at the bottom. [v1.19, v1.21]
- **Carteira** (`/webui/carteira`) — the portfolio: the 👥 usuários → 👤 contas → 🏦 conta drill-down (user/account cards with live totals — sums never across users), transações de compra/venda (BR-standard form, shorts 🚨 / bonificações ⚠️, quick ✅/❌ per position) → PM positions (preço médio brasileiro); ticker metadata from CVM; watched accounts + tickers surface on the Painel (grouped by user). [v1.21 + fix 1]
- **Company page** (`/webui/company/{ticker}`) — identity card + 8 tabs: Visão Geral (candlestick 7 ranges, Ctrl+wheel zoom), Preço (5 subtabs), Financeiro (TTM + waterfall + all 5 Demonstrações), Valuation (5 subtabs), Proventos, Opções, Acionistas, Insiders. [v1.1–v1.10]
- **Macro** (`/webui/macro`) — BCB SGS + Focus in 8 lazy subtabs. [v1.11]
- **Mercado** (`/webui/mercado`) — the DDM families: Focus, Fluxo, Índices, Inflação, Juros, Ações (with the stocks_history evolution store), Proventos (BDR split). [v1.12–v1.18]
- **Sincronização** (`/webui/sync`) — freshness table, per-source buttons ("Sincronizar tudo" = stale only), live SSE log, pre-flight diagnostics panel. [v1, v1.5, v1.7]
- **Configurações** (`/webui/settings`) — schema-driven form (see below). [v1.20]
- **System log drawer** — the 📜 top-bar button; a right-side panel on every page with the live request/sync/error tail. [v1.20]

### Architecture decisions that hold

- One process, one port (`python webui.py`) — the WebUI mounts on the existing FastAPI gateway
- Service layer over the skill engines (direct imports; **no forked numerics** — shared helpers)
- Adapter contract + registry (`webui/adapters/`) — every lazy subtab a `<family>:<sub>` key behind ONE generic endpoint per scope (company / macro / mercado)
- SSE, not WebSocket (sync stream + system log stream)
- Pure-ASGI request logging middleware (SSE-safe), threadpool `def` handlers
- Vendored JS (HTMX + Alpine + Chart.js, no CDN), no build step
- CSS variables 3-layer theme system; JSON i18n (shell bilingual, content pt-BR)
- Security posture: loopback-only by default (LAN = `WEBUI_ALLOW_LAN=1`), ticker regex at every company route (ONE definition, `webui/validators.py` [v1.22] — B3SA3/BDRs pass), allow-lists for tabs/adapters, reflected-XSS closed; [v1.22] CSRF guard on every router (`CrossSiteGuardMiddleware` — cross-site mutations rejected, JSON-only bodies) + NaN/±inf rejected at the numeric boundary
- **Settings as data** [v1.20] — one dict entry in `webui/services/settings.py` SCHEMA = a new setting (form auto-renders; storage `memory_db/webui_settings.json`); sync preferences (auto-sync at boot, stale threshold, periodic schedule), Painel knobs, theme/locale, log level/buffer — all wired, no dead knobs
- **System log** [v1.20] — one in-memory ring buffer (`webui/services/syslog.py`) fed by three capture paths (request middleware, root-logger handler, explicit points); SSE while the drawer is open, 15s poll + unseen-error badge while closed
- **Carteira store** [v1.21] — `memory_db/webui_portfolio.json` (users/accounts/txs/watchlist/ticker-metadata; the settings.py storage pattern) + the PM engine and `quotes_for()` quote enrichment in `webui/services/portfolio.py`; CRUD validated all-or-nothing (PT-BR per-field errors; sells free to short — the replay never rejects, it computes). [v1.22] deterministic replay — `(date, created_at, seq)` order, seq a monotonic insertion counter backfilled for pre-v1.22 files; shorts count in the totals; corrupt-store quarantine + `.bak` + PT-BR 503 writes-refusal (the store never wipes); flip fee split; mixed long+short PM "—"; cross-user tx moves blocked; edit/delete short-open warnings; regression tests (`tests/webui/test_portfolio_engine.py`) — the money engine never gets touched again without them

---

## 🔄 Next Up

### Carteira — the money roadmap (the 4-review feature picks, rough value order)
- [ ] **Broker CSV import** — preview + dedup + dry-run: paste/upload a broker export (CEI/B3, XP, Clear…) and see the transactions it WOULD create before anything is written. The onboarding killer feature — every one of the 4 adversarial reviews picked it first. Natural fit: the Gerenciar modal, staged as a table + diff against existing txs (same-second dedup via `seq`).
- [ ] **Proventos per position / yield-on-cost** — dividends received per position over its holding period, DY on cost basis; the data is two joins away (carteira txs × dividends.db events by ticker + ex-date inside the position window).
- [ ] **IR/DARF helper** — swing-trade × day-trade split (same-day buys+sells = day), the R$ 20k monthly exemption rule, per-month realized totals + darf estimate per owner. Pure replay arithmetic over the existing store.
- [ ] **Performance: TWR/XIRR vs CDI/IBOV** — money-weighted (XIRR over the tx cashflows) and time-weighted returns, benchmarked against CDI (juros.db) and IBOV (indexes.db) over the same window; the patrimônio evolution curve (replay the book to every date × quote map — the engine already computes per-tx state).
- [ ] **Corporate actions ingestion** — splits / bonificações / grupamentos as a tx type that re-bases quantities and PM without a synthetic trade (today a bonificação is a manual buy at R$ 0,00; a 2:1 split needs editing every earlier tx).
- [ ] **Allocation & concentration** — per-setor/per-ticker concentration table (the CVM sector cache already lands in the store); alerts (price thresholds via the quote map); what-if simulator ("sell X at Y" → resulting KPIs without writing).
- [ ] **Ledger polish** — pagination + filters on the transações table (the 200-cap keeps the newest), undo toast after every mutation (delete/edit), export/restore the store JSON in Gerenciar, per-symbol quote dates ("cotação de 21/11" when the paper is illiquid), gross long/short exposure KPIs, "Lucro hoje" → "Lucro não realizado" relabel, position-detail drawer (the full PM ladder per ticker).
- [ ] **Engine perf/precision** — threadpool `def` mutation handlers (the async mutation path holds the event loop during the atomic write), QuoteSet immutability, replay memoization (invalidate on mutation), Decimal reconciliation at the store boundary (float today — fine at B3 magnitudes, but the day someone types a 17-digit quantity…). After correctness lands — never before.

### Company Tabs
- [ ] **Historical tab** — 5Y price chart with overlays (P/L bands, Graham Number, moving averages), metric time series (revenue, earnings, margins). Reuse `skills/cvm/historical/` engines.

### Screener
- [ ] **Sector screener** — select sector → all companies with key metrics (P/L, DY, ROE, market cap).
- [ ] **Filter + sort** — by P/L range, DY range, market cap range.
- [ ] **Peer comparison** — side-by-side of 2-5 tickers.

### Polish
- [ ] **Theme accent color** — user-selectable accent (teal, blue, violet, orange) via CSS variable override; pairs naturally with the v1.20 settings schema.
- [ ] **i18n honesty pass** — externalize app.js strings via a `window.I18N` dump OR document pt-BR as the content language and keep en-US for the shell.
- [ ] **Accessibility** — `role=tab`/`aria-selected` on tab buttons, aria-labels on charts, keyboard nav on the search dropdown.
- [ ] **Mobile** — sidebar hamburger (the sidebar renders open and squeezes content on every page at 390px today), `overflow-x` on wide tables, touch pan on charts.

---

## 🔮 Planned (v2)

### Watchlist
- [x] ~~**Add-from-company-page** — a ⭐ button on the company page feeding the Carteira watchlist~~ **SHIPPED in v1.21 fix 1** (⭐ in the company tab bar, every tab; also ⭐ toggles on the account cards).

### Export
- [ ] **Download report** — "Download as HTML" on each company page (reuse `build_dashboard()`).
- [ ] **Export to Excel** — export ratios table to .xlsx.

### Data
- [ ] **ddm poupança** — the last DDM indicator without a Mercado family (same recipe as v1.12–v1.18).

---

## 🔮 Planned (v3)

### Agent Integration
- [ ] **Agent chat tab** — embedded chat using the existing `/chat` + `/ws` endpoints.
- [ ] **Task history** — recent agent tasks with status + result preview.

### Polish
- [ ] **Multiple themes** — solarized, midnight, high-contrast.
- [ ] **ES (Spanish) locale** — third language.
- [ ] **Keyboard shortcuts** — `/` to focus search, `g d` to go to dashboard.
- [ ] **Loading indicators** — HTMX `hx-indicator` spinners on all async requests.
- [ ] **Error toasts** — non-blocking error notifications.

---

## 🚫 Deferred / Out of Scope

- **User authentication / multi-user** — the WebUI is a local single-user tool. The gateway's Bearer token is sufficient.
- **Real-time price streaming** — prices are daily (COTAHIST). Poll on page load; don't build a real-time feed.
- **Custom chart builder** — Chart.js with predefined configs is enough.
- **Plugin system** — the page registry is a simple list of dicts. Don't build one until there are 5+ toolset pages.
- **Offline PWA** — the Python server must run; don't build a Progressive Web App.
- **Persistent log file** — the system log is an in-memory tail by design (what happened since boot). A rotating file is a `logging` config change, not a WebUI feature.
