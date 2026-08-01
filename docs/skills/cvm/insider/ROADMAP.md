<- Back to [INSIDER Overview](../INSIDER.md)

# 🗺️ Insider ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | I1 — Cumulative chart by role | Cumulative net volume chart split per insider role (diretor / oficial / acionista) |
| P3 | I2 — By-asset breakdown | Add a tab breaking down movements by Tipo_Ativo (Ação, Opção, Bônus, etc.) |
| P3 | I3 — Window filters | `start_date` / `end_date` params to filter the dashboard to a custom range |
| Done | v1.2 dashboard reorg | Charts (monthly net + cumulative) added; detailed `[insider]` print output |
| Done | v2.0 _base.py extraction | _registry + __init__ delegate to shared `skills/_base.py` |
| Done | v1.1 modular split | Modes split into `modes/` + `report.py` + dashboard mode |

---

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### I1 — Cumulative chart by role

**Priority:** P2

Split the cumulative insider volume line chart by `Tipo_Cargo` so the user
can see whether directors / officers / large shareholders are net buyers
or sellers independently. Currently `build_cumulative_chart` collapses all
roles into one line; a multi-dataset variant (one dataset per role) would
make role-level trends visible at a glance.

**Blocker:** None — the underlying data (history() movements already has
`Tipo_Cargo`) is available. Just needs a new builder that groups by role
before accumulating.

### I2 — By-asset breakdown tab

**Priority:** P3

Add a fifth tab "By Asset" showing insider movements broken down by
`Tipo_Ativo` (Ação, Opção, Debênture, Bônus de Subscrição, etc.). Most
insider activity is common shares, but option exercises and debenture
conversions are materially important signals. The tab would have a small
table + a doughnut chart of volume by asset type.

### I3 — Window filters (start_date / end_date)

**Priority:** P3

Add optional `start_date` and `end_date` parameters to the dashboard mode
so users can scope the dashboard to a custom window (e.g. "insider activity
in the last 30 days" or "around the Q3 2024 earnings call"). Currently the
dashboard shows the entire VLMO history, which is overwhelming for
long-tenured tickers.

### I4 — Sentiment timeline chart

**Priority:** P3

A line/area chart showing how the insider sentiment (buying vs selling
volume ratio) evolved month-by-month. Currently sentiment is a single
top-level KPI card (BUYING / SELLING / NEUTRAL) computed over the whole
window; a timeline would reveal whether sentiment flipped at a specific
moment (e.g. before a earnings miss).

---

*Last updated: 2026-08-02 (v1.2 — dashboard reorg). See [CHANGELOG.md](CHANGELOG.md) for version history.*
