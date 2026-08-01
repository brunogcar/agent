<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 🗺️ Governance ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | G1 — Per-chapter doughnut charts | One compliance doughnut per Capitulo |
| P2 | G2 — Multi-year governance trend | Line chart of score_pct over time |
| P3 | G3 — Peer comparison | Compare governance scores across sector peers |
| P3 | G4 — Practice drill-down | Expandable rows showing full explanation text |
| Done | v1.2 dashboard reorg | Added practices compliance doughnut |
| Done | Sync guard (v1.2) | required_sources wired via make_route() |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### G1 — Per-chapter doughnut charts

**Priority:** P2

Add a small doughnut chart per Capitulo (chapter) to the By Chapter tab,
showing the Adequado / Parcialmente / Não Adequado distribution within
each chapter. The By Chapter table already has the adopted / partial /
not_adopted counts — the chart builder just needs to render one doughnut
per row. Useful because some chapters (Board composition, Audit) matter
more than others.

### G2 — Multi-year governance trend

**Priority:** P2

Add a line chart to the Overview tab showing the governance score
(`score_pct`) over time, one point per Data_Referencia. Currently the
score is a single point-in-time value — this would visualize whether
the company's governance is improving or deteriorating. Requires
fetching all historical CGVN filings for the company, not just the
latest.

### G3 — Peer comparison

**Priority:** P3

New tab comparing the company's governance score against sector peers.
Pulls the same `score()` data for 3-5 peers (resolved via the CAD
sector classification) and renders a horizontal bar chart. Useful for
benchmarking — a 60% Sim score means very different things in banking
vs real estate. Could reuse the `comparison` skill's peer-resolution
logic.

### G4 — Practice drill-down

**Priority:** P3

Make each row in the Practices tab expandable to show the full
`Explicacao` text (currently the column is truncated to fit the table
width). Uses the dashboard template's `collapsible` section type. Would
also surface the `Pratica_Recomendada` (the B3-recommended practice)
prominently when expanded, so users can compare what was recommended
vs what was adopted.

---

*Last updated: 2026-07-31 (v1.2 — dashboard reorg + sync guard). See [CHANGELOG.md](CHANGELOG.md) for version history.*
