<- Back to [CVM Skills](../../)

# 📋 Instructions — dividends skill

## Prerequisites

Sync the underlying data sources first:

```
data_source(domain="b3", sub_domain="dividends", mode="sync", params='{"ticker":"PETR4"}')
data_source(domain="cvm", sub_domain="dfp", mode="sync")
data_source(domain="cvm", sub_domain="ipe", mode="sync")
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')
```

## Quick Start

```
# Individual dividend events (B3)
skill(domain="cvm", sub_domain="dividends", mode="history", params='{"company":"PETR4"}')

# Annual declared totals (DFP DVA)
skill(domain="cvm", sub_domain="dividends", mode="annual", params='{"company":"PETR4"}')

# Dividends payable (declared but unpaid)
skill(domain="cvm", sub_domain="dividends", mode="payable", params='{"company":"VALE3"}')

# Official filings (IPE)
skill(domain="cvm", sub_domain="dividends", mode="announcements", params='{"company":"PETR4"}')

# Combined summary
skill(domain="cvm", sub_domain="dividends", mode="summary", params='{"company":"PETR4"}')
```

## When to Use Which Mode

| Question | Mode |
|----------|------|
| What dividends were paid recently? | `history` |
| How much was declared per year? | `annual` |
| What's still owed to shareholders? | `payable` |
| Show me official announcements | `announcements` |
| Give me the full picture | `summary` |

## JCP vs Dividendos

The `label` field in `history` mode distinguishes:
- **Dividendo** — regular cash dividend
- **JCP** — Juros sobre Capital Próprio (interest on equity, tax-deductible)

Both are shareholder remuneration. DFP `annual` mode shows them separately:
7.08.04.02 (Dividendos) + 7.08.04.01 (JCP).

---

*Last updated: 2026-07-23 (v1.0).*
