<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Roadmap

> What's built, what's next, and what's deferred for the Brazilian Financial Data WebUI.

---

## ✅ Built (v1 → v1.12)

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
- [x] **[v1.7.1] ITR snapshot re-key** — quarterly balanços fixed at the DATA layer: the sync engine re-keys each filing's BPA/BPP rows into the quarter bucket reported by its own flow rows (fiscal-year filers included; Dec filings stay 12); existing DBs migrate via `python -m tools.migrations.rekey_itr_snapshots --apply` (batched UPDATE + WAL checkpoint + engine-cache wipe — fingerprints don't change with a re-key). `PRAGMA user_version=2` is the marker; the pre-flight itr.db row warns "re-key pendente" until it runs. Zero query-layer changes — every consumer (`_snap`, bpa/bpp engines, TTM balances, Altman Z, liquidity ratios, Valuation > Fundamentos) was already written for the correct semantics and heals as soon as the data is re-keyed.

### Pages
- [x] Dashboard (`/webui/`) — market overview, quick links, sync ribbon (HTML since v1.5)
- [x] Company (`/webui/company/{ticker}`) — header + 4 tabs
- [x] Macro (`/webui/macro`) — 8 lazy subtabs over BCB SGS + Focus (v1.11; was a placeholder since v1)
- [x] Mercado (`/webui/mercado`) — the DDM dashboards' home: family pills + subtabs, Focus family first (v1.12)
- [x] Sync (`/webui/sync`) — freshness table + pre-flight panel (v1.7) + Sincronizar buttons + live SSE log
- [x] Settings (`/webui/settings`) — theme + language dropdowns

