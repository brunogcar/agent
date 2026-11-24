<- Back to [WebUI Overview](../WEBUI.md)

# 🏗️ WebUI Architecture

> File map, design decisions, and data flow for the Brazilian Financial Data WebUI.

Last updated: 2026-11-21 (v1.7 — adapter contract + registry + pre-flight checks)

---

## File Map

```text
agent/
├── webui.py                          # Single-command entry point (python webui.py)
├── core/
│   └── db_wal.py                     # SQLite WAL mode setup (concurrent read/write)
├── webui/                            # WebUI package
│   ├── __init__.py                   # Package marker
│   ├── app.py                        # FastAPI app factory (mounts routes + static + gateway)
│   ├── templating.py                 # ONE shared Jinja2Templates env (__file__-relative)
│   ├── adapters/                     # [v1.7] Section payload contract + subtab registry
│   │   ├── contract.py               # Payload/section shapes + builders + validation
│   │   └── registry.py               # "<family>:<sub>" registry + dispatch() + service singletons
│   ├── i18n.py                       # JSON-based i18n (t() function, locale negotiation)
│   ├── theme.py                      # CSS variable theme registry (JSON theme files)
│   ├── routes/                       # HTTP route modules
│   │   ├── pages.py                  # HTML page routes (/webui/*)
│   │   ├── api.py                    # JSON + HTMX partial routes (/api/webui/*)
│   │   ├── sync.py                   # SSE sync progress (/api/webui/sync/*)
│   │   ├── preflight.py              # [v1.7] Pre-flight checks (/api/webui/preflight/*)
│   │   └── system.py                 # [v1.20] System log + settings (/api/webui/logs|settings*)
│   ├── services/                     # Service layer (ONLY place that imports skills)
│   │   ├── company.py                # Company header + ratios + price series
│   │   ├── price.py                  # Preço tab (OHLCV, indicators, volatility, volume, Fibonacci)
│   │   ├── financials.py             # Financeiro tab (TTM overview + 5-statement single fetch)
│   │   ├── valuation.py              # Valuation tab (ratios mode + report-builder sections)
│   │   ├── proventos.py              # Proventos tab (dividends.db + yield at ex-date)
│   │   ├── options.py                # [v1.8] Opções tab (chain, activity, IV, positions)
│   │   ├── shareholders.py           # [v1.9] Acionistas tab (fre.db + dfp.db)
│   │   ├── insiders.py               # [v1.10] Insiders tab (vlmo.db)
│   │   ├── macro.py                  # [v1.11] Macro page (SGS numerics — shared by home.py)
│   │   ├── focus.py                  # [v1.12] Mercado Focus family
│   │   ├── fluxo.py                  # [v1.13] Mercado Fluxo family
│   │   ├── indexes.py                # [v1.14] Mercado Índices family
│   │   ├── inflation.py              # [v1.15] Mercado Inflação family
│   │   ├── juros.py                  # [v1.16] Mercado Juros family
│   │   ├── poupanca.py               # [v1.23] Mercado Poupança family (× IPCA × CDI)
│   │   ├── acoes.py                  # [v1.17] Mercado Ações family
│   │   ├── dividendos.py             # [v1.18] Mercado Proventos family (BDR split)
│   │   ├── home.py                   # [v1.19] Painel landing (SGS KPIs + 5 ranked cards, TTL memo)
│   │   ├── sync.py                   # Freshness check + background sync + SSE pub/sub + scheduler
│   │   ├── preflight.py              # [v1.7] Pre-flight checklist (DBs, system, adapters, config)
│   │   ├── settings.py               # [v1.20] Schema-driven settings store (webui_settings.json)
│   │   └── syslog.py                 # [v1.20] System log ring buffer + request middleware + logging handler
│   ├── templates/                    # Jinja2 templates
│   │   ├── base.html                 # Shell: sidebar + topbar + content area + 📜 log drawer
│   │   ├── pages/                    # Full HTML pages (extend base.html)
│   │   │   ├── dashboard.html        # [v1.19] Painel (KPI row + 5 cards + bottom sync box)
│   │   │   ├── company.html          # Company view (header + tabs)
│   │   │   ├── macro.html            # Macro indicators
│   │   │   ├── mercado.html          # Mercado page (family pills + subtabs)
│   │   │   ├── sync.html             # Sync status + pre-flight panel + SSE log
│   │   │   └── settings.html         # [v1.20] Schema-driven settings (JS-rendered form)
│   │   └── partials/                 # HTMX fragments (no <html> wrapper)
│   │       ├── search_results.html   # Ticker search dropdown
│   │       ├── identity_card.html    # Persistent identity header (all tabs)
│   │       ├── sync_status.html      # Freshness table (Sync page + Dashboard)
│   │       ├── sync_box.html         # [v1.19] Compact collapsed sync box (Painel bottom)
│   │       ├── preflight_panel.html  # [v1.7] Grouped checks card (Sync page)
│   │       ├── preflight_banner.html # [v1.7] One-line diagnosis (Dashboard)
│   │       ├── tab_visao_geral.html  # Visão Geral tab (reg tables + chart)
│   │       ├── tab_preco.html        # Preço tab shell (5 lazy subtabs)
│   │       ├── tab_financials.html   # Financeiro tab shell (2 lazy subtabs)
│   │       ├── tab_valuation.html    # Valuation tab shell (5 lazy subtabs)
│   │       ├── tab_proventos.html    # Proventos tab shell (3 lazy subtabs)
│   │       ├── tab_options.html      # [v1.8] Opções tab shell
│   │       ├── tab_shareholders.html # [v1.9] Acionistas tab shell
│   │       └── tab_insiders.html     # [v1.10] Insiders tab shell
│   ├── static/                       # Static assets (CSS, JS, vendor)
│   │   ├── favicon.svg               # Teal bar-chart icon
│   │   ├── css/app.css               # 3-layer token system + layout + components
│   │   ├── js/app.js                 # Tab/subtab loaders + generic section renderer + chart lifecycle
│   │   └── vendor/                   # Vendored JS (local, no CDN)
│   │       ├── htmx.min.js           # HTMX 2.0 (50 KB)
│   │       ├── alpine.min.js         # Alpine.js 3.x (44 KB)
│   │       ├── chart.umd.min.js      # Chart.js 4.4 (205 KB)
│   │       ├── hammer.min.js         # Hammer.js (touch gestures for chart zoom)
│   │       └── chartjs-plugin-zoom.min.js  # Zoom plugin (Ctrl+wheel, Shift+drag)
│   ├── themes/                       # Theme JSON files
│   │   ├── dark.json                 # Dark theme tokens
│   │   └── light.json                # Light theme tokens
│   └── locales/                      # i18n JSON files
│       ├── pt-BR.json                # Portuguese (default)
│       └── en-US.json                # English
└── docs/webui/                       # This documentation
```

