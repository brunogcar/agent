<- Back to [CVM Skills](../CVM.md)

# ⚖️ COMPARISON — Multi-Ticker Comparison Skill

The `comparison` skill compares N tickers across the 3 CVM analytical dimensions (financials + valuation + dividends) in one call. It calls the existing skills internally per ticker (best-effort — a ticker missing from one source doesn't fail the whole comparison) and merges into a side-by-side structure.

**Key characteristics:**
- **Orchestration only** — no new database, no sync. Calls `financials.summary()`, `valuation.ratios()`, `dividends.summary()` per ticker.
- **Best-effort per ticker** — if one source fails for a ticker (e.g. price unavailable), that ticker's cells in that section are `None` (rendered as `—`), but the other sections still populate. The comparison never fails wholesale.
- **Tickers as rows, metrics as columns** — matches how investors read comparison tables, and keeps each section unit-homogeneous so per-column format specs work.
- **3 modes** — side_by_side (3 sections, full), summary (single quick-compare table, 10 KPIs), growth (QoQ + YoY % change + TTM ratios).
- **Calculations integration (v1.3)** — since Phase 2B, `valuation.ratios()` returns ~10 additional ratios sourced from the central calculations engines (roe, roa, margem_bruta, margem_operacional, margem_liquida, divida_pl, giro_ativos, liquidez_corrente, roic, graham_number, p_ebit, p_fco, p_fcf). Comparison surfaces 5 of these (ROE, ROA, Marg. Líquida, Dívida/PL, Liquidez Corrente) as new columns in the valuation section of `side_by_side()`. No new data fetching — picked up transitively via the existing `entry["valuation"] = r.get("ratios", {})` line.
- **Read-only** — no sync. Assumes dfp.db + itr.db + fre.db + bridge.db + dividends.db are synced.

---

## 🚀 Quick Start

```
# Full side-by-side (3 sections: valuation, financials, dividends)
skill(domain="cvm", sub_domain="comparison", mode="side_by_side",
      params='{"tickers":["SUZB3","KLBN11"]}')

# Quick summary (single table, 10 KPIs)
skill(domain="cvm", sub_domain="comparison", mode="summary",
      params='{"tickers":["PETR4","VALE3","ITUB4"]}')
```

---

## ⚙️ Configuration

No skill-specific config. Requires the underlying skills' data sources synced:
- `data_sources/cvm/dfp` (dfp.db — financials)
- `data_sources/cvm/itr` (itr.db — quarterly financials)
- `data_sources/cvm/fre` (fre.db — shares, for valuation)
- `data_sources/cvm/bridge` (bridge.db — auto-syncs on ticker query)
- `data_sources/b3/dividends` (dividends.db — dividend events)
- brapi.dev or investsite (price — fetched live by valuation skill)

---

## 📊 Rendering & Export

Pipe a `comparison` result into the `report` tool (adapters: `comparison_side_by_side`, `comparison_summary`):

```
report(action="table", title="SUZB3 vs KLBN11",
       data=<comparison JSON>, config={"adapter":"comparison_side_by_side"})

report(action="export", title="SUZB3 vs KLBN11",
       data=<comparison JSON>, config={"format":"xlsx","adapter":"comparison_side_by_side"})
```

See [CVM Skills — Report Integration](../CVM.md#-report-integration-v12).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](comparison/ARCHITECTURE.md) | Orchestration flow, best-effort logic, column definitions |
| [API.md](comparison/API.md) | 2 modes: side_by_side, summary |
| [CHANGELOG.md](comparison/CHANGELOG.md) | Version history + roadmap |
| [INSTRUCTIONS.md](comparison/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-27 (v1.3 — calculations integration).*
