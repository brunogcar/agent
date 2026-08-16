<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🗺️ OPTIONS Skill ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| P2 | P1 — Implied Volatility (Black-Scholes) | Compute IV per option using Black-Scholes + Selic rate from BCB SGS |
| P2 | P2 — IV Smile heatmap | Strike (y) vs maturity (x), colored by IV. Blocked on P1 |
| P3 | P3 — Open interest (DerivativesOpenPosition API) | API changed — needs investigation before wiring |
| P3 | P4 — "Opções" tab in price dashboard | Cross-skill integration — price dashboard embeds an options tab |
| P4 | P5 — Futures/forward skill (BDI 26) | DB is prepared (TERM rows already in cotahist_derivatives). Separate skill for later |

> **Note:** v1.0 launch is in [CHANGELOG.md](CHANGELOG.md). The ROADMAP
> only tracks backlog + deferred items.

---

## 📋 Backlog

### P1 — Implied Volatility (Black-Scholes)

**Priority:** P2
**Source:** Derivatives traders

Compute the implied volatility per option using the Black-Scholes model.
Currently the Cadeia de Opções tab shows price + volume + bid/ask but NOT
the implied vol — the most important options metric.

**Implementation:**
1. Add a Black-Scholes engine to a new `skills/b3/options/engines.py` (or
   a shared `skills/b3/options/bs.py`):
   - `bs_call(S, K, T, r, sigma)` / `bs_put(...)` — pricing.
   - `implied_vol(price, S, K, T, r, option_type)` — invert BS via
     Newton-Raphson (or bisection fallback when vega ≈ 0).
2. Risk-free rate `r` = the Selic rate from `data_sources.bcb.sgs`
   (annualized, converted to continuous compounding).
3. Underlying spot `S` = latest close from `cotahist` (equities table).
4. Time to maturity `T` = `(maturity_date - refdate).days / 365`.
5. Add a 4th tab **"Volatilidade Implícita"** to the dashboard: IV table
   + smile chart (IV vs strike).

**Blocker:** Need the Selic rate synced (`REQUIRED_SOURCES` grows to
`["cotahist", "sgs"]`). The Black-Scholes math itself is ~30 lines of
pure Python (no external libs).

### P2 — IV Smile heatmap

**Priority:** P2
**Source:** Volatility surface visualization

A 2D heatmap: strike (y-axis) × maturity (x-axis), each cell colored by
the implied volatility at that (strike, maturity) point. Reveals the
"volatility smile" + term structure simultaneously.

**Implementation:**
1. Reuse the IV engine from P1.
2. Query all maturities for the underlying (`available_maturities`).
3. For each (maturity, strike) pair, compute IV from the latest close.
4. Render as a Chart.js matrix/heatmap (custom plugin or `chartjs-chart-matrix`).

**Blocker:** Blocked on P1 (IV engine).

### P3 — Open interest (DerivativesOpenPosition API)

**Priority:** P3
**Source:** B3 DerivativesOpenPosition API

The `cotahist_derivatives` table currently has trade volume but NOT open
interest (number of outstanding contracts). Open interest is the key
support/resistance indicator — high OI strikes act as magnets.

**Implementation:**
1. Investigate the B3 `DerivativesOpenPosition` API — the endpoint
   changed since this skill was planned, so the exact URL + response shape
   need to be re-discovered (B3 docs: <https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historical-data/derivatives-open-position/>).
2. Add a new sync sub-domain or extend `cotahist_derivatives.sync_engine`
   with a `sync_open_position(date)` function.
3. Add an `open_interest` column to the `cotahist_derivatives` schema.
4. Surface OI in the Cadeia de Opções table + Volume por Strike chart
   (third bar dataset, or a separate OI-by-strike chart).

**Blocker:** API investigation — the endpoint contract changed.

### P4 — "Opções" tab in price dashboard

**Priority:** P3
**Source:** Cross-skill integration

The `price` skill dashboard (5/7 tabs for an equity) could embed a 6th/8th
"Opções" tab that calls the `options` skill's `dashboard` mode and renders
the Cadeia de Opções table inline. Currently a user has to call the
options skill separately.

**Implementation:**
1. In `skills/b3/price/modes/dashboard.py`, add a tab that calls
   `skills.b3.options.modes.dashboard.dashboard(underlying=ticker)`.
2. Extract just the Cadeia de Opções tab sections (skip the P/C ratio +
   Volume por Strike tabs to keep the price dashboard compact).
3. Wrap in try/except — if the underlying has no listed options, skip the
   tab silently (don't break the price dashboard).

**Blocker:** None technical. Tracked in the price skill ROADMAP (P3) —
see [../price/ROADMAP.md](../price/ROADMAP.md). Need to confirm the
price dashboard doesn't grow past 8 tabs (currently 7).

### P5 — Futures/forward skill (BDI 26)

**Priority:** P4
**Source:** Derivatives traders

The `cotahist_derivatives` table already contains TERM rows (BDI code 26)
— the DB is prepared. But TERM contracts have no strike/maturity ticker
convention (they're OTC-style), so they need a separate query path +
analytics view (forward curve, basis = spot − forward, etc.).

**Implementation:**
1. New skill `skills/b3/futures/` mirroring the options skill structure.
2. New query functions in `cotahist_derivatives.query_engine`:
   `forward_curve(underlying)`, `basis(underlying, maturity)`.
3. Dashboard: forward curve chart + basis table.

**Blocker:** None technical — the DB is ready. Just needs the analytics
layer. Deferred as a separate skill (not bolted onto options).

---

*Last updated: 2026-08-18 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
