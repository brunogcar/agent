<- Back to [DIVIDENDS Overview](../DIVIDENDS.md)

# 🗺️ Changelog — dividends skill

| Version | Date | Summary |
|---------|------|---------|
| **v2.0** | 2026-07-30 | **skills/_base.py extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base.py` module (ModeSpec + make_registry + make_route + auto_discover_modes). _registry.py shrank from ~97 lines to ~16 lines; __init__.py shrank from ~88 lines to ~50 lines. No behavior change — same modes, same route() signature, same MANIFEST. Bug fixes to the dispatch infrastructure now only need to be made in ONE place (skills/_base.py) instead of 11. |
| v1.1 | 2026-07-29 | **Modular split + dashboard mode.** Split monolithic `dividends.py` (283 lines) into `_registry.py` + `modes/` (6 mode files: history, annual, payable, announcements, summary, dashboard) + `report.py` — mirrors the `financials`/`valuation`/`comparison`/`backtest` modular pattern (`_registry.py` + `modes/*.py` auto-discovered via `@register_mode`). New `dashboard` mode produces a multi-tab dashboard payload for the report tool. New `dividends_dashboard` adapter (report tool v1.7, 69th adapter). 6 modes total. |
| v1.0.1 | 2026-07-23 | **P1 hotfix: escala parser.** `annual` + `payable` modes crashed with `could not convert string to float: 'MIL'` — DFP stores ESCALA_MOEDA as Portuguese words (MIL/MILHOES/UNIDADE), not numbers. Fix: use new `parse_escala()` helper from `_db.py`. Also benefited from IPE v1.0.1 tuple fix (announcements mode now works with tickers). |
| v1.0 | 2026-07-23 | **Initial implementation.** Combines B3 dividends (individual events) + DFP DVA 7.08.04.* (annual declared totals) + DFP BPP 2.01.05.02.01 (payable) + CVM IPE (official filings). 5 modes: history, annual, payable, announcements, summary. Read-only over already-synced data. 17 tests. |

---

*Last updated: 2026-07-30 (v2.0).*
