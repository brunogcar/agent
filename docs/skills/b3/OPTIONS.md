<- Back to [B3 Skills](../B3.md)

# 📊 OPTIONS — B3 Options Analytics Skill

The `options` skill produces a 3-tab options (derivatives) dashboard for any
B3-listed underlying: options chain + put/call ratio + volume by strike.

**Key characteristics:**
- **Single mode** — `dashboard` (3-tab deep dive). No `quote` mode (options
  don't have a single "latest" snapshot that's useful standalone).
- **Single data source** — `data_sources/b3/cotahist_derivatives` (the
  `cotahist_derivatives` table in the shared `cotahist.db`). No CVM joins,
  no brapi. Pure derivatives analytics.
- **Shared DB** — derivatives live in the SAME `cotahist.db` as equities
  (populated during the standard COTAHIST sync pass). So
  `REQUIRED_SOURCES = ["cotahist"]` — the sync guard reuses the cotahist
  sync engine, no separate sync for derivatives.
- **Underlying normalization** — accepts both `"PETR"` (4-letter code) and
  `"PETR4"` (full ticker). Trailing digits are stripped before querying.
- **Option ticker legend** — Call month codes A-L (Jan-Dec), Put month codes
  M-X (Jan-Dec). Strike encoded as integer; trailing `5` = half-point
  (e.g. `215` → R$ 21,50).
- **Accent colors** — Calls = green (`#22c55e`), Puts = red (`#ef4444`),
  P/C reference line at 1.0 = dashed grey (`#9ca3af`).
- **Graceful degradation** — if the derivatives table is missing or empty,
  the dashboard stays `status=ok` with error sections (so other tabs still
  render). Mirrors the CVM financials + bcb/macro contract.

---

## 🚀 Quick Start

```
# 3-tab dashboard (options chain + put/call ratio + volume by strike)
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR4"}')

# Also accepts the 4-letter code directly
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR"}')
```

Every `route(mode="dashboard", ...)` call auto-generates an HTML file
(`PETR_options_dashboard.html` in `workspace/reports/`).

---

## ⚙️ Configuration

Read-only over already-synced data sources:
- `data_sources/b3/cotahist_derivatives` (`cotahist_derivatives` table in
  the shared `cotahist.db` — populated during the standard COTAHIST sync).

Sync command (run once before first use — same command syncs both the
equities table AND the derivatives table in one pass):
```powershell
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"
```

Escape hatches (set automatically in tests):
- `CVM_SKIP_SYNC=1` — bypass sync guard (no freshness check, no force-sync)
- `CVM_SKIP_HTML=1` — skip auto-HTML generation

---

## 📊 Rendering & Export

Pipe an `options` result into the `report` tool to render a table or export
to Excel. The `dashboard` action auto-writes HTML — see [B3 Skills —
Auto-HTML Generation](../B3.md#-auto-html-generation).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](options/ARCHITECTURE.md) | File map, data flow, query-engine inventory, design decisions |
| [API.md](options/API.md) | dashboard mode signature + response shape + error responses |
| [CHANGELOG.md](options/CHANGELOG.md) | Version history (v1.0) |
| [INSTRUCTIONS.md](options/INSTRUCTIONS.md) | AI editing rules — what NOT to break, ALWAYS DO |
| [ROADMAP.md](options/ROADMAP.md) | Backlog: DerivativesOpenPosition, IV (Black-Scholes), IV smile heatmap, futures skill, price-dashboard Opções tab |

> **Note on `COMPONENT.md`:** this project uses the uppercase skill name
> (`OPTIONS.md`) as the landing page instead of `COMPONENT.md` — see
> `PRICE.md` and `INDEX.md` for the established convention. No
> `COMPONENT.md` is created.

---

*Last updated: 2026-08-18 (v1.0 — options skill launch).*
