<- Back to [SCREENER Overview](../SCREENER.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `skills/cvm/screener/__init__.py` | MANIFEST + route() — dispatches sector / compare |
| `skills/cvm/screener/screener.py` | Sector search, peer valuation, median computation, comparison |
| `tools/report_ops/adapters/screener.py` | screener_sector report adapter |
| `tests/skills/cvm/test_screener.py` | Skill tests (mocked CAD + bridge + valuation) |

---

## 🔀 Data Flow

```mermaid
graph TD
    A["skill(domain='cvm', sub_domain='screener', mode='sector', params='{\"setor\":\"Papel e Celulose\"}')"]
    A --> B["screener.sector(setor)"]
    B --> C["CAD.search(setor) -> companies list"]
    C --> D["For each company: bridge.lookup(cd_cvm) -> ticker"]
    D --> E["For each ticker: valuation.ratios(ticker)"]
    E --> F["peers list with P/L, ROE, EV/EBITDA, etc."]
    F --> G["_compute_medians(peers)"]
    F --> H["Sort by P/L cheapest-first"]
    G & H --> I["{status, setor, peer_count, medians, peers, errors}"]
```

---

## 💡 Key Design Decisions

- **Orchestration only** — screener imports and calls CAD + bridge + valuation. No database, no sync, no duplicate SQL. If valuation changes, screener picks up the changes automatically.
- **Best-effort per company** — companies without a ticker (not in bridge) or with failed valuation are skipped. The `errors` list captures what was skipped. The screener never fails wholesale.
- **Sorted by P/L cheapest-first** — investors want to see value opportunities first. None P/L goes last.
- **Sector medians** — uses `statistics.median()` over non-None values. If a metric is None for all peers, median is None.
- **Compare mode** resolves the ticker's sector from CAD (via bridge → CNPJ → CAD lookup → SETOR_ATIV), then reuses `sector()` to get peers + medians, then builds a per-metric comparison with "cheap"/"expensive"/"above"/"below" labels.

---

## 📊 Comparison Logic

For each metric, the comparison dict contains:

| Metric | "cheap" / "expensive" logic |
|--------|----------------------------|
| P/L | below median = "cheap", above = "expensive" |
| P/VPA | below median = "cheap", above = "expensive" |
| EV/EBITDA | below median = "cheap", above = "expensive" |
| ROE | above median = "above", below = "below" |
| Div Yield | above median = "above", below = "below" |

`delta_pct` = `(my_value - median) / |median|` — positive = above median.

---

*Last updated: 2026-07-25 (v1.0).*
