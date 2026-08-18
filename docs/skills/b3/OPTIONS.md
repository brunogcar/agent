<- Back to [B3 Skills](../B3.md)

# 📊 OPTIONS — B3 Options Analytics Skill

The `options` skill produces a 5-tab options (derivatives) dashboard for any
B3-listed underlying: options chain + put/call ratio + volume by strike +
exercise of calls/puts + implied volatility (Black-Scholes).

**Key characteristics:**
- **Single mode** — `dashboard` (5-tab deep dive). No `quote` mode (options
  don't have a single "latest" snapshot that's useful standalone).
- **Two data sources** — `data_sources/b3/cotahist` (the
  `cotahist_derivatives` + `cotahist` equities tables in the shared
  `cotahist.db`) + `data_sources/bcb/sgs` (the `sgs.db` Selic rate for the
  IV tab). No CVM joins, no brapi. Pure derivatives analytics.
- **Shared DB** — derivatives + equities live in the SAME `cotahist.db`
  (populated during the standard COTAHIST sync pass). The IV tab also reads
  the Selic rate from `sgs.db` (BCB SGS series 432). So
  `REQUIRED_SOURCES = ["cotahist", "sgs"]` — the sync guard triggers both.
- **Underlying normalization** — accepts both `"PETR"` (4-letter code) and
  `"PETR4"` (full ticker). Trailing digits are stripped before querying.
- **Option ticker legend** — [v2] 2-column CALLS|PUTS table in the
  Cadeia de Opções tab showing both month-code systems side by side. Call
  month codes A-L (Jan-Dec), Put month codes M-X (Jan-Dec). Strike encoded
  as integer; trailing `5` = half-point (e.g. `215` → R$ 21,50).
- **Black-Scholes IV engine** — [v1.2] Pure-Python `engines.py` (no scipy,
  no numpy). Newton-Raphson + bisection fallback, clamp [0.01, 5.0] vol.
  Risk-free rate = Selic from BCB SGS series 432 ("Meta Selic Copom", % a.a.)
  converted to continuous compounding.
- **Accent colors** — Calls = green (`#22c55e`), Puts = red (`#ef4444`),
  P/C reference line at 1.0 = dashed grey (`#9ca3af`).
- **Column alignment** — [v2] R$ + numeric columns in all tables are
  right-aligned with `font-variant-numeric: tabular-nums` so digits line
  up. Text columns stay left-aligned.
- **Graceful degradation** — if the derivatives table is missing or empty,
  the dashboard stays `status=ok` with error sections (so other tabs still
  render). Mirrors the CVM financials + bcb/macro contract.

---

## 🚀 Quick Start

```
# 5-tab dashboard (options chain + P/C ratio + volume by strike + exercise + IV)
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR4"}')

# Also accepts the 4-letter code directly
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR"}')
```

Every `route(mode="dashboard", ...)` call auto-generates an HTML file
(`PETR4_options_dashboard.html` in `workspace/reports/`).

---

## ⚙️ Configuration

Read-only over already-synced data sources:
- `data_sources/b3/cotahist` (`cotahist_derivatives` + `cotahist` equities
  tables in the shared `cotahist.db` — populated during the standard
  COTAHIST sync).
- `data_sources/bcb/sgs` (`sgs.db` — Selic rate from BCB SGS series 432,
  populated during the standard BCB SGS sync).

Sync commands (run once before first use):
```powershell
# Cotahist (equities + derivatives in one pass)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.b3.cotahist.sync_engine import sync; print(sync(year=2025))"

# BCB SGS (Selic rate for the IV tab)
D:\mcp\agent\venv\Scripts\python.exe -c "from data_sources.bcb.sgs.sync_engine import sync_series; print(sync_series(432))"
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
| [CHANGELOG.md](options/CHANGELOG.md) | Version history (v1.0 → v1.3) |
| [INSTRUCTIONS.md](options/INSTRUCTIONS.md) | AI editing rules — what NOT to break, ALWAYS DO |
| [ROADMAP.md](options/ROADMAP.md) | Backlog: DerivativesOpenPosition, futures skill, price-dashboard Opções tab (P1 + P2 done) |

> **Note on `COMPONENT.md`:** this project uses the uppercase skill name
> (`OPTIONS.md`) as the landing page instead of `COMPONENT.md` — see
> `PRICE.md` and `INDEX.md` for the established convention. No
> `COMPONENT.md` is created.

---

*Last updated: 2026-09-05 (v1.3 — IV Black-Scholes tab + 2-box legend + column alignment).*
