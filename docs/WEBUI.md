<- Back to [Structure](STRUCTURE.md)

# 🖥️ WebUI — Live Web Interface

Brazilian Financial Data WebUI — a live, server-rendered web interface that replaces static HTML report generation with real-time data access. Built on the existing FastAPI gateway + calculation engines, it provides a dashboard-style UI for browsing companies, valuation ratios, financials, macro indicators, and data sync status.

**Key characteristics:**
- **One process, one port** — `python webui.py` boots everything (FastAPI + Jinja2 + HTMX + Chart.js)
- **Live data** — queries SQLite directly on each page load, no pre-generated HTML
- **Direct engine imports** — uses `skills/cvm/calculations/engines/` as a data layer, bypassing the MCP dispatcher
- **Theme-aware** — CSS variables with dark/light themes, user-customizable
- **Multilingual** — JSON-based i18n (pt-BR default, en-US), no gettext
- **Real-time sync** — SSE (Server-Sent Events) for live sync progress
- **System log** — a 📜 top-bar button opens a right-side drawer with the live request/sync/error tail (SSE while open, badge-polling while closed) [v1.20]
- **Settings as data** — schema-driven Configurações page; sync preferences (auto-sync at boot, stale threshold, periodic schedule), Painel knobs, theme/locale and log controls, all wired [v1.20]
- **No build step** — vanilla JS + HTMX + Alpine.js, no Node.js, no bundler

## Quick Start

```bash
# Launch the WebUI (default: http://127.0.0.1:8000/webui)
python webui.py

# Custom port
python webui.py --port 7860

# Dev mode (auto-reload on file change)
python webui.py --reload

# Skip the startup freshness check
python webui.py --no-sync
```

> **Security note (v1.5):** the app is loopback-only by default. Binding a
> non-loopback host additionally requires `WEBUI_ALLOW_LAN=1` — the mounted
> gateway routes (`/task`, `/chat`, `/ws`) execute agent tools unauthenticated,
> so an accidental `--host 0.0.0.0` must stay opt-in.

## Architecture

- **Frontend:** Jinja2 (server-rendered) + HTMX (partial updates) + Alpine.js (client state) + Chart.js (charts)
- **Backend:** FastAPI, extending the existing `core/gateway_backend/` gateway
- **Data layer:** Direct imports from `skills/cvm/calculations/engines/` and `skills/cvm/_shared_report/`
- **Themes:** CSS variables (3-layer: primitives → semantic → component) from JSON theme files
- **i18n:** JSON translation files + custom `t()` function (not gettext)
- **Sync:** SSE for live progress, background threads for sync execution
- **Concurrency:** SQLite WAL mode for concurrent read/write

See [ARCHITECTURE.md](webui/ARCHITECTURE.md) for the full file map and design decisions.

## API

All WebUI routes are prefixed `/webui` (HTML pages) or `/api/webui` (JSON/SSE). The existing gateway routes (`/chat`, `/task`, `/ws`, `/health`) are mounted on the same app.

See [API.md](webui/API.md) for the full route reference.

## Subfiles

- [ARCHITECTURE.md](webui/ARCHITECTURE.md) — File map, design decisions, data flow, theme/i18n/SSE systems
- [API.md](webui/API.md) — All HTTP routes (HTML pages, JSON API, SSE endpoints)
- [CHANGELOG.md](webui/CHANGELOG.md) — Version history
- [INSTRUCTIONS.md](webui/INSTRUCTIONS.md) — Rules for AI editors (NEVER DO, ALWAYS DO)
- [ROADMAP.md](webui/ROADMAP.md) — What's built, what's next

## Tech Stack

| Component | Technology | Size | Source |
|-----------|-----------|------|--------|
| Web framework | FastAPI | — | Already in requirements.txt |
| Template engine | Jinja2 | — | Already installed |
| Partial updates | HTMX 2.0 | 50 KB | Vendored (`webui/static/vendor/`) |
| Client state | Alpine.js 3.x | 44 KB | Vendored |
| Charts | Chart.js 4.4 | 205 KB | Vendored |
| Themes | CSS variables | — | JSON theme files |
| i18n | Custom JSON | — | `webui/locales/*.json` |

**No new Python dependencies.** No Node.js, no npm, no build step.
