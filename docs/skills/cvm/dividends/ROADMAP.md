<- Back to [DIVIDENDS Overview](../DIVIDENDS.md)

# 🗺️ Dividends ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | D1 — Dividend yield history chart | Line chart of trailing yield over time |
| P2 | D2 — JCP vs Dividendo split | Stacked bar chart (annual tab) |
| P3 | D3 — Dividend growth rate metric | CAGR of dividends per share over 3Y/5Y |
| P3 | D4 — Payable vs Paid reconciliation | Table comparing declared (DVA) vs unpaid (BPP) |
| Done | v1.2 dashboard reorg | Added history line chart + annual bar chart |
| Done | Sync guard (v1.2) | required_sources wired via make_route() |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### D1 — Dividend yield history chart

**Priority:** P2

Add a line chart to the History tab showing trailing 12-month dividend
yield over time (rate per share / closing price at each payment date).
Requires pulling historical COTAHIST closing prices alongside the B3
dividends events. Currently the Overview KPI shows a single point-in-time
yield — this would visualize how the yield has evolved across each
dividend payment.

### D2 — JCP vs Dividendo split

**Priority:** P2

Augment the Annual tab's bar chart with a stacked-bar option that splits
each year's total into Dividendos (DVA 7.08.04.02) vs JCP (DVA 7.08.04.01).
The data is already in `periods[i].accounts` — the chart builder just
needs a second dataset for JCP. Useful because JCP has different tax
treatment (interest on equity) than dividends.

### D3 — Dividend growth rate metric

**Priority:** P3

Compute CAGR of dividends per share over 3Y and 5Y windows, surface as
a KPI card + a small trend line in the Annual tab. Requires multi-year
DVA data (currently the Annual tab shows up to 3 periods by default —
the metric would extend that lookback). Inspired by the valuation
skill's CAGR backlog item.

### D4 — Payable vs Paid reconciliation

**Priority:** P3

New tab showing declared-but-unpaid dividends (BPP 2.01.05.02.01)
alongside the actual B3 events paid in the same period. Highlights
discrepancies between what was declared and what was actually
distributed. Combines the existing `payable` mode data with the B3
events list, joined on date proximity.

---

*Last updated: 2026-07-31 (v1.2 — dashboard reorg + sync guard). See [CHANGELOG.md](CHANGELOG.md) for version history.*
