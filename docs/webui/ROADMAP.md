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
- **Mercado** (`/webui/mercado`) — the DDM families: Focus, Fluxo, Índices, Inflação, Juros, Poupança (the caderneta vs IPCA/CDI + its own matrix — v1.23), Ações (with the stocks_history evolution store), Proventos (BDR split). [v1.12–v1.18, v1.23]
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
- [x] ~~**Broker CSV import**~~ **SHIPPED in v1.22.2 as NOTA DE CORRETAGEM PDF IMPORT** (brokers give retail PDFs, not CSVs — validated against real XP ×2 layouts, modelo B3, BTG): upload → server-side dry-run preview (nothing written) → hand-map the specs without ticker (modelo B3) → ONE atomic bulk commit with dedup (CNPJ + nº nota + pregão — the same nota in two layouts is a duplicate) + ↩️ undo registry. Pro-rata fee allocation cent-exact; fracionário unifies with the lote padrão (KLBN4F → KLBN4). OCR/scanned PDFs are refused clearly, not silently empty.
- [x] ~~**Proventos per position / yield-on-cost**~~ **SHIPPED in v1.22.3** (🪙 Proventos view on the account page): the two joins made — carteira txs × dividends.db events with the ENTITLEMENT rule (position at the DATA COM: buys that day receive, sells that day don't; corp actions re-base the quantity first — the engine's own ladder walk). Per-ticker received/pending/YOC (yield sobre o custo atual), the full events table (R$/ação × qtd na data), JCP-bruto + short-pays-the-dividend notes. `webui/services/portfolio_provents.py`.
- [x] ~~**IR/DARF helper**~~ **SHIPPED in v1.22.2** (🧾 IR — mês a mês on the user page): swing × day-trade split with the day carve-out (matched same-day pairs never touch the custo médio), the R$ 20k monthly exemption, separate swing/day loss carry pools computed chronologically, IRRF estimates (0,005% swing / 1% day per account), 15%/20%, DARF 6015/6120 with due dates. A separate deterministic walk in `webui/services/ir_helper.py` — the PM engine stays untouched.
- [x] ~~**Performance: TWR/XIRR vs CDI/IBOV**~~ **SHIPPED in v1.22.3** (📈 Evolução view): the patrimônio evolution curve (book replayed to every month-end × the close of that date), TWR chained between cashflow dates (r = (V−CF)/V_prev — the cashflow executes at the day's close), XIRR by bisection over the tx flows + terminal value, CDI from the sgs daily series 12 (compounded per day; juros.db monthly as the fallback) and IBOV proxied by BOVA11 over the same window — all annualized on the same day count. `webui/services/portfolio_perf.py`.
- [x] ~~**Corporate actions ingestion**~~ **SHIPPED in v1.22.3**: the third tx type (🔀 evento corporativo — desdobramento/grupamento/bonificação with a factor): qty ×= f, PM ÷= f, custo total invariant; replays FIRST within its date (B3 ex-date semantics) in BOTH walks (the engine and the IR helper — pinned by the regression suite); the manual-buy-at-0 workaround and the edit-every-earlier-tx dance are dead.
- [x] ~~**Allocation & concentration**~~ **SHIPPED in v1.22.3** (🥧 Alocação view + 🔔 alertas + 🧪 Simular): per-setor doughnut + per-ticker weights over the LONG book, HHI (×10.000 antitrust scale) + maior posição/top-3 cards, the short book as its own exposure line; price alerts (one per ticker+condition, live evaluation against the quote map, triggered chips on the account page + management in Gerenciar); the what-if simulator — hypothetical sells/buys against the live PM, before/after KPIs, NOTHING written. `webui/services/portfolio_views.py`.
- [x] ~~**Ledger polish**~~ **SHIPPED in v1.22.3**: the transações view is its own paginated/filtered endpoint (GET /txs — ticker, tipo, janela de datas, busca; página 1 = as mais recentes), the ↩️ undo toast after every tx create/edit/delete (server-side restore registry, same id/seq on delete-undo), export/restore the store JSON in Gerenciar (validate-then-swap; the .bak is automatic), per-symbol quote dates (🕰️ "cotação de …" when the paper missed the last session), gross long/short exposure KPIs + totals, "Lucro hoje" → "Lucro não realizado" relabel everywhere, and the 🔍 position-detail drawer (the full PM ladder + proventos per ticker, per account).
- [x] ~~**Engine perf/precision**~~ **SHIPPED in v1.22.3**: mutations run via `run_in_threadpool` (the event loop never waits on the store lock + atomic write; the PDF parse too), the quote map is an immutable MappingProxyType (copy-then-swap publishes), the per-account replay is memoized on a store REVISION (bumped by every save/reload — a cached walk can never outlive its data), aggregates sum with math.fsum, and the store boundary RECONCILES every tx number (finite + magnitude caps; strings normalize; 1e999/inf → quarantine, the never-wipe posture).
- [x] ~~**The v1.22.3 shakedown (user reports)**~~ **SHIPPED in v1.22.4**: the evolução 500 root-caused (a sign-flipped TWR chain annualized into a COMPLEX number → json.dumps TypeError → plain-text 500 → "Erro: Unexpected token 'I'"; now `_annualize` refuses base ≤ 0, the report GETs answer JSON on ANY failure, and `api()` renders friendly PT-BR errors), the ticker filter is a PREFIX with datalist suggestions (the exact-match rule 400'd mid-keystroke and wiped the view), notas importadas moved into the Transações view, the company header walks a five-step fallback chain (FCA → CAD any-SIT → CAD by CD_CVM → bridge.db → B3 company_info — MBRF3/KLBN4-grade setor gaps self-heal, plus a once-per-boot metadata backfill), evolução gained BR month ticks + the IVVB11 (S&P 500, BRL) benchmark, the corp-event form flows event→factor with locked-0 qty/price + instructions (corp rows persist zeros), the 🔍 drawer got per-row ✏️ edit + click-outside/Esc close + post-edit refresh, and proventos events merge the DDM agenda as a second source (deduped, source-tagged). Pinned by `tests/webui/test_portfolio_v1224.py` (14 tests — 100/100 total).

### Company Tabs
- [x] ~~**Historical tab**~~ **SHIPPED in v1.24** (the company page's 8th tab, between Valuation and Proventos): the company vs its OWN 5A history — 4 subtabs reshaping the static dashboard's 9 tabs (Visão Geral = 6 KPIs + the direction-aware **Heatmap de Valoração — Indicadores Coloridos** + Tendência collapsed; Valuation 5A = P/L | P/VPA | EV/EBITDA | DY band charts side by side; Rentabilidade e Crescimento; Alavancagem e Risco + the point-in-time WACC/DuPont/Altman). ONE engine-cache-scoped build per ticker + 10-min TTL + month-end downsampling. `webui/services/historical.py` — 17 metrics via `skills/cvm/historical` engines.
- [x] ~~**Backtest tab**~~ **SHIPPED in v1.25** (the company page's 10th, last tab — the reading flow ends in simulation): the static PETR4_backtest_dashboard.html reborn as an INTERACTIVE simulator — 8 strategies with editable thresholds (the static's 6 fundamental + ma_cross + buy_hold), engine params (período presets clamped to the ticker's range, capital, % posição, prazo máx., stop/take on close, corretagem, saída por reversão), the bdi=2 + per-date-dedupe price cleaning the static lacked, KPIs + equity × buy&hold + drawdown + price-with-trade-markers + trade log, and the Cenários manager (pin runs to localStorage, comparison table + overlaid equity curves, load-params-back). `webui/services/backtest.py` + `POST /backtest/run` (threadpool). Pinned by `tests/webui/test_backtest_v125.py` (20 tests).
- [x] ~~**Governança + Informações Periódicas tabs**~~ **SHIPPED in v1.26** (the company page's 11th+12th tabs, between Insiders and Backtest — TWO tabs, TWO purposes after the fix 1 split: "both provide info, but they are not supposed to be together"): **Governança** = CGVN, the Código de Melhores Práticas self-assessment (score KPIs, the FOUR-bucket donut incl. Não se Aplica, per-chapter stacked bars, the score EVOLUTION across the 9 annual protocolos, the 54-practice table with Exercício/Capítulo/Situação filters + expandable Explicação); **Informações Periódicas** = IPE, the event index (the faceted explorer — Categoria/Tipo/Espécie/Ano selects driven by the ticker's own data, cascading facets, AGO/AGE/Assembleias/Aviso/Fato Relevante/Calendário chips, busca, 25/page pagination, CVM links, reapresentação badges; the Ano select chronological since fix 1 — the count-ordered select the user reported). `webui/services/governance.py` + `webui/services/ipe.py` (the split) + `ipe.browse()`/`cgvn.filings()` (additive engine extensions) + GET /governance/practices + GET /ipe/events. Pinned by `tests/webui/test_governance_v126.py` (14 tests).

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
- [x] ~~**ddm poupança**~~ **SHIPPED in v1.23** (the last DDM indicator gets its Mercado family — between Juros and Ações, the renda fixa slot): Visão Geral = the comparison the static never drew (Poupança × IPCA — the real yield, month by month and at 12m — × CDI compounded to a 12-month return so all lines share one unit; the month table's Poupança − IPCA column colors the losing-to-inflation months red), Poupança = the per-index pattern (evolução 3 lines + matriz ano × mês WITH the Ano column the source page lacks + Histórico mensal COLLAPSED — the v1.23 convention now shared with Inflação and Juros, where the matrix moved ABOVE the histórico). `webui/services/poupanca.py` + the `collapsed` table-section flag in the generic renderer.

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