### Company Tabs
- [x] Visão Geral — company header (identity card) + registration tables + activity description + candlestick chart (7 range options, Ctrl+wheel zoom)
- [x] Preço — 5 lazy subtabs: Cotação (tables + Histograma + Início vs Fim), Indicadores (RSI/MACD/Stochastic/OBV/ADX/CCI/Williams %R), Volatilidade (Bollinger Bands + rolling vol), Volume (volume bars + trade count + contracts), Fibonacci (global dropdowns + COMPRA/VENDA + dividend adjustments)
- [x] Financeiro — Visão Geral (TTM + **Conversão da Receita em Lucro waterfall [v1.7.1]** — Anual/Trimestral toggle, client-derived from the overview payload + Trajetória + WACC/DuPont/Altman + Red Flags) + Demonstrações (all 5 statements, one fetch, per-statement charts; **quarterly balanço shows real Mar/Jun/Sep period-end values since the v1.7.1 re-key**)
- [x] Valuation — Visão Geral / Múltiplos (nested subtabs + per-group 5Y history charts + side-by-side layout since v1.7.2) / Valor Intrínseco / Fundamentos (nested subtabs) / Todas as métricas
- [x] **[v1.6] Proventos** — complete corporate-actions view: Histórico (every cash_dividends row, type pills + year filter + sortable columns + yield at ex-date + upcoming-payments + corporate actions + subscriptions), Visão Geral (6 KPIs + stacked annual + monthly seasonality + yield TTM history), Anual (per-ex-year aggregation + DVA declarado). ISIN dedupe across share classes. Renamed from "Dividends" (covers dividendos, JCP, rendimentos, bonificações, desdobramentos, grupamentos, subscrições).
- [x] **[v1.7.2] Múltiplos parity** — Preço (P/L,LPA,P/VP,VPA + Múltiplos de Preço dual-axis histories | Múltiplos + Per-share tables | Comparativos), EBIT/EBITDA (EBIT + EBITDA history charts | tables), Menos Comuns (Preço/Balanço + Ativo/Preço histories + table); Tudo/10A/…/1M range bar on every history chart (client-side filter).
- [x] **[v1.8] Opções** — the static options dashboard reorganized: Visão Geral (6 KPIs + dual-axis P/C Ratio + Últimas Observações | Resumo CALL vs PUT + OI walls), Cadeia (maturity pill bar + Calls | Puts side by side, top-30 by volume, sortable), Volume & Exercícios (merged), Vol. Implícita (smile + term-structure heatmap capped to ±25% spot × 8 expiries), Posições (CALL/PUT split, top-50 by OI, sortable). Same data layer as the skill's static report; maturity pills refetch server-side; generic table click-sort added to the shared renderer. **[fix1]** Datas no padrão brasileiro: dd/mm/yyyy nas tabelas (Data/Vencimento) e refs de texto; eixos + tooltips de TODOS os gráficos com labels ISO (P/C, Exercícios e os históricos 5A do Valuation) formatados pelo `renderValChart`; colunas de data ordenáveis cronologicamente (`_valSortKey` parseia dd/mm/yy[yy]).
- [x] **[v1.9] Acionistas** — the static shareholders dashboard reorganized: Visão Geral (6 KPIs + evolução do free float + evolução de acionistas PF/PJ/Inst. empilhados + Mercado|Patrimônio blocks + top-5 preview), Posição Acionária (tabela completa com % ON \| % PN \| % Total lado a lado + CPF/CNPJ mascarado, sortable, cap 60 + doughnut top-5 com disambiguação de nomes duplicados e fatia de remanescente clamped), Free Float (7 KPIs + os dois charts de evolução + tabela de TODOS os períodos — o estático mostrava uma única linha), Estrutura Patrimonial (6 KPIs BPP + Composição bar + Evolução PL/Capital line + tabela de todos os exercícios em BRL compacto + Capital Social FRE). Same data layer as the skill's static report (fre.db + dfp.db); degradação por fonte; `renderValChart` honra cutout do server (doughnut).
- [x] **[v1.10] Insiders** — the static insider dashboard reorganized (reference: `PETR4_insider_dashboard.html` / `skills/cvm/insider`; data: VLMO vlmo.db): Visão Geral (6 KPIs — Sentimento/Volume Comprado/Volume Vendido/Net Volume/Transações na janela de 24 meses + Última Movimentação + chart de volume líquido mensal com labels BR `jun/2026` + preview das 20 últimas movimentações), Movimentações (volume líquido acumulado em linha ACIMA da tabela, sobre a janela inteira — o estático desenhava sobre 10 pontos — + as 120 mais recentes, sortable), Por Cargo (agregado por Tipo_Cargo em TODO o histórico, Net Volume formatado em fmt_brl — o estático exibia floats crus — + barras comprado vs vendido + KPIs de maior comprador/vendedor líquido), Mensal (chart de net mensal verde/vermelho ACIMA da tabela + 24 meses com Mês em label BR `jun/2026`, sortable + KPIs de melhor/pior mês). **Engine fix**: `_query_by_role`/`_query_summary` do VLMO agora agregam por prefixo (`LIKE 'Compra%'/'Venda%'`) — o match exato perdia os "Compra à vista"/"Venda à vista" (o estático mostrava 2026-06 com R$ 0,00 apesar de ~R$ 1,4 bi em vendas na própria tabela de transações). **Sort fix (global)**: `_valSortKey` stripa o marcador de tooltip ⓘ da célula ("03/11/2026 ⓘ" não casava o regex de data ancorado → datas em sort lexicográfico, não cronológico) e parseia labels de mês BR (`jun/2026`), `YYYY-MM` e BRL compacto (`R$ 4,27 bi` → 4,27e9) cronologicamente/numericamente. Same data layer as the skill's modes; `_error` PT-BR aponta a fonte `vlmo`.
- [ ] Historical — 5Y price + ratio charts (buttons hidden until shipped)

