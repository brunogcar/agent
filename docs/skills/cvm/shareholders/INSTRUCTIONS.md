<- Back to [CVM Skills](../../)

# 📋 Instructions — shareholders skill

## Prerequisites

Sync the underlying data sources first:

```
data_source(domain="cvm", sub_domain="fre", mode="sync")
data_source(domain="cvm", sub_domain="dfp", mode="sync")
data_source(domain="cvm", sub_domain="bridge", mode="sync", params='{"ticker":"PETR4"}')
```

The bridge auto-syncs on first ticker query, but pre-syncing makes the first
query faster.

## Quick Start

```
# Named shareholders
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')

# Free float
skill(domain="cvm", sub_domain="shareholders", mode="free_float", params='{"company":"VALE3"}')

# Equity structure (5 years)
skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params='{"company":"PETR4"}')

# Combined summary
skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
```

## When to Use Which Mode

| Question | Mode |
|----------|------|
| Who owns the company? | `shareholders` |
| What % is free float? | `free_float` |
| How has equity evolved? | `equity_structure` |
| Give me the full picture | `summary` |

---

*Last updated: 2026-07-23 (v1.0).*
