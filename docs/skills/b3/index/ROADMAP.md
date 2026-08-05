<- Back to [INDEX Overview](../INDEX.md)

# 🗺️ INDEX Skill ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | I1 — Beta calculation | Per-constituent beta vs parent index (OLS regression) |
| P2 | I2 — Sector weight analysis | Cross-index sector weight divergence (stacked bar chart) |
| P2 | I3 — Historical comparison | Multi-window returns (1M/3M/6M/1Y/5Y/YTD) with rebalance awareness |
| P3 | I4 — More indices | Expand `ACTIVE_INDICES` from 5 to 10 (add IGC, ISE, IBRA, IVBX, IMOB) |
| Done | v1.0 launch | 3 modes (dashboard, compare, ticker) + sync guard wired |

> **Note:** Recently completed items are in [CHANGELOG.md](CHANGELOG.md).

---

## 📋 Backlog

### I1 — Beta calculation

**Priority:** P2
**Source:** Quant analysis need

Per-constituent beta vs the parent index, computed via OLS regression of
constituent daily returns on index daily returns over a trailing window
(default 252 trading days = 1Y). Beta > 1 = more volatile than the index;
beta < 1 = less volatile.

**Implementation:**
1. Fetch index `history` (close prices, 252 days).
2. For each constituent, fetch `cotahist` daily close (252 days).
3. Compute daily returns: `(close_t / close_{t-1}) - 1`.
4. OLS regression: `R_constituent = alpha + beta * R_index + epsilon`.
5. Surface as a new "Risk" tab in the dashboard (table + scatter plot of
   beta vs weight).

**Blocker:** Requires `data_sources/b3/cotahist` synced for the constituent
price history. Add `cotahist` to `REQUIRED_SOURCES` when this lands.

### I2 — Sector weight analysis

**Priority:** P2
**Source:** Portfolio management use case

Compare sector weights across indices in `compare` mode. Currently the
Sectors tab shows a per-index table; a stacked bar chart would make the
divergence visually obvious (e.g., IBOV is 30% financials, SMLL is 10% —
the bar chart shows this in one glance).

**Implementation:**
1. For each index in `indices` param, group constituents by sector
   (joined from B3 API instruments `segment` field).
2. Normalize weights within each sector.
3. Build a Chart.js stacked bar chart: x-axis = indices, y-axis = %,
   stacks = sectors (top 8 + "Outros").

**Blocker:** B3 API instruments table needs `segment` populated. Currently
the segment field is sometimes empty for newer listings.

### I3 — Historical comparison

**Priority:** P2
**Source:** Investment horizon analysis

Multi-window return comparison in `compare` mode. Currently the
Performance tab shows only the trailing-`history_days` return. A table
with 1M / 3M / 6M / 1Y / 5Y / YTD columns would let the user see at a
glance which index is winning across horizons.

**Implementation:**
1. For each index + each window, fetch the close at start and end of
   the window from `history`.
2. Return = `(close_end / close_start) - 1`.
3. Rebalance awareness: document that returns are price-only (not total
   return). Total return would require dividend adjustment (deferred to
   a future ROADMAP item — needs B3 dividends + cotahist adjusted close).

### I4 — More indices

**Priority:** P3
**Source:** Power user requests

Expand `ACTIVE_INDICES` from 5 to 10 by adding:
- **IGC** (Índice de Ações com Governança Diferenciada) — governance-focused
- **ISE** (Índice de Sustentabilidade Empresarial) — ESG
- **IBRA** (Índice Brasil Amplo) — broad market
- **IVBX** (Índice Valor Bovespa) — large + mid cap
- **IMOB** (Índice Imobiliário) — real estate

**Implementation:**
1. Add 5 entries to `ACTIVE_INDICES` in `catalog.py`.
2. Re-run `sync_all()` to populate.
3. Update docs (5→10 active indices throughout).

**Blocker:** None technical — but the 5 additional indices add ~30s to
`sync_all()` and increase DB size from ~5MB to ~10MB.

---

*Last updated: 2026-08-05 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
