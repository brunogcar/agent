<- Back to [CVM Skills](../CVM.md)

# 👥 SHAREHOLDERS — Shareholder + Equity Structure Skill

The `shareholders` skill combines FRE (named shareholders, free float) + DFP (equity structure in BRL) into a unified shareholder view.

**Key characteristics:**
- **Named shareholders** — FRE `posicao_acionaria` provides individual shareholder names + ownership % (ON/PN/total), controlling status. Not available in DFP.
- **Free float** — FRE `distribuicao_capital` provides circulation % + shareholder counts (PF/PJ/institutional).
- **Equity structure in BRL** — DFP BPP 2.03.* provides total equity + components (capital social, reservas, lucros acumulados, minority interest) over N periods.
- **5 modes** — shareholders, free_float, equity_structure, summary, dashboard.
- **Modular layout (v1.1)** — split into `_registry.py` + `modes/{shareholders,free_float,equity_structure,summary,dashboard}.py` + `report.py`. Auto-discovery via `@register_mode`.
- **Read-only** — no sync. Calls data_source query engines directly.

---

## 🚀 Quick Start

```
# Named shareholders
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')

# Equity structure (5 years)
skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params='{"company":"PETR4"}')

# Combined summary
skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
```

---

## ⚙️ Configuration

No skill-specific config. Read-only over already-synced data sources:
- `data_sources/cvm/fre` (fre.db)
- `data_sources/cvm/dfp` (dfp.db)
- `data_sources/cvm/bridge` (bridge.db — auto-syncs on ticker query)

---

## 📊 Rendering & Export

Pipe a `shareholders` result into the `report` tool (adapters: `shareholders_shareholders`, `shareholders_free_float`, `shareholders_equity_structure`, `shareholders_summary`, `shareholders_dashboard`):

```
# Named shareholders table
report(action="table", title="PETR4 Shareholders",
       data=<shareholders JSON>, config={"adapter":"shareholders_shareholders"})

# Multi-tab dashboard (Overview + Top Shareholders + Free Float + Equity Structure)
report(action="dashboard", title="PETR4 Shareholders Dashboard",
       data=<shareholders dashboard JSON>, config={"adapter":"shareholders_dashboard"})
```

See [CVM Skills — Report Integration](../CVM.md#-report-integration-v12).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](shareholders/ARCHITECTURE.md) | Data flow, mode → source mapping, design decisions |
| [API.md](shareholders/API.md) | 5 modes: shareholders, free_float, equity_structure, summary, dashboard |
| [CHANGELOG.md](shareholders/CHANGELOG.md) | Version history (v1.0 → v1.1) |
| [INSTRUCTIONS.md](shareholders/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-29 (v1.1 — modular split + dashboard mode).*
