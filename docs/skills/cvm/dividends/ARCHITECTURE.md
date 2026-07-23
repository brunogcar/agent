<- Back to [CVM Skills](../../)

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

## Resolution

- `history`: accepts ticker (B3 dividends keyed by ticker)
- `annual` / `payable`: accepts ticker/name/CNPJ (via bridge → DFP)
- `announcements`: accepts ticker/name/CNPJ (via bridge → IPE)
- `summary`: ticker preferred (covers all 3 sources)

## File Layout

```
skills/cvm/dividends/
├── __init__.py     # Manifest + route (5 modes)
└── dividends.py    # Logic: delegates to B3 + DFP + IPE query engines
```

---

*Last updated: 2026-07-23 (v1.0).*
