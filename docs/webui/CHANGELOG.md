<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Changelog

> Version history for the Brazilian Financial Data WebUI.

---

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1** | 2026-09-16 | **Initial vertical slice — foundational architecture.** (1) **Entry point**: `webui.py` — single-command launcher (`python webui.py`), one process, one port. CLI args: `--host`, `--port`, `--reload`, `--no-sync`. (2) **SQLite WAL**: `core/db_wal.py` sets `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` + `busy_timeout=5000` on every DB at startup. Critical for concurrent reads (WebUI) + background sync writes. Idempotent. (3) **App factory**: `webui/app.py` — extends the existing FastAPI gateway. Mounts WebUI routes + existing gateway routes (/chat, /task, /ws, /health) on the same app. (4) **Service layer**: `webui/services/company.py` (wraps `build_company_header()` + `compute_all_ratios()` + `price_series()`) + `webui/services/sync.py` (freshness check + background sync + SSE pub/sub). (5) **Routes**: `pages.py` (6 HTML pages: dashboard, company, macro, sync, settings), `api.py` (5 JSON/HTMX endpoints: search, header, ratios, price-chart, tab content), `sync.py` (3 sync endpoints: status, trigger, SSE stream). (6) **Templates**: `base.html` shell (sidebar + topbar + content area, FOUC prevention, vendor JS, theme CSS), 5 page templates, 4 HTMX partials. (7) **Theme system**: CSS variables 3-layer (primitives → semantic → component), JSON theme files (`dark.json`, `light.json`), `theme.py` generates inline CSS. FOUC prevention via inline script in `<head>`. (8) **i18n**: JSON translation files (`pt-BR.json`, `en-US.json`), custom `t()` function (NOT gettext). Domain terms (DRE, P/L, ROE) NOT translated. Locale negotiation: query > cookie > Accept-Language > default. (9) **HTMX chart init**: `app.js` listens for `htmx:afterSwap` and inits charts in swapped content (inline `<script>` doesn't execute in HTMX-swapped content by default). (10) **Vendor JS**: HTMX 2.0 (50KB), Alpine.js 3.x (44KB), Chart.js 4.4 (205KB) — all vendored locally, no CDN. (11) **SSE for sync**: Server-Sent Events for live sync progress (NOT WebSocket). Auto-reconnects, keepalive comments, graceful disconnect handling. (12) **Direct engine imports**: WebUI imports `skills/cvm/calculations/engines/*` directly, bypassing the MCP dispatcher. 10-100x faster, type-safe, no JSON serialization. Architecture based on 9-LLM review consensus (ChatGPT, Mimo, Kimi, DeepSeek, Minimax, Mistral, Claude 1, Claude 2, Qwen). |

---

## 🔄 In Progress / Next Up

See [ROADMAP.md](ROADMAP.md) for the full backlog.

### v2 (planned)
- Company tabs: financials (DRE/BPA/BPP/DFC/DVA statement tables)
- Company tabs: dividends (DPA history + dividend events)
- Company tabs: historical (5Y price + ratio charts)
- Price chart rendering (Chart.js init after HTMX swap)
- Macro page (Selic, IPCA, CDI, FX, Focus bulletin)
- Sync page: trigger sync buttons + live progress via SSE

### v3 (planned)
- Settings page: auto-generated from schema (SDNext pattern)
- Theme accent color customization
- Watchlist (SQLite-stored recent tickers)
- Screener (sector filter + peer comparison)
- Export to PDF/Excel (reuse `report_ops/export.py`)

### v4 (planned)
- Agent chat tab (embedded `/chat` + `/ws` for live LLM interaction)
- Task history page
- Multiple themes (solarized, midnight, etc.)
- ES (Spanish) locale
- Mobile responsive optimization
