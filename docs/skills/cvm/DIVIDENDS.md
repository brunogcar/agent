<- Back to [CVM Skills](../CVM.md)

# 💸 DIVIDENDS — Dividend Skill (B3 + DFP + IPE)

The `dividends` skill combines B3 dividends (individual events) + DFP DVA (annual declared totals) + DFP BPP (payable) + CVM IPE (official filings) into a unified dividend view.

**Key characteristics:**
- **Individual events** — B3 dividends provides per-event rate, approved_on, payment_date, label (Dividendo/JCP).
- **Annual declared totals** — DFP DVA 7.08.04.* provides Dividendos + JCP per fiscal year.
- **Payable** — DFP BPP 2.01.05.02.01 shows dividends declared but not yet paid (balance sheet liability).
- **Official filings** — CVM IPE provides regulatory announcements (keyword "dividendo").
- **6 modes** — history, annual, payable, announcements, summary, dashboard.
- **Read-only** — no sync. Calls data_source query engines directly.
- **Modular layout (v1.1)** — `_registry.py` + `modes/` (6 mode files) + `report.py` auto-discovered via `@register_mode`. Mirrors the `financials`/`valuation`/`comparison`/`backtest` modular pattern.

---

## 🚀 Quick Start

```
# Individual dividend events (B3)
skill(domain="cvm", sub_domain="dividends", mode="history", params='{"company":"PETR4"}')

# Annual declared totals (DFP DVA)
skill(domain="cvm", sub_domain="dividends", mode="annual", params='{"company":"PETR4"}')

# Combined summary
skill(domain="cvm", sub_domain="dividends", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Read-only over already-synced data sources:
- `data_sources/b3/dividends` (dividends.db)
- `data_sources/cvm/dfp` (dfp.db)
- `data_sources/cvm/ipe` (ipe.db)
- `data_sources/cvm/bridge` (bridge.db — auto-syncs on ticker query)

---

## 📊 Rendering & Export

Pipe a `dividends` result into the `report` tool (adapters: `dividends_history`,
`dividends_annual`, `dividends_summary`, `dividends_dashboard`):

```
report(action="table", title="PETR4 Dividends",
       data=<dividends JSON>, config={"adapter":"dividends_history"})
report(action="export", title="PETR4 Dividends",
       data=<dividends JSON>, config={"format":"xlsx","adapter":"dividends_annual"})
report(action="dashboard", title="PETR4 Dividends Dashboard",
       data=<dividends dashboard JSON>, config={"adapter":"dividends_dashboard"})
```

See [CVM Skills — Report Integration](../CVM.md#-report-integration-v12).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](dividends/ARCHITECTURE.md) | 3-source combination, DVA codes, mode → source mapping, modular file layout |
| [API.md](dividends/API.md) | 6 modes: history, annual, payable, announcements, summary, dashboard |
| [CHANGELOG.md](dividends/CHANGELOG.md) | Version history (v1.0 → v1.1) |
| [ROADMAP.md](dividends/ROADMAP.md) | Backlog + priorities |
| [INSTRUCTIONS.md](dividends/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-08-04 (v1.2 — dashboard overhaul with sidebar groups + company header + price chart + freshness footer; see CHANGELOG.md).*