### Macro Page
- [x] **[v1.11] Macro** — the static macro dashboard reorganized (reference: `macro_dashboard.html` / `skills/bcb/macro`; data: `sgs.db` + `focus.db`): the LANDING subtab carries only what is general (the static's "Indicadores Atuais" — 4 KPIs + the 12-series current table with computed IPCA/IGP-M acumulado 12m); every specific view is its own lazy subtab — Juros (Selic/CDI/Meta Copom in ONE % a.a. chart — the static shipped 5 near-duplicates — + TR + Selic acumulada + monthly tables ANNUALIZED), Inflação (IPCA vs IGP-M mensal + acumulado 12m, one chart per question), Câmbio (ptax diária + média mensal + máx/mín 12m), Atividade (PIB nominal trimestral em R$ tri `T3 2026` + salário mínimo), Retorno Real (Fisher — real line joined to a monthly IPCA step), Expectativas Focus (mediana ± faixa min/max, IPCA/Selic/Câmbio, dedupe por rodada), Curva de Juros (Selic Focus por ano — forward-looking, sem range bar). Ticker-less dispatch (`takes_ticker`) + generic `GET /api/webui/macro/sections/{key}`; same data layer as the skill's query engines; degradation per fonte (`sgs`/`focus`). **PIB unit fix**: SGS 4380 catalog "R$ mil" → "R$ milhões" (the static read "R$ 1.165.623 mil" — R$ 1,17 bi per quarter, absurd for a country's GDP).

### Mercado Page
- [x] **[v1.12] Mercado — Focus family** — the new nav session for the DDM dashboards (dadosdemercado.com.br), next to Macro: family pills (Focus; dividends/índices/fluxo/inflação/juros as later families, hidden until shipped) + the family's subtabs. The static focus dashboard reorganized (reference: `focus_dashboard.html` / `skills/ddm/focus`; data: `memory_db/ddm/focus.db`): the LANDING subtab carries the general content (4 KPIs + o Boletim Focus, uma tabela por ano — the static's 4 year subtabs stacked); the 12 per-indicator tabs regrouped into 6 question-driven subtabs — Inflação (IPCA + IPCA Adm + IGP-M), Atividade (PIB), Juros (Selic), Câmbio, Setor Externo (Conta corrente + Balança + Investimento direto), Fiscal (Dívida líquida + Primário + Nominal) — each with a KPI card per indicator (Hoje do ano corrente, tooltip com todos os anos + comparação 4 semanas + respondentes — novo vs o estático) + grouped bar chart 3 janelas × 4 anos + tabela por ano sortable. Ticker-less dispatch reaproveitado do v1.11 (zero registry changes) + generic `GET /api/webui/mercado/sections/{key}`. **Unit map fix**: 5 nomes de indicadores faltavam no `_INDICATOR_UNITS` do skill — o estático renderizava "IPCA Adm 4,77" sem %, "Investimento direto no país 80.000,00" sem US$ mi (alias truncado nunca casava); corrigido na fonte (skill v1.1).

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
- [x] Cache-busting (?v=46 on static URLs, ?_t= on API fetch)
- [x] Price service (ohlcv_with_mas, price_data, indicators, volatility, volume, fibonacci)
- [x] Chart.js zoom plugin + Hammer.js (vendored locally)
- [x] [v1.5] Chart lifecycle: destroy on HTMX cleanup + before re-renders (no leaks)
- [x] [v1.5] Lazy subtabs everywhere (Preço/Financeiro/Valuation — active subtab only)
- [x] [v1.5] Shared 60s-TTL OHLCV cache (4 Preço subtabs = 1 DB scan)
- [x] [v1.5] pt-BR number formatting (Intl.NumberFormat, thousands separators)
- [x] [v1.7] Valuation + Proventos loaders fetch through the generic `/sections/{key}` endpoint (adapter dispatch path)

---

## 🔄 Next Up

### v1.8 — Feature wave (built on the v1.7 adapter registry)

#### Company Tabs
- [x] **Options tab** — shipped v1.8 (see Built). The recipe held: service + register() + shell partial + loader, zero api.py endpoint edits (only the maturity passthrough param).
- [x] **Insider tab** — shipped v1.10 (see Built).
- [ ] **Historical tab** — 5Y price chart with overlays (P/L bands, Graham Number, moving averages), metric time series (revenue, earnings, margins). Reuse `skills/cvm/historical/` engines.

#### Screener
- [ ] **Sector screener** — select sector → see all companies with key metrics (P/L, DY, ROE, market cap).
- [ ] **Filter + sort** — filter by P/L range, DY range, market cap range. Sort by any column.
- [ ] **Peer comparison** — side-by-side comparison of 2-5 tickers.

#### Macro Page (v1.11 shipped the BCB layer — see Built)
- [ ] **ddm-specific indicators** — next phase per the v1.11 plan: poupança, acoes, fluxo, index, inflation, juros, dividends dashboards (ddm data sources) as new macro subtabs.
- [ ] **Macro dashboard ribbon** — ribbon of key indicators on the dashboard page.

### Polish
- [ ] **i18n honesty pass** — externalize app.js strings via a `window.I18N` dump OR document pt-BR as the content language and keep en-US for the shell.
- [ ] **Accessibility** — `role=tab`/`aria-selected` on tab buttons, aria-labels on charts, keyboard nav on the search dropdown (blur/Escape dismissal).
- [ ] **Mobile** — sidebar hamburger, `overflow-x` on wide tables, touch pan on charts.

---

## 🔮 Planned (v2)

### Macro Page — ddm phase
- [ ] **ddm dashboards** — the ddm-specific indicators become macro subtabs (same recipe as the v1.11 BCB layer): acoes, dividends, fluxo, index, inflation, juros, poupanca.
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
