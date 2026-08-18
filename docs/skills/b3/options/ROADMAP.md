<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🗺️ OPTIONS Skill ROADMAP

## 📋 Quick View — What's Next

| Priority | Item | Description |
|----------|------|-------------|
| ✅ Done | P1 — Implied Volatility (Black-Scholes) | [v1.2] Black-Scholes engine + Selic rate from BCB SGS series 432 + IV smile chart + IV table. |
| ✅ Done | P2 — IV Smile heatmap | [v1.2] Strike × maturity heatmap colored by IV (green=calm → red=panic). [v1.2] Fixed to render with a single maturity. |
| P3 | P3 — Open interest (DerivativesOpenPosition API) | API changed — needs investigation before wiring |
| P3 | P4 — "Opções" tab in price dashboard | Cross-skill integration — price dashboard embeds an options tab |
| P4 | P5 — Futures/forward skill (BDI 26) | DB is prepared (TERM rows already in cotahist_derivatives). Separate skill for later |

> **Note:** v1.0 launch + v1.2 IV tab + v1.2 v2 tweaks are in [CHANGELOG.md](CHANGELOG.md). The ROADMAP only tracks backlog + deferred items.

---

## 📋 Backlog

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
   Volume por Strike + IV tabs to keep the price dashboard compact).
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

## ✅ Done

### P1 — Implied Volatility (Black-Scholes) — DONE in v1.2

[v1.2] Added `skills/b3/options/engines.py` (pure-Python Black-Scholes):
- `bs_price(S, K, T, r, sigma, option_type)` — call/put pricing.
- `bs_vega(S, K, T, r, sigma)` — dPrice/dSigma for Newton-Raphson.
- `implied_vol(price, S, K, T, r, option_type)` — Newton-Raphson + bisection
  fallback, clamp [0.01, 5.0], None for invalid inputs.

Risk-free rate = Selic from BCB SGS series 432 ("Meta Selic Copom", % a.a.),
converted to continuous compounding (`r_cont = ln(1 + r_simple)`).
Spot price = latest PETR4 close from cotahist equities table.
T = `(maturity - refdate).days / 365`.

`REQUIRED_SOURCES` grew from `["cotahist"]` to `["cotahist", "sgs"]` so the
sync guard triggers the BCB SGS sync if the Selic rate is stale.

### P2 — IV Smile heatmap — DONE in v1.2 (+ single-maturity fix in v1.2)

[v1.2] Added `_build_iv_tab()` which emits 3 sections:
1. IV Smile line chart (IV vs strike, calls green + puts red).
2. IV table (Papel | Tipo | Strike | Prêmio | IV).
3. IV Term Structure heatmap — strike (rows) × maturity (cols), colored
   by IV (green=calm <10% → yellow ~55% → red=panic >100%). Built via
   `report.build_heatmap_section()` and rendered by the `heatmap` block in
   `macros.html`.

[v1.2] Fixed the heatmap to render even with a single maturity (was silently
skipped — single-column heatmap is still useful to visualize the smile).

---

*Last updated: 2026-09-05 (v1.2). See [CHANGELOG.md](CHANGELOG.md) for version history.*
