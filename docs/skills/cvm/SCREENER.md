<- Back to [CVM Skills](../CVM.md)

# 🔍 SCREENER — Sector Screener Skill

The `screener` skill lists companies in a sector and computes sector medians (P/L, ROE, EV/EBITDA) so the LLM can ask "is SUZB3 cheap vs its sector?".

**Key characteristics:**
- **2 modes** — sector (list peers + medians), compare (is ticker X cheap/expensive vs sector)
- **Orchestration only** — calls CAD + bridge + valuation internally. No own database, no sync.
- **Best-effort** — companies without a ticker (not in bridge) or with failed valuation are skipped, not fatal.
- **Sorted by P/L** — peers table is sorted cheapest-first so the LLM sees value opportunities immediately.
- **Sector medians** — P/L, P/VPA, EV/EBITDA, ROE, Div Yield, Market Cap medians computed from peers. [v1.2] Also ROA, Marg. Líquida, Dívida/PL medians (sourced from calculations metrics via valuation.ratios).
- **Calculations integration (v1.2)** — since Phase 2B, `valuation.ratios()` returns `roe` directly (computed by `calculations.metrics.roe_at`). The `_roe_from_ratios()` helper was simplified to `ratios.get("roe")` — no more lucro_liquido/patrimonio_liquido division. Peer dicts + medians + comparison now also include `roa`, `margem_liquida`, `divida_pl` from the calculations metrics surfaced in valuation.ratios.

---

## 🚀 Quick Start

```
# List all companies in "Papel e Celulose" sector + medians
skill(domain="cvm", sub_domain="screener", mode="sector",
      params='{"setor":"Papel e Celulose"}')

# Is SUZB3 cheap vs its sector?
skill(domain="cvm", sub_domain="screener", mode="compare",
      params='{"company":"SUZB3"}')
```

---

## ⚙️ Configuration

No skill-specific config. Requires:
- `data_sources/cvm/cad` synced (CAD — company register + sectors)
- `data_sources/cvm/bridge` synced (ticker ↔ CNPJ ↔ CD_CVM)
- `data_sources/cvm/dfp` + `fre` synced (for valuation.ratios)
- brapi.dev or investsite (price — fetched live by valuation)

---

## 📊 Rendering & Export

Pipe a `screener` result into the `report` tool (adapter: `screener_sector`):

```
report(action="table", title="Papel e Celulose Sector",
       data=<screener sector JSON>, config={"adapter":"screener_sector"})
```

See [CVM Skills — Report Integration](../CVM.md#-report-integration-v12).

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](screener/ARCHITECTURE.md) | Data flow, median computation, comparison logic |
| [API.md](screener/API.md) | 2 modes: sector, compare |
| [CHANGELOG.md](screener/CHANGELOG.md) | Version history + roadmap |
| [INSTRUCTIONS.md](screener/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-27 (v1.2 — calculations integration).*
