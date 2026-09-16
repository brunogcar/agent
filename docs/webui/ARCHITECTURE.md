<- Back to [WebUI Overview](../WEBUI.md)

# 🏗️ WebUI Architecture

> File map, design decisions, and data flow for the Brazilian Financial Data WebUI.

Last updated: 2026-09-16 (v1 — initial vertical slice)

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
│   ├── i18n.py                       # JSON-based i18n (t() function, locale negotiation)
│   ├── theme.py                      # CSS variable theme registry (JSON theme files)
│   ├── routes/                       # HTTP route modules
│   │   ├── pages.py                  # HTML page routes (/webui/*)
│   │   ├── api.py                    # JSON + HTMX partial routes (/api/webui/*)
│   │   └── sync.py                   # SSE sync progress (/api/webui/sync/*)
│   ├── services/                     # Service layer (ONLY place that imports skills)
│   │   ├── company.py                # Company header + ratios + price series
│   │   └── sync.py                   # Freshness check + background sync + SSE pub/sub
│   ├── templates/                    # Jinja2 templates
│   │   ├── base.html                 # Shell: sidebar + topbar + content area
│   │   ├── pages/                    # Full HTML pages (extend base.html)
│   │   │   ├── dashboard.html        # Home (market overview)
│   │   │   ├── company.html          # Company view (header + tabs)
│   │   │   ├── macro.html            # Macro indicators
│   │   │   ├── sync.html             # Sync status + SSE log
│   │   │   └── settings.html         # Theme + language settings
│   │   └── partials/                 # HTMX fragments (no <html> wrapper)
│   │       ├── search_results.html   # Ticker search dropdown
│   │       ├── identity_card.html    # Persistent identity header (all tabs)
│   │       ├── tab_visao_geral.html  # Visão Geral tab (reg tables + chart)
│   │       └── tab_valuation.html    # Valuation tab content
│   ├── static/                       # Static assets (CSS, JS, vendor)
│   │   ├── favicon.svg               # Teal bar-chart icon
│   │   ├── css/app.css               # 3-layer token system + layout + components
│   │   ├── js/app.js                 # HTMX config + chart init after swap
│   │   ├── js/charts.js              # Chart.js factory (theme-aware)
│   │   └── vendor/                   # Vendored JS (local, no CDN)
│   │       ├── htmx.min.js           # HTMX 2.0 (50 KB)
│   │       ├── alpine.min.js         # Alpine.js 3.x (44 KB)
│   │       └── chart.umd.min.js      # Chart.js 4.4 (205 KB)
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
| `webui/app.py` | FastAPI app factory — mounts routes, static files, existing gateway |
| `webui/i18n.py` | JSON i18n — `t()` function, locale negotiation, `available_locales()` |
| `webui/theme.py` | Theme registry — `render_theme_css()`, `available_themes()` |
| `webui/services/company.py` | Company data — wraps `build_company_header()` + `compute_all_ratios()` |
| `webui/services/price.py` | Price data — wraps `ohlcv_series` + `compute_sma` + indicators + Bollinger + Fibonacci |
| `webui/services/sync.py` | Sync service — freshness check, background sync, SSE pub/sub |
| `webui/routes/pages.py` | HTML page routes — `/webui`, `/webui/company/{ticker}`, etc. |
| `webui/routes/api.py` | JSON + HTMX partials — search, header, ratios, charts, tabs |
| `webui/routes/sync.py` | SSE stream + sync status + sync trigger |
| `webui/templates/base.html` | Shell — sidebar, topbar, FOUC prevention, vendor JS |
| `webui/static/css/app.css` | 3-layer CSS: primitives (from theme JSON) → semantic → component |
| `webui/static/js/app.js` | HTMX `afterSwap` listener — inits charts in swapped content |
| `webui/static/js/charts.js` | Chart.js factory — theme-aware via CSS variables |

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
