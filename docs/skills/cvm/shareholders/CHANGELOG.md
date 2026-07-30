<- Back to [SHAREHOLDERS Overview](../SHAREHOLDERS.md)

# 🗺️ Changelog — shareholders skill

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-07-30 | **Modular split + dashboard mode.** Split monolithic `shareholders.py` (233 lines) into `_registry.py` + `modes/` (5 mode files: shareholders, free_float, equity_structure, summary, dashboard) + `report.py` — mirrors the `financials`/`valuation`/`comparison`/`backtest`/`dividends`/`governance`/`historical`/`screener` modular pattern (`_registry.py` + `modes/*.py` auto-discovered via `@register_mode`). New `dashboard` mode produces a 4-tab dashboard payload (Overview / Top Shareholders / Free Float / Equity Structure) for the report tool. New `shareholders_dashboard` adapter (report tool, 73rd adapter). 5 modes total (was 4). |
| v1.0.1 | 2026-07-23 | **P1 hotfix: escala parser.** `equity_structure` mode crashed with `could not convert string to float: 'MIL'` — DFP stores ESCALA_MOEDA as Portuguese words (MIL/MILHOES/UNIDADE), not numbers. Fix: use new `parse_escala()` helper from `_db.py`. Also benefited from FRE v1.0.1 tuple fix (shareholders/free_float modes now work with tickers). |
| v1.0 | 2026-07-23 | **Initial implementation.** Combines FRE (named shareholders, free float) + DFP (equity structure in BRL). 4 modes: shareholders (FRE posicao_acionaria), free_float (FRE distribuicao_capital), equity_structure (DFP BPP 2.03.*), summary (combined). Read-only over already-synced data. 15 tests. |

---

*Last updated: 2026-07-30 (v1.1).*