## Source Code Reference

| File | Purpose |
|------|---------|
| `webui.py` | Entry point — parses CLI args, runs WAL setup, launches uvicorn |
| `core/db_wal.py` | Sets `PRAGMA journal_mode=WAL` on every SQLite DB at startup |
| `webui/app.py` | FastAPI app factory — mounts routes, static files, existing gateway; [v1.22] `CrossSiteGuardMiddleware` (pure ASGI, every router): cross-site mutations rejected (`Sec-Fetch-Site: cross-site` always; non-loopback `Origin` unless `WEBUI_ALLOW_LAN=1`) + JSON bodies must be `application/json` |
| `webui/adapters/contract.py` | [v1.7] Section payload contract — shapes, builders, validation |
| `webui/adapters/registry.py` | [v1.7] Subtab adapter registry + `dispatch()` + memoized service singletons |
| `webui/i18n.py` | JSON i18n — `t()` function, locale negotiation, `available_locales()` |
| `webui/theme.py` | Theme registry — `render_theme_css()`, `available_themes()` |
| `webui/services/company.py` | Company data — wraps `build_company_header()` + `compute_all_ratios()` |
| `webui/services/price.py` | Price data — wraps `ohlcv_series` + `compute_sma` + indicators + Bollinger + Fibonacci |
| `webui/services/financials.py` | Financeiro tab — TTM overview + all-5-statements single fetch |
| `webui/services/valuation.py` | Valuation tab — ratios mode + report-builder sections |
| `webui/services/proventos.py` | Proventos tab — dividends.db queries + yield at ex-date |
| `webui/services/home.py` | [v1.19] Painel landing — SGS KPI row (macro.py's numerics) + 5 ranked ticker cards over `market_snapshot()` (cotahist) + b3-index |
| `webui/services/sync.py` | Sync service — freshness check, background sync, SSE pub/sub |
| `webui/services/preflight.py` | [v1.7] Pre-flight checks — DB/schema/WAL/rows, sync coverage, system, adapters, config; [v1.7.1] itr.db re-key marker (`PRAGMA user_version`) |
| `webui/services/syslog.py` | [v1.20] System log — the in-memory ring buffer behind the 📜 drawer (request middleware + root-logger handler + explicit points) |
| `webui/services/settings.py` | [v1.20] Schema-driven settings — SCHEMA dict + JSON store (`memory_db/webui_settings.json`) |
| `webui/services/portfolio.py` | [v1.21] Carteira — users/accounts/txs/watchlist JSON store, the PM (preço médio) position engine, `quotes_for()` enrichment, CVM ticker-metadata cache; [v1.22] hardening — shorts in the totals, corrupt-store quarantine/.bak/PT-BR-503, deterministic replay `(date, created_at, seq)`, flip fee split, mixed-leg PM "—", cross-user move block, short-open warnings; [v1.22.2] notas registry (dedup + undo), alerts, the ledger pager/filters, the undo-toast registry, export/restore, per-symbol quote dates, gross long/short exposure, replay memoization (store-revision keyed), fsum aggregates, MappingProxyType quote map, threadpool mutations, tx reconciliation at the store boundary, the `corp` tx type (eventos corporativos — replays first within its date), the `_ticker_ladder` PM walk |
| `webui/services/portfolio_provents.py` | [v1.22.3] Proventos per position / yield-on-cost — the txs × dividends.db join with the DATA COM entitlement rule (the engine's ladder gives the quantity at any date; corp actions re-base first) + the position-detail drawer payload (per-account PM ladder + proventos) |
| `webui/services/portfolio_perf.py` | [v1.22.3] TWR/XIRR vs CDI/IBOV + the patrimônio evolution curve — price maps (cotahist, TTL-cached), the CDI daily series (sgs 12, juros.db monthly fallback), the BOVA11 IBOV proxy, XIRR by bisection |
| `webui/services/portfolio_views.py` | [v1.22.3] Allocation & concentration (per-setor/per-ticker weights over the long book, HHI) + the what-if simulator (hypothetical trades against the live PM — nothing written) |
| `webui/validators.py` | [v1.22] ONE ticker definition for every layer (`TICKER_RE` — digits in the stem, so B3SA3 and BDRs pass; option-shaped strings pass too — the documented price of B3SA3/A1MD34; unknown symbols simply get no quote) — a strict superset: the four drifted copies it replaced each rejected a different slice of B3 |
| `webui/services/acoes.py` | [v1.17] Mercado page / Ações family — the stocks_history evolution store + overview (DDM) |
| `webui/services/dividendos.py` | [v1.18] Mercado page / Proventos family — overview, por empresa, calendário, BDR split (DDM) |
| `webui/services/fluxo.py` | [v1.13] Mercado page / Fluxo family — B3 investment flow: overview, mensal, anual, por investidor (DDM) |
| `webui/services/focus.py` | [v1.12] Mercado page / Focus family — Boletim Focus: juros, inflação, câmbio, atividade, fiscal, externo (DDM) |
| `webui/services/indexes.py` | [v1.14] Mercado page / Índices family — IBOV, SMLL, IDIV, IFIX, BDRX (b3-index) |
| `webui/services/inflation.py` | [v1.15] Mercado page / Inflação family — IPCA, IGP-M, INPC (DDM) |
| `webui/services/insiders.py` | [v1.10] Company Insiders tab — CVM insider trading: transações, mensal, por cargo |
| `webui/services/juros.py` | [v1.16] Mercado page / Juros family — Selic, CDI, meta Selic (DDM) |
| `webui/services/poupanca.py` | [v1.23] Mercado page / Poupança family — the caderneta vs IPCA/CDI (12m compounded) + the per-index view with matrix-before-collapsed-histórico (DDM) |
| `webui/services/macro.py` | [v1.11] Macro page — BCB SGS + Focus in 8 lazy subtabs; home.py imports its numerics (the no-forked-numerics rule) |
| `webui/services/options.py` | [v1.8] Company Opções tab — B3 options: chain, IV, activity, positions |
| `webui/services/shareholders.py` | [v1.9] Company Acionistas tab — CVM shareholders: holders, free float, evolução da posição |
| `webui/routes/pages.py` | HTML page routes — `/webui`, `/webui/company/{ticker}`, etc. |
| `webui/routes/api.py` | JSON + HTMX partials — search, header, `/sections/{key}` dispatch, charts, tabs |
| `webui/routes/sync.py` | SSE stream + sync status + sync trigger |
| `webui/routes/preflight.py` | [v1.7] Pre-flight endpoints — JSON report + panel/banner partials |
| `webui/routes/system.py` | [v1.20] System surface — logs (+SSE stream) + settings GET/PUT |
| `webui/routes/portfolio.py` | [v1.21] Carteira REST — state/positions/overview + users/accounts/txs/watchlist CRUD + ticker-metadata refresh |
| `webui/templates/base.html` | Shell — sidebar, topbar, FOUC prevention, vendor JS |
| `webui/static/css/app.css` | 3-layer CSS: primitives (from theme JSON) → semantic → component |
| `webui/static/js/app.js` | Tab/subtab loaders + generic section renderer + Chart.js lifecycle |

---

## Design Decisions

### 1. Server-rendered Jinja2 + HTMX (NOT SPA)

**Decision:** Jinja2 server-rendered HTML + HTMX for partial updates + Alpine.js for client state. No React, Vue, Svelte, or any JS framework requiring a build step.

**Rationale (9-LLM review consensus):**
- The data is server-owned (SQLite DBs), calculations are Python — rendering should be server-side
- HTMX gives SPA-like partial updates (swap a `<div>` without full reload) with zero JavaScript
- Alpine.js handles client-only state (theme toggle, dropdowns) with declarative `x-data` syntax
- No build step = `python webui.py` boots everything, no `npm run dev`, no bundler
- Total JS payload: ~300 KB (HTMX 50KB + Alpine 44KB + Chart.js 205KB), all vendored locally

### 2. Direct Engine Imports (NOT MCP Dispatcher)

**Decision:** The WebUI imports `skills/cvm/calculations/engines/*` and `skills/cvm/_shared_report/*` directly. It does NOT call `skill(domain="cvm", sub_domain="valuation", mode="ratios")` through the MCP dispatcher.

**Rationale:**
- The MCP dispatcher is LLM-shaped (stringified JSON params, trace_ids, LLM error envelopes)
- Direct imports are 10-100x faster (no JSON serialization, no dispatcher overhead)
- Type-safe, IDE-autocompletable
- The WebUI shapes its own response contracts independently of the `skill()` interface

**Pattern:**
```python
# webui/services/company.py (the ONLY layer that imports skills)
from skills.cvm._shared_report.company_header import build_company_header
from skills.cvm.calculations._registry import compute_all_ratios

class CompanyService:
    def ratios(self, ticker: str) -> dict:
        from skills._base import engine_cache_scope
        with engine_cache_scope():
            return compute_all_ratios(ticker, today)
```

### 3. Service Layer Between Routes and Engines

**Decision:** Routes never import skill engines directly. All data access goes through `webui/services/`.

**Rationale:**
- Routes stay thin (HTTP handling only)
- Services are independently testable without HTTP
- Services are where caching lives (TTL cache, engine_cache_scope)
- 30 route handlers don't each open their own SQLite connections

### 4. SSE for Sync Progress (NOT WebSocket)

**Decision:** Server-Sent Events for sync progress streaming. WebSocket only for the existing agent `/ws` route.

**Rationale:**
- SSE is one-way (server→client) — perfect for sync progress
- Auto-reconnects (browser's `EventSource` handles it)
- Works through proxies (with `X-Accel-Buffering: no` header)
- No protocol library needed — plain HTTP
- WebSocket is for bidirectional communication (not needed here)

### 5. CSS Variables 3-Layer Theme System

**Decision:** Themes are JSON files (`webui/themes/dark.json`). CSS uses a 3-layer token system: primitives (from theme JSON) → semantic (in `app.css`) → component (in `app.css`).

**Rationale:**
- Drop a new JSON = new theme, no code change
- `data-theme` attribute on `<html>` + CSS variable blocks = instant theme switch
- FOUC prevention: inline script in `<head>` sets `data-theme` before CSS loads
- localStorage (instant apply) + cookie (cross-device persistence)

### 6. JSON i18n (NOT gettext)

**Decision:** JSON translation files + a custom `t()` function. No gettext, no Babel, no `.po`/`.mo` compilation.

**Rationale:**
- ~200-300 strings — gettext's toolchain is overkill
- JSON is editable by anyone, no poEdit needed
- No compilation step (`pybabel compile` is easy to forget)
- Domain terms (DRE, P/L, ROE, EBITDA) are NOT translated — they're proper nouns in finance

### 7. SQLite WAL Mode

**Decision:** `core/db_wal.py` sets `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` + `busy_timeout=5000` on every DB at startup.

**Rationale:**
- Concurrent reads (WebUI HTTP requests) + background sync writes on the same SQLite files
- Without WAL: sync writes block UI reads → `database is locked` errors
- With WAL: readers don't block writers (and vice versa)
- WAL is persistent (stored in DB header) — setting it once is enough; the module is idempotent

### 8. HTMX Chart Initialization

**Decision:** `app.js` listens for `htmx:afterSwap` and initializes any `<canvas data-chart-type="...">` found in the swapped content.

**Rationale:**
- Inline `<script>` tags in HTMX-swapped content don't execute by default
- This is the #1 gotcha when combining HTMX with Chart.js
- Solution: one `initChartsInElement()` function called after every swap

### 9. Vendored JS (No CDN)

**Decision:** HTMX, Alpine.js, Chart.js are downloaded to `webui/static/vendor/`. No CDN dependencies.

**Rationale:**
- Local-first project — works offline
- No version drift (pinned versions)
- No CDN availability dependency
- Faster page load (no external DNS lookup)

### 10. Adapter Contract + Registry (v1.7)

**Decision:** Every lazy subtab payload is produced by an adapter registered in `webui/adapters/registry.py` under a `"<family>:<sub>"` key, and served by ONE generic endpoint (`GET /api/webui/company/{ticker}/sections/{key}`). Generic-renderer payloads are validated against `webui/adapters/contract.py` at dispatch time.

**Rationale:**
- The pattern already existed ad hoc (Valuation v1.4, Proventos v1.6: report builders → section dicts → ONE client renderer). v1.7 makes it the explicit contract so the v1.8 wave (Options, Insider, Shareholders, Historical, Macro, dashboards) plugs in without new API routes or client renderer code
- Contract violations surface in the server log with `_contract_violations` attached to the payload — visible during development, non-breaking in production (the client ignores unknown keys)
- Service singletons are owned by `registry.service()` (memoized factory) — routes and dispatch share ONE PriceService, so the 60s-TTL OHLCV cache is never duplicated
- Custom-renderer payloads (Preço, Financeiro, Proventos Histórico) register with `generic=False`: same dispatch path, no contract validation (their shape belongs to their client renderer)

**Adding a v1.8 tab:**
1. Service method returning a contract payload (use `contract.py` builders)
2. ONE `register("options:overview", …)` call in `registry.py`
3. Tab shell partial + client loader → `/api/webui/company/{ticker}/sections/options:overview`

### 11. Pre-flight Checks Surfaced in the UI (v1.7)

**Decision:** `webui/services/preflight.py` runs a checklist on demand (DB existence + expected schema + WAL + `MAX(rowid)` row sanity per DB, sync coverage, vendor assets, Python version, disk space, write access, adapter registry integrity, launch config) and surfaces it as a Sync-page panel + Dashboard banner.

**Rationale:**
- Errors used to surface deep inside engines ("FileNotFoundError: dfp.db — Run sync first" mid-dashboard). The pre-flight panel shows the same diagnosis on ONE page, before things break at render time
- Checks are cheap (file stats, pragmas, `MAX(rowid)` — never `COUNT(*)`, which full-scans multi-GB tables) and side-effect free (the memory root is resolved WITHOUT mkdir, so a missing DB never leaves empty domain folders behind)
- The panel doubles as post-sync verification ("did the DB appear / fill?")

### 12. Data Re-key Over Query-Layer Patching (v1.7.1)

**Decision:** The quarterly-balanços bug (ITR BPA/BPP snapshots all stamped `meses=12`, quarter buckets 3/6/9 empty, every consumer carrying year-end values forward) was fixed by re-keying the DATA — the sync engine re-keys each filing's snapshots into the bucket its own flow rows report, and existing DBs are healed by a FORCE re-sync (the engine re-keys each year as it re-parses — the per-source `itr` button covers current+previous year; `sync(full_history=True, force=True)` covers the whole history; the re-key is idempotent, only rows still at `meses=12` are touched) — with ZERO changes to the query layer.

**Rationale:**
- Every consumer (`fetchers._snap`, `_get_snapshot_value`, the bpa/* + bpp/* engines' `meses IN (3,6,9)` lookups) was already written for the correct semantics — patching them to work around mis-keyed data would have doubled the code paths and left the DB wrong
- The filing's flow rows (DRE/DFC/DVA have DT_INI_EXERC) are the ground truth for its period — deriving the bucket from them handles fiscal-year filers (May/Aug/Nov quarter ends) for free, where a calendar-month mapping would mis-bucket
- `PRAGMA user_version=2` marks a re-keyed DB (sync sets it, migration sets it, pre-flight warns until it sees it); the migration also wipes the engine cache because fingerprints (MAX(versao)+MAX(data_fim_exerc)) don't change with a re-key — cached engine results would keep serving the collapsed balances

### 13. Client-Derived Visualizations When the Payload Already Has the Data (v1.7.1)

**Decision:** The Financeiro "Conversão da Receita em Lucro" waterfall (with its Anual/Trimestral toggle) is derived entirely client-side from the `financials:overview` payload (annual periods newest-first, quarterly standalone oldest-first) — no new endpoint, no adapter registration, instant toggle.

**Rationale:**
- The overview payload already carries every anchor (3.01/3.03/3.05/3.06/3.11 per period); a server round-trip per toggle would add latency + a route for zero new data
- Deltas are computed from the DRE subtotals (Custos = Receita − Lucro Bruto), so the chart needs no per-line code presence and degrades gracefully when a subtotal is missing
- The card lives inside a custom-rendered subtab (financials:overview, `generic=False`), so this doesn't bypass the adapter contract — new TABS still go through the registry

### 14. The System Log Is a Ring Buffer Fed by Three Capture Paths (v1.20)

**Decision:** The 📜 drawer's data is ONE in-memory, per-process ring buffer (`webui/services/syslog.py`) with three feeders: a pure-ASGI request middleware (method/path/status/duration for every non-static request — SSE-safe, no BaseHTTPMiddleware), a root-logger handler (WARNING+; unhandled ASGI exceptions land here), and explicit `syslog.log()` points (sync lifecycle, startup, scheduler, settings changes).

**Rationale:**
- In-memory ONLY, deliberately: the panel answers "what happened since I opened it" — a tail, not a log file. Persisting history is a `logging` config concern, not a UI feature (and the terminal already has everything)
- The pure-ASGI middleware (vs BaseHTTPMiddleware) wraps the send channel only — the two SSE streams pass through untouched, and a streaming request logs its OPEN, not a completion line that would only appear minutes later on disconnect
- No subscriber registry (unlike the sync SSE): the buffer is PULLED — the stream endpoint polls it every ~1s inside the generator, so worker threads never push and there is nothing to register/unregister
- While the drawer is closed the feed degrades to a 15s poll of `?after=<id>` — enough to keep the unseen-error badge counting without holding a stream on every page
- Request noise control: /static/, /docs, favicon and OPTIONS preflights are skipped; 4xx logs as warning, 5xx and exceptions as error

### 15. Settings as Data — One Dict Entry per Setting (v1.20)

**Decision:** Every setting is ONE entry in the `SCHEMA` list in `webui/services/settings.py` (key, section, label, type, default + type-specific extras). The Configurações page renders itself from `GET /api/webui/settings`; `PUT` validates + persists all-or-nothing to `memory_db/webui_settings.json` (atomic write, mtime-checked in-memory read cache).

**Rationale:**
- Adding a setting = one dict entry — no template edit, no route edit, no form HTML (the SDNext pattern the roadmap asked for)
- Storage is a JSON FILE, not a table: settings are a handful of scalars, the file is human-readable/diffable/atomic-replaceable, and there is no migration story to carry
- EVERY shipped setting is wired end-to-end (sync preferences → lifespan/scheduler/freshness; Painel knobs → HomeService with memo invalidation; theme/locale → Set-Cookie so the cookie stays the single source of truth; log level/buffer → live re-trim). No dead knobs — a setting that does nothing is documentation debt wearing a form
- Validation rejects the whole patch on any invalid key (no partial saves); errors are PT-BR per key
- The scheduler re-reads its interval every cycle, so changing `sync.schedule_hours` applies without a restart

---

## Data Flow

```
Browser
  │
  ├─ GET /webui/company/PETR4          (HTML page)
  │    │
  │    ▼
  │  routes/pages.py → company_overview()
  │    │
  │    ▼
  │  services/company.py → CompanyService.header("PETR4")
  │    │
  │    ▼
  │  skills/cvm/_shared_report/company_header.py → build_company_header()
  │    │
  │    ▼
  │  FCA + CAD + COTAHIST + B3 instruments DBs → SQLite (WAL mode)
  │    │
  │    ▼
  │  Jinja2 template → HTML response → browser
  │
  ├─ GET /api/webui/company/PETR4/tab/valuation  (HTMX partial)
  │    │
  │    ▼
  │  routes/api.py → company_tab_fragment()
  │    │
  │    ▼
  │  services/company.py → CompanyService.ratios("PETR4")
  │    │
  │    ▼
  │  skills/cvm/calculations/_registry → compute_all_ratios()
  │    │
  │    ▼
  │  26 calculation engines + 79 metrics → SQLite (WAL mode)
  │    │
  │    ▼
  │  Jinja2 partial → HTML fragment → HTMX swaps into #tab-content
  │
  ├─ GET /api/webui/company/PETR4/sections/valuation:overview  (lazy subtab JSON)
  │    │
  │    ▼
  │  routes/api.py → company_sections()
  │    │
  │    ▼
  │  adapters/registry.py → dispatch("valuation:overview", "PETR4")
  │    │      (contract validation, error containment)
  │    ▼
  │  services/valuation.py → ValuationService.overview()
  │    │
  │    ▼
  │  skills/cvm/valuation/report/* → section dicts
  │    │
  │    ▼
  │  JSON → app.js renderValSubtab (generic renderer)
  │
  └─ GET /api/webui/sync/stream  (SSE)
       │
       ▼
     routes/sync.py → sync_stream()
       │
       ▼
     services/sync.py → SyncService.subscribe()
       │
       ▼
     Background sync thread → _publish() events to SSE queue
       │
       ▼
     StreamingResponse → browser EventSource
```

---

## Theme System

### 3-Layer Tokens

1. **Primitives** (from theme JSON): `--bg`, `--text`, `--brand`, `--border`, etc.
2. **Semantic** (in `app.css`): `--color-bg: var(--bg)`, `--color-text: var(--text)`, etc.
3. **Component** (in `app.css`): `.btn-primary { background: var(--color-brand); }`

### Theme Switching

```html
<!-- FOUC prevention (inline in <head>, runs before CSS) -->
<script>
  var saved = localStorage.getItem('webui_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
</script>

<!-- Theme CSS (generated by theme.py from JSON) -->
<style>
  :root[data-theme="dark"] { --bg: #0a0c10; --text: #e6edf3; ... }
  :root[data-theme="light"] { --bg: #ffffff; --text: #1f2328; ... }
</style>
```

### Adding a New Theme

1. Create `webui/themes/solarized.json` with CSS variable tokens
2. Done — `theme.py` auto-discovers it, the settings page shows it in the dropdown

---

## i18n System

### Structure

```json
// webui/locales/pt-BR.json
{
  "_name": "Português (Brasil)",
  "nav": { "dashboard": "Painel", "company": "Empresa", ... },
  "company": { "search_placeholder": "Buscar ticker (ex: PETR4)...", ... }
}
```

### Locale Negotiation

Priority: `?lang=` query param > cookie > `Accept-Language` header > default (pt-BR)

### Usage

```python
# In Python
from webui.i18n import t
label = t("nav.dashboard", locale="pt-BR")  # → "Painel"

# In Jinja2
{{ t("nav.dashboard") }}
{{ _("company.search_placeholder") }}
```

### Domain Terms NOT Translated

DRE, DFC, DVA, P/L, P/VPA, ROE, EBITDA, CNPJ, CD CVM — these are proper nouns in finance. An English-language Brazilian finance UI still says "DRE", the same way nobody translates "10-K" for an SEC tool.

---

## Relationship to Existing Systems

```
                    webui.py (NEW)
                       │
                       ▼
                  ┌─────────┐
                  │ FastAPI │  (extends core/gateway_backend/)
                  └────┬────┘
                       │
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
      WebUI           REST          MCP/Gateway
    Jinja/HTMX       /api/webui     existing (/chat, /task, /ws)
        │              │
        └──────┬───────┘
               ▼
        Application Services (webui/services/)
               │
       ┌───────┴────────┐
       ▼                ▼
  Calculations        SyncManager
  (skills/cvm/        (data_sources/
   calculations/)      dispatcher)
       │                │
       └────────┬───────┘
                ▼
          Data Sources (SQLite DBs)
```

**The MCP server (`server.py`) is unchanged.** LM Studio / Claude Desktop continue to use the MCP stdio protocol. The WebUI is a separate HTTP entry point that shares the same Python codebase (skills, data_sources, calculations) but serves browser clients.
