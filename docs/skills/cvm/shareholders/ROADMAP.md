<- Back to [SHAREHOLDERS Overview](../SHAREHOLDERS.md)

# 🗺️ Shareholders ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | S1 — Shareholder concentration index | HHI calculation + KPI card |
| P2 | S2 — Multi-period shareholder changes | Table showing inflows/outflows between FRE filings |
| P3 | S3 — Insider transactions overlay | Combine with insider skill data |
| P3 | S4 — Treasury shares tracking | Ações em tesouraria (BPP 2.03.03) breakdown |
| Done | v1.2 dashboard reorg | Added shareholder doughnut + equity bar chart |
| Done | Sync guard (v1.2) | required_sources wired via make_route() |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### S1 — Shareholder concentration index

**Priority:** P2

Compute the Herfindahl-Hirschman Index (HHI) of the shareholder base —
sum of squared percentage shares — and surface as a KPI card on the
Overview tab. HHI > 0.25 = highly concentrated; HHI < 0.10 = dispersed.
Requires only the top shareholders list (already in the dashboard
payload). Useful for governance + risk assessment (concentrated
ownership = controller risk).

### S2 — Multi-period shareholder changes

**Priority:** P2

Add a Changes tab showing how the top shareholder positions evolved
between consecutive FRE filings — who bought, who sold, who entered/exited
the top 5. Requires fetching multiple FRE periods (currently the
dashboard shows only the latest). Renders as a table with columns:
Shareholder, Previous %, Current %, Change (pct points).

### S3 — Insider transactions overlay

**Priority:** P3

Combine the shareholders data with the `insider` skill's transaction
history (B3 ITR/DIE filings) to show which top shareholders have been
trading recently. Adds an "Insider Activity" column to the Top
Shareholders table showing buy/sell counts + net volume over the last
90 days. Useful because a controller reducing their position is a
strong signal.

### S4 — Treasury shares tracking

**Priority:** P3

Surface ações em tesouraria (treasury shares, BPP 2.03.03) as a KPI +
add it to the Equity Structure bar chart. Currently `_EQUITY_CODES`
skips 2.03.03 — adding it would show how much of the company's own
stock it holds. Useful for buyback analysis: a growing treasury
balance signals ongoing buyback programs.

---

*Last updated: 2026-07-31 (v1.2 — dashboard reorg + sync guard). See [CHANGELOG.md](CHANGELOG.md) for version history.*
