<- Back to [CVM Skills](../../)

# 🗺️ Changelog — dividends skill

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-23 | **P1 hotfix: escala parser.** `annual` + `payable` modes crashed with `could not convert string to float: 'MIL'` — DFP stores ESCALA_MOEDA as Portuguese words (MIL/MILHOES/UNIDADE), not numbers. Fix: use new `parse_escala()` helper from `_db.py`. Also benefited from IPE v1.0.1 tuple fix (announcements mode now works with tickers). |
| v1.0 | 2026-07-23 | **Initial implementation.** Combines B3 dividends (individual events) + DFP DVA 7.08.04.* (annual declared totals) + DFP BPP 2.01.05.02.01 (payable) + CVM IPE (official filings). 5 modes: history, annual, payable, announcements, summary. Read-only over already-synced data. 17 tests. |

---

*Last updated: 2026-07-23 (v1.0.1).*
