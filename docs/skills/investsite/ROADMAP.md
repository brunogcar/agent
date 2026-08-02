<- Back to [Investsite Overview](../INVESTSITE.md)

# 🗺️ Investsite ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P3 | I3 — Statement charts | Bar/doughnut charts from statements mode data |
| P3 | I4 — Browser charts | Playwright extraction of amCharts data (Desempenho, DuPont, etc.) |
| P2 | I5 — Sidebar optimization | Smaller sidebar items for 12+ tabs (current sidebar overflows on small screens) |
| P2 | I6 — More tooltips | Add tooltips to DFC, BPA, BPP, DVA, shares statement account rows |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Backlog

### I3 — Statement charts

**Priority:** P3

Add charts from the `statements` mode data — e.g., a doughnut chart
showing revenue breakdown by segment, or a bar chart showing YoY
revenue growth.

### I4 — Browser charts (amCharts extraction)

**Priority:** P3

investsite uses amCharts with dynamically-loaded data. Pages:
Desempenho Operacional, Análise DuPont, Dividend Yield, Aluguel de
Ações. Need Playwright (browser tool) to extract — investigate
viability in a future spike.

### I5 — Sidebar optimization

**Priority:** P2

The 12-tab dashboard sidebar overflows on smaller screens. Options:
- Smaller font/padding on nav items when count > 8
- Collapsible group headers (click to expand/collapse tabs within group)
- Two-column sidebar layout for large tab counts

### I6 — More tooltips

**Priority:** P2

Add tooltips to:
- DFC section metrics (FCO, FCI, FCF)
- BPA/BPP/DVA statement account rows (codigo → description)
- Shares statement rows
- Events table columns (what each field means)

---

*Last updated: 2026-08-02. See [CHANGELOG.md](CHANGELOG.md) for version history.*
