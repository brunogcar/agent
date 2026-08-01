<- Back to [Investsite Overview](../INVESTSITE.md)

# 🗺️ Investsite ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | I1 — Returns & Margins tab | Separate tab for retornos_margens with bar chart |
| P2 | I2 — Events timeline | Chronological timeline visualization of events |
| P3 | I3 — Statement charts | Bar/doughnut charts from statements mode data |
| P3 | I4 — Caching | TTL cache for fetched pages (currently fetches live each call) |
| Done | v1.2 dashboard reorg | Added indicator bar chart to Key Indicators tab |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

## 📋 Backlog

### I1 — Returns & Margins tab

**Priority:** P2

Split the Key Indicators tab into two: Valuation (P/L, P/VPA, EV/EBITDA,
DY) and Returns & Margins (ROE, ROA, Margem EBITDA, Margem Líquida). Add
a bar chart to each showing the values.

### I2 — Events timeline

**Priority:** P2

Visualize the Latest Events as a chronological timeline instead of a
table. Would help see clusters of events (earnings season, corporate
actions).

### I3 — Statement charts

**Priority:** P3

Add charts from the `statements` mode data — e.g., a doughnut chart
showing revenue breakdown by segment, or a bar chart showing YoY
revenue growth.

### I4 — Caching

**Priority:** P3

Add a TTL cache (1h?) for fetched investsite pages so repeated calls
within the same session don't hit the network each time. Currently
fetches live on every call.

---

*Last updated: 2026-08-01. See [CHANGELOG.md](CHANGELOG.md) for version history.*
