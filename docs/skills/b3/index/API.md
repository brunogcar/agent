<- Back to [INDEX Overview](../INDEX.md)

# 📖 API Reference

## skill(domain="b3", sub_domain="index", ...)

### mode="dashboard" (default)

Single-index deep dive: overview KPIs, top constituents (table + weight chart), historical line chart, sector breakdown.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| index | str | — | Index symbol (IBOV, SMLL, BDRX, IFIX, IDIV). Required |
| top_n | int | 10 | Top N constituents to show in detail |
| history_days | int | 365 | Days of history for the trend chart |
| skip_sync | bool | False | Bypass sync guard (no freshness check, no force-sync) |

**Response shape:**
```json
{
  "status": "ok",
  "index": "IBOV",
  "kpis": [
    {"label": "Constituents",    "value": "82",      "unit": "count"},
    {"label": "Latest Close",    "value": "134,521", "unit": "points"},
    {"label": "1Y Return",       "value": "+18.4%",  "unit": "pct"},
    {"label": "Top 10 Weight",   "value": "52.3%",   "unit": "pct"}
  ],
  "tabs": [
    {"name": "Overview",     "sections": [{"type": "table", ...}, {"type": "chart", ...}]},
    {"name": "Constituents", "sections": [{"type": "table", ...}, {"type": "chart", ...}]},
    {"name": "History",      "sections": [{"type": "chart", ...}]},
    {"name": "Sectors",      "sections": [{"type": "table", ...}, {"type": "chart", ...}]}
  ],
  "_sync": {"synced": [], "fresh": ["index"], "errors": [], "skipped": []}
}
```

**`_sync` field**: Present when sync guard is active (i.e., `skip_sync` not passed). Shows which sources were force-synced, which were already fresh, which had errors, and which were skipped (via `B3_SKIP_SYNC=1` env var).

### mode="compare"

Side-by-side multi-index comparison: performance table, composition overlap (Jaccard similarity), sector weight divergence.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| indices | list[str] | — | 2-5 index symbols. Required (min 2) |
| history_days | int | 365 | Days of history for the comparison chart |
| skip_sync | bool | False | Bypass sync guard |

**Response shape:**
```json
{
  "status": "ok",
  "indices": ["IBOV", "SMLL"],
  "tabs": [
    {"name": "Performance", "sections": [{"type": "table", ...}, {"type": "chart", ...}]},
    {"name": "Overlap",     "sections": [{"type": "table", ...}]},
    {"name": "Sectors",     "sections": [{"type": "table", ...}, {"type": "chart", ...}]}
  ],
  "_sync": {"synced": [], "fresh": ["index"], "errors": [], "skipped": []}
}
```

### mode="ticker"

Reverse-lookup: given a ticker, list all indices it belongs to + its weight in each.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ticker | str | — | Ticker symbol (PETR4). Required |
| skip_sync | bool | False | Bypass sync guard |

**Response shape:**
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "indices": [
    {"index": "IBOV", "weight": 0.0821, "position": 3,  "name": "Índice Bovespa"},
    {"index": "IDIV", "weight": 0.0456, "position": 12, "name": "Índice Dividendos"}
  ],
  "summary": {"total_indices": 2, "max_weight": 0.0821, "in_active_indices": 2}
}
```

## Examples

```
skill(domain="b3", sub_domain="index", mode="dashboard", params='{"index":"IBOV"}')
skill(domain="b3", sub_domain="index", mode="dashboard", params='{"index":"SMLL","top_n":20}')
skill(domain="b3", sub_domain="index", mode="compare",   params='{"indices":["IBOV","SMLL","BDRX"]}')
skill(domain="b3", sub_domain="index", mode="ticker",    params='{"ticker":"PETR4"}')
```

---

*Last updated: 2026-08-05 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
