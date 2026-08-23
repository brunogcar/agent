<- Back to [DIVIDENDS Overview](../DIVIDENDS.md)

# 🏗️ Architecture — dividends skill

## Purpose

Combines three data sources into a unified dividend view:

| Source | What it provides | Granularity |
|--------|-----------------|-------------|
| B3 dividends | Individual events: rate, approved_on, payment_date, label (Dividendo/JCP) | Per event |
| DFP DVA 7.08.04.* | Annual declared totals: Dividendos + JCP | Per fiscal year |
| DFP BPP 2.01.05.02.01 | Dividends declared but not yet paid (liability) | Per balance sheet date |
| CVM IPE | Official regulatory filings (announcements) | Per filing |

## Why a skill (not just data_source)?

Each data source has a different view of dividends:
- **B3** = what was actually paid per event (exchange perspective)
- **DFP DVA** = what was declared per fiscal year (accounting perspective)
- **DFP BPP** = what's still owed (balance sheet liability)
- **IPE** = official regulatory announcements

This skill combines them so the LLM can answer any dividend question from one
entry point.

## DVA Codes (DFP)

| Code | Label |
|------|-------|
| 7.08.04 | Remuneração de Capitais Próprios (total) |
| 7.08.04.01 | Juros sobre Capital Próprio (JCP) |
| 7.08.04.02 | Dividendos |
| 7.08.04.03 | Lucros Retidos / Prejuízos do Exercício |

JCP (Juros sobre Capital Próprio) is a Brazilian tax mechanism — economically
equivalent to dividends but tax-deductible for the company.

## Modes

| Mode | Source | Returns |
|------|--------|---------|
| `history` | B3 | Individual events (rate, dates, label) |
| `annual` | DFP DVA | Annual declared totals per fiscal year |
| `payable` | DFP BPP | Declared-but-unpaid amount per period |
| `announcements` | IPE | Official filings (keyword "dividendo") |
| `summary` | B3 + DFP | Recent events + annual trend + last payable |
| `dashboard` | B3 + DFP + IPE | Multi-tab dashboard payload (Overview + Events + Annual + Payable + Filings) |

## Resolution

- `history`: accepts ticker (B3 dividends keyed by ticker)
- `annual` / `payable`: accepts ticker/name/CNPJ (via bridge → DFP)
- `announcements`: accepts ticker/name/CNPJ (via bridge → IPE)
- `summary`: ticker preferred (covers all 3 sources)
- `dashboard`: ticker preferred (covers all sources across the dashboard tabs)

## File Layout

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base/` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|------|---------|
| `skills/_base/` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |

```text
skills/cvm/dividends/
├── __init__.py           # [v2.0] uses auto_discover_modes() + make_route() from skills/_base/ — ~50 lines
├── _registry.py          # [v2.0] delegates to skills/_base/ (make_registry()) — ~16 lines
├── report.py             # Skill-level report helpers (consumed by adapters)
└── modes/
    ├── __init__.py
    ├── history.py        # mode="history" — B3 individual events
    ├── annual.py         # mode="annual" — DFP DVA declared totals
    ├── payable.py        # mode="payable" — DFP BPP declared-but-unpaid
    ├── announcements.py  # mode="announcements" — CVM IPE filings
    ├── summary.py        # mode="summary" — combined multi-source
    └── dashboard.py      # mode="dashboard" — multi-tab dashboard payload (v1.1)

tools/report_ops/adapters/
├── dividends.py                # dividends_{history,annual,summary} table adapters
└── dividends_dashboard.py      # dividends_dashboard adapter (v1.1 — 69th adapter)
```

### Modular pattern (v1.1)

The skill follows the same `_registry.py` + `modes/` auto-discovery pattern used by `financials`, `valuation`, `comparison`, and `backtest`. Adding a new mode = drop a file in `modes/` + `@register_mode(...)`; no edits to `__init__.py`. The previous monolithic `dividends.py` (283 lines) was decomposed into the structure above.

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base/` extraction; see CHANGELOG.md for details).*
