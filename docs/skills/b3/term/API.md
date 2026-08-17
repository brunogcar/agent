<- Back to [TERM](../TERM.md)

# API Reference

## skill(domain="b3", sub_domain="term", ...)

### mode="dashboard"

3-tab term contracts dashboard.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ticker | str | "PETR4" | Stock ticker (PETR4, VALE3). NOT stripped — PETR4 ≠ PETR3. |
| days | int | 90 | History lookback window. |

**Tabs (3):**
| Tab | Group | Sections |
|-----|-------|----------|
| Contratos Ativos | Termo | info text + collapsible table |
| Spread Termo vs Spot | Análise | dual-axis line chart (term + spot + spread) |
| Volume Histórico | Análise | bar chart + range selector |

## Examples
```
skill(domain="b3", sub_domain="term", mode="dashboard", params='{"ticker":"PETR4"}')
```
